import pandas as pd
import plotly.express as px
import streamlit as st

from core.session_keys import EXTRACTION_JOBS, EXTRACTION_RUNS
from doobie_panels import run_extraction_doobie
from ui.components import render_metric_card, render_section_header
from ui_polish import chart_card_end, chart_card_start

METHOD_OPTIONS = ["All", "BHO", "CO2", "Rosin", "Ethanol"]
ENTRY_METHOD_OPTIONS = ["BHO", "CO2", "Rosin", "Ethanol"]
PRODUCT_TYPE_OPTIONS = [
    "Sugar",
    "Badder / Batter",
    "Shatter",
    "Sauce",
    "Diamonds (THCa Diamonds)",
    "Live Resin",
    "Live Rosin",
    "Cured Resin",
    "Fresh Press (Rosin)",
    "Rosin Jam",
    "Hash Rosin",
    "Bubble Hash / Ice Water Hash",
    "Dry Sift / Kief",
    "Distillate",
    "Crude Oil",
    "RSO (Rick Simpson Oil)",
    "Tincture",
    "Wax",
    "Crumble",
    "Pull-and-Snap",
    "Terp Sauce",
    "HTFSE (High Terpene Full Spectrum Extract)",
    "HCFSE (High Cannabinoid Full Spectrum Extract)",
    "THCa Isolate",
    "CBD Isolate",
    "Full Spectrum Oil",
    "Broad Spectrum Oil",
    "Caviar / Moon Rocks",
    "Infused Pre-Roll (concentrate output)",
    "Vape Cart Oil",
    "Dab-ready Concentrate",
    "Other",
]


def _ensure_defaults():
    if EXTRACTION_RUNS not in st.session_state:
        st.session_state[EXTRACTION_RUNS] = pd.DataFrame(
            [
                {
                    "run_date": "2026-03-27",
                    "state": "MA",
                    "license_name": "Example Lab",
                    "client_name": "In House",
                    "batch_id_internal": "BHO-0001",
                    "metrc_package_id_input": "1A4060300000000000001111",
                    "metrc_package_id_output": "1A4060300000000000002222",
                    "metrc_manifest_or_transfer_id": "TR-001",
                    "method": "BHO",
                    "strain": "The 4th Kind",
                    "product_type": "Sugar",
                    "input_material_type": "Fresh Frozen",
                    "input_weight_g": 2500.0,
                    "intermediate_output_g": 480.0,
                    "finished_output_g": 430.0,
                    "residual_loss_g": 50.0,
                    "yield_pct": 17.2,
                    "post_process_efficiency_pct": 89.6,
                    "solvent_recovery_pct": 92.0,
                    "cycle_time_hours": 6.5,
                    "operator": "Operator A",
                    "machine_line": "BHO-1",
                    "status": "Complete",
                    "toll_processing": False,
                    "processing_fee_usd": 0.0,
                    "est_revenue_usd": 3440.0,
                    "cogs_usd": 1200.0,
                    "coa_status": "Passed",
                    "qa_hold": False,
                    "notes": "Sample seed record",
                },
                {
                    "run_date": "2026-03-28",
                    "state": "MA",
                    "license_name": "Example Lab",
                    "client_name": "In House",
                    "batch_id_internal": "ETH-0001",
                    "metrc_package_id_input": "1A4060300000000000003333",
                    "metrc_package_id_output": "1A4060300000000000004444",
                    "metrc_manifest_or_transfer_id": "TR-002",
                    "method": "Ethanol",
                    "strain": "Night Tonic",
                    "product_type": "Crude",
                    "input_material_type": "Cured Biomass",
                    "input_weight_g": 5000.0,
                    "intermediate_output_g": 900.0,
                    "finished_output_g": 780.0,
                    "residual_loss_g": 120.0,
                    "yield_pct": 15.6,
                    "post_process_efficiency_pct": 86.7,
                    "solvent_recovery_pct": 88.0,
                    "cycle_time_hours": 8.0,
                    "operator": "Operator B",
                    "machine_line": "ETH-1",
                    "status": "Complete",
                    "toll_processing": False,
                    "processing_fee_usd": 0.0,
                    "est_revenue_usd": 4680.0,
                    "cogs_usd": 1900.0,
                    "coa_status": "Passed",
                    "qa_hold": False,
                    "notes": "Seed ethanol record",
                },
            ]
        )
    if EXTRACTION_JOBS not in st.session_state:
        st.session_state[EXTRACTION_JOBS] = pd.DataFrame(
            [
                {
                    "client_name": "North Shore Processing",
                    "state": "MA",
                    "license_or_registration": "LIC-001",
                    "metrc_transfer_id": "TR-001",
                    "material_received_date": "2026-03-25",
                    "promised_completion_date": "2026-03-30",
                    "method": "BHO",
                    "strain": "The 4th Kind",
                    "input_weight_g": 2500.0,
                    "expected_output_g": 450.0,
                    "actual_output_g": 430.0,
                    "sla_status": "On Track",
                    "invoice_status": "Draft",
                    "payment_status": "Pending",
                    "coa_status": "Passed",
                    "job_status": "Processing",
                }
            ]
        )


