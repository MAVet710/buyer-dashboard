"""Shared data intake workspace for retail and production operations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
from pathlib import Path
import re
from typing import Any, Mapping, MutableMapping

import pandas as pd
import streamlit as st

from extraction_partner_upload_upgrade import render_extraction_partner_upload_ui
from modules.coman.db import create_coman_engine
from modules.data_hub_repository import DataHubRepository, hydrate_durable_sources
from services.data_mapping_agent import suggest_column_mapping


MAX_UPLOAD_BYTES = 10 * 1024 * 1024

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
    "Product Sales": {
        "Product": "Product Name",
        "Units sold": "Quantity Sold",
        "Category": "Category",
    },
    "Sales / Pricing Detail": {"Product": "Product Name", "Revenue": "Net Sales"},
    "Quarantine": {"Product": "Product Name"},
}

RETAIL_CACHE_KEYS = tuple(str(spec["cache_key"]) for spec in RETAIL_DATASETS)


@st.cache_resource
def get_data_hub_repository() -> DataHubRepository:
    """Reuse one pooled database engine for Data Hub operations."""

    return DataHubRepository(create_coman_engine())


def restore_durable_retail_sources(
    state: MutableMapping[str, Any], *, force: bool = False
) -> tuple[int, str]:
    """Hydrate the selected tenant's active files without blocking the app."""

    organization_id = str(state.get("active_organization_id") or "").strip()
    facility_id = str(state.get("active_facility_id") or "").strip()
    if not organization_id or not facility_id:
        return 0, ""
    scope = f"{organization_id}|{facility_id}"
    if state.get("_durable_data_hub_scope") != scope:
        for cache_key in RETAIL_CACHE_KEYS:
            state.pop(cache_key, None)
        state["_durable_data_hub_scope"] = scope
        state.pop("_durable_data_hub_restored_scope", None)
    retry_after_raw = str(state.get("_durable_data_hub_retry_after") or "")
    if retry_after_raw and not force:
        try:
            if datetime.fromisoformat(retry_after_raw) > datetime.now(timezone.utc):
                return 0, str(
                    state.get("_durable_data_hub_error")
                    or "Durable data storage is temporarily unavailable."
                )
        except ValueError:
            state.pop("_durable_data_hub_retry_after", None)
    if not force and state.get("_durable_data_hub_restored_scope") == scope:
        return sum(
            bool(isinstance(state.get(key), dict) and state[key].get("durable"))
            for key in RETAIL_CACHE_KEYS
        ), ""
    try:
        restored = hydrate_durable_sources(
            state,
            get_data_hub_repository(),
            organization_id=organization_id,
            facility_id=facility_id,
            cache_keys=RETAIL_CACHE_KEYS,
        )
        state.pop("_durable_data_hub_error", None)
        state.pop("_durable_data_hub_retry_after", None)
        return restored, ""
    except Exception as exc:
        # Session uploads remain usable while a migration or connection is unavailable.
        message = str(exc).strip() or "Durable data storage is unavailable."
        state["_durable_data_hub_error"] = message
        state["_durable_data_hub_retry_after"] = (
            datetime.now(timezone.utc) + timedelta(seconds=60)
        ).isoformat()
        return 0, message


def _publish_durable_source(
    spec: Mapping[str, Any], staged: dict[str, Any], inspection: Mapping[str, Any]
) -> None:
    organization_id = str(st.session_state.get("active_organization_id") or "").strip()
    facility_id = str(st.session_state.get("active_facility_id") or "").strip()
    if not organization_id or not facility_id:
        raise ValueError("Select an organization and facility before publishing data.")
    actor = str(
        st.session_state.get("admin_user")
        or st.session_state.get("user_user")
        or "system"
    )
    try:
        record = get_data_hub_repository().publish_source(
            organization_id=organization_id,
            facility_id=facility_id,
            dataset_key=str(spec["dataset_key"]),
            dataset_label=str(spec["label"]),
            cache_key=str(spec["cache_key"]),
            filename=str(staged["name"]),
            fingerprint=str(staged["fingerprint"]),
            payload=bytes(staged["bytes"]),
            inspection=inspection,
            content_type=str(staged.get("content_type") or ""),
            imported_by_user_id=st.session_state.get("auth_user_id"),
            imported_by=actor,
        )
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "Supabase could not save this source. Verify the Data Hub migration and database connection."
        ) from exc
    staged["durable_id"] = record.id
    staged["durable"] = True
    st.session_state[spec["cache_key"]] = staged
    st.session_state["_durable_data_hub_restored_scope"] = (
        f"{organization_id}|{facility_id}"
    )


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


