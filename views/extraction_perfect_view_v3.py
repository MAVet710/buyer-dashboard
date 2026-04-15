import pandas as pd
import streamlit as st

from core.session_keys import EXTRACTION_JOBS, EXTRACTION_RUNS
from doobie_panels import run_extraction_doobie
from ui.components import render_metric_card, render_section_header

METHOD_OPTIONS = ["All", "BHO", "CO2", "Rosin", "Ethanol"]
ENTRY_METHOD_OPTIONS = ["BHO", "CO2", "Rosin", "Ethanol"]
PROCESS_STAGE_OPTIONS = [
    "Intake",
    "In Extraction",
    "Winterization",
    "Solvent Recovery",
    "Post-Processing",
    "Awaiting QA",
    "QA Hold",
    "Packaging",
    "Complete",
]
RUN_STATUS_OPTIONS = ["Queued", "Active", "Hold", "Complete", "Failed"]
COA_STATUS_OPTIONS = ["Pending", "Passed", "Failed", "Not Submitted"]


def _ensure_defaults():
    if EXTRACTION_RUNS not in st.session_state:
        st.session_state[EXTRACTION_RUNS] = pd.DataFrame(
            [
                {
                    "run_date": "2026-03-27",
                    "last_updated": "2026-03-27",
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
                    "process_stage": "Complete",
                    "run_status": "Complete",
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
                    "toll_processing": False,
                    "processing_fee_usd": 0.0,
                    "est_revenue_usd": 3440.0,
                    "cogs_usd": 1200.0,
                    "coa_status": "Passed",
                    "qa_hold": False,
                    "packaged_units": 0,
                    "notes": "Sample seed record",
                },
                {
                    "run_date": "2026-03-28",
                    "last_updated": "2026-03-28",
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
                    "process_stage": "Solvent Recovery",
                    "run_status": "Active",
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
                    "toll_processing": False,
                    "processing_fee_usd": 0.0,
                    "est_revenue_usd": 4680.0,
                    "cogs_usd": 1900.0,
                    "coa_status": "Pending",
                    "qa_hold": False,
                    "packaged_units": 0,
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


def _filtered_frames(run_df: pd.DataFrame, job_df: pd.DataFrame, selected_state: str, selected_method: str, toll_only: bool):
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
    if toll_only and "toll_processing" in rf.columns:
        rf = rf[rf["toll_processing"] == True]
    return rf, jf


def _compute_alerts(run_df: pd.DataFrame, job_df: pd.DataFrame):
    alerts = []
    if run_df is not None and not run_df.empty:
        low_yield = run_df[pd.to_numeric(run_df.get("yield_pct", 0), errors="coerce").fillna(0) < 12]
        if not low_yield.empty:
            alerts.append(f"Low yield runs: {len(low_yield)} below 12% yield.")
        qa_holds = int(run_df.get("qa_hold", pd.Series(dtype=bool)).fillna(False).sum())
        if qa_holds > 0:
            alerts.append(f"QA holds active: {qa_holds} run(s).")
        pending_or_failed = int(run_df.get("coa_status", pd.Series(dtype=str)).isin(["Pending", "Failed"]).sum())
        if pending_or_failed > 0:
            alerts.append(f"COA risk: {pending_or_failed} run(s) pending/failed.")
        low_recovery = run_df[pd.to_numeric(run_df.get("solvent_recovery_pct", 0), errors="coerce").fillna(0) < 85]
        if not low_recovery.empty:
            alerts.append(f"Low solvent recovery detected on {len(low_recovery)} run(s).")
        long_cycles = run_df[pd.to_numeric(run_df.get("cycle_time_hours", 0), errors="coerce").fillna(0) > 10]
        if not long_cycles.empty:
            alerts.append(f"Long cycle times detected on {len(long_cycles)} run(s) over 10 hours.")
    if job_df is not None and not job_df.empty:
        at_risk_jobs = int((job_df.get("sla_status", pd.Series(dtype=str)) == "At Risk").sum())
        if at_risk_jobs > 0:
            alerts.append(f"Toll jobs at SLA risk: {at_risk_jobs}.")
        overdue = int((job_df.get("invoice_status", pd.Series(dtype=str)) == "Overdue").sum())
        if overdue > 0:
            alerts.append(f"Overdue toll invoices: {overdue}.")
    return alerts


def _method_efficiency_summary(run_df: pd.DataFrame) -> pd.DataFrame:
    if run_df is None or run_df.empty or "method" not in run_df.columns:
        return pd.DataFrame()
    metrics = [c for c in ["yield_pct", "post_process_efficiency_pct", "solvent_recovery_pct", "cycle_time_hours", "finished_output_g", "input_weight_g", "est_revenue_usd", "cogs_usd"] if c in run_df.columns]
    summary = run_df.groupby("method", dropna=False)[metrics].mean(numeric_only=True).reset_index()
    if "est_revenue_usd" in run_df.columns and "cogs_usd" in run_df.columns:
        rev = run_df.groupby("method", dropna=False)["est_revenue_usd"].sum().reset_index(name="total_revenue_usd")
        cogs = run_df.groupby("method", dropna=False)["cogs_usd"].sum().reset_index(name="total_cogs_usd")
        summary = summary.merge(rev, on="method", how="left").merge(cogs, on="method", how="left")
        summary["gross_margin_pct"] = summary.apply(lambda r: ((r["total_revenue_usd"] - r["total_cogs_usd"]) / r["total_revenue_usd"] * 100) if r.get("total_revenue_usd", 0) else 0, axis=1)
        summary["cost_per_gram"] = summary.apply(lambda r: (r["total_cogs_usd"] / (r.get("finished_output_g", 0) * len(run_df[run_df['method'] == r['method']])) ) if r.get("finished_output_g", 0) else 0, axis=1)
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


def _machine_summary(run_df: pd.DataFrame) -> pd.DataFrame:
    if run_df is None or run_df.empty or "machine_line" not in run_df.columns:
        return pd.DataFrame()
    metrics = [c for c in ["yield_pct", "post_process_efficiency_pct", "solvent_recovery_pct", "cycle_time_hours", "finished_output_g"] if c in run_df.columns]
    return run_df.groupby(["method", "machine_line"], dropna=False)[metrics].mean(numeric_only=True).reset_index()


def _recompute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["input_weight_g", "intermediate_output_g", "finished_output_g"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)
    if {"input_weight_g", "finished_output_g"}.issubset(out.columns):
        out["yield_pct"] = out.apply(lambda r: (r["finished_output_g"] / r["input_weight_g"] * 100) if r["input_weight_g"] else 0, axis=1)
    if {"intermediate_output_g", "finished_output_g"}.issubset(out.columns):
        out["post_process_efficiency_pct"] = out.apply(lambda r: (r["finished_output_g"] / r["intermediate_output_g"] * 100) if r["intermediate_output_g"] else 0, axis=1)
    out["last_updated"] = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    return out


def render_extraction_perfect_view_v3():
    _ensure_defaults()
    render_section_header(
        "Extraction Command Center",
        "Living extraction workflow with editable run records, stage-based updates, method efficiency tracking, machine benchmarking, compliance/METRC, and Doobie ops briefing.",
    )

    s1, s2, s3 = st.columns(3)
    with s1:
        selected_state = st.selectbox("State", ["All", "MA", "ME", "NY", "NJ", "MI", "NV", "CA", "Other"], key="ecc_selected_state_v3")
    with s2:
        selected_method = st.selectbox("Extraction Method", METHOD_OPTIONS, key="ecc_selected_method_v3")
    with s3:
        toll_only = st.toggle("Show Toll Processing Only", value=False, key="ecc_toll_only_v3")

    run_df_all = st.session_state[EXTRACTION_RUNS].copy()
    job_df_all = st.session_state[EXTRACTION_JOBS].copy()
    run_df, job_df = _filtered_frames(run_df_all, job_df_all, selected_state, selected_method, toll_only)

    top = st.columns(8)
    with top[0]:
        render_metric_card("Runs", f"{len(run_df):,}")
    with top[1]:
        render_metric_card("Active", f"{int((run_df.get('run_status', pd.Series(dtype=str)) == 'Active').sum()):,}")
    with top[2]:
        render_metric_card("QA Hold", f"{int(run_df.get('qa_hold', pd.Series(dtype=bool)).fillna(False).sum()):,}")
    with top[3]:
        render_metric_card("Avg Yield", f"{pd.to_numeric(run_df.get('yield_pct', 0), errors='coerce').fillna(0).mean():.1f}%")
    with top[4]:
        render_metric_card("Solvent Recovery", f"{pd.to_numeric(run_df.get('solvent_recovery_pct', 0), errors='coerce').fillna(0).mean():.1f}%")
    with top[5]:
        render_metric_card("Cycle Time", f"{pd.to_numeric(run_df.get('cycle_time_hours', 0), errors='coerce').fillna(0).mean():.1f} hr")
    with top[6]:
        est_rev = float(pd.to_numeric(run_df.get('est_revenue_usd', 0), errors='coerce').fillna(0).sum())
        render_metric_card("Revenue", f"${est_rev:,.0f}")
    with top[7]:
        cogs = float(pd.to_numeric(run_df.get('cogs_usd', 0), errors='coerce').fillna(0).sum())
        gm = ((est_rev - cogs) / est_rev * 100) if est_rev else 0
        render_metric_card("Gross Margin", f"{gm:.1f}%")

    tabs = st.tabs([
        "Workflow Board",
        "Method Efficiency",
        "Machine Benchmarking",
        "Run Analytics",
        "Toll Processing",
        "Compliance / METRC",
        "Data Input",
        "Doobie Ops Brief",
    ])

    with tabs[0]:
        st.markdown("### Live Workflow Board")
        board_cols = [c for c in ["batch_id_internal", "method", "process_stage", "run_status", "coa_status", "qa_hold", "last_updated", "finished_output_g", "packaged_units", "notes"] if c in run_df_all.columns]
        edited = st.data_editor(
            run_df_all[board_cols],
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="ecc_live_board_editor",
        )
        if st.button("Save Workflow Updates", key="ecc_save_workflow_updates"):
            merged = run_df_all.copy()
            for col in board_cols:
                if col in edited.columns:
                    merged[col] = edited[col]
            merged = _recompute_metrics(merged)
            st.session_state[EXTRACTION_RUNS] = merged
            st.success("Workflow updates saved.")
        st.caption("Use this board to update stage, status, COA, QA hold, finished output, packaged units, and notes as the batch progresses.")

    with tabs[1]:
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

    with tabs[2]:
        st.markdown("### Machine / Line Benchmarking")
        machine = _machine_summary(run_df)
        if machine.empty:
            st.info("No machine-line summary available yet.")
        else:
            st.dataframe(machine, use_container_width=True, hide_index=True)

    with tabs[3]:
        st.markdown("### Run Analytics")
        st.dataframe(run_df, use_container_width=True, hide_index=True)
        with st.expander("Add Run Record", expanded=False):
            r1, r2, r3 = st.columns(3)
            with r1:
                run_date = st.date_input("Run Date", key="ecc_run_date_v3")
                state = st.selectbox("State / Jurisdiction", ["MA", "ME", "NY", "NJ", "MI", "NV", "CA", "Other"], key="ecc_run_state_v3")
                license_name = st.text_input("Facility / License Name", key="ecc_license_name_v3")
                client_name = st.text_input("Client Name", value="In House", key="ecc_client_name_v3")
                batch_id_internal = st.text_input("Internal Batch ID", key="ecc_batch_id_v3")
                method = st.selectbox("Method", ENTRY_METHOD_OPTIONS, key="ecc_method_v3")
                product_type = st.selectbox("Product Type", ["Sugar", "Badder", "Shatter", "Sauce", "Distillate", "Rosin Jam", "Fresh Press", "Crude", "Other"], key="ecc_product_type_v3")
                process_stage = st.selectbox("Process Stage", PROCESS_STAGE_OPTIONS, key="ecc_process_stage_v3")
                run_status = st.selectbox("Run Status", RUN_STATUS_OPTIONS, key="ecc_run_status_v3")
            with r2:
                input_material_type = st.selectbox("Input Material Type", ["Fresh Frozen", "Cured Biomass", "Hash", "Flower", "Trim", "Other"], key="ecc_input_material_type_v3")
                input_weight_g = st.number_input("Input Weight (g)", min_value=0.0, step=1.0, key="ecc_input_weight_v3")
                intermediate_output_g = st.number_input("Intermediate Output (g)", min_value=0.0, step=0.1, key="ecc_intermediate_output_v3")
                finished_output_g = st.number_input("Finished Output (g)", min_value=0.0, step=0.1, key="ecc_finished_output_v3")
                residual_loss_g = st.number_input("Residual Loss (g)", min_value=0.0, step=0.1, key="ecc_residual_loss_v3")
                solvent_recovery_pct = st.number_input("Solvent Recovery %", min_value=0.0, max_value=100.0, step=0.1, key="ecc_solvent_recovery_v3")
                cycle_time_hours = st.number_input("Cycle Time (hours)", min_value=0.0, step=0.1, key="ecc_cycle_time_v3")
                packaged_units = st.number_input("Packaged Units", min_value=0, step=1, key="ecc_packaged_units_v3")
            with r3:
                metrc_package_id_input = st.text_input("METRC Package ID - Input", key="ecc_pkg_input_v3")
                metrc_package_id_output = st.text_input("METRC Package ID - Output", key="ecc_pkg_output_v3")
                metrc_manifest_or_transfer_id = st.text_input("METRC Manifest / Transfer ID", key="ecc_manifest_id_v3")
                coa_status = st.selectbox("COA Status", COA_STATUS_OPTIONS, key="ecc_coa_status_v3")
                qa_hold = st.checkbox("QA Hold", key="ecc_qa_hold_v3")
                toll_processing_flag = st.checkbox("Toll Processing Job", key="ecc_toll_flag_v3")
                processing_fee_usd = st.number_input("Processing Fee (USD)", min_value=0.0, step=10.0, key="ecc_processing_fee_v3")
                est_revenue_usd = st.number_input("Estimated Revenue (USD)", min_value=0.0, step=10.0, key="ecc_est_revenue_v3")
                cogs_usd = st.number_input("COGS (USD)", min_value=0.0, step=10.0, key="ecc_cogs_v3")
                operator = st.text_input("Operator", key="ecc_operator_v3")
                machine_line = st.text_input("Machine / Line", key="ecc_machine_line_v3")
                notes = st.text_area("Run Notes", key="ecc_notes_v3")
            if st.button("Add Run", key="ecc_add_run_v3"):
                yield_pct = (finished_output_g / input_weight_g * 100) if input_weight_g else 0.0
                post_eff = (finished_output_g / intermediate_output_g * 100) if intermediate_output_g else 0.0
                new_row = pd.DataFrame([{
                    "run_date": str(run_date),
                    "last_updated": pd.Timestamp.today().normalize().strftime("%Y-%m-%d"),
                    "state": state,
                    "license_name": license_name,
                    "client_name": client_name,
                    "batch_id_internal": batch_id_internal,
                    "metrc_package_id_input": metrc_package_id_input,
                    "metrc_package_id_output": metrc_package_id_output,
                    "metrc_manifest_or_transfer_id": metrc_manifest_or_transfer_id,
                    "method": method,
                    "product_type": product_type,
                    "process_stage": process_stage,
                    "run_status": run_status,
                    "input_material_type": input_material_type,
                    "input_weight_g": input_weight_g,
                    "intermediate_output_g": intermediate_output_g,
                    "finished_output_g": finished_output_g,
                    "residual_loss_g": residual_loss_g,
                    "yield_pct": yield_pct,
                    "post_process_efficiency_pct": post_eff,
                    "solvent_recovery_pct": solvent_recovery_pct,
                    "cycle_time_hours": cycle_time_hours,
                    "packaged_units": packaged_units,
                    "operator": operator,
                    "machine_line": machine_line,
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

    with tabs[4]:
        st.markdown("### Toll Processing Command View")
        st.dataframe(job_df, use_container_width=True, hide_index=True)

    with tabs[5]:
        st.markdown("### Compliance / METRC Traceability")
        st.dataframe(pd.DataFrame([
            ["METRC Package ID - Input", "Starting package used in the run"],
            ["METRC Package ID - Output", "Finished package created from the run"],
            ["METRC Manifest / Transfer ID", "Movement and custody tracking"],
            ["COA Status", "Pending, passed, failed, or not submitted"],
            ["QA Hold", "Operational hold flag"],
            ["Process Stage", "Where the run currently sits in production"],
            ["Run Status", "Queued, Active, Hold, Complete, Failed"],
        ], columns=["Field", "Purpose"]), use_container_width=True, hide_index=True)

    with tabs[6]:
        st.markdown("### Raw Data Upload Staging")
        uploaded = st.file_uploader("Upload CSV run log", type=["csv"], key="ecc_upload_v3")
        if uploaded is not None:
            try:
                uploaded_df = pd.read_csv(uploaded)
                st.success("CSV loaded into preview.")
                st.dataframe(uploaded_df, use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(f"Could not read CSV: {exc}")

    with tabs[7]:
        st.markdown("### Doobie Operations Brief")
        alerts = _compute_alerts(run_df, job_df)
        if alerts:
            for alert in alerts:
                st.warning(alert)
        else:
            st.success("No high-priority extraction alerts detected from current dataset.")
        if st.button("Generate Doobie Extraction Brief", key="ecc_doobie_ops_brief_v3"):
            payload = run_df.copy()
            if not job_df.empty:
                payload["toll_jobs_visible"] = len(job_df)
            run_extraction_doobie(payload, state=(selected_state if selected_state != "All" else "MA"))
