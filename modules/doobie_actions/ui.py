"""Human approval queue for Doobie operational actions."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from modules.coman.db import create_coman_engine

from .service import DoobieActionService


def _actor() -> str:
    return str(st.session_state.get("admin_user") or st.session_state.get("user_user") or "system")


def render_doobie_action_center() -> None:
    org = str(st.session_state.get("active_organization_id") or "")
    facility = str(st.session_state.get("active_facility_id") or "")
    if not org or not facility:
        st.info("Select an organization and facility first.")
        return
    service = DoobieActionService(create_coman_engine())
    proposals = service.list_proposals(org, facility)
    st.markdown("## Doobie Actions")
    st.caption("Recommend → Preview → Human approves → deterministic service executes.")
    if not proposals:
        st.info("No operational actions are waiting for review.")
        return
    frame = pd.DataFrame([
        {
            "Action": p.title,
            "Type": p.action_type.replace("_", " ").title(),
            "Impact": float(p.financial_impact_usd or 0),
            "Risk": p.risk_level.title(),
            "Status": p.status.title(),
            "Source": p.source_type,
        }
        for p in proposals
    ])
    st.dataframe(frame, hide_index=True, width="stretch")
    labels = {f"${float(p.financial_impact_usd or 0):,.0f} · {p.title} · {p.status.title()}": p for p in proposals}
    proposal = labels[st.selectbox("Review action", list(labels), key="doobie_action_selected")]
    st.markdown(f"### {proposal.title}")
    st.write(proposal.rationale)
    preview = json.loads(proposal.preview_json or "{}")
    payload = json.loads(proposal.payload_json or "{}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Financial Impact", f"${float(proposal.financial_impact_usd or 0):,.2f}")
    c2.metric("Risk", proposal.risk_level.title())
    c3.metric("Status", proposal.status.title())
    with st.expander("Preview", expanded=True):
        st.json(preview)
    with st.expander("Deterministic payload", expanded=False):
        st.json(payload)
    if proposal.status in {"proposed","failed"}:
        a, b = st.columns(2)
        if a.button("Approve", type="primary", key=f"approve_action_{proposal.id}", use_container_width=True):
            service.approve(organization_id=org, facility_id=facility, proposal_id=proposal.id, actor=_actor())
            st.rerun()
        if b.button("Reject", key=f"reject_action_{proposal.id}", use_container_width=True):
            service.reject(organization_id=org, facility_id=facility, proposal_id=proposal.id, actor=_actor())
            st.rerun()
    elif proposal.status == "approved":
        st.warning("This will execute the exact approved preview through a deterministic service. No AI decides the mutation.")
        if st.button("Execute approved action", type="primary", key=f"execute_action_{proposal.id}", use_container_width=True):
            try:
                result = service.execute(organization_id=org, facility_id=facility, proposal_id=proposal.id, actor=_actor())
                st.success("Action executed.")
                st.json(result)
            except Exception as exc:
                st.error(str(exc))
            st.rerun()


def render_doobie_action_dialog() -> None:
    if hasattr(st, "dialog"):
        @st.dialog("Doobie Actions", width="large")
        def _dialog() -> None:
            render_doobie_action_center()
        _dialog()
    else:
        render_doobie_action_center()