class _MappedUpload(BytesIO):
    pass


def build_mapped_upload(
    uploaded_file: Any,
    dataset_label: str,
    matches: Mapping[str, str],
) -> Any:
    """Return a reviewed source rewritten to canonical Buyer Dashboard headers."""
    requirements = DATASET_REQUIREMENTS.get(dataset_label, {})
    canonical = CANONICAL_COLUMN_NAMES.get(dataset_label, {})
    missing = [field for field in requirements if not str(matches.get(field) or "").strip()]
    if missing:
        raise ValueError("Required mapping is unresolved: " + ", ".join(missing))

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
    invalid = [
        f"{field} -> {source}"
        for field, source in matches.items()
        if field in requirements and str(source) not in columns
    ]
    if invalid:
        raise ValueError("Mapped source column no longer exists: " + ", ".join(invalid))

    selected_sources = {str(source) for source in matches.values() if source}
    rename: dict[str, str] = {}
    for field, source in matches.items():
        if field not in canonical:
            continue
        source = str(source)
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
        "content_type": str(getattr(uploaded_file, "type", "") or ""),
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
        storage_note = " · saved to Supabase" if cached.get("durable") else " · session only"
        st.success(f"Current source: {cached.get('name', selected_label)}{storage_note}")

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

    requirements = DATASET_REQUIREMENTS.get(selected_label, {})
    source_columns = list(dict.fromkeys(str(column) for column in inspection["preview"].columns))
    file_token = hashlib.sha256(_file_bytes(uploaded)).hexdigest()[:12]
    agent_state_key = f"data_hub_mapping_agent_{spec['dataset_key']}_{file_token}"
    agent_result = st.session_state.get(agent_state_key)

    if inspection["missing"]:
        st.warning(
            "These required fields were not detected automatically: "
            + ", ".join(inspection["missing"])
            + ". Use the Mapping Agent or choose the source columns manually before publishing."
        )
        if st.button(
            "Ask Mapping Agent",
            key=f"ask_mapping_agent_{spec['dataset_key']}_{file_token}",
            type="secondary",
        ):
            agent_result = suggest_column_mapping(
                source_columns,
                requirements,
                existing_matches=inspection["matches"],
                dataset_label=selected_label,
            )
            st.session_state[agent_state_key] = agent_result
            for proposal in agent_result.get("proposals", []):
                field = str(proposal.get("required_field") or "")
                source = str(proposal.get("source_column") or "")
                selector_key = (
                    f"data_hub_map_{spec['dataset_key']}_{file_token}_{_normalize_column(field).replace(' ', '_')}"
                )
                if field in requirements and source in source_columns:
                    st.session_state[selector_key] = source

    agent_by_field: dict[str, dict[str, Any]] = {}
    if isinstance(agent_result, dict):
        proposals = [dict(row) for row in agent_result.get("proposals", []) if isinstance(row, dict)]
        agent_by_field = {str(row.get("required_field") or ""): row for row in proposals}
        if proposals:
            st.markdown("##### Mapping Agent suggestions")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Required field": row.get("required_field", ""),
                            "Suggested column": row.get("source_column", ""),
                            "Confidence": row.get("confidence", ""),
                            "Why": row.get("reason", ""),
                        }
                        for row in proposals
                    ]
                ),
                width="stretch",
                hide_index=True,
            )
        st.caption(
            str(
                agent_result.get("privacy_note")
                or "The mapping assistant evaluates headers only; row values are not sent to Gemini."
            )
        )

    st.markdown("##### Confirm column mapping")
    confirmed_matches: dict[str, str] = {}
    for purpose in requirements:
        options = ["Not mapped", *source_columns]
        suggested = str(
            inspection["matches"].get(purpose)
            or agent_by_field.get(purpose, {}).get("source_column")
            or "Not mapped"
        )
        selector_key = (
            f"data_hub_map_{spec['dataset_key']}_{file_token}_{_normalize_column(purpose).replace(' ', '_')}"
        )
        if selector_key not in st.session_state:
            st.session_state[selector_key] = suggested if suggested in options else "Not mapped"
        selected = st.selectbox(
            purpose,
            options,
            key=selector_key,
            help="Choose the source column that represents this required Buyer Dashboard field.",
        )
        if selected != "Not mapped":
            confirmed_matches[purpose] = selected

    duplicate_mapping = len(set(confirmed_matches.values())) != len(confirmed_matches)
    inspection["matches"] = confirmed_matches
    inspection["missing"] = [purpose for purpose in requirements if purpose not in confirmed_matches]
    inspection["quality"] = "Ready" if not inspection["missing"] and not duplicate_mapping else "Review mapping"
    inspection["mapping_provider"] = (
        str(agent_result.get("provider") or "manual") if isinstance(agent_result, dict) else "manual"
    )
    if duplicate_mapping:
        st.error("One source column is assigned to more than one required field. Choose a unique column for each field.")
    elif not inspection["missing"]:
        st.success("Required fields are mapped and ready to normalize for Buyer Dashboard.")

    with st.expander("Preview first 8 rows", expanded=bool(inspection["missing"])):
        st.dataframe(inspection["preview"], width="stretch", hide_index=True)

    confirmed = st.checkbox(
        "I reviewed the source and want it available to Retail Operations.",
        key=f"confirm_{spec['widget_key']}",
    )
    publish_label = "Replace current source" if cached else "Publish source"
    if st.button(
        f"4. {publish_label}",
        type="primary",
        disabled=not confirmed or bool(inspection["missing"]) or duplicate_mapping,
        key=f"publish_{spec['widget_key']}",
    ):
        try:
            mapped_upload = build_mapped_upload(
                uploaded,
                selected_label,
                inspection["matches"],
            )
            staged = stage_uploaded_dataset(
                st.session_state,
                mapped_upload,
                cache_key=spec["cache_key"],
                dataset_label=selected_label,
            )
            staged["source_name"] = inspection["name"]
            staged["column_mapping"] = dict(inspection["matches"])
            staged["mapping_provider"] = inspection.get("mapping_provider", "manual")
            _publish_durable_source(spec, staged, inspection)
            st.success(
                f"{staged['name']} is saved to Supabase and available across Retail Operations."
            )
        except Exception as exc:
            st.error(f"{selected_label} could not be published: {exc}")


