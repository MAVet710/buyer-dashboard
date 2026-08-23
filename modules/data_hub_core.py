"""UI-independent Data Hub dataset inspection shared by web clients."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from typing import Any, Mapping

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

CANONICAL_COLUMN_NAMES = {
    "Inventory": {"Product": "Product Name", "Category": "Category", "On hand": "On Hand"},
    "Product Sales": {"Product": "Product Name", "Units sold": "Quantity Sold", "Category": "Category"},
    "Sales / Pricing Detail": {"Product": "Product Name", "Revenue": "Net Sales"},
    "Quarantine": {"Product": "Product Name"},
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


class _MappedUpload(BytesIO):
    pass


def build_mapped_upload(uploaded_file: Any, dataset_label: str, matches: Mapping[str, str]) -> Any:
    """Rewrite reviewed source headers without importing the Streamlit runtime."""

    requirements = DATASET_REQUIREMENTS.get(dataset_label, {})
    canonical = CANONICAL_COLUMN_NAMES.get(dataset_label, {})
    missing = [field for field in requirements if not str(matches.get(field) or "").strip()]
    if missing:
        raise ValueError("Required mapping is unresolved: " + ", ".join(missing))
    selected = [str(matches[field]) for field in requirements]
    if len(set(selected)) != len(selected):
        raise ValueError("One source column is assigned to more than one required field. Choose a unique column for each field.")

    payload = _file_bytes(uploaded_file)
    name = str(getattr(uploaded_file, "name", dataset_label))
    extension = Path(name).suffix.casefold()
    if extension == ".csv":
        frame = pd.read_csv(BytesIO(payload))
    elif extension in {".xlsx", ".xls"}:
        frame = pd.read_excel(BytesIO(payload))
    else:
        raise ValueError("Use a CSV, XLSX, or XLS file.")
    columns = [str(column) for column in frame.columns]
    invalid = [f"{field} -> {source}" for field, source in matches.items() if field in requirements and str(source) not in columns]
    if invalid:
        raise ValueError("Mapped source column no longer exists: " + ", ".join(invalid))

    selected_sources = set(selected)
    rename: dict[str, str] = {}
    for field, source_value in matches.items():
        if field not in canonical:
            continue
        source = str(source_value)
        target = str(canonical[field])
        if target in frame.columns and source != target and target not in selected_sources:
            frame = frame.rename(columns={target: f"Unmapped {target}"})
        rename[source] = target
    frame = frame.rename(columns=rename)

    output = BytesIO()
    normalized_name = name
    content_type = str(getattr(uploaded_file, "type", "") or "")
    if extension == ".csv":
        frame.to_csv(output, index=False)
        content_type = "text/csv"
    else:
        frame.to_excel(output, index=False)
        if extension == ".xls":
            normalized_name = str(Path(name).with_suffix(".xlsx"))
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    mapped = _MappedUpload(output.getvalue())
    mapped.name = normalized_name
    mapped.type = content_type
    mapped.source_name = name
    mapped.column_mapping = dict(matches)
    return mapped
