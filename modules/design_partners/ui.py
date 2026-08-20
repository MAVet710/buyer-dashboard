"""Admin-only pilot measurement and feedback cockpit."""

from __future__ import annotations

from datetime import date, timedelta
import json

import pandas as pd
import streamlit as st

from modules.coman.db import create_coman_engine

from .service import DEFAULT_SUCCESS_TARGETS, DesignPartnerService


METRICS = {
    "hours_saved_per_week": ("Hours saved / week", "hours", "higher"),
    "reconciliation_errors_avoided": ("Reconciliation errors avoided", "errors", "higher"),
    "inventory_accuracy_pct": ("Inventory accuracy", "%", "higher"),
    "cogs_coverage_pct": ("COGS coverage", "%", "higher"),
    "yield_improvement_pct": ("Yield improvement", "pct points", "higher"),
}


def _actor() -> str:
    return str(st.session_state.get("admin_user") or st.session_state.get("user_user") or "system")


def render_design_partner_cockpit() -> None:
    org = str(st.session_state.get("active_organization_id") or "")
    role = str(st.session_state.get("effective_role") or st.session_state.get("user_role") or "").casefold()
    if role not in {"admin","dev"}:
        st.warning("Design-partner administration is limited to admin/dev roles.")
        return
    if not org:
        st.info("Select an organization first.")
        return
    service = DesignPartnerService(create_coman_engine())
    snapshot = service.snapshot(org)
    account = snapshot["account"]
    st.markdown("## Design Partner Cockpit")
    st.caption("Measure whether the product actually saves time, reduces errors, improves economics, and earns a case study.")

    if account is None:
        st.info("This organization is not enrolled in the design-partner program.")
        champion = st.text_input("Operational champion", key="dp_champion")
        email = st.text_input("Champion email", key="dp_email")
        pain = st.text_area("Current pain / replacement stack", placeholder="Metrc + Distru + spreadsheets; duplicate inventory entry; weak extraction costing…", key="dp_pain")
        if st.button("Enroll as pilot", type="primary", key="dp_enroll", use_container_width=True):
            service.enroll(organization_id=org, actor=_actor(), champion_name=champion, champion_email=email, pain_profile=pain, success_targets=DEFAULT_SUCCESS_TARGETS, target_case_study_date=date.today() + timedelta(days=90))
            st.rerun()
        return

    readiness = snapshot["readiness"]
    top = st.columns(4)
    top[0].metric("Pilot Status", account.status.replace("_", " ").title())
    top[1].metric("Case Study Score", f"{readiness['score']}%")
    top[2].metric("Measured Wins", len(readiness["wins"]))
    top[3].metric("Open Feedback", sum(row.status == "open" for row in snapshot["feedback"]))
    if readiness["ready"]:
        st.success("This pilot has enough measured wins to start building a case study.")
    else:
        st.caption("Still needed: " + ", ".join(readiness["missing"]) if readiness["missing"] else "Keep measuring outcomes.")

    with st.popover("Pilot profile", use_container_width=True):
        status_options = ["prospect","pilot","live","case_study","graduated","churned"]
        status = st.selectbox("Status", status_options, index=status_options.index(account.status), key="dp_status")
        st.write(account.pain_profile or "No pain profile recorded.")
        st.json(json.loads(account.success_targets_json or "{}"), expanded=False)
        if st.button("Update status", type="primary", key="dp_status_save"):
            service.set_status(organization_id=org, status=status, actor=_actor())
            st.rerun()

    st.markdown("### Outcome scorecard")
    if snapshot["metrics"]:
        st.dataframe(pd.DataFrame([{
            "Metric": METRICS.get(row.metric_key, (row.metric_key,"","") )[0],
            "Baseline": row.baseline_value,
            "Current": row.current_value,
            "Unit": row.unit,
            "Evidence": row.evidence,
        } for row in snapshot["metrics"]]), hide_index=True, width="stretch")
    with st.popover("Record outcome", use_container_width=True):
        key = st.selectbox("Metric", list(METRICS), format_func=lambda value: METRICS[value][0], key="dp_metric_key")
        baseline = st.number_input("Baseline", value=0.0, key="dp_metric_baseline")
        current = st.number_input("Current", value=0.0, key="dp_metric_current")
        evidence = st.text_input("Evidence / source", placeholder="Inventory audit 8/20; payroll timing study; Extraction Run 360…", key="dp_metric_evidence")
        label, unit, direction = METRICS[key]
        if st.button("Save outcome", type="primary", key="dp_metric_save"):
            service.upsert_metric(organization_id=org, metric_key=key, baseline_value=baseline, current_value=current, unit=unit, actor=_actor(), direction=direction, evidence=evidence)
            st.rerun()

    st.markdown("### Product feedback")
    if snapshot["feedback"]:
        st.dataframe(pd.DataFrame([{"Area": row.area, "Severity": row.severity.title(), "Feedback": row.feedback, "Status": row.status.title(), "When": row.created_at} for row in snapshot["feedback"]]), hide_index=True, width="stretch")
    with st.popover("Capture feedback", use_container_width=True):
        area = st.selectbox("Area", ["Migration","Inventory","Production","Extraction","Wholesale","Finance","Doobie","UX","Reporting","Other"], key="dp_feedback_area")
        severity = st.selectbox("Severity", ["low","medium","high","critical"], index=1, key="dp_feedback_severity")
        feedback = st.text_area("Feedback", key="dp_feedback_text")
        if st.button("Add feedback", type="primary", key="dp_feedback_save"):
            service.add_feedback(organization_id=org, area=area, feedback=feedback, actor=_actor(), severity=severity)
            st.rerun()

    if readiness["wins"]:
        st.markdown("### Case-study proof")
        st.dataframe(pd.DataFrame(readiness["wins"]), hide_index=True, width="stretch")


def render_design_partner_dialog() -> None:
    if hasattr(st, "dialog"):
        @st.dialog("Design Partner Cockpit", width="large")
        def _dialog() -> None:
            render_design_partner_cockpit()
        _dialog()
    else:
        render_design_partner_cockpit()
