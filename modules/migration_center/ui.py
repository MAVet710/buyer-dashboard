"""Low-click Switch to Buyer Dash migration command center UI."""

from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
from typing import Any, MutableMapping

import pandas as pd
import streamlit as st

from modules.coman.db import create_coman_engine
from modules.product_master.resolver import search_product_master

from .service import MigrationCenterService, detect_source_system


ENTITY_LABELS = {
    "Product Catalog": "product",
    "Vendors": "vendor",
    "Inventory / Packages": "inventory",
    "Historical Sales": "sales",
}
SOURCE_LABELS = {
    "Auto-detect": "",
    "Dutchie": "dutchie",
    "Distru": "distru",
    "Metrc": "metrc",
    "Spreadsheet / Other": "spreadsheet",
}


def _scope(state: MutableMapping[str, Any]) -> tuple[str, str]:
    return str(state.get("active_organization_id") or "").strip(), str(state.get("active_facility_id") or "").strip()


def _actor(state: MutableMapping[str, Any]) -> str:
    return str(state.get("admin_user") or state.get("user_user") or state.get("auth_user_id") or "system")


def _read_upload(uploaded: Any) -> tuple[pd.DataFrame, bytes]:
    payload = bytes(uploaded.getvalue())
    suffix = Path(str(uploaded.name)).suffix.casefold()
    if suffix == ".csv":
        return pd.read_csv(BytesIO(payload)), payload
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(BytesIO(payload)), payload
    raise ValueError("Use CSV, XLSX, or XLS.")


def _batch_frame(batches) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Batch": row.id[:8],
            "Source": row.source_system.title(),
            "Entity": row.entity_type.title(),
            "File": row.filename,
            "Records": row.total_records,
            "Matched": row.matched_records,
            "Review": row.review_records,
            "Unmapped": row.unmapped_records,
            "Conflicts": row.conflict_records,
            "Committed": row.committed_records,
            "Status": row.status.title(),
            "batch_id": row.id,
        }
        for row in batches
    ])


def _record_frame(records) -> pd.DataFrame:
    rows = []
    for record in records:
        normalized = json.loads(record.normalized_json or "{}")
        label = normalized.get("name") or normalized.get("product_name") or normalized.get("package_id") or normalized.get("external_id") or f"Row {record.source_row_number}"
        rows.append({
            "Row": record.source_row_number,
            "Record": label,
            "Status": record.match_status.replace("_", " ").title(),
            "Confidence": round(float(record.confidence or 0) * 100),
            "Reason": record.match_reason,
            "Decision": record.decision_action.title(),
            "Canonical ID": record.canonical_entity_id,
            "record_id": record.id,
        })
    return pd.DataFrame(rows)


def _render_record_resolution(service: MigrationCenterService, state: MutableMapping[str, Any], organization_id: str, facility_id: str, record) -> None:
    normalized = json.loads(record.normalized_json or "{}")
    st.markdown(f"#### Resolve row {record.source_row_number}")
    st.json(normalized, expanded=False)
    if record.match_status == "auto_match":
        st.success(f"Deterministic match: {record.match_reason}")
        if st.button("Keep exact match", type="primary", key=f"mig_keep_{record.id}"):
            service.set_decision(organization_id=organization_id, facility_id=facility_id, record_id=record.id, action="accept", actor=_actor(state), canonical_entity_id=record.canonical_entity_id)
            st.rerun()
        return

    if record.entity_type == "vendor":
        c1, c2 = st.columns(2)
        if c1.button("Create new vendor", type="primary", key=f"mig_create_vendor_{record.id}"):
            service.set_decision(organization_id=organization_id, facility_id=facility_id, record_id=record.id, action="create", actor=_actor(state))
            st.rerun()
        if c2.button("Skip", key=f"mig_skip_vendor_{record.id}"):
            service.set_decision(organization_id=organization_id, facility_id=facility_id, record_id=record.id, action="skip", actor=_actor(state))
            st.rerun()
        return

    query = str(normalized.get("name") or normalized.get("product_name") or "").strip()
    candidates = search_product_master(service.engine, organization_id, query, limit=8) if query else []
    if candidates:
        labels = {f"{row.get('product_name','')} · {row.get('sku','')} · {row.get('brand','')}": row for row in candidates}
        chosen = st.selectbox("Link to existing Product Master item", list(labels), key=f"mig_candidate_{record.id}")
        if st.button("Link selected", type="primary", key=f"mig_link_{record.id}"):
            service.set_decision(organization_id=organization_id, facility_id=facility_id, record_id=record.id, action="link", actor=_actor(state), canonical_entity_id=str(labels[chosen].get("canonical_product_id") or ""))
            st.rerun()
    if record.entity_type == "product":
        c1, c2 = st.columns(2)
        if c1.button("Create canonical product", key=f"mig_create_product_{record.id}", use_container_width=True):
            service.set_decision(organization_id=organization_id, facility_id=facility_id, record_id=record.id, action="create", actor=_actor(state))
            st.rerun()
        if c2.button("Skip", key=f"mig_skip_product_{record.id}", use_container_width=True):
            service.set_decision(organization_id=organization_id, facility_id=facility_id, record_id=record.id, action="skip", actor=_actor(state))
            st.rerun()
    else:
        st.caption("Inventory and sales rows must link to a canonical Product Master item before cutover.")
        if st.button("Skip row", key=f"mig_skip_{record.id}"):
            service.set_decision(organization_id=organization_id, facility_id=facility_id, record_id=record.id, action="skip", actor=_actor(state))
            st.rerun()