def _compute_alerts(run_df: pd.DataFrame, job_df: pd.DataFrame):
    alerts = []
    if run_df is not None and not run_df.empty:
        if "yield_pct" in run_df.columns:
            low_yield = run_df[pd.to_numeric(run_df["yield_pct"], errors="coerce").fillna(0) < 12]
            if not low_yield.empty:
                alerts.append(f"Low yield runs: {len(low_yield)} below 12% yield.")
        if "qa_hold" in run_df.columns:
            qa_holds = int(run_df["qa_hold"].fillna(False).sum())
            if qa_holds > 0:
                alerts.append(f"QA holds active: {qa_holds} run(s).")
        if "coa_status" in run_df.columns:
            pending_or_failed = int(run_df["coa_status"].isin(["Pending", "Failed"]).sum())
            if pending_or_failed > 0:
                alerts.append(f"COA risk: {pending_or_failed} run(s) pending/failed.")
        gross_rev = float(pd.to_numeric(run_df.get("est_revenue_usd", 0), errors="coerce").fillna(0).sum())
        gross_cogs = float(pd.to_numeric(run_df.get("cogs_usd", 0), errors="coerce").fillna(0).sum())
        gm = ((gross_rev - gross_cogs) / gross_rev * 100) if gross_rev else 0
        if gross_rev and gm < 35:
            alerts.append("Gross margin is compressed below 35%. Review process losses, fees, and yield.")
        if "solvent_recovery_pct" in run_df.columns:
            low_recovery = run_df[pd.to_numeric(run_df["solvent_recovery_pct"], errors="coerce").fillna(0) < 85]
            if not low_recovery.empty:
                alerts.append(f"Low solvent recovery detected on {len(low_recovery)} run(s).")
        if "cycle_time_hours" in run_df.columns:
            long_cycles = run_df[pd.to_numeric(run_df["cycle_time_hours"], errors="coerce").fillna(0) > 10]
            if not long_cycles.empty:
                alerts.append(f"Long cycle times detected on {len(long_cycles)} run(s) over 10 hours.")
    if job_df is not None and not job_df.empty:
        if "sla_status" in job_df.columns:
            at_risk_jobs = int((job_df["sla_status"] == "At Risk").sum())
            if at_risk_jobs > 0:
                alerts.append(f"Toll jobs at SLA risk: {at_risk_jobs}.")
        if "invoice_status" in job_df.columns:
            overdue = int((job_df["invoice_status"] == "Overdue").sum())
            if overdue > 0:
                alerts.append(f"Overdue toll invoices: {overdue}.")
    return alerts


