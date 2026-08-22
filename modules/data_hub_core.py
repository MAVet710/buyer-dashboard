"""UI-independent Data Hub dataset inspection shared by web clients."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from typing import Any

import pandas as pd


RETAIL_DATASETS = (
    {
        "label": "Inventory",
        "dataset_key": "inventory",
        "cache_key": "_cache_inv",
        "widget_key": "data_hub_inventory_upload",
        "types": ["csv", "xlsx", "xls"],
        "description": "Current on-hand inventory, cost, price, package size, and aging data.",
    },
    {
        "label": "Product Sales",
        "dataset_key": "product_sales",
        "cache_key": "_cache_sales",
        "widget_key": "data_hub_sales_upload",
        "types": ["csv", "xlsx", "xls"],
        "description": "Quantity-based sales history used by buyer intelligence and replenishment.",
    },
    {
        "label": "Sales / Pricing Detail",
        "dataset_key": "sales_pricing_detail",
        "cache_key": "_cache_extra_sales",
        "widget_key": "data_hub_extra_sales_upload",
        "types": ["csv", "xlsx", "xls"],
        "description": "Optional revenue, discount, and pricing detail.",
    },
    {
        "label": "Quarantine",
        "dataset_key": "quarantine",
        "cache_key": "_cache_quarantine",
        "widget_key": "data_hub_quarantine_upload",
        "types": ["csv", "xlsx", "xls"],
        "description": "Optional held inventory that should be excluded from purchasing decisions.",
    },
)

DATASET_REQUIREMENTS = {
    "Inventory": {
        "Product": ("product", "product name", "item", "item name", "name", "sku name"),
        "Category": ("category", "subcategory", "master category", "department"),
        "On hand": ("available", "on hand", "quantity", "qty", "inventory available"),
    },
    "Product Sales": {
        "Product": ("product", "product name", "item", "item name", "name"),
        "Units sold": ("quantity sold", "qty sold", "units sold", "items sold", "total inventory sold"),
        "Category": ("category", "subcategory", "master category", "department"),
    },
    "Sales / Pricing Detail": {
        "Product": ("product", "product name", "item", "item name", "name"),
        "Revenue": ("net sales", "gross sales", "revenue", "total sales"),
    },
    "Quarantine": {
        "Product": ("product", "product name", "item", "item name", "name", "sku name"),
    },
}


def _normalize_column(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().casefold()).strip()


def _file_bytes(uploaded_file: Any) -> bytes:
    if hasattr(uploaded_file, "getvalue"):
        return bytes(uploaded_file.getvalue())
    uploaded_file.seek(0)
    payload = bytes(uploaded_file.read())
    uploaded_file.seek(0)
    return payload


def inspect_uploaded_dataset(uploaded_file: Any, dataset_label: str) -> dict[str, Any]:
    """Inspect a staged CSV or workbook without importing a UI framework."""

    payload = _file_bytes(uploaded_file)
    name = str(getattr(uploaded_file, "name", dataset_label))
    extension = Path(name).suffix.casefold()
    if extension == ".csv":
        frame = pd.read_csv(BytesIO(payload))
    elif extension in {".xlsx", ".xls"}:
        frame = pd.read_excel(BytesIO(payload))
    else:
        raise ValueError("Use a CSV, XLSX, or XLS file.")
    if frame.empty:
        raise ValueError("The selected file contains no data rows.")

    normalized_columns = {_normalize_column(column): str(column) for column in frame.columns}
    requirements = DATASET_REQUIREMENTS.get(dataset_label, {})
    matches: dict[str, str] = {}
    missing: list[str] = []
    for purpose, aliases in requirements.items():
        match = next(
            (
                normalized_columns[normalized]
                for alias in aliases
                if (normalized := _normalize_column(alias)) in normalized_columns
            ),
            "",
        )
        if match:
            matches[purpose] = match
        else:
            missing.append(purpose)

    return {
        "name": name,
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "matches": matches,
        "missing": missing,
        "preview": frame.head(8),
        "quality": "Ready" if not missing else "Review mapping",
    }