def render_switch_center(state: MutableMapping[str, Any] | None = None) -> None:
    state = state or st.session_state
    organization_id, facility_id = _scope(state)
    st.markdown("## Switch to Buyer Dash")
    st.caption("Import the old system once. Buyer Dash reconciles exact matches automatically and makes you review only the ambiguous records.")
    if not organization_id or not facility_id:
        st.info("Select an organization and facility before starting a cutover.")
        return
    try:
        service = MigrationCenterService(create_coman_engine())
        batches = service.list_batches(organization_id, facility_id)
    except Exception as exc:
        st.error(f"Migration Command Center could not load: {exc}")
        return

    if batches:
        latest = batches[0]
        top = st.columns(5)
        top[0].metric("Imported", latest.total_records)
        top[1].metric("Exact Matches", latest.matched_records)
        top[2].metric("Needs Review", latest.review_records)
        top[3].metric("Unmapped", latest.unmapped_records)
        top[4].metric("Conflicts", latest.conflict_records)

    with st.expander("Start a new cutover import", expanded=not bool(batches)):
        c1, c2 = st.columns(2)
        entity_label = c1.selectbox("What are you importing?", list(ENTITY_LABELS), key="switch_entity")
        source_label = c2.selectbox("Source system", list(SOURCE_LABELS), key="switch_source")
        uploaded = st.file_uploader("Export file", type=["csv", "xlsx", "xls"], key="switch_upload")
        if uploaded is not None:
            try:
                frame, payload = _read_upload(uploaded)
                detected = detect_source_system(frame.columns)
                st.caption(f"Detected source: {detected.title()} · {len(frame):,} rows · {len(frame.columns):,} columns")
                st.dataframe(frame.head(8), width="stretch", hide_index=True)
                if st.button("Stage + reconcile", type="primary", key="switch_stage", use_container_width=True):
                    batch = service.stage_dataframe(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        frame=frame,
                        entity_type=ENTITY_LABELS[entity_label],
                        actor=_actor(state),
                        source_system=SOURCE_LABELS[source_label],
                        filename=str(uploaded.name),
                        fingerprint=hashlib.sha256(payload).hexdigest(),
                    )
                    state["switch_selected_batch_id"] = batch.id
                    st.rerun()
            except Exception as exc:
                st.error(str(exc))

    if not batches:
        return
    st.markdown("### Cutover batches")
    batch_frame = _batch_frame(batches)
    st.dataframe(batch_frame.drop(columns=["batch_id"]), width="stretch", hide_index=True)
    selected_id = str(state.get("switch_selected_batch_id") or batches[0].id)
    batch_by_id = {row.id: row for row in batches}
    if selected_id not in batch_by_id:
        selected_id = batches[0].id
    batch = batch_by_id[selected_id]

    with st.expander(f"Review {batch.filename or batch.id[:8]}", expanded=batch.status != "committed"):
        records = service.records(organization_id, facility_id, batch.id)
        frame = _record_frame(records)
        st.dataframe(frame.drop(columns=["record_id"]), width="stretch", hide_index=True)
        unresolved = [row for row in records if row.decision_action == "pending" and row.match_status not in {"committed", "skipped"}]
        if unresolved:
            labels = {f"Row {row.source_row_number} · {json.loads(row.normalized_json or '{}').get('name') or json.loads(row.normalized_json or '{}').get('product_name') or row.match_status}": row for row in unresolved}
            chosen = st.selectbox("Resolve record", list(labels), key=f"switch_resolve_{batch.id}")
            _render_record_resolution(service, state, organization_id, facility_id, labels[chosen])
        else:
            st.success("Every record has a decision. This batch is ready to commit.")
        if st.button("Commit reviewed cutover", type="primary", key=f"switch_commit_{batch.id}", disabled=bool(unresolved), use_container_width=True):
            result = service.commit_batch(organization_id=organization_id, facility_id=facility_id, batch_id=batch.id, actor=_actor(state))
            if result["blocked"]:
                st.warning(f"{result['blocked']} row(s) are still blocked. Nothing ambiguous was guessed.")
            else:
                st.success(f"Committed {result['committed']} record(s); skipped {result['skipped']}.")
            st.rerun()


def render_switch_center_dialog(state: MutableMapping[str, Any] | None = None) -> None:
    state = state or st.session_state
    if hasattr(st, "dialog"):
        @st.dialog("Switch to Buyer Dash", width="large")
        def _dialog() -> None:
            render_switch_center(state)
        _dialog()
    else:
        render_switch_center(state)