def render_data_hub_workspace() -> None:
    """Render the shared Connect / Upload / Review / Publish intake experience."""
    st.markdown("## Data Hub")
    st.caption(
        "Load operational data once, verify its status, and reuse it across Retail Ops "
        "and Production Ops. Existing workspace-specific uploaders remain available."
    )

    _, durable_error = restore_durable_retail_sources(st.session_state)
    if durable_error:
        st.warning(
            "Durable source storage is temporarily unavailable. You can still review files "
            "in this session, but publishing requires the Data Hub database migration."
        )
    elif not (
        st.session_state.get("active_organization_id")
        and st.session_state.get("active_facility_id")
    ):
        st.info("Select an organization and facility to publish reusable retail sources.")

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
                "Clear files from this session",
                key="data_hub_clear_retail",
                type="secondary",
            ):
                for spec in RETAIL_DATASETS:
                    st.session_state.pop(spec["cache_key"], None)
                st.success("Session copies cleared. Published Supabase sources remain available.")
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
        durable_history: list[dict[str, Any]] = []
        organization_id = str(st.session_state.get("active_organization_id") or "")
        facility_id = str(st.session_state.get("active_facility_id") or "")
        if organization_id and facility_id and not durable_error:
            try:
                durable_history = [
                    {
                        "Dataset": row.dataset_label,
                        "File": row.filename,
                        "Size": row.payload_size,
                        "Status": row.status.title(),
                        "Imported At": row.activated_at,
                        "Imported By": row.imported_by,
                        "Rows": row.row_count,
                    }
                    for row in get_data_hub_repository().list_history(
                        organization_id, facility_id
                    )
                ]
            except Exception:
                durable_history = []
        history = durable_history or list(st.session_state.get("data_hub_import_history", []))
        if not history:
            st.info("No sources have been published for this facility yet.")
        else:
            history_frame = pd.DataFrame(history).drop(columns=["Fingerprint"], errors="ignore")
            if "Size" in history_frame.columns:
                history_frame["Size"] = history_frame["Size"].map(
                    lambda value: f"{float(value) / 1024:,.0f} KB"
                )
            st.dataframe(history_frame, width="stretch", hide_index=True)
