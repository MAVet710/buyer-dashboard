"""Read-only Gemini agents for Buyer Dashboard operational workspaces.

One Gemini runtime is shared across specialized agent personas. Each agent gets
only read-only tools and a bounded, sanitized view of the data relevant to its
workspace. No agent can mutate Buyer Dashboard, Supabase, METRC, Dutchie, or
any other external system.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from io import BytesIO
import json
import os
import re
from typing import Any, Mapping, get_type_hints

import pandas as pd

from services.agent_registry import AgentProfile, PROFILES, resolve_agent_profile

try:
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover
    genai = None
    types = None


DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
MAX_TOOL_ROWS = 75
MAX_CELL_CHARS = 500

SENSITIVE_COLUMN_PATTERNS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "email",
    "phone",
    "address",
    "customer_name",
    "patient",
    "employee",
    "contact",
    "first_name",
    "last_name",
    "dob",
    "birth",
    "ssn",
    "username",
    "created_by",
    "counted_by",
    "actor",
)


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _safe_scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    text = str(value)
    return text[:MAX_CELL_CHARS]


def _safe_columns(df: pd.DataFrame) -> list[str]:
    out: list[str] = []
    for col in df.columns:
        normalized = _norm(col)
        if any(_norm(pattern) in normalized for pattern in SENSITIVE_COLUMN_PATTERNS):
            continue
        out.append(str(col))
    return out


def _frame_records(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    limit: int = MAX_TOOL_ROWS,
) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    allowed = _safe_columns(df)
    if columns:
        requested = {_norm(c) for c in columns}
        allowed = [c for c in allowed if _norm(c) in requested]
    if not allowed:
        return []
    subset = df.loc[:, allowed].head(max(1, min(int(limit), MAX_TOOL_ROWS)))
    return [
        {str(k): _safe_scalar(v) for k, v in row.items()}
        for row in subset.to_dict(orient="records")
    ]


def _find_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    lookup = {_norm(c): str(c) for c in df.columns}
    for alias in aliases:
        if _norm(alias) in lookup:
            return lookup[_norm(alias)]
    for alias in aliases:
        needle = _norm(alias)
        for normalized, original in lookup.items():
            if needle and (needle in normalized or normalized in needle):
                return original
    return None


def _objects_frame(items: Any) -> pd.DataFrame:
    """Convert detached ORM/dataclass/mapping rows to a local DataFrame."""

    rows: list[dict[str, Any]] = []
    for item in list(items or []):
        if item is None:
            continue
        if isinstance(item, Mapping):
            rows.append(dict(item))
            continue
        if is_dataclass(item):
            rows.append(asdict(item))
            continue
        table = getattr(item, "__table__", None)
        if table is not None:
            rows.append(
                {
                    str(column.name): getattr(item, str(column.name), None)
                    for column in table.columns
                }
            )
            continue
        values = getattr(item, "__dict__", {})
        if isinstance(values, dict):
            rows.append({k: v for k, v in values.items() if not str(k).startswith("_")})
    return pd.DataFrame(rows)


def _coerce_frame(value: Any, name: str = "") -> pd.DataFrame | None:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, list):
        try:
            frame = pd.DataFrame(value)
            return frame if not frame.empty else None
        except Exception:
            return None
    if isinstance(value, tuple):
        try:
            frame = pd.DataFrame(list(value))
            return frame if not frame.empty else None
        except Exception:
            return None
    if isinstance(value, dict):
        payload = value.get("bytes")
        file_name = str(value.get("name") or name or "").casefold()
        if isinstance(payload, (bytes, bytearray)):
            try:
                if file_name.endswith(".csv"):
                    return pd.read_csv(BytesIO(bytes(payload)))
                if file_name.endswith((".xlsx", ".xls")):
                    return pd.read_excel(BytesIO(bytes(payload)))
            except Exception:
                return None
        try:
            if value and all(not isinstance(v, (dict, list, tuple, set)) for v in value.values()):
                return pd.DataFrame([value])
        except Exception:
            return None
    if hasattr(value, "getvalue"):
        try:
            payload = bytes(value.getvalue())
            file_name = str(getattr(value, "name", name) or "").casefold()
            if file_name.endswith(".csv"):
                return pd.read_csv(BytesIO(payload))
            if file_name.endswith((".xlsx", ".xls")):
                return pd.read_excel(BytesIO(payload))
        except Exception:
            return None
    return None


def _runtime_typed_tool(function: Any) -> Any:
    """Resolve deferred annotations before the Gemini SDK inspects a tool."""

    target = getattr(function, "__func__", function)
    try:
        resolved = get_type_hints(function)
    except Exception:
        return function
    if resolved and hasattr(target, "__annotations__"):
        target.__annotations__ = dict(resolved)
    return function


def _gemini_tool_functions(tools: "ReadOnlyDataTools") -> list[Any]:
    """Return SDK-facing tools with concrete runtime parameter annotations."""

    return [
        _runtime_typed_tool(tools.list_datasets),
        _runtime_typed_tool(tools.preview_dataset),
        _runtime_typed_tool(tools.search_dataset),
        _runtime_typed_tool(tools.summarize_numeric),
        _runtime_typed_tool(tools.top_rows),
        _runtime_typed_tool(tools.group_summary),
        _runtime_typed_tool(tools.numeric_exceptions),
        _runtime_typed_tool(tools.inventory_reorder_candidates),
    ]


class ReadOnlyDataTools:
    """Generic, bounded analytics tools shared by all workspace agents."""

    def __init__(self, datasets: Mapping[str, pd.DataFrame]):
        self.datasets = datasets

    def _dataset(self, name: str) -> pd.DataFrame:
        requested = _norm(name)
        aliases = {
            "inv": "inventory",
            "productsales": "sales",
            "extrasales": "extra_sales",
            "deliveries": "delivery",
            "runs": "extraction_runs",
            "orders": "production_orders",
            "commercialorders": "commercial_orders",
            "audit": "audit_lines",
        }
        requested = _norm(aliases.get(requested, name))
        for dataset_name, frame in self.datasets.items():
            if _norm(dataset_name) == requested and isinstance(frame, pd.DataFrame):
                return frame
        raise ValueError(f"Dataset '{name}' is not loaded for this agent.")

    def list_datasets(self) -> dict[str, Any]:
        """List read-only datasets available to the current workspace agent."""
        result: dict[str, Any] = {}
        for name, frame in self.datasets.items():
            if isinstance(frame, pd.DataFrame):
                result[name] = {
                    "rows": int(len(frame)),
                    "columns": _safe_columns(frame)[:60],
                }
        return result

    def preview_dataset(self, dataset: str, limit: int = 20) -> dict[str, Any]:
        """Preview sanitized rows from a loaded workspace dataset."""
        frame = self._dataset(dataset)
        return {"dataset": dataset, "rows": _frame_records(frame, limit=limit)}

    def search_dataset(self, dataset: str, query: str, limit: int = 30) -> dict[str, Any]:
        """Search non-sensitive fields for products, brands, lots, orders, statuses, vendors, or other terms."""
        frame = self._dataset(dataset)
        safe = _safe_columns(frame)
        if not safe:
            return {"dataset": dataset, "matches": []}
        q = str(query or "").strip().lower()
        if not q:
            return self.preview_dataset(dataset, limit)
        mask = pd.Series(False, index=frame.index)
        for col in safe:
            mask = mask | frame[col].astype(str).str.lower().str.contains(re.escape(q), na=False)
        return {"dataset": dataset, "matches": _frame_records(frame.loc[mask], limit=limit)}

    def summarize_numeric(self, dataset: str, column: str) -> dict[str, Any]:
        """Summarize a numeric column with count, total, average, median, min, and max."""
        frame = self._dataset(dataset)
        col = _find_col(frame, [column])
        if not col or col not in _safe_columns(frame):
            raise ValueError(f"Column '{column}' is unavailable.")
        values = pd.to_numeric(frame[col], errors="coerce").dropna()
        if values.empty:
            return {"dataset": dataset, "column": col, "count": 0}
        return {
            "dataset": dataset,
            "column": col,
            "count": int(values.count()),
            "total": float(values.sum()),
            "average": float(values.mean()),
            "median": float(values.median()),
            "min": float(values.min()),
            "max": float(values.max()),
        }

    def top_rows(
        self,
        dataset: str,
        sort_column: str,
        limit: int = 20,
        ascending: bool = False,
    ) -> dict[str, Any]:
        """Return highest or lowest rows by a numeric field."""
        frame = self._dataset(dataset).copy()
        col = _find_col(frame, [sort_column])
        if not col or col not in _safe_columns(frame):
            raise ValueError(f"Column '{sort_column}' is unavailable.")
        frame["__sort"] = pd.to_numeric(frame[col], errors="coerce")
        frame = frame.sort_values("__sort", ascending=bool(ascending), na_position="last").drop(columns=["__sort"])
        return {"dataset": dataset, "sort_column": col, "rows": _frame_records(frame, limit=limit)}

    def group_summary(
        self,
        dataset: str,
        group_column: str,
        value_column: str = "",
        operation: str = "count",
        limit: int = 25,
    ) -> dict[str, Any]:
        """Group rows and count or aggregate a numeric value with sum/mean/min/max."""
        frame = self._dataset(dataset).copy()
        group_col = _find_col(frame, [group_column])
        if not group_col or group_col not in _safe_columns(frame):
            raise ValueError(f"Group column '{group_column}' is unavailable.")
        operation = str(operation or "count").strip().lower()
        if operation == "count" or not value_column:
            grouped = frame.groupby(group_col, dropna=False).size().reset_index(name="count")
            sort_col = "count"
        else:
            value_col = _find_col(frame, [value_column])
            if not value_col or value_col not in _safe_columns(frame):
                raise ValueError(f"Value column '{value_column}' is unavailable.")
            numeric = pd.to_numeric(frame[value_col], errors="coerce")
            working = pd.DataFrame({group_col: frame[group_col], value_col: numeric})
            allowed = {"sum", "mean", "min", "max"}
            if operation not in allowed:
                raise ValueError("operation must be count, sum, mean, min, or max")
            grouped = working.groupby(group_col, dropna=False)[value_col].agg(operation).reset_index()
            sort_col = value_col
        grouped = grouped.sort_values(sort_col, ascending=False, na_position="last")
        return {
            "dataset": dataset,
            "group_column": group_col,
            "operation": operation,
            "rows": _frame_records(grouped, limit=limit),
        }

    def numeric_exceptions(
        self,
        dataset: str,
        column: str,
        threshold: float,
        direction: str = "above",
        limit: int = 30,
    ) -> dict[str, Any]:
        """Find rows above or below a numeric threshold, useful for variance, yield, aging, cost, and margin exceptions."""
        frame = self._dataset(dataset).copy()
        col = _find_col(frame, [column])
        if not col or col not in _safe_columns(frame):
            raise ValueError(f"Column '{column}' is unavailable.")
        numeric = pd.to_numeric(frame[col], errors="coerce")
        if str(direction).strip().lower() == "below":
            filtered = frame.loc[numeric < float(threshold)].copy()
            filtered["__sort"] = numeric.loc[filtered.index]
            filtered = filtered.sort_values("__sort", ascending=True).drop(columns=["__sort"])
        else:
            filtered = frame.loc[numeric > float(threshold)].copy()
            filtered["__sort"] = numeric.loc[filtered.index]
            filtered = filtered.sort_values("__sort", ascending=False).drop(columns=["__sort"])
        return {"dataset": dataset, "column": col, "rows": _frame_records(filtered, limit=limit)}

    def inventory_reorder_candidates(self, days_cover: int = 14, limit: int = 30) -> dict[str, Any]:
        """Calculate read-only reorder candidates from loaded inventory and sales data."""
        try:
            inv = self._dataset("inventory").copy()
            sales = self._dataset("sales").copy()
        except ValueError:
            return {"error": "Inventory and product-sales datasets are both required for reorder analysis."}
        inv_name = _find_col(inv, ["product name", "product", "item name", "item", "name", "sku name"])
        inv_qty = _find_col(inv, ["available", "on hand", "onhand", "quantity", "qty", "inventory available", "med total"])
        sales_name = _find_col(sales, ["product name", "product", "item name", "item", "name", "sku name", "description"])
        sales_qty = _find_col(sales, ["quantity sold", "qty sold", "units sold", "units", "total units"])
        if not all([inv_name, inv_qty, sales_name, sales_qty]):
            return {
                "error": "Could not identify required product and quantity columns.",
                "inventory_columns": _safe_columns(inv),
                "sales_columns": _safe_columns(sales),
            }

        inv["__name"] = inv[inv_name].astype(str).str.strip().str.lower()
        sales["__name"] = sales[sales_name].astype(str).str.strip().str.lower()
        inv["__qty"] = pd.to_numeric(inv[inv_qty], errors="coerce").fillna(0)
        sales["__sold"] = pd.to_numeric(sales[sales_qty], errors="coerce").fillna(0)
        inv_g = inv.groupby("__name", as_index=False).agg(product=(inv_name, "first"), on_hand=("__qty", "sum"))
        sales_g = sales.groupby("__name", as_index=False).agg(units_sold=("__sold", "sum"))
        merged = inv_g.merge(sales_g, on="__name", how="left").fillna({"units_sold": 0})
        merged["daily_velocity_est"] = merged["units_sold"] / 30.0
        merged["target_units"] = (merged["daily_velocity_est"] * max(1, int(days_cover))).round(0)
        merged["suggested_reorder"] = (merged["target_units"] - merged["on_hand"]).clip(lower=0).round(0)
        merged["days_cover_est"] = merged.apply(
            lambda row: round(row["on_hand"] / row["daily_velocity_est"], 1)
            if row["daily_velocity_est"] > 0
            else None,
            axis=1,
        )
        output = merged[merged["suggested_reorder"] > 0].sort_values(
            ["suggested_reorder", "units_sold"], ascending=False
        )
        cols = [
            "product",
            "on_hand",
            "units_sold",
            "daily_velocity_est",
            "days_cover_est",
            "target_units",
            "suggested_reorder",
        ]
        return {
            "method_note": "Uses loaded sales units with a 30-day normalization because source report period metadata is not guaranteed.",
            "target_days_cover": int(days_cover),
            "candidates": _frame_records(output[cols], limit=limit),
        }


class GeminiWorkspaceAgent:
    """Gemini function-calling agent with workspace-specific read-only context."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        profile: AgentProfile | None = None,
    ) -> None:
        self.api_key = str(api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        self.model = str(model or DEFAULT_GEMINI_MODEL).strip()
        self.profile = profile or PROFILES["buyer"]

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and genai is not None and types is not None)

    def run(
        self,
        question: str,
        datasets: Mapping[str, pd.DataFrame],
        app_mode: str = "",
        section: str = "",
        history: list[dict[str, str]] | None = None,
        profile: AgentProfile | None = None,
    ) -> str:
        if not self.enabled:
            raise RuntimeError("Gemini is not configured. Add GEMINI_API_KEY to app secrets/environment.")
        active = profile or self.profile or resolve_agent_profile(app_mode, section)
        tools = ReadOnlyDataTools(datasets)
        functions = _gemini_tool_functions(tools)
        client = genai.Client(api_key=self.api_key)
        history_text = "\n".join(
            f"{item.get('role', 'user')}: {item.get('content', '')}"
            for item in (history or [])[-8:]
        )
        available = ", ".join(datasets.keys()) or "none"
        focus = ", ".join(active.focus)
        compliance_rule = (
            "- This is a sourced-compliance workflow. Never state a regulation, legal requirement, penalty, or compliance conclusion from model memory. "
            "Only analyze evidence returned by tools or tell the user what should be verified in the app's sourced Compliance Q&A.\n"
            if active.compliance_grounded_only
            else "- Never infer cannabis regulations from model memory. For legal or regulatory conclusions, use the app's sourced compliance workflow.\n"
        )
        prompt = f"""You are {active.name}, the {active.role} inside Buyer Dashboard.

Workspace: {app_mode}
Section: {section}
Specialist focus: {focus}
Read-only datasets currently available: {available}
Recent conversation:\n{history_text or '(none)'}

User request: {question}

Rules:
- Use the provided read-only tools whenever the answer depends on operational data.
- Never claim to submit, edit, receive, adjust, transfer, fulfill, count, schedule, order, reserve, or modify anything. You have no write tools.
- Do not invent values that are not returned by a tool.
- Clearly label estimates and assumptions.
- Keep recommendations practical and specific to this workspace.
- Mention missing or unavailable data when it limits the answer.
{compliance_rule}- Do not request or expose secrets, customer/patient information, employee PII, credentials, or API keys.
"""
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=functions,
                temperature=0.2,
                max_output_tokens=1400,
            ),
        )
        text = str(getattr(response, "text", "") or "").strip()
        return text or f"{active.name} did not return an answer."


