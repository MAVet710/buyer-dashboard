"""Deterministic read contracts for current inventory, not uploaded forecasts."""
from __future__ import annotations

from typing import Any

import pandas as pd

from .analytics import find_col
from .datasets import LoadedDataset
from .sanitization import norm, records


QUANTITY_COLUMNS = frozenset({
    "on_hand", "available", "reserved", "production_reserved",
    "wholesale_committed", "wholesale_reserved", "usable",
})
SALES_TOOLS = (
    "inventory_stockout_risk", "inventory_overstock", "inventory_slow_movers",
    "inventory_reorder_candidates",
)
CURRENT_TOOLS = (*SALES_TOOLS, "inventory_aging", "inventory_availability")


def _missing(message: str, required: str, *, state: str = "unavailable") -> dict[str, Any]:
    # _agent_summary keeps the deterministic formatter from describing a
    # blocked/unknown calculation as "no matching candidates were found".
    return {"method": "canonical inventory", "state": state, "rows": [],
            "missing_data": [required], "_agent_summary": message}


def canonical_inventory_result(name: str, args: dict[str, Any], datasets: dict[str, LoadedDataset]) -> dict[str, Any] | None:
    """Return a guarded result, or None to retain unrelated/legacy behavior."""
    if "inventory_evidence" not in datasets:
        return None
    targets_inventory = str(args.get("dataset") or "").casefold() == "inventory"
    if name not in CURRENT_TOOLS and not targets_inventory:
        return None
    evidence = datasets["inventory_evidence"].frame
    inventory = datasets.get("inventory")
    state = str(evidence.iloc[0].get("state") or "unavailable") if len(evidence) == 1 else "unavailable"
    if state not in {"available", "empty"} or inventory is None:
        return _missing("Current inventory evidence is unavailable. No stock total, stockout conclusion or reorder quantity can be established, and an uploaded snapshot was not substituted.", "Successful current inventory read")
    if name in SALES_TOOLS:
        return _missing("Current stock is available, but this sales-dependent calculation needs verified product/unit mapping and sales-period coverage. Uploaded sales are not silently joined to package quantities. This does not mean there are no reorder needs or inventory risks.", "Verified sales product/unit mapping and reporting-period coverage", state="needs_sales_mapping")
    frame = inventory.frame
    if frame.empty:
        return {"method": "canonical inventory", "state": "empty", "rows": [],
                "_agent_summary": "The successful current inventory read returned no retail package records for the selected facility. This is not a live provider-sync verification."}
    limit = max(1, min(int(args.get("limit") or 30), int(inventory.spec.max_tool_rows), 100))
    column = find_col(frame, (str(args.get("value_column") if name == "group_summary" else args.get("sort_column") if name == "top_rows" else args.get("column") or ""),))
    quantity = norm(column) in QUANTITY_COLUMNS if column else False
    needs_units = name == "inventory_availability" or quantity
    if needs_units and ("unit" not in frame or frame["unit"].isna().any() or frame["unit"].astype(str).str.strip().eq("").any()):
        return _missing("Inventory quantities have missing units. No combined quantity was calculated.", "Unit of measure for every quantity")
    result = None
    if name == "inventory_availability":
        columns = [key for key in ("on_hand", "available", "reserved", "production_reserved", "wholesale_committed", "wholesale_reserved") if key in frame]
        result = frame.groupby("unit", dropna=False)[columns].sum().reset_index()
        result["package_count"] = result["unit"].map(frame.groupby("unit").size())
    elif name == "inventory_aging":
        columns = [key for key in ("id", "package_id", "product_id", "sku", "product_name", "status", "on_hand", "available", "unit", "received_at", "expiration_at", "age_days", "days_to_expiry") if key in frame]
        result = frame.loc[:, columns].copy()
        dated = result.get("received_at", pd.Series(None, index=result.index)).notna() | result.get("expiration_at", pd.Series(None, index=result.index)).notna()
        result = result.loc[dated]
        if result.empty:
            return _missing("Current inventory was read, but its packages have no received or expiration dates to rank. No aging-risk conclusion was generated.", "Received or expiration dates")
        result = result.sort_values([key for key in ("days_to_expiry", "age_days") if key in result], ascending=[True, False][:sum(key in result for key in ("days_to_expiry", "age_days"))], na_position="last")
    elif name == "summarize_numeric" and quantity:
        working = frame.assign(**{column: pd.to_numeric(frame[column], errors="coerce")})
        result = working.groupby("unit")[column].agg(count="count", total="sum", average="mean", median="median", min="min", max="max").reset_index()
    elif name == "group_summary" and quantity and str(args.get("operation") or "count") != "count":
        group = find_col(frame, (str(args.get("group_column") or ""),))
        operation = str(args.get("operation"))
        if not group or group == column:
            return {"error": "invalid_quantity_group"}
        if operation not in {"sum", "mean", "min", "max"}:
            return {"error": "invalid_operation"}
        groups = list(dict.fromkeys([group, "unit"]))
        working = frame.assign(**{column: pd.to_numeric(frame[column], errors="coerce")})
        result = working.groupby(groups, dropna=False)[column].agg(operation).reset_index()
    elif name in {"top_rows", "numeric_exceptions"} and quantity and frame["unit"].nunique() > 1:
        return _missing("A single numeric ranking or threshold cannot compare unlike inventory units. Review package rows with their units, or use unit-grouped quantity summaries.", "A single comparable quantity unit", state="mixed_units")
    if result is None:
        return None
    return {"method": "canonical inventory", "state": state, "dataset": "inventory",
            "unit_grouped": name != "inventory_aging", "rows": records(result, limit=limit),
            "total_result_rows": len(result), "truncated": len(result) > limit,
            "warnings": ["Quantities retain their original units; on_hand is physical stock and available excludes commitments/holds. A database read does not verify provider-sync freshness."]}
