"""Privacy-first facility and network benchmark UI."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from modules.coman.db import create_coman_engine

from .service import BenchmarkService


LABELS = {
    "extraction_yield_pct": "Extraction Yield",
    "extraction_cost_per_output": "Extraction Cost / Output",
    "extraction_cycle_hours": "Extraction Cycle Time",
    "extraction_solvent_recovery_pct": "Solvent Recovery",
    "production_attainment_pct": "Production Attainment",
    "production_cost_per_unit": "Production Cost / Unit",
    "sales_units_per_day": "Sales Units / Day",
    "sales_revenue_per_unit": "Sales Revenue / Unit",
}


def _actor() -> str:
    return str(st.session_state.get("admin_user") or st.session_state.get("user_user") or "system")


def render_benchmark_network() -> None:
    org = str(st.session_state.get("active_organization_id") or "")
    facility = str(st.session_state.get("active_facility_id") or "")
    if not org or not facility:
        st.info("Select an organization and facility first.")
        return
    service = BenchmarkService(create_coman_engine())
    setting = service.setting(org)
    opted_in = bool(getattr(setting, "share_anonymized_aggregates", False))
    minimum = int(getattr(setting, "minimum_cohort_size", 5) or 5)

    st.markdown("## Buyer Dash Benchmarks")
    st.caption("Your facility vs. its own history first; anonymous network comparisons unlock only from opted-in aggregate cohorts.")
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**Privacy contract**")
        st.caption("No product names, package tags, customers, source rows, or other company identities are stored in benchmark observations.")
    with c2.popover("Benchmark sharing", use_container_width=True):
        share = st.toggle("Share anonymized aggregates", value=opted_in, key="benchmark_opt_in")
        floor = st.number_input("Minimum organizations per cohort", min_value=3, max_value=50, value=minimum, step=1, key="benchmark_min_cohort")
        if st.button("Save privacy settings", type="primary", key="benchmark_save_settings", use_container_width=True):
            service.set_opt_in(organization_id=org, share=share, actor=_actor(), minimum_cohort_size=int(floor))
            st.rerun()

    if st.button("Refresh facility aggregates", type="primary", key="benchmark_capture", use_container_width=True):
        observations = service.capture_facility(organization_id=org, facility_id=facility, days=30)
        st.success(f"Captured {len(observations)} aggregate benchmark observation(s).")
        st.rerun()

    dashboard = service.facility_dashboard(org, facility)
    if not dashboard:
        st.info("No benchmark observations yet. Refresh facility aggregates after operational data is available.")
        return
    rows = []
    for item in dashboard:
        network = item["network"]
        rows.append({
            "Metric": LABELS.get(item["metric_key"], item["metric_key"].replace("_", " ").title()),
            "Cohort": item["cohort_key"],
            "Facility": item["value"],
            "Unit": item["unit"],
            "Samples": item["sample_count"],
            "Network Median": network.get("median") if network.get("available") else None,
            "Percentile": network.get("percentile") if network.get("available") else None,
            "Network": f"{network.get('cohort_organizations',0)} orgs" if network.get("available") else network.get("message", "Private / insufficient cohort"),
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    selected = st.selectbox("Explore benchmark", range(len(dashboard)), format_func=lambda i: f"{LABELS.get(dashboard[i]['metric_key'], dashboard[i]['metric_key'])} · {dashboard[i]['cohort_key']}", key="benchmark_selected")
    item = dashboard[int(selected)]
    network = item["network"]
    if network.get("available"):
        cols = st.columns(4)
        cols[0].metric("Facility", f"{item['value']:.2f}")
        cols[1].metric("Network Median", f"{float(network['median']):.2f}")
        cols[2].metric("Percentile", f"{float(network['percentile'] or 0):.0f}th")
        cols[3].metric("Opted-in Orgs", int(network["cohort_organizations"]))
        st.caption(f"Anonymous interquartile range: {float(network['p25']):.2f} – {float(network['p75']):.2f} {item['unit']}.")
    else:
        st.info(network.get("message") or "Network benchmark is not available yet.")


def render_benchmark_dialog() -> None:
    if hasattr(st, "dialog"):
        @st.dialog("Buyer Dash Benchmarks", width="large")
        def _dialog() -> None:
            render_benchmark_network()
        _dialog()
    else:
        render_benchmark_network()
