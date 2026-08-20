"""Backoffice traceability queue and reconciliation work window."""

from __future__ import annotations

import json
from typing import Any, MutableMapping

import pandas as pd
import streamlit as st

from modules.coman.db import ComanDatabaseConfigurationError, create_coman_engine
from .backoffice import MANUAL_TRACEABILITY_ROLES, TraceabilityBackofficeRepository


STATUS_LABELS = {
    "requested": "Requested",
    "validated": "Validated",
    "queued": "Queued",
    "submitted": "Submitted",
    "accepted": "Accepted",
    "rejected": "Rejected",
    "verified": "Verified",
    "reconciliation_required": "Reconciliation required",
    "cancelled": "Cancelled",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def can_manage_traceability(state: MutableMapping[str, Any]) -> bool:
    role = _clean(state.get("auth_user_role")).casefold()
    if not role and bool(state.get("is_admin")):
        role = "admin"
    return role in MANUAL_TRACEABILITY_ROLES


def _actor(state: MutableMapping[str, Any]) -> str:
    return _clean(
        state.get("display_user")
        or state.get("admin_user")
        or state.get("user_user")
        or state.get("auth_username")
        or state.get("auth_user_id")
        or "system"
    )


def transaction_rows(transactions) -> pd.DataFrame:
    rows = []
    for transaction in transactions:
        rows.append(
            {
                "ID": transaction.id,
                "Status": STATUS_LABELS.get(transaction.status, transaction.status),
                "Provider": str(transaction.provider or "").upper(),
                "Operation": transaction.operation_type,
                "Entity Type": transaction.entity_type,
                "Entity": transaction.entity_id,
                "External Ref": transaction.external_reference,
                "Attempts": int(transaction.attempt_count or 0),
                "Requested By": transaction.requested_by,
                "Requested At": transaction.requested_at,
                "Error": transaction.error_message or transaction.error_code,
            }
        )
    return pd.DataFrame(rows)


def _json_payload(raw: str) -> Any:
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {"raw": str(raw or "")}


def _repository_and_scope(state: MutableMapping[str, Any]):
    organization_id = _clean(state.get("active_organization_id"))
    facility_id = _clean(state.get("active_facility_id"))
    if not organization_id or not facility_id:
        raise ValueError("Choose an organization and facility before opening Traceability Operations.")
    return TraceabilityBackofficeRepository(create_coman_engine()), organization_id, facility_id


def _render_transaction_detail(
    state: MutableMapping[str, Any],
    repository: TraceabilityBackofficeRepository,
    organization_id: str,
    facility_id: str,
    transaction,
) -> None:
    st.markdown("### Transaction detail")
    top = st.columns(4)
    top[0].metric("Status", STATUS_LABELS.get(transaction.status, transaction.status))
    top[1].metric("Provider", str(transaction.provider or "").upper())
    top[2].metric("Attempts", int(transaction.attempt_count or 0))
    top[3].metric("Entity", transaction.entity_type)
    st.caption(
        f"{transaction.operation_type} · {transaction.entity_id} · requested by {transaction.requested_by}"
    )
    if transaction.external_reference:
        st.caption(f"External reference: {transaction.external_reference}")
    if transaction.error_message or transaction.error_code:
        st.error(transaction.error_message or transaction.error_code)

    overview_tab, attempts_tab, lifecycle_tab, payload_tab = st.tabs(
        ["Overview", "Attempts", "Lifecycle", "Payloads"]
    )
    with overview_tab:
        st.write(
            {
                "license": transaction.license_number,
                "reason": transaction.reason,
                "requested_at": str(transaction.requested_at),
                "submitted_at": str(transaction.submitted_at or ""),
                "completed_at": str(transaction.completed_at or ""),
                "next_attempt_at": str(transaction.next_attempt_at or ""),
                "idempotency_key": transaction.idempotency_key,
            }
        )
    with attempts_tab:
        attempts = repository.list_attempts(organization_id, facility_id, transaction.id)
        if not attempts:
            st.info("No provider submission attempts have been recorded yet.")
        else:
            attempt_rows = pd.DataFrame(
                [
                    {
                        "Attempt": attempt.attempt_number,
                        "HTTP": attempt.http_status,
                        "Error": attempt.error_message or attempt.error_code,
                        "Started": attempt.started_at,
                        "Completed": attempt.completed_at,
                    }
                    for attempt in attempts
                ]
            )
            st.dataframe(attempt_rows, width="stretch", hide_index=True)
    with lifecycle_tab:
        events = repository.list_status_events(organization_id, facility_id, transaction.id)
        if not events:
            st.info("No lifecycle transitions have been recorded for this transaction yet.")
        else:
            event_rows = pd.DataFrame(
                [
                    {
                        "From": STATUS_LABELS.get(event.from_status, event.from_status),
                        "To": STATUS_LABELS.get(event.to_status, event.to_status),
                        "Actor": event.actor,
                        "Reason": event.reason,
                        "Source": event.source,
                        "When": event.occurred_at,
                    }
                    for event in events
                ]
            )
            st.dataframe(event_rows, width="stretch", hide_index=True)
    with payload_tab:
        request_col, response_col = st.columns(2)
        with request_col:
            st.caption("SANITIZED REQUEST")
            st.json(_json_payload(transaction.request_payload_json))
        with response_col:
            st.caption("SANITIZED RESPONSE")
            st.json(_json_payload(transaction.response_payload_json))

    if not can_manage_traceability(state):
        st.info("Your role can review traceability state but cannot change queue or reconciliation status.")
        return

    allowed = {
        "requeue": transaction.status in {"rejected", "reconciliation_required"},
        "verify": transaction.status in {"accepted", "reconciliation_required"},
        "cancel": transaction.status not in {"verified", "cancelled"},
    }
    if not any(allowed.values()):
        return

    st.markdown("### Reconciliation action")
    reason = st.text_area(
        "Reason / reconciliation evidence *",
        key=f"traceability_reason_{transaction.id}",
        placeholder="Describe what was checked and why this lifecycle change is appropriate.",
    )
    confirmed = st.checkbox(
        "I reviewed the external state and understand this action is audit logged.",
        key=f"traceability_confirm_{transaction.id}",
    )
    action_cols = st.columns(3)

    def execute(action: str) -> None:
        clean_reason = _clean(reason)
        if not clean_reason or not confirmed:
            st.error("Enter a reason and confirm the review before changing traceability state.")
            return
        actor = _actor(state)
        if action == "requeue":
            repository.requeue_manual(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                actor=actor,
                reason=clean_reason,
            )
            st.success("Transaction returned to the traceability queue.")
        elif action == "verify":
            repository.verify_manual(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                actor=actor,
                reason=clean_reason,
            )
            st.success("Transaction marked verified with reconciliation evidence.")
        elif action == "cancel":
            repository.cancel_manual(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                actor=actor,
                reason=clean_reason,
            )
            st.success("Transaction cancelled with an audit reason.")
        st.rerun()

    if allowed["requeue"] and action_cols[0].button(
        "Requeue",
        key=f"traceability_requeue_{transaction.id}",
        width="stretch",
        type="primary",
    ):
        execute("requeue")
    if allowed["verify"] and action_cols[1].button(
        "Mark verified",
        key=f"traceability_verify_{transaction.id}",
        width="stretch",
    ):
        execute("verify")
    if allowed["cancel"] and action_cols[2].button(
        "Cancel action",
        key=f"traceability_cancel_{transaction.id}",
        width="stretch",
    ):
        execute("cancel")


def render_traceability_console(state: MutableMapping[str, Any]) -> None:
    st.caption("TRACEABILITY OPERATIONS · BACKOFFICE")
    st.markdown("## Queue & Reconciliation")
    st.caption(
        "Buyer Dash keeps the internal operational record visible even when the state system rejects, delays, or conflicts with an action."
    )

    try:
        repository, organization_id, facility_id = _repository_and_scope(state)
        summary = repository.summary(organization_id, facility_id)
    except ComanDatabaseConfigurationError:
        st.warning("The Backoffice database is not configured in this environment.")
        return
    except Exception as exc:
        message = str(exc)
        if "traceability" in message.casefold() or "does not exist" in message.casefold():
            st.warning("Traceability Operations requires database migration 0018_traceability_transactions.")
        else:
            st.warning(f"Traceability Operations is unavailable: {message}")
        return

    metrics = st.columns(4)
    metrics[0].metric("Needs reconciliation", summary.get("needs_reconciliation", 0))
    metrics[1].metric("In flight", summary.get("in_flight", 0))
    metrics[2].metric("Verified", summary.get("verified", 0))
    metrics[3].metric("Total actions", summary.get("total", 0))

    filter_col, provider_col = st.columns(2)
    status_filter = filter_col.selectbox(
        "Queue view",
        ["Needs reconciliation", "In flight", "All", "Verified", "Cancelled"],
        key="traceability_queue_view",
    )
    provider_filter = provider_col.selectbox(
        "Provider",
        ["All", "METRC", "BioTrack", "Other"],
        key="traceability_provider_filter",
    )
    status_map = {
        "Needs reconciliation": ("rejected", "reconciliation_required"),
        "In flight": ("requested", "validated", "queued", "submitted", "accepted"),
        "Verified": ("verified",),
        "Cancelled": ("cancelled",),
        "All": (),
    }
    provider = "" if provider_filter == "All" else provider_filter.casefold()
    transactions = repository.list_transactions(
        organization_id,
        facility_id,
        statuses=status_map[status_filter],
        provider=provider,
        limit=500,
    )
    frame = transaction_rows(transactions)
    if frame.empty:
        st.info("No traceability actions match this queue view.")
        return

    st.dataframe(
        frame.drop(columns=["ID"]),
        width="stretch",
        hide_index=True,
    )
    labels = {
        f"{row['Status']} · {row['Operation']} · {row['Entity']}": row["ID"]
        for _, row in frame.iterrows()
    }
    selected_label = st.selectbox(
        "Inspect transaction",
        list(labels.keys()),
        key="traceability_selected_transaction",
    )
    selected = repository.get_transaction(
        organization_id,
        facility_id,
        labels[selected_label],
    )
    _render_transaction_detail(
        state,
        repository,
        organization_id,
        facility_id,
        selected,
    )


def render_traceability_console_dialog(state: MutableMapping[str, Any]) -> None:
    if hasattr(st, "dialog"):
        @st.dialog("Traceability Operations", width="large")
        def _dialog() -> None:
            close_col, _ = st.columns([1, 5])
            if close_col.button("Close", key="traceability_console_close"):
                state["traceability_console_open"] = False
                st.rerun()
            render_traceability_console(state)

        _dialog()
    else:
        with st.container(border=True):
            render_traceability_console(state)