def _filtered_frames(
    run_df: pd.DataFrame,
    job_df: pd.DataFrame,
    selected_state: str,
    selected_method: str,
    toll_only: bool,
    selected_strain: str = "All",
):
    rf = run_df.copy()
    jf = job_df.copy()
    if selected_state != "All":
        if "state" in rf.columns:
            rf = rf[rf["state"] == selected_state]
        if "state" in jf.columns:
            jf = jf[jf["state"] == selected_state]
    if selected_method != "All":
        if "method" in rf.columns:
            rf = rf[rf["method"] == selected_method]
        if "method" in jf.columns:
            jf = jf[jf["method"] == selected_method]
    if selected_strain != "All":
        if "strain" in rf.columns:
            rf = rf[rf["strain"] == selected_strain]
        if "strain" in jf.columns:
            jf = jf[jf["strain"] == selected_strain]
    if toll_only and "toll_processing" in rf.columns:
        rf = rf[rf["toll_processing"] == True]
    return rf, jf


def _method_efficiency_summary(run_df: pd.DataFrame) -> pd.DataFrame:
    if run_df is None or run_df.empty:
        return pd.DataFrame()
    cols = [c for c in ["yield_pct", "post_process_efficiency_pct", "solvent_recovery_pct", "cycle_time_hours", "finished_output_g", "input_weight_g", "est_revenue_usd", "cogs_usd"] if c in run_df.columns]
    if "method" not in run_df.columns:
        return pd.DataFrame()
    summary = run_df.groupby("method", dropna=False)[cols].mean(numeric_only=True).reset_index()
    if "est_revenue_usd" in run_df.columns and "cogs_usd" in run_df.columns:
        rev = run_df.groupby("method", dropna=False)["est_revenue_usd"].sum().reset_index(name="total_revenue_usd")
        cogs = run_df.groupby("method", dropna=False)["cogs_usd"].sum().reset_index(name="total_cogs_usd")
        summary = summary.merge(rev, on="method", how="left").merge(cogs, on="method", how="left")
        summary["gross_margin_pct"] = summary.apply(lambda r: ((r["total_revenue_usd"] - r["total_cogs_usd"]) / r["total_revenue_usd"] * 100) if r.get("total_revenue_usd", 0) else 0, axis=1)
    return summary


def _variance_summary(run_df: pd.DataFrame) -> pd.DataFrame:
    if run_df is None or run_df.empty or "method" not in run_df.columns:
        return pd.DataFrame()
    frames = []
    for metric in ["yield_pct", "post_process_efficiency_pct", "solvent_recovery_pct", "cycle_time_hours"]:
        if metric in run_df.columns:
            grp = run_df.groupby("method", dropna=False)[metric].agg(["mean", "std", "min", "max"]).reset_index()
            grp["metric"] = metric
            frames.append(grp)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def render_extraction_perfect_view_v2():
    _ensure_defaults()
    render_section_header(
        "Extraction Command Center",
        "Parity-focused extraction workspace with method-level efficiency tracking, variance analytics, compliance/METRC, toll processing, and Doobie ops briefing.",
    )

    if "ecc_selected_state_v2" not in st.session_state:
        st.session_state["ecc_selected_state_v2"] = "All"
    if "ecc_selected_method_v2" not in st.session_state:
        st.session_state["ecc_selected_method_v2"] = "All"
    if "ecc_toll_only_v2" not in st.session_state:
        st.session_state["ecc_toll_only_v2"] = False
    if "ecc_selected_strain_v2" not in st.session_state:
        st.session_state["ecc_selected_strain_v2"] = "All"

    run_df_all = st.session_state[EXTRACTION_RUNS].copy()
    job_df_all = st.session_state[EXTRACTION_JOBS].copy()
    strain_values = (
        run_df_all.get("strain", pd.Series(dtype=str))
        .fillna("")
        .astype(str)
        .str.strip()
    )
    strain_options = ["All"] + sorted([value for value in strain_values.unique().tolist() if value])

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        selected_state = st.selectbox("State", ["All", "MA", "ME", "NY", "NJ", "MI", "NV", "CA", "Other"], key="ecc_selected_state_v2")
    with s2:
        selected_method = st.selectbox("Extraction Method", METHOD_OPTIONS, key="ecc_selected_method_v2")
    with s3:
        toll_only = st.toggle("Show Toll Processing Only", value=st.session_state["ecc_toll_only_v2"], key="ecc_toll_only_v2")
    with s4:
        selected_strain = st.selectbox("Strain", strain_options, key="ecc_selected_strain_v2")

    run_df, job_df = _filtered_frames(
        run_df_all,
        job_df_all,
        selected_state,
        selected_method,
        toll_only,
        selected_strain,
    )

    total_runs = len(run_df)
    total_finished_output = float(pd.to_numeric(run_df.get("finished_output_g", 0), errors="coerce").fillna(0).sum()) if not run_df.empty else 0.0
    avg_yield = float(pd.to_numeric(run_df.get("yield_pct", 0), errors="coerce").fillna(0).mean()) if not run_df.empty else 0.0
    avg_post_eff = float(pd.to_numeric(run_df.get("post_process_efficiency_pct", 0), errors="coerce").fillna(0).mean()) if not run_df.empty else 0.0
    avg_solvent_recovery = float(pd.to_numeric(run_df.get("solvent_recovery_pct", 0), errors="coerce").fillna(0).mean()) if not run_df.empty else 0.0
    avg_cycle_time = float(pd.to_numeric(run_df.get("cycle_time_hours", 0), errors="coerce").fillna(0).mean()) if not run_df.empty else 0.0
    at_risk_batches = int(((run_df.get("qa_hold", pd.Series(dtype=bool)).fillna(False)) | (run_df.get("coa_status", pd.Series(dtype=str)).isin(["Failed", "Pending"]))).sum()) if not run_df.empty else 0
    est_revenue = float(pd.to_numeric(run_df.get("est_revenue_usd", 0), errors="coerce").fillna(0).sum()) if not run_df.empty else 0.0
    cogs = float(pd.to_numeric(run_df.get("cogs_usd", 0), errors="coerce").fillna(0).sum()) if not run_df.empty else 0.0
    gross_margin_pct = ((est_revenue - cogs) / est_revenue * 100) if est_revenue else 0.0

    top = st.columns(8)
    with top[0]:
        render_metric_card("Runs", f"{total_runs:,}")
    with top[1]:
        render_metric_card("Finished Output", f"{total_finished_output:,.1f} g")
    with top[2]:
        render_metric_card("Avg Yield", f"{avg_yield:.1f}%")
    with top[3]:
        render_metric_card("Post-Process Eff.", f"{avg_post_eff:.1f}%")
    with top[4]:
        render_metric_card("Solvent Recovery", f"{avg_solvent_recovery:.1f}%")
    with top[5]:
        render_metric_card("Avg Cycle Time", f"{avg_cycle_time:.1f} hr")
    with top[6]:
        render_metric_card("At-Risk Batches", f"{at_risk_batches:,}")
    with top[7]:
        render_metric_card("Gross Margin", f"{gross_margin_pct:.1f}%")

    overview_tab, method_tab, runs_tab, toll_tab, compliance_tab, inputs_tab, ai_ops_tab = st.tabs([
        "Executive Overview",
        "Method Efficiency",
        "Run Analytics",
        "Toll Processing",
        "Compliance / METRC",
        "Data Input",
        "Doobie Ops Brief",
    ])

    with overview_tab:
        c1, c2 = st.columns([1.2, 1])
        with c1:
            chart_card_start("Output by Method", "Total finished output by extraction method")
            if run_df.empty or "method" not in run_df.columns:
                st.info("No data yet.")
            else:
                method_summary = run_df.groupby("method", as_index=False)[["finished_output_g", "input_weight_g"]].sum().sort_values("finished_output_g", ascending=False)
                fig_method = px.bar(
                    method_summary,
                    x="method",
                    y="finished_output_g",
                    color="method",
                )
                fig_method.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                    font=dict(color="rgba(255,255,255,0.86)"),
                )
                st.plotly_chart(fig_method, use_container_width=True)
            chart_card_end()
        with c2:
            st.markdown("### Smart Flags")
            alerts = _compute_alerts(run_df, job_df)
            if not alerts:
                st.success("No major automated flags from the current filtered view.")
            else:
                for flag in alerts:
                    st.warning(flag)
        sc1, sc2 = st.columns(2)
        with sc1:
            chart_card_start("Yield by Strain", "Average yield percentage by strain")
            if run_df.empty or "strain" not in run_df.columns or "yield_pct" not in run_df.columns:
                st.info("No strain yield data yet.")
            else:
                yield_by_strain = (
                    run_df.assign(strain=run_df["strain"].fillna("").astype(str).str.strip())
                    .query("strain != ''")
                    .groupby("strain", as_index=False)["yield_pct"]
                    .mean()
                    .sort_values("yield_pct", ascending=False)
                )
                if yield_by_strain.empty:
                    st.info("No strain yield data yet.")
                else:
                    fig_yield = px.bar(
                        yield_by_strain,
                        x="strain",
                        y="yield_pct",
                        color_discrete_sequence=["#ff9a3c"],
                    )
                    fig_yield.update_layout(
                        margin=dict(l=10, r=10, t=10, b=10),
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        showlegend=False,
                        font=dict(color="rgba(255,255,255,0.86)"),
                    )
                    st.plotly_chart(fig_yield, use_container_width=True)
            chart_card_end()
        with sc2:
            chart_card_start("Output by Strain", "Total finished output grams by strain")
            if run_df.empty or "strain" not in run_df.columns or "finished_output_g" not in run_df.columns:
                st.info("No strain output data yet.")
            else:
                output_by_strain = (
                    run_df.assign(strain=run_df["strain"].fillna("").astype(str).str.strip())
                    .query("strain != ''")
                    .groupby("strain", as_index=False)["finished_output_g"]
                    .sum()
                    .sort_values("finished_output_g", ascending=False)
                )
                if output_by_strain.empty:
                    st.info("No strain output data yet.")
                else:
                    fig_output = px.bar(
                        output_by_strain,
                        x="strain",
                        y="finished_output_g",
                        color_discrete_sequence=["#ff9a3c"],
                    )
                    fig_output.update_layout(
                        margin=dict(l=10, r=10, t=10, b=10),
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        showlegend=False,
                        font=dict(color="rgba(255,255,255,0.86)"),
                    )
                    st.plotly_chart(fig_output, use_container_width=True)
            chart_card_end()

    with method_tab:
        st.markdown("### Method Efficiency Tracker")
        eff = _method_efficiency_summary(run_df)
        if eff.empty:
            st.info("No method summary available yet.")
        else:
            st.dataframe(eff, use_container_width=True, hide_index=True)
            chart_cols = [c for c in ["yield_pct", "post_process_efficiency_pct", "solvent_recovery_pct", "cycle_time_hours"] if c in eff.columns]
            if chart_cols:
                st.line_chart(eff.set_index("method")[chart_cols], use_container_width=True)
        st.markdown("### Method Variance")
        variance = _variance_summary(run_df)
        if variance.empty:
            st.info("No variance summary available yet.")
        else:
            st.dataframe(variance, use_container_width=True, hide_index=True)
        st.markdown("### Strain Performance")
        if run_df.empty or "strain" not in run_df.columns:
            st.info("No strain performance data available yet.")
        else:
            strain_perf = (
                run_df.assign(strain=run_df["strain"].fillna("").astype(str).str.strip())
                .query("strain != ''")
                .groupby("strain", as_index=False)
                .agg(
                    avg_yield_pct=("yield_pct", "mean"),
                    avg_efficiency_pct=("post_process_efficiency_pct", "mean"),
                    total_output_g=("finished_output_g", "sum"),
                )
                .sort_values("avg_yield_pct", ascending=False)
            )
            if strain_perf.empty:
                st.info("No strain performance data available yet.")
            else:
                st.dataframe(strain_perf, use_container_width=True, hide_index=True)
                fig_strain_perf = px.bar(
                    strain_perf,
                    x="strain",
                    y="avg_yield_pct",
                    color_discrete_sequence=["#ff9a3c"],
                )
                fig_strain_perf.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                    font=dict(color="rgba(255,255,255,0.86)"),
                )
                st.plotly_chart(fig_strain_perf, use_container_width=True)

    with runs_tab:
        st.markdown("### Run Explorer")
        run_df_display = run_df.copy()
        if "strain" not in run_df_display.columns:
            run_df_display["strain"] = ""
        st.dataframe(run_df_display, use_container_width=True, hide_index=True)
        with st.expander("Add Run Record", expanded=False):
            r1, r2, r3 = st.columns(3)
            with r1:
                run_date = st.date_input("Run Date", key="ecc_run_date_v2")
                state = st.selectbox("State / Jurisdiction", ["MA", "ME", "NY", "NJ", "MI", "NV", "CA", "Other"], key="ecc_run_state_v2")
                license_name = st.text_input("Facility / License Name", key="ecc_license_name_v2")
                client_name = st.text_input("Client Name", value="In House", key="ecc_client_name_v2")
                batch_id_internal = st.text_input("Internal Batch ID", key="ecc_batch_id_v2")
                method = st.selectbox("Method", ENTRY_METHOD_OPTIONS, key="ecc_method_v2")
                strain = st.text_input("Strain", key="ecc_strain_v2")
                product_type = st.selectbox("Product Type", PRODUCT_TYPE_OPTIONS, key="ecc_product_type_v2")
            with r2:
                input_material_type = st.selectbox("Input Material Type", ["Fresh Frozen", "Cured Biomass", "Hash", "Flower", "Trim", "Other"], key="ecc_input_material_type_v2")
                input_weight_g = st.number_input("Input Weight (g)", min_value=0.0, step=1.0, key="ecc_input_weight_v2")
                intermediate_output_g = st.number_input("Intermediate Output (g)", min_value=0.0, step=0.1, key="ecc_intermediate_output_v2")
                finished_output_g = st.number_input("Finished Output (g)", min_value=0.0, step=0.1, key="ecc_finished_output_v2")
                residual_loss_g = st.number_input("Residual Loss (g)", min_value=0.0, step=0.1, key="ecc_residual_loss_v2")
                solvent_recovery_pct = st.number_input("Solvent Recovery %", min_value=0.0, max_value=100.0, step=0.1, key="ecc_solvent_recovery_v2")
                cycle_time_hours = st.number_input("Cycle Time (hours)", min_value=0.0, step=0.1, key="ecc_cycle_time_v2")
            with r3:
                metrc_package_id_input = st.text_input("METRC Package ID - Input", key="ecc_pkg_input_v2")
                metrc_package_id_output = st.text_input("METRC Package ID - Output", key="ecc_pkg_output_v2")
                metrc_manifest_or_transfer_id = st.text_input("METRC Manifest / Transfer ID", key="ecc_manifest_id_v2")
                coa_status = st.selectbox("COA Status", ["Pending", "Passed", "Failed", "Not Submitted"], key="ecc_coa_status_v2")
                qa_hold = st.checkbox("QA Hold", key="ecc_qa_hold_v2")
                toll_processing_flag = st.checkbox("Toll Processing Job", key="ecc_toll_flag_v2")
                processing_fee_usd = st.number_input("Processing Fee (USD)", min_value=0.0, step=10.0, key="ecc_processing_fee_v2")
                est_revenue_usd = st.number_input("Estimated Revenue (USD)", min_value=0.0, step=10.0, key="ecc_est_revenue_v2")
                cogs_usd = st.number_input("COGS (USD)", min_value=0.0, step=10.0, key="ecc_cogs_v2")
                operator = st.text_input("Operator", key="ecc_operator_v2")
                machine_line = st.text_input("Machine / Line", key="ecc_machine_line_v2")
                notes = st.text_area("Run Notes", key="ecc_notes_v2")
            if st.button("Add Run", key="ecc_add_run_v2"):
                yield_pct = (finished_output_g / input_weight_g * 100) if input_weight_g else 0.0
                post_eff = (finished_output_g / intermediate_output_g * 100) if intermediate_output_g else 0.0
                new_row = pd.DataFrame([{
                    "run_date": str(run_date),
                    "state": state,
                    "license_name": license_name,
                    "client_name": client_name,
                    "batch_id_internal": batch_id_internal,
                    "metrc_package_id_input": metrc_package_id_input,
                    "metrc_package_id_output": metrc_package_id_output,
                    "metrc_manifest_or_transfer_id": metrc_manifest_or_transfer_id,
                    "method": method,
                    "strain": strain,
                    "product_type": product_type,
                    "input_material_type": input_material_type,
                    "input_weight_g": input_weight_g,
                    "intermediate_output_g": intermediate_output_g,
                    "finished_output_g": finished_output_g,
                    "residual_loss_g": residual_loss_g,
                    "yield_pct": yield_pct,
                    "post_process_efficiency_pct": post_eff,
                    "solvent_recovery_pct": solvent_recovery_pct,
                    "cycle_time_hours": cycle_time_hours,
                    "operator": operator,
                    "machine_line": machine_line,
                    "status": "Complete",
                    "toll_processing": toll_processing_flag,
                    "processing_fee_usd": processing_fee_usd,
                    "est_revenue_usd": est_revenue_usd,
                    "cogs_usd": cogs_usd,
                    "coa_status": coa_status,
                    "qa_hold": qa_hold,
                    "notes": notes,
                }])
                st.session_state[EXTRACTION_RUNS] = pd.concat([st.session_state[EXTRACTION_RUNS], new_row], ignore_index=True)
                st.success("Run added.")

    with toll_tab:
        st.markdown("### Toll Processing Command View")
        st.dataframe(job_df, use_container_width=True, hide_index=True)
        with st.expander("Add Toll Processing Job", expanded=False):
            t1, t2, t3 = st.columns(3)
            with t1:
                client_name = st.text_input("Client Name", key="ecc_job_client_name_v2")
                state = st.selectbox("State", ["MA", "ME", "NY", "NJ", "MI", "NV", "CA", "Other"], key="ecc_job_state_v2")
                license_or_registration = st.text_input("Client License / Registration", key="ecc_job_license_v2")
                method = st.selectbox("Method", ENTRY_METHOD_OPTIONS, key="ecc_job_method_v2")
                strain = st.text_input("Strain", key="ecc_job_strain_v2")
            with t2:
                metrc_transfer_id = st.text_input("METRC Transfer ID", key="ecc_job_metrc_v2")
                material_received_date = st.date_input("Material Received Date", key="ecc_job_received_v2")
                promised_completion_date = st.date_input("Promised Completion Date", key="ecc_job_promised_v2")
                input_weight_g = st.number_input("Input Weight (g)", min_value=0.0, step=1.0, key="ecc_job_input_v2")
            with t3:
                expected_output_g = st.number_input("Expected Output (g)", min_value=0.0, step=0.1, key="ecc_job_expected_v2")
                actual_output_g = st.number_input("Actual Output (g)", min_value=0.0, step=0.1, key="ecc_job_actual_v2")
                invoice_status = st.selectbox("Invoice Status", ["Draft", "Sent", "Paid", "Overdue"], key="ecc_job_invoice_v2")
                payment_status = st.selectbox("Payment Status", ["Pending", "Partial", "Paid"], key="ecc_job_payment_v2")
                coa_status = st.selectbox("COA Status", ["Pending", "Passed", "Failed"], key="ecc_job_coa_v2")
                job_status = st.selectbox("Job Status", ["Queued", "Processing", "Packaging", "Complete", "Hold"], key="ecc_job_status_v2")
            if st.button("Add Toll Job", key="ecc_add_job_v2"):
                today = pd.Timestamp.today().normalize()
                promised = pd.Timestamp(promised_completion_date)
                sla_status = "At Risk" if promised < today else "On Track"
                new_job = pd.DataFrame([{
                    "client_name": client_name,
                    "state": state,
                    "license_or_registration": license_or_registration,
                    "metrc_transfer_id": metrc_transfer_id,
                    "material_received_date": str(material_received_date),
                    "promised_completion_date": str(promised_completion_date),
                    "method": method,
                    "strain": strain,
                    "input_weight_g": input_weight_g,
                    "expected_output_g": expected_output_g,
                    "actual_output_g": actual_output_g,
                    "sla_status": sla_status,
                    "invoice_status": invoice_status,
                    "payment_status": payment_status,
                    "coa_status": coa_status,
                    "job_status": job_status,
                }])
                st.session_state[EXTRACTION_JOBS] = pd.concat([st.session_state[EXTRACTION_JOBS], new_job], ignore_index=True)
                st.success("Toll job added.")

    with compliance_tab:
        st.markdown("### Compliance / METRC Traceability")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.text_input("Facility License Number", placeholder="Example: LIC123-OPERATIONS", key="ecc_facility_license_number_v2")
        with c2:
            st.text_input("Primary METRC License Label", placeholder="Example: MA Processing License", key="ecc_metrc_license_label_v2")
        with c3:
            st.selectbox("Seed-to-Sale Tracking", ["METRC", "BioTrack", "Other / Mixed"], key="ecc_seed_to_sale_tracking_v2")
        required_fields = pd.DataFrame(
            [
                ["State", "Jurisdiction for reporting and workflow rules"],
                ["Facility / License Name", "Required internal mapping for multi-site operations"],
                ["Internal Batch ID", "Your own batch identifier"],
                ["METRC Package ID - Input", "Starting package used in the run"],
                ["METRC Package ID - Output", "Finished package created from the run"],
                ["METRC Manifest / Transfer ID", "Movement and custody tracking"],
                ["Client License / Registration", "Critical for toll processing"],
                ["COA Status", "Pending, passed, failed, or not submitted"],
                ["QA Hold", "Operational hold flag"],
                ["Run Notes", "Exception log, deviations, and event context"],
            ],
            columns=["Field", "Purpose"],
        )
        st.dataframe(required_fields, use_container_width=True, hide_index=True)

    with inputs_tab:
        st.markdown("### Raw Data Upload Staging")
        uploaded = st.file_uploader("Upload CSV run log", type=["csv"], key="ecc_upload_v2")
        if uploaded is not None:
            try:
                uploaded_df = pd.read_csv(uploaded)
                st.success("CSV loaded into preview.")
                st.dataframe(uploaded_df, use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(f"Could not read CSV: {exc}")

    with ai_ops_tab:
        st.markdown("### Doobie Operations Brief")
        alerts = _compute_alerts(run_df, job_df)
        if alerts:
            st.markdown("#### Current Alerts")
            for alert in alerts:
                st.warning(alert)
        else:
            st.success("No high-priority extraction alerts detected from current dataset.")
        st.caption("Generate a shift-ready brief grounded in current run and toll job data.")
        if st.button("Generate Doobie Extraction Brief", key="ecc_doobie_ops_brief_v2"):
            payload = run_df.copy()
            if not job_df.empty:
                payload = payload.copy()
                payload["toll_jobs_visible"] = len(job_df)
            run_extraction_doobie(payload, state=(selected_state if selected_state != "All" else "MA"))
