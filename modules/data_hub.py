"""Shared data intake workspace for retail and production operations."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from io import BytesIO
from pathlib import Path
import re
from typing import Any, MutableMapping

import pandas as pd
import streamlit as st

from extraction_partner_upload_upgrade import render_extraction_partner_upload_ui


MAX_UPLOAD_BYTES = 25 * 1024 * 1024

RETAIL_DATASETS = (
    {
        "label": "Inventory",
        "cache_key": "_cache_inv",
        "widget_key": "data_hub_inventory_upload",
        "types": ["csv", "xlsx", "xls"],
        "description": "Current on-hand inventory, cost, price, package size, and aging data.",
    },
    {
        "label": "Product Sales",
        "cache_key": "_cache_sales",
        "widget_key": "data_hub_sales_upload",
        "types": ["csv", "xlsx", "xls"],
        "description": "Quantity-based sales history used by buyer intelligence and replenishment.",
    },
    {
        "label": "Sales / Pricing Detail",
        "cache_key": "_cache_extra_sales",
        "widget_key": "data_hub_extra_sales_upload",
        "types": ["csv", "xlsx", "xls"],
        "description": "Optional revenue, discount, and pricing detail.",
    },
    {
        "label": "Quarantine",
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


def inspect_uploaded_dataset(uploaded_file: Any, dataset_label: str) -> dict[str, Any]:
    """Read a staged file and return a lightweight, user-facing quality preview."""

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


def _file_bytes(uploaded_file: Any) -> bytes:
    if hasattr(uploaded_file, "getvalue"):
        return bytes(uploaded_file.getvalue())
    uploaded_file.seek(0)
    payload = bytes(uploaded_file.read())
    uploaded_file.seek(0)
    return payload


def stage_uploaded_dataset(
    state: MutableMapping[str, Any],
    uploaded_file: Any,
    *,
    cache_key: str,
    dataset_label: str,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
) -> dict[str, Any]:
    """Stage one uploaded dataset and record a de-duplicated import event."""
    payload = _file_bytes(uploaded_file)
    if len(payload) > max_upload_bytes:
        raise ValueError(
            f"{dataset_label} exceeds the {max_upload_bytes // (1024 * 1024)} MB upload limit."
        )

    name = str(getattr(uploaded_file, "name", dataset_label))
    fingerprint = hashlib.sha256(payload).hexdigest()
    staged_at = datetime.now(timezone.utc).isoformat()
    existing = state.get(cache_key)
    if isinstance(existing, dict) and existing.get("fingerprint") == fingerprint:
        return existing

    staged = {
        "name": name,
        "bytes": payload,
        "fingerprint": fingerprint,
        "staged_at": staged_at,
        "dataset": dataset_label,
    }
    state[cache_key] = staged

    history = list(state.get("data_hub_import_history", []))
    history.insert(
        0,
        {
            "Dataset": dataset_label,
            "File": name,
            "Size": len(payload),
            "Status": "Staged",
            "Imported At": staged_at,
            "Fingerprint": fingerprint,
        },
    )
    state["data_hub_import_history"] = history[:100]
    return staged


def build_data_hub_status(state: MutableMapping[str, Any]) -> list[dict[str, Any]]:
    """Return compact source-health rows without depending on Streamlit widgets."""
    rows: list[dict[str, Any]] = []
    for spec in RETAIL_DATASETS:
        cached = state.get(spec["cache_key"])
        ready = isinstance(cached, dict) and bool(cached.get("bytes"))
        rows.append(
            {
                "Operations": "Retail Ops",
                "Dataset": spec["label"],
                "Status": "Ready" if ready else "Not loaded",
                "Source": cached.get("name", "") if ready else "",
                "Rows": "Validated in Buyer Operations" if ready else "",
                "Updated": cached.get("staged_at", "") if ready else "",
            }
        )

    extraction_runs = state.get("ecc_run_log")
    extraction_count = (
        len(extraction_runs)
        if isinstance(extraction_runs, pd.DataFrame)
        else 0
    )
    rows.append(
        {
            "Operations": "Production Ops",
            "Dataset": "Extraction Runs",
            "Status": "Ready" if extraction_count else "Not loaded",
            "Source": "Current production session" if extraction_count else "",
            "Rows": extraction_count,
            "Updated": "",
        }
    )
    rows.append(
        {
            "Operations": "Production Ops",
            "Dataset": "Co-Man Master Data",
            "Status": (
                "Ready"
                if state.get("active_organization_id") and state.get("active_facility_id")
                else "Select organization and facility"
            ),
            "Source": state.get("active_facility_name", ""),
            "Rows": "Durable Supabase records",
            "Updated": "",
        }
    )
    for operations, label, state_key, source in (
        (
            "Commercial Ops",
            "Orders & Fulfillment",
            "demo_commercial_orders_df",
            "Durable sandbox order ledger",
        ),
        (
            "Retail Ops",
            "Nomenclature Catalog",
            "demo_nomenclature_catalog_df",
            "Organization Dutchie catalog",
        ),
        (
            "Production Ops",
            "Production Capacity",
            "demo_production_machines_df",
            "Machines, hand labor, and crew plan",
        ),
        (
            "Retail Ops",
            "Compliance Sources",
            "compliance_sources_df",
            "Reviewed structured source library",
        ),
    ):
        frame = state.get(state_key)
        count = len(frame) if isinstance(frame, pd.DataFrame) else 0
        rows.append(
            {
                "Operations": operations,
                "Dataset": label,
                "Status": "Ready" if count else "Not loaded",
                "Source": source if count else "",
                "Rows": count,
                "Updated": "",
            }
        )
    return rows


def _render_upload_slot(spec: dict[str, Any]) -> None:
    st.markdown(f"#### {spec['label']}")
    st.caption(spec["description"])
    cached = st.session_state.get(spec["cache_key"])
    if isinstance(cached, dict) and cached.get("bytes"):
        st.success(
            f"Ready: {cached.get('name', spec['label'])} "
            f"({len(cached['bytes']) / 1024:,.0f} KB)"
        )
    uploaded = st.file_uploader(
        f"Upload {spec['label']}",
        type=spec["types"],
        key=spec["widget_key"],
        label_visibility="collapsed",
    )
    if uploaded is not None:
        try:
            staged = stage_uploaded_dataset(
                st.session_state,
                uploaded,
                cache_key=spec["cache_key"],
                dataset_label=spec["label"],
            )
            st.success(f"{staged['name']} staged successfully.")
        except Exception as exc:
            st.error(f"{spec['label']} could not be staged: {exc}")


def _render_guided_retail_import() -> None:
    """Render one focused upload flow instead of four persistent upload widgets."""

    st.markdown("### Import retail data")
    st.caption("Choose one source, upload it, review the detected structure, then publish it for reuse.")

    labels = [spec["label"] for spec in RETAIL_DATASETS]
    selected_label = st.selectbox(
        "1. Choose the dataset",
        labels,
        key="data_hub_selected_retail_dataset",
    )
    spec = next(item for item in RETAIL_DATASETS if item["label"] == selected_label)
    st.info(spec["description"])

    cached = st.session_state.get(spec["cache_key"])
    if isinstance(cached, dict) and cached.get("bytes"):
        st.success(f"Current source: {cached.get('name', selected_label)}")

    uploaded = st.file_uploader(
        "2. Upload the source file",
        type=spec["types"],
        key=f"guided_{spec['widget_key']}",
        help="The file remains in review until you explicitly publish it.",
    )
    if uploaded is None:
        st.caption("Nothing changes until a file is uploaded and published.")
        return

    try:
        inspection = inspect_uploaded_dataset(uploaded, selected_label)
    except Exception as exc:
        st.error(f"The file could not be inspected: {exc}")
        return

    st.markdown("#### 3. Review detected structure")
    metrics = st.columns(3)
    metrics[0].metric("Rows", f"{inspection['rows']:,}")
    metrics[1].metric("Columns", inspection["columns"])
    metrics[2].metric("Quality", inspection["quality"])

    mapping_rows = [
        {
            "Required field": purpose,
            "Detected column": inspection["matches"].get(purpose, "Not detected"),
            "Status": "Matched" if purpose in inspection["matches"] else "Review",
        }
        for purpose in DATASET_REQUIREMENTS.get(selected_label, {})
    ]
    if mapping_rows:
        st.dataframe(pd.DataFrame(mapping_rows), width="stretch", hide_index=True)
    if inspection["missing"]:
        st.warning(
            "These fields were not detected automatically: "
            + ", ".join(inspection["missing"])
            + ". You can still publish the source and confirm the mapping in Buyer Operations."
        )
    with st.expander("Preview first 8 rows", expanded=not inspection["missing"]):
        st.dataframe(inspection["preview"], width="stretch", hide_index=True)

    confirmed = st.checkbox(
        "I reviewed the source and want it available to Retail Operations.",
        key=f"confirm_{spec['widget_key']}",
    )
    publish_label = "Replace current source" if cached else "Publish source"
    if st.button(
        f"4. {publish_label}",
        type="primary",
        disabled=not confirmed,
        key=f"publish_{spec['widget_key']}",
    ):
        try:
            staged = stage_uploaded_dataset(
                st.session_state,
                uploaded,
                cache_key=spec["cache_key"],
                dataset_label=selected_label,
            )
            st.success(f"{staged['name']} is now available across Retail Operations.")
        except Exception as exc:
            st.error(f"{selected_label} could not be published: {exc}")


def render_data_hub_workspace() -> None:
    """Render the shared Connect / Upload / Review / Publish intake experience."""
    st.markdown("## Data Hub")
    st.caption(
        "Load operational data once, verify its status, and reuse it across Retail Ops "
        "and Production Ops. Existing workspace-specific uploaders remain available."
    )

    status_rows = build_data_hub_status(st.session_state)
    ready_count = sum(row["Status"] == "Ready" for row in status_rows)
    metrics = st.columns(4)
    metrics[0].metric("Sources Ready", f"{ready_count}/{len(status_rows)}")
    metrics[1].metric(
        "Retail Sources",
        sum(
            row["Status"] == "Ready" and row["Operations"] == "Retail Ops"
            for row in status_rows
        ),
    )
    metrics[2].metric(
        "Extraction Runs",
        next(
            (
                row["Rows"]
                for row in status_rows
                if row["Dataset"] == "Extraction Runs"
            ),
            0,
        ),
    )
    metrics[3].metric(
        "Active Facility",
        st.session_state.get("active_facility_name") or "Not selected",
    )

    overview_tab, retail_tab, production_tab, history_tab = st.tabs(
        ["Readiness", "Import Retail Data", "Import Production Data", "History"]
    )

    with overview_tab:
        st.markdown("### Operational source status")
        st.dataframe(
            pd.DataFrame(status_rows),
            width="stretch",
            hide_index=True,
        )
        st.info(
            "Recommended flow: upload or connect a source, review its mapping and quality, "
            "then open the destination workspace to publish operational decisions."
        )

    with retail_tab:
        _render_guided_retail_import()

        staged_retail = [
            spec for spec in RETAIL_DATASETS if st.session_state.get(spec["cache_key"])
        ]
        if staged_retail:
            st.success(
                f"{len(staged_retail)} retail source(s) staged. "
                "Open Buyer Operations to validate columns and refresh analytics."
            )
            if st.button("Open Retail Operations", key="data_hub_open_retail", type="secondary"):
                st.session_state["operations_group"] = "🛍️ Retail Ops"
                st.session_state["workspace_mode"] = "🛒 Buyer Operations"
                st.session_state["buyer_section_group"] = "Overview"
                st.session_state["buyer_section"] = "📊 Inventory Dashboard"
                st.rerun()
        with st.expander("Manage staged retail files", expanded=False):
            if st.button(
                "Clear staged retail files",
                key="data_hub_clear_retail",
                type="secondary",
            ):
                for spec in RETAIL_DATASETS:
                    st.session_state.pop(spec["cache_key"], None)
                st.success("Staged retail files cleared.")
                st.rerun()

    with production_tab:
        st.markdown("### Production Ops source intake")
        st.caption(
            "Extraction run imports use automatic header detection, field mapping, "
            "deduplication, and a review preview before rows are appended."
        )
        render_extraction_partner_upload_ui()
        st.divider()
        st.markdown("#### Co-Man durable data")
        if st.session_state.get("active_organization_id") and st.session_state.get(
            "active_facility_id"
        ):
            st.success(
                "Organization and facility are selected. Products, lots, customers, "
                "machines, schedules, and production history are stored in Supabase."
            )
        else:
            st.warning(
                "Select an organization and facility to create or update Co-Man master data."
            )
        st.caption(
            "Use Co-Man Production for product, lot, BOM, machine, crew, and customer setup. "
            "Those records are master data and should be entered once, not re-uploaded per job."
        )

    with history_tab:
        history = list(st.session_state.get("data_hub_import_history", []))
        if not history:
            st.info("No files have been staged through Data Hub in this session.")
        else:
            history_frame = pd.DataFrame(history).drop(columns=["Fingerprint"], errors="ignore")
            if "Size" in history_frame.columns:
                history_frame["Size"] = history_frame["Size"].map(
                    lambda value: f"{float(value) / 1024:,.0f} KB"
                )
            st.dataframe(history_frame, width="stretch", hide_index=True)
