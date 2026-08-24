from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable

import pandas as pd

from .analytics import (
    audit_metrics,
    commercial_fulfillment,
    cultivation_metrics,
    find_col,
    inventory_health,
    production_attainment,
    production_capacity_risks,
    purchase_order_metrics,
    reorder_candidates,
    vendor_performance,
)
from .datasets import LoadedDataset
from .sanitization import norm, records


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def provider_schema(self) -> dict[str, Any]:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


class ToolRegistry:
    """Read-only structured tools bound to already authorized datasets."""

    def __init__(self, datasets: dict[str, LoadedDataset], *, knowledge_search: Callable[[str, int], dict[str, Any]] | None = None) -> None:
        self.datasets = datasets
        self.knowledge_search = knowledge_search
        self._tools: dict[str, ToolSpec] = {}
        self._register_generic()
        self._register_domain()
        if knowledge_search is not None:
            self._register(ToolSpec(
                "knowledge_search",
                "Search tenant-scoped approved knowledge sources.",
                {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 12}}, "required": ["query"]},
                lambda args: knowledge_search(str(args.get("query") or ""), max(1, min(int(args.get("limit") or 6), 12))),
            ))

    def _register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.provider_schema() for tool in self._tools.values()]

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def execute(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        tool = self._tools.get(str(name or ""))
        if tool is None:
            return {"error": "tool_unavailable", "tool": name}
        try:
            return tool.handler(dict(arguments or {}))
        except Exception as exc:
            return {"error": "tool_failed", "tool": name, "detail": exc.__class__.__name__}

    def _frame(self, name: str) -> pd.DataFrame:
        dataset = self.datasets.get(str(name or "").casefold())
        if dataset is None:
            raise ValueError("Dataset is not available for this request.")
        return dataset.frame

    def _bounded(self, name: str, frame: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
        loaded = self.datasets[name]
        maximum = max(1, min(int(loaded.spec.max_tool_rows), 100))
        return records(frame, limit=min(maximum, max(1, int(limit))))

    def _register_generic(self) -> None:
        self._register(ToolSpec("list_datasets", "List authorized datasets and freshness; never changes data.", {"type": "object", "properties": {}}, lambda _args: {
            "datasets": [{"key": key, "description": value.spec.description, "rows": len(value.frame), "columns": list(value.frame.columns)[:80], "freshness": value.freshness} for key, value in self.datasets.items()]
        }))
        self._register(ToolSpec("describe_dataset", "Describe one authorized dataset.", {"type": "object", "properties": {"dataset": {"type": "string"}}, "required": ["dataset"]}, self._describe_dataset))
        self._register(ToolSpec("preview_dataset", "Preview a small bounded set of authorized rows.", {"type": "object", "properties": {"dataset": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "required": ["dataset"]}, self._preview))
        self._register(ToolSpec("search_dataset", "Search authorized fields for a literal term.", {"type": "object", "properties": {"dataset": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "required": ["dataset", "query"]}, self._search))
        self._register(ToolSpec("summarize_numeric", "Calculate count,total,average,median,min,max for an authorized numeric field.", {"type": "object", "properties": {"dataset": {"type": "string"}, "column": {"type": "string"}}, "required": ["dataset", "column"]}, self._summarize_numeric))
        self._register(ToolSpec("group_summary", "Group an authorized dataset and count/sum/mean/min/max.", {"type": "object", "properties": {"dataset": {"type": "string"}, "group_column": {"type": "string"}, "value_column": {"type": "string"}, "operation": {"type": "string", "enum": ["count", "sum", "mean", "min", "max"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "required": ["dataset", "group_column"]}, self._group_summary))
        self._register(ToolSpec("top_rows", "Return a bounded highest/lowest ranking by a numeric field.", {"type": "object", "properties": {"dataset": {"type": "string"}, "sort_column": {"type": "string"}, "ascending": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "required": ["dataset", "sort_column"]}, self._top_rows))
        self._register(ToolSpec("numeric_exceptions", "Find authorized rows above or below a numeric threshold.", {"type": "object", "properties": {"dataset": {"type": "string"}, "column": {"type": "string"}, "threshold": {"type": "number"}, "direction": {"type": "string", "enum": ["above", "below"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "required": ["dataset", "column", "threshold"]}, self._numeric_exceptions))

    def _register_domain(self) -> None:
        bounded = {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}}
        if "inventory" in self.datasets and "sales" in self.datasets:
            self._register(ToolSpec("inventory_stockout_risk", "Calculate days/weeks of supply and stockout risk deterministically.", bounded, self._inventory_stockout))
            self._register(ToolSpec("inventory_overstock", "Find deterministic overstock candidates.", bounded, self._inventory_overstock))
            self._register(ToolSpec("inventory_slow_movers", "Find deterministic slow-moving inventory.", bounded, self._inventory_slow))
            self._register(ToolSpec("inventory_aging", "Rank aging inventory and approaching expirations.", bounded, self._inventory_aging))
            self._register(ToolSpec("inventory_reorder_candidates", "Calculate reorder candidates using sales velocity, inventory and open PO quantity where available.", {"type": "object", "properties": {"target_days": {"type": "integer", "minimum": 1, "maximum": 120}, "lead_time_days": {"type": "integer", "minimum": 0, "maximum": 120}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}}, self._inventory_reorder))
        if "purchase_recommendations" in self.datasets:
            self._register(ToolSpec("purchase_recommendations", "Return canonical deterministic RetailPlanningService replenishment recommendations.", bounded, self._purchase_recommendations))
        if {"purchase_orders", "purchase_order_lines", "purchase_receipts"}.issubset(self.datasets):
            self._register(ToolSpec("delivery_exceptions", "Find late, due-soon, partial, and outstanding purchase-order receipts.", bounded, self._delivery_exceptions))
            if "vendors" in self.datasets:
                self._register(ToolSpec("vendor_performance", "Calculate vendor fill rate, outstanding value, and on-time delivery when due/receipt dates exist.", bounded, self._vendor_performance))
        if "audit_lines" in self.datasets:
            self._register(ToolSpec("audit_variance_summary", "Calculate audit unit/percent/value variance and completion evidence.", bounded, self._audit_variance))
            self._register(ToolSpec("audit_recount_candidates", "Rank audit lines needing recount.", bounded, self._audit_recount))
        if "production_orders" in self.datasets and "production_actuals" in self.datasets:
            self._register(ToolSpec("production_attainment", "Calculate planned/requested versus actual production attainment.", bounded, self._production_attainment))
        if "production_orders" in self.datasets:
            self._register(ToolSpec("production_capacity_risks", "Assess aggregate production demand against configured machine and crew capacity without inventing job routing.", bounded, self._production_capacity))
            self._register(ToolSpec("production_material_shortages", "Check reserved material against lot balances and report missing requirement linkage when exact BOM demand cannot be proven.", bounded, self._production_material_shortages))
        if "extraction_run_analysis" in self.datasets:
            self._register(ToolSpec("extraction_run_analysis", "Return deterministic extraction mass-balance, yield, QA, margin, terpene, turnaround, downtime and integrity metrics.", bounded, self._extraction_analysis))
        if "extraction_method_summary" in self.datasets:
            self._register(ToolSpec("extraction_method_comparison", "Compare deterministic extraction performance by method.", bounded, self._extraction_method))
        if "commercial_orders" in self.datasets:
            self._register(ToolSpec("commercial_fulfillment_risk", "Calculate allocation fill rate, shortages, and due-date risk.", bounded, self._commercial_risk))
        if "cultivation_plants" in self.datasets:
            self._register(ToolSpec("cultivation_harvest_forecast", "Calculate upcoming harvest timing from authorized plant records.", bounded, self._cultivation_harvest))
            self._register(ToolSpec("cultivation_lifecycle_exceptions", "Find missing/inconsistent cultivation lifecycle dates.", bounded, self._cultivation_exceptions))
        if "active_data_sources" in self.datasets:
            self._register(ToolSpec("data_quality_report", "Summarize source freshness, mapping completeness and validation exceptions without exposing raw uploaded rows.", bounded, self._data_quality))
        if "product_master" in self.datasets:
            self._register(ToolSpec("catalog_naming_exceptions", "Find deterministic missing naming attributes and normalized duplicate-name candidates.", bounded, self._catalog_naming))

    def _describe_dataset(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("dataset") or "").casefold()
        loaded = self.datasets.get(name)
        if loaded is None:
            return {"error": "dataset_unavailable"}
        return {"dataset": name, "description": loaded.spec.description, "rows": len(loaded.frame), "columns": list(loaded.frame.columns), "freshness": loaded.freshness, "domain": loaded.spec.domain}

    def _preview(self, args):
        name = str(args.get("dataset") or "").casefold()
        return {"dataset": name, "rows": self._bounded(name, self._frame(name), int(args.get("limit") or 20))}

    def _search(self, args):
        name = str(args.get("dataset") or "").casefold()
        frame = self._frame(name)
        query = str(args.get("query") or "").strip().casefold()
        if not query:
            return self._preview({"dataset": name, "limit": args.get("limit") or 20})
        mask = pd.Series(False, index=frame.index)
        for column in frame.columns:
            mask |= frame[column].astype(str).str.casefold().str.contains(query, regex=False, na=False)
        return {"dataset": name, "matches": self._bounded(name, frame.loc[mask], int(args.get("limit") or 30))}

    def _summarize_numeric(self, args):
        name = str(args.get("dataset") or "").casefold()
        frame = self._frame(name)
        column = find_col(frame, (str(args.get("column") or ""),))
        if not column:
            return {"error": "column_unavailable"}
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if values.empty:
            return {"dataset": name, "column": column, "count": 0}
        return {"dataset": name, "column": column, "count": int(values.count()), "total": float(values.sum()), "average": float(values.mean()), "median": float(values.median()), "min": float(values.min()), "max": float(values.max())}

    def _group_summary(self, args):
        name = str(args.get("dataset") or "").casefold()
        frame = self._frame(name)
        group = find_col(frame, (str(args.get("group_column") or ""),))
        operation = str(args.get("operation") or "count")
        if not group:
            return {"error": "group_column_unavailable"}
        if operation == "count" or not args.get("value_column"):
            result = frame.groupby(group, dropna=False).size().reset_index(name="count").sort_values("count", ascending=False)
        else:
            value = find_col(frame, (str(args.get("value_column") or ""),))
            if not value:
                return {"error": "value_column_unavailable"}
            if operation not in {"sum", "mean", "min", "max"}:
                return {"error": "invalid_operation"}
            working = pd.DataFrame({group: frame[group], value: pd.to_numeric(frame[value], errors="coerce")})
            result = working.groupby(group, dropna=False)[value].agg(operation).reset_index().sort_values(value, ascending=False)
        return {"dataset": name, "operation": operation, "rows": records(result, limit=int(args.get("limit") or 25))}

    def _top_rows(self, args):
        name = str(args.get("dataset") or "").casefold()
        frame = self._frame(name).copy()
        column = find_col(frame, (str(args.get("sort_column") or ""),))
        if not column:
            return {"error": "column_unavailable"}
        frame["__sort"] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.sort_values("__sort", ascending=bool(args.get("ascending")), na_position="last").drop(columns="__sort")
        return {"dataset": name, "sort_column": column, "rows": self._bounded(name, frame, int(args.get("limit") or 20))}

    def _numeric_exceptions(self, args):
        name = str(args.get("dataset") or "").casefold()
        frame = self._frame(name).copy()
        column = find_col(frame, (str(args.get("column") or ""),))
        if not column:
            return {"error": "column_unavailable"}
        values = pd.to_numeric(frame[column], errors="coerce")
        threshold = float(args.get("threshold") or 0)
        below = str(args.get("direction") or "above") == "below"
        selected = frame.loc[values < threshold if below else values > threshold]
        return {"dataset": name, "column": column, "rows": self._bounded(name, selected, int(args.get("limit") or 30))}

    def _inventory_health(self):
        return inventory_health(self._frame("inventory"), self._frame("sales"))

    def _inventory_stockout(self, args):
        frame = self._inventory_health().sort_values(["days_of_supply", "on_hand"], na_position="last")
        return {"method": "deterministic", "rows": records(frame, limit=int(args.get("limit") or 30))}

    def _inventory_overstock(self, args):
        frame = self._inventory_health()
        frame = frame.loc[frame["overstock"]].sort_values("days_of_supply", ascending=False, na_position="last")
        return {"method": "deterministic", "rows": records(frame, limit=int(args.get("limit") or 30))}

    def _inventory_slow(self, args):
        frame = self._inventory_health()
        frame = frame.loc[frame["slow_mover"]].sort_values("inventory_value", ascending=False)
        return {"method": "deterministic", "rows": records(frame, limit=int(args.get("limit") or 30))}

    def _inventory_aging(self, args):
        frame = self._inventory_health()
        if "age_days" not in frame and "days_to_expiration" not in frame:
            return {"method": "deterministic", "rows": [], "missing_data": ["Received date or expiration date"]}
        sort_column = "age_days" if "age_days" in frame else "days_to_expiration"
        frame = frame.sort_values(sort_column, ascending=sort_column == "days_to_expiration", na_position="last")
        return {"method": "deterministic", "rows": records(frame, limit=int(args.get("limit") or 30))}

    def _inventory_reorder(self, args):
        open_po = self.datasets.get("purchase_order_lines")
        frame = reorder_candidates(self._frame("inventory"), self._frame("sales"), target_days=int(args.get("target_days") or 21), lead_time_days=int(args.get("lead_time_days") or 0), open_po=open_po.frame if open_po else None)
        return {"method": "deterministic", "rows": records(frame, limit=int(args.get("limit") or 30))}

    def _purchase_recommendations(self, args):
        return {"method": "RetailPlanningService", "rows": self._bounded("purchase_recommendations", self._frame("purchase_recommendations"), int(args.get("limit") or 30))}

    def _purchase_metrics(self):
        return purchase_order_metrics(self._frame("purchase_orders"), self._frame("purchase_order_lines"), self._frame("purchase_receipts"))

    def _delivery_exceptions(self, args):
        frame = self._purchase_metrics()
        if frame.empty:
            return {"method": "deterministic", "rows": []}
        if "delivery_risk" in frame:
            selected = frame.loc[(frame["delivery_risk"] != "normal") | (frame["outstanding_quantity"] > 0)].sort_values(["delivery_risk", "outstanding_value"], ascending=[True, False])
        else:
            selected = frame.loc[frame["outstanding_quantity"] > 0].sort_values("outstanding_value", ascending=False)
        return {"method": "deterministic", "rows": records(selected, limit=int(args.get("limit") or 30))}

    def _vendor_performance(self, args):
        frame = vendor_performance(self._frame("purchase_orders"), self._frame("purchase_order_lines"), self._frame("purchase_receipts"), self._frame("vendors"))
        return {"method": "deterministic", "rows": records(frame, limit=int(args.get("limit") or 30))}

    def _audit_variance(self, args):
        return {"method": "deterministic", "rows": records(audit_metrics(self._frame("audit_lines")), limit=int(args.get("limit") or 50))}

    def _audit_recount(self, args):
        frame = audit_metrics(self._frame("audit_lines"))
        frame = frame.loc[frame["recount_priority"] != "normal"].sort_values("absolute_variance", ascending=False)
        return {"method": "deterministic", "rows": records(frame, limit=int(args.get("limit") or 30))}

    def _production_attainment(self, args):
        return {"method": "deterministic", "rows": records(production_attainment(self._frame("production_orders"), self._frame("production_actuals")), limit=int(args.get("limit") or 50))}

    def _production_capacity(self, args):
        machines = self.datasets.get("facility_machines")
        crew = self.datasets.get("crew_availability")
        result = production_capacity_risks(self._frame("production_orders"), machines.frame if machines else pd.DataFrame(), crew.frame if crew else pd.DataFrame())
        result["method"] = "deterministic"
        return result

    def _production_material_shortages(self, args):
        reservations = self.datasets.get("material_reservations")
        transactions = self.datasets.get("inventory_transactions")
        if not reservations or not transactions:
            return {"method": "deterministic", "rows": [], "missing_data": ["Material reservations and inventory transaction balances"]}
        reserved = reservations.frame.copy()
        tx = transactions.frame.copy()
        lot_r = find_col(reserved, ("lot_id",))
        qty_r = find_col(reserved, ("quantity",))
        status_r = find_col(reserved, ("status",))
        lot_t = find_col(tx, ("lot_id",))
        qty_t = find_col(tx, ("quantity_delta", "quantity"))
        if not all((lot_r, qty_r, lot_t, qty_t)):
            return {"method": "deterministic", "rows": [], "missing_data": ["Lot/quantity fields needed for material-balance analysis"]}
        if status_r:
            reserved = reserved.loc[reserved[status_r].astype(str).str.casefold().eq("reserved")]
        reserved_by_lot = pd.DataFrame({"lot_id": reserved[lot_r].astype(str), "reserved": pd.to_numeric(reserved[qty_r], errors="coerce").fillna(0.0)}).groupby("lot_id", as_index=False)["reserved"].sum()
        balance_by_lot = pd.DataFrame({"lot_id": tx[lot_t].astype(str), "balance": pd.to_numeric(tx[qty_t], errors="coerce").fillna(0.0)}).groupby("lot_id", as_index=False)["balance"].sum()
        merged = reserved_by_lot.merge(balance_by_lot, on="lot_id", how="left").fillna({"balance": 0.0})
        merged["unreserved_balance"] = merged["balance"] - merged["reserved"]
        exceptions = merged.loc[merged["unreserved_balance"] < 0].sort_values("unreserved_balance")
        return {"method": "deterministic", "rows": records(exceptions, limit=int(args.get("limit") or 30)), "missing_data": ["Exact BOM-to-production-order material requirements are not linked in the current durable schema; shortage demand cannot be fabricated."]}

    def _extraction_analysis(self, args):
        return {"method": "existing extraction formulas", "rows": self._bounded("extraction_run_analysis", self._frame("extraction_run_analysis"), int(args.get("limit") or 30))}

    def _extraction_method(self, args):
        return {"method": "existing extraction formulas", "rows": self._bounded("extraction_method_summary", self._frame("extraction_method_summary"), int(args.get("limit") or 30))}

    def _commercial_risk(self, args):
        lines = self.datasets.get("commercial_order_lines")
        allocations = self.datasets.get("order_allocations")
        frame = commercial_fulfillment(self._frame("commercial_orders"), lines.frame if lines else pd.DataFrame(), allocations.frame if allocations else pd.DataFrame())
        return {"method": "deterministic", "rows": records(frame, limit=int(args.get("limit") or 50))}

    def _cultivation_harvest(self, args):
        return {"method": "deterministic", "rows": records(cultivation_metrics(self._frame("cultivation_plants"))["harvest_forecast"], limit=int(args.get("limit") or 50))}

    def _cultivation_exceptions(self, args):
        return {"method": "deterministic", "rows": records(cultivation_metrics(self._frame("cultivation_plants"))["exceptions"], limit=int(args.get("limit") or 50))}

    def _data_quality(self, args):
        frame = self._frame("active_data_sources").copy()
        validation = find_col(frame, ("validation_errors",))
        complete = find_col(frame, ("mapping_complete",))
        status = find_col(frame, ("status",))
        mask = pd.Series(False, index=frame.index)
        if validation:
            mask |= pd.to_numeric(frame[validation], errors="coerce").fillna(0).gt(0)
        if complete:
            mask |= ~frame[complete].fillna(False).astype(bool)
        if status:
            mask |= ~frame[status].astype(str).str.casefold().eq("active")
        selected = frame.loc[mask] if mask.any() else frame
        return {"method": "deterministic metadata review", "rows": records(selected, limit=int(args.get("limit") or 50))}

    def _catalog_naming(self, args):
        frame = self._frame("product_master").copy()
        name_col = find_col(frame, ("name", "product_name"))
        if not name_col:
            return {"method": "deterministic", "rows": [], "missing_data": ["Product name"]}
        frame["normalized_name"] = frame[name_col].fillna("").astype(str).map(lambda value: re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip())
        duplicate_names = set(frame.loc[frame["normalized_name"].duplicated(keep=False) & frame["normalized_name"].ne(""), "normalized_name"])
        brand = find_col(frame, ("brand",))
        category = find_col(frame, ("category",))
        mask = frame["normalized_name"].isin(duplicate_names) | frame["normalized_name"].eq("")
        if brand:
            mask |= frame[brand].fillna("").astype(str).str.strip().eq("")
        if category:
            mask |= frame[category].fillna("").astype(str).str.strip().eq("")
        selected = frame.loc[mask].copy()
        selected["duplicate_candidate"] = selected["normalized_name"].isin(duplicate_names)
        return {"method": "deterministic", "rows": records(selected, limit=int(args.get("limit") or 50))}