class GeminiBuyerAgent(GeminiWorkspaceAgent):
    """Backward-compatible Buyer Agent wrapper."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        super().__init__(api_key=api_key, model=model, profile=PROFILES["buyer"])


BASE_SESSION_DATASETS = {
    "inventory": "inv_raw_df",
    "sales": "sales_raw_df",
    "extra_sales": "extra_sales_df",
    "delivery": "delivery_raw_df",
    "buyer_forecast": "detail_cached_df",
    "buyer_product_forecast": "detail_product_cached_df",
}

EXTRACTION_SESSION_DATASETS = {
    "extraction_runs": "ecc_run_log",
    "extraction_value": "ecc_run_value_snapshot",
    "extraction_weekly": "ecc_weekly_summary",
    "partner_extraction_runs": "ecc_partner_run_log",
}

DATA_HUB_CACHE_DATASETS = {
    "inventory": "_cache_inv",
    "sales": "_cache_sales",
    "extra_sales": "_cache_extra_sales",
    "quarantine": "_cache_quarantine",
}


def _put_frame(output: dict[str, pd.DataFrame], name: str, value: Any) -> None:
    frame = _coerce_frame(value, name)
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        output[name] = frame


def _load_base_session_datasets(session_state: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    for public_name, session_key in BASE_SESSION_DATASETS.items():
        _put_frame(output, public_name, session_state.get(session_key))
    return output


def _load_extraction_datasets(session_state: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    for public_name, session_key in EXTRACTION_SESSION_DATASETS.items():
        _put_frame(output, public_name, session_state.get(session_key))
    return output


def _load_data_hub_datasets(session_state: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    output = _load_base_session_datasets(session_state)
    for public_name, session_key in DATA_HUB_CACHE_DATASETS.items():
        if public_name not in output:
            _put_frame(output, public_name, session_state.get(session_key))
    return output


def _load_repack_datasets(session_state: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    _put_frame(output, "package_plan", session_state.get("white_label_package_plan"))
    scenario_rows: list[dict[str, Any]] = []
    for key, value in session_state.items():
        key_text = str(key)
        if not key_text.startswith("wl_"):
            continue
        if any(_norm(pattern) in _norm(key_text) for pattern in ("password", "secret", "token", "api_key")):
            continue
        if isinstance(value, (str, int, float, bool, date, datetime)) or value is None:
            scenario_rows.append({"field": key_text[3:], "value": _safe_scalar(value)})
    if scenario_rows:
        output["repack_scenario"] = pd.DataFrame(scenario_rows)
    return output


def _tenant_ids(session_state: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(session_state.get("active_organization_id") or "").strip(),
        str(session_state.get("active_facility_id") or "").strip(),
    )


def _adapter_unavailable(name: str) -> dict[str, pd.DataFrame]:
    return {
        f"{name}_adapter_status": pd.DataFrame(
            [{"status": "unavailable", "message": "Read-only workspace data is not currently available."}]
        )
    }


def _load_coman_datasets(session_state: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    organization_id, facility_id = _tenant_ids(session_state)
    if not organization_id or not facility_id:
        return {}
    try:
        from modules.coman.db import create_coman_engine
        from modules.coman.repository import ComanRepository

        repo = ComanRepository(create_coman_engine())
        output = {
            "production_orders": _objects_frame(repo.list_production_orders(organization_id, facility_id)),
            "production_actuals": _objects_frame(repo.list_production_actuals(organization_id, facility_id)),
            "facility_machines": _objects_frame(repo.list_facility_machines(organization_id, facility_id)),
            "crew_availability": _objects_frame(repo.list_crew_availability(organization_id, facility_id, date.today())),
            "products": _objects_frame(repo.list_products(organization_id)),
            "inventory_lots": _objects_frame(repo.list_inventory_lots(organization_id, facility_id)),
            "inventory_transactions": _objects_frame(repo.list_inventory_transactions(organization_id, facility_id, limit=250)),
            "material_reservations": _objects_frame(repo.list_material_reservations(organization_id, facility_id)),
        }
        return {name: frame for name, frame in output.items() if not frame.empty}
    except Exception:
        return _adapter_unavailable("coman")


def _load_commercial_datasets(session_state: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    organization_id, facility_id = _tenant_ids(session_state)
    if not organization_id or not facility_id:
        return {}
    try:
        from modules.coman.db import create_coman_engine
        from modules.coman.repository import ComanRepository
        from modules.commercial.repository import CommercialRepository

        engine = create_coman_engine()
        commercial = CommercialRepository(engine)
        coman = ComanRepository(engine)
        output = {
            "trade_partners": _objects_frame(commercial.list_trade_partners(organization_id)),
            "commercial_orders": _objects_frame(commercial.list_orders(organization_id, facility_id)),
            "commercial_order_lines": _objects_frame(commercial.list_order_lines(organization_id)),
            "order_allocations": _objects_frame(commercial.list_allocations(organization_id, facility_id)),
            "commercial_transactions": _objects_frame(commercial.list_commercial_transactions(organization_id, facility_id)),
            "products": _objects_frame(coman.list_products(organization_id)),
            "inventory_lots": _objects_frame(coman.list_inventory_lots(organization_id, facility_id)),
        }
        return {name: frame for name, frame in output.items() if not frame.empty}
    except Exception:
        return _adapter_unavailable("commercial")


def _load_audit_datasets(session_state: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    organization_id, facility_id = _tenant_ids(session_state)
    output = _load_base_session_datasets(session_state)
    if not organization_id or not facility_id:
        return output
    try:
        from modules.coman.db import create_coman_engine
        from modules.coman.repository import ComanRepository
        from modules.inventory_audit.repository import InventoryAuditRepository

        engine = create_coman_engine()
        audits = InventoryAuditRepository(engine)
        coman = ComanRepository(engine)
        audit_rows = audits.list_audits(organization_id, facility_id, operation_type="retail")
        if audit_rows:
            output["inventory_audits"] = _objects_frame(audit_rows)
            selected_id = str(session_state.get("current_audit_id_retail") or "").strip()
            selected = next((row for row in audit_rows if str(row.id) == selected_id), None)
            if selected is None:
                selected = next((row for row in audit_rows if row.status in {"in_progress", "paused", "stopped"}), audit_rows[0])
            output["audit_lines"] = _objects_frame(audits.list_lines(organization_id, selected.id))
            output["audit_scans"] = _objects_frame(audits.list_scans(organization_id, selected.id))
        output["products"] = _objects_frame(coman.list_products(organization_id))
        output["inventory_lots"] = _objects_frame(coman.list_inventory_lots(organization_id, facility_id))
        return {name: frame for name, frame in output.items() if not frame.empty}
    except Exception:
        output.update(_adapter_unavailable("audit"))
        return output


def datasets_from_session(
    session_state: Mapping[str, Any],
    app_mode: str = "",
    section: str = "",
    profile: AgentProfile | None = None,
) -> dict[str, pd.DataFrame]:
    """Build the current specialist's read-only datasets from session/tenant data."""

    active = profile or resolve_agent_profile(app_mode, section)
    if active.key == "extraction":
        return _load_extraction_datasets(session_state)
    if active.key == "repack":
        return _load_repack_datasets(session_state)
    if active.key == "coman":
        return _load_coman_datasets(session_state)
    if active.key == "commercial":
        return _load_commercial_datasets(session_state)
    if active.key == "audit":
        return _load_audit_datasets(session_state)
    if active.key == "data_hub":
        return _load_data_hub_datasets(session_state)
    # Buyer, Purchasing, Inventory, Compliance, Nomenclature, and Home use
    # the retail operational datasets already loaded into the current session.
    output = _load_base_session_datasets(session_state)
    if active.key == "ops":
        output.update({name: frame for name, frame in _load_extraction_datasets(session_state).items() if name not in output})
    return output