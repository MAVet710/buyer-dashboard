"""Shared data intake workspace for retail and production operations."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
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
        ["Source Status", "Retail Ops Intake", "Production Ops Intake", "Import History"]
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
        st.markdown("### Retail Ops source intake")
        st.caption(
            "Files staged here are automatically reused by Buyer Operations. "
            "You do not need to upload them again in the sidebar."
        )
        left, right = st.columns(2)
        for index, spec in enumerate(RETAIL_DATASETS):
            with left if index % 2 == 0 else right:
                _render_upload_slot(spec)

        staged_retail = [
            spec for spec in RETAIL_DATASETS if st.session_state.get(spec["cache_key"])
        ]
        if staged_retail:
            st.success(
                f"{len(staged_retail)} retail source(s) staged. "
                "Open Buyer Operations to validate columns and refresh analytics."
            )
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

