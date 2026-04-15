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
STAGE_TO_TIMESTAMP_FIELD = {
    "Intake": "stage_intake_ts",
    "In Extraction": "stage_extraction_ts",
    "Winterization": "stage_winterization_ts",
    "Solvent Recovery": "stage_recovery_ts",
    "Post-Processing": "stage_postprocess_ts",
    "Awaiting QA": "stage_awaiting_qa_ts",
    "QA Hold": "stage_qa_hold_ts",
    "Packaging": "stage_packaging_ts",
    "Complete": "stage_complete_ts",
}


def _today_str():
    return pd.Timestamp.today().normalize().strftime("%Y-%m-%d")


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
                    "reprocessed": False,
                    "notes": "Sample seed record",
                    "stage_intake_ts": "2026-03-25",
                    "stage_extraction_ts": "2026-03-26",
                    "stage_recovery_ts": "2026-03-26",
                    "stage_postprocess_ts": "2026-03-27",
                    "stage_packaging_ts": "2026-03-27",
                    "stage_complete_ts": "2026-03-27",
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
                    "reprocessed": False,
                    "notes": "Seed ethanol record",
                    "stage_intake_ts": "2026-03-26",
                    "stage_extraction_ts": "2026-03-27",
                    "stage_recovery_ts": "2026-03-28",
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


def _compute_stage_metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ts_cols = [c for c in STAGE_TO_TIMESTAMP_FIELD.values() if c in out.columns]
    for c in ts_cols:
        out[c] = pd.to_datetime(out[c], errors="coerce")
    if {"stage_intake_ts", "stage_extraction_ts"}.issubset(out.columns):
        out["days_intake_to_extraction"] = (out["stage_extraction_ts"] - out["stage_intake_ts"]).dt.days
    if {"stage_extraction_ts", "stage_recovery_ts"}.issubset(out.columns):
        out["days_extraction_to_recovery"] = (out["stage_recovery_ts"] - out["stage_extraction_ts"]).dt.days
    if {"stage_recovery_ts", "stage_postprocess_ts"}.issubset(out.columns):
        out["days_recovery_to_postprocess"] = (out["stage_postprocess_ts"] - out["stage_recovery_ts"]).dt.days
    if {"stage_postprocess_ts", "stage_packaging_ts"}.issubset(out.columns):
        out["days_postprocess_to_packaging"] = (out["stage_packaging_ts"] - out["stage_postprocess_ts"]).dt.days
    if {"stage_intake_ts", "stage_complete_ts"}.issubset(out.columns):
        out["days_total_process"] = (out["stage_complete_ts"] - out["stage_intake_ts"]).dt.days
    return out


def _recompute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["input_weight_g", "intermediate_output_g", "finished_output_g", "cogs_usd", "est_revenue_usd", "packaged_units"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)
    if {"input_weight_g", "finished_output_g"}.issubset(out.columns):
        out["yield_pct"] = out.apply(lambda r: (r["finished_output_g"] / r["input_weight_g"] * 100) if r["input_weight_g"] else 0, axis=1)
    if {"intermediate_output_g", "finished_output_g"}.issubset(out.columns):
        out["post_process_efficiency_pct"] = out.apply(lambda r: (r["finished_output_g"] / r["intermediate_output_g"] * 100) if r["intermediate_output_g"] else 0, axis=1)
    out["cost_per_gram"] = out.apply(lambda r: (r["cogs_usd"] / r["finished_output_g"]) if r["finished_output_g"] else 0, axis=1)
    out["revenue_per_gram"] = out.apply(lambda r: (r["est_revenue_usd"] / r["finished_output_g"]) if r["finished_output_g"] else 0, axis=1)
    out["gross_margin_pct"] = out.apply(lambda r: ((r["est_revenue_usd"] - r["cogs_usd"]) / r["est_revenue_usd"] * 100) if r["est_revenue_usd"] else 0, axis=1)
    out["yield_drop_from_intermediate_g"] = out.apply(lambda r: (r["intermediate_output_g"] - r["finished_output_g"]) if r["intermediate_output_g"] else 0, axis=1)
    out["yield_drop_from_intermediate_pct"] = out.apply(lambda r: ((r["intermediate_output_g"] - r["finished_output_g"]) / r["intermediate_output_g"] * 100) if r["intermediate_output_g"] else 0, axis=1)
    today = _today_str()
    out["last_updated"] = today
    if "process_stage" in out.columns:
        for stage, field in STAGE_TO_TIMESTAMP_FIELD.items():
            if field not in out.columns:
                out[field] = pd.NaT
        for idx, row in out.iterrows():
            stage = row.get("process_stage")
            field = STAGE_TO_TIMESTAMP_FIELD.get(stage)
            if field and pd.isna(pd.to_datetime(row.get(field), errors="coerce")):
                out.at[idx, field] = today
    out = _compute_stage_metrics(out)
    return out


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
        reprocessed = int(run_df.get("reprocessed", pd.Series(dtype=bool)).fillna(False).sum())
        if reprocessed > 0:
            alerts.append(f"Reprocessed batches present: {reprocessed} run(s).")
        large_drop = run_df[pd.to_numeric(run_df.get("yield_drop_from_intermediate_pct", 0), errors="coerce").fillna(0) > 15]
        if not large_drop.empty:
            alerts.append(f"High post-process yield drop on {len(large_drop)} run(s) above 15%.")
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
    metrics = [c for c in ["yield_pct", "post_process_efficiency_pct", "solvent_recovery_pct", "cycle_time_hours", "cost_per_gram", "revenue_per_gram", "gross_margin_pct", "yield_drop_from_intermediate_pct"] if c in run_df.columns]
    return run_df.groupby("method", dropna=False)[metrics].mean(numeric_only=True).reset_index()


def _machine_summary(run_df: pd.DataFrame) -> pd.DataFrame:
    if run_df is None or run_df.empty or "machine_line" not in run_df.columns:
        return pd.DataFrame()
    metrics = [c for c in ["yield_pct", "post_process_efficiency_pct", "solvent_recovery_pct", "cycle_time_hours", "cost_per_gram", "gross_margin_pct"] if c in run_df.columns]
    return run_df.groupby(["method", "machine_line"], dropna=False)[metrics].mean(numeric_only=True).reset_index()


def render_extraction_perfect_view_v4():
    _ensure_defaults()
    st.session_state[EXTRACTION_RUNS] = _recompute_metrics(st.session_state[EXTRACTION_RUNS])
    render_section_header(
        "Extraction Command Center",
        "Living extraction workflow with stage timing, yield-drop visibility, reprocessing flags, cost-per-gram tracking, method efficiency, machine benchmarking, compliance/METRC, and Doobie ops briefing.",
    )

    s1, s2, s3 = st.columns(3)
    with s1:
        selected_state = st.selectbox("State", ["All", "MA", "ME", "NY", "NJ", "MI", "NV", "CA", "Other"], key="ecc_selected_state_v4")
    with s2:
        selected_method = st.selectbox("Extraction Method", METHOD_OPTIONS, key="ecc_selected_method_v4")
    with s3:
        toll_only = st.toggle("Show Toll Processing Only", value=False, key="ecc_toll_only_v4")

    run_df_all = st.session_state[EXTRACTION_RUNS].copy()
    job_df_all = st.session_state[EXTRACTION_JOBS].copy()
    run_df, job_df = _filtered_frames(run_df_all, job_df_all, selected_state, selected_method, toll_only)

    est_rev = float(pd.to_numeric(run_df.get("est_revenue_usd", 0), errors="coerce").fillna(0).sum())
    cogs = float(pd.to_numeric(run_df.get("cogs_usd", 0), errors="coerce").fillna(0).sum())
    top = st.columns(8)
    with top[0]: render_metric_card("Runs", f"{len(run_df):,}")
    with top[1]: render_metric_card("Active", f"{int((run_df.get('run_status', pd.Series(dtype=str)) == 'Active').sum()):,}")
    with top[2]: render_metric_card("Avg Yield", f"{pd.to_numeric(run_df.get('yield_pct', 0), errors='coerce').fillna(0).mean():.1f}%")
    with top[3]: render_metric_card("Solvent Recovery", f"{pd.to_numeric(run_df.get('solvent_recovery_pct', 0), errors='coerce').fillna(0).mean():.1f}%")
    with top[4]: render_metric_card("Cycle Time", f"{pd.to_numeric(run_df.get('cycle_time_hours', 0), errors='coerce').fillna(0).mean():.1f} hr")
    with top[5]: render_metric_card("Cost / Gram", f"${pd.to_numeric(run_df.get('cost_per_gram', 0), errors='coerce').fillna(0).mean():.2f}")
    with top[6]: render_metric_card("Yield Drop", f"{pd.to_numeric(run_df.get('yield_drop_from_intermediate_pct', 0), errors='coerce').fillna(0).mean():.1f}%")
    with top[7]: render_metric_card("Gross Margin", f"{(((est_rev - cogs) / est_rev) * 100 if est_rev else 0):.1f}%")

    tabs = st.tabs([
        "Workflow Board",
        "Stage Timing",
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
        board_cols = [c for c in ["batch_id_internal", "method", "process_stage", "run_status", "coa_status", "qa_hold", "reprocessed", "finished_output_g", "packaged_units", "last_updated", "notes"] if c in run_df_all.columns]
        edited = st.data_editor(run_df_all[board_cols], use_container_width=True, hide_index=True, num_rows="dynamic", key="ecc_live_board_editor_v4")
        if st.button("Save Workflow Updates", key="ecc_save_workflow_updates_v4"):
            merged = run_df_all.copy()
            for col in board_cols:
                if col in edited.columns:
                    merged[col] = edited[col]
            merged = _recompute_metrics(merged)
            st.session_state[EXTRACTION_RUNS] = merged
            st.success("Workflow updates saved.")
        st.caption("Update stage, status, QA, reprocessing, outputs, packaging counts, and notes as the run moves forward.")

    with tabs[1]:
        st.markdown("### Stage Timing")
        timing_cols = [c for c in ["batch_id_internal", "method", "process_stage", "days_intake_to_extraction", "days_extraction_to_recovery", "days_recovery_to_postprocess", "days_postprocess_to_packaging", "days_total_process"] if c in run_df.columns]
        if timing_cols:
            st.dataframe(run_df[timing_cols], use_container_width=True, hide_index=True)
        else:
            st.info("No stage timing data available yet.")

    with tabs[2]:
        st.markdown("### Method Efficiency Tracker")
        eff = _method_efficiency_summary(run_df)
        if eff.empty:
            st.info("No method summary available yet.")
        else:
            st.dataframe(eff, use_container_width=True, hide_index=True)
            chart_cols = [c for c in ["yield_pct", "post_process_efficiency_pct", "solvent_recovery_pct", "cycle_time_hours", "cost_per_gram", "yield_drop_from_intermediate_pct"] if c in eff.columns]
            if chart_cols:
                st.line_chart(eff.set_index("method")[chart_cols], use_container_width=True)

    with tabs[3]:
        st.markdown("### Machine / Line Benchmarking")
        machine = _machine_summary(run_df)
        if machine.empty:
            st.info("No machine-line summary available yet.")
        else:
            st.dataframe(machine, use_container_width=True, hide_index=True)

    with tabs[4]:
        st.markdown("### Run Analytics")
        st.dataframe(run_df, use_container_width=True, hide_index=True)
        with st.expander("Add Run Record", expanded=False):
            r1, r2, r3 = st.columns(3)
            with r1:
                run_date = st.date_input("Run Date", key="ecc_run_date_v4")
                state = st.selectbox("State / Jurisdiction", ["MA", "ME", "NY", "NJ", "MI", "NV", "CA", "Other"], key="ecc_run_state_v4")
                license_name = st.text_input("Facility / License Name", key="ecc_license_name_v4")
                client_name = st.text_input("Client Name", value="In House", key="ecc_client_name_v4")
                batch_id_internal = st.text_input("Internal Batch ID", key="ecc_batch_id_v4")
                method = st.selectbox("Method", ENTRY_METHOD_OPTIONS, key="ecc_method_v4")
                product_type = st.selectbox("Product Type", ["Sugar", "Badder", "Shatter", "Sauce", "Distillate", "Rosin Jam", "Fresh Press", "Crude", "Other"], key="ecc_product_type_v4")
                process_stage = st.selectbox("Process Stage", PROCESS_STAGE_OPTIONS, key="ecc_process_stage_v4")
                run_status = st.selectbox("Run Status", RUN_STATUS_OPTIONS, key="ecc_run_status_v4")
            with r2:
                input_material_type = st.selectbox("Input Material Type", ["Fresh Frozen", "Cured Biomass", "Hash", "Flower", "Trim", "Other"], key="ecc_input_material_type_v4")
                input_weight_g = st.number_input("Input Weight (g)", min_value=0.0, step=1.0, key="ecc_input_weight_v4")
                intermediate_output_g = st.number_input("Intermediate Output (g)", min_value=0.0, step=0.1, key="ecc_intermediate_output_v4")
                finished_output_g = st.number_input("Finished Output (g)", min_value=0.0, step=0.1, key="ecc_finished_output_v4")
                residual_loss_g = st.number_input("Residual Loss (g)", min_value=0.0, step=0.1, key="ecc_residual_loss_v4")
                solvent_recovery_pct = st.number_input("Solvent Recovery %", min_value=0.0, max_value=100.0, step=0.1, key="ecc_solvent_recovery_v4")
                cycle_time_hours = st.number_input("Cycle Time (hours)", min_value=0.0, step=0.1, key="ecc_cycle_time_v4")
                packaged_units = st.number_input("Packaged Units", min_value=0, step=1, key="ecc_packaged_units_v4")
            with r3:
                metrc_package_id_input = st.text_input("METRC Package ID - Input", key="ecc_pkg_input_v4")
                metrc_package_id_output = st.text_input("METRC Package ID - Output", key="ecc_pkg_output_v4")
                metrc_manifest_or_transfer_id = st.text_input("METRC Manifest / Transfer ID", key="ecc_manifest_id_v4")
                coa_status = st.selectbox("COA Status", COA_STATUS_OPTIONS, key="ecc_coa_status_v4")
                qa_hold = st.checkbox("QA Hold", key="ecc_qa_hold_v4")
                reprocessed = st.checkbox("Reprocessed Batch", key="ecc_reprocessed_v4")
                toll_processing_flag = st.checkbox("Toll Processing Job", key="ecc_toll_flag_v4")
                processing_fee_usd = st.number_input("Processing Fee (USD)", min_value=0.0, step=10.0, key="ecc_processing_fee_v4")
                est_revenue_usd = st.number_input("Estimated Revenue (USD)", min_value=0.0, step=10.0, key="ecc_est_revenue_v4")
                cogs_usd = st.number_input("COGS (USD)", min_value=0.0, step=10.0, key="ecc_cogs_v4")
                operator = st.text_input("Operator", key="ecc_operator_v4")
                machine_line = st.text_input("Machine / Line", key="ecc_machine_line_v4")
                notes = st.text_area("Run Notes", key="ecc_notes_v4")
            if st.button("Add Run", key="ecc_add_run_v4"):
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
                    "product_type": product_type,
                    "process_stage": process_stage,
                    "run_status": run_status,
                    "input_material_type": input_material_type,
                    "input_weight_g": input_weight_g,
                    "intermediate_output_g": intermediate_output_g,
                    "finished_output_g": finished_output_g,
                    "residual_loss_g": residual_loss_g,
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
                    "reprocessed": reprocessed,
                    "notes": notes,
                }])
                new_row = _recompute_metrics(new_row)
                st.session_state[EXTRACTION_RUNS] = pd.concat([st.session_state[EXTRACTION_RUNS], new_row], ignore_index=True)
                st.success("Run added.")

    with tabs[5]:
        st.markdown("### Toll Processing Command View")
        st.dataframe(job_df, use_container_width=True, hide_index=True)

    with tabs[6]:
        st.markdown("### Compliance / METRC Traceability")
        st.dataframe(pd.DataFrame([
            ["METRC Package ID - Input", "Starting package used in the run"],
            ["METRC Package ID - Output", "Finished package created from the run"],
            ["METRC Manifest / Transfer ID", "Movement and custody tracking"],
            ["COA Status", "Pending, passed, failed, or not submitted"],
            ["QA Hold", "Operational hold flag"],
            ["Process Stage", "Where the run currently sits in production"],
            ["Run Status", "Queued, Active, Hold, Complete, Failed"],
            ["Reprocessed", "Flags runs that required rework"],
        ], columns=["Field", "Purpose"]), use_container_width=True, hide_index=True)

    with tabs[7]:
        st.markdown("### Raw Data Upload Staging")
        uploaded = st.file_uploader("Upload CSV run log", type=["csv"], key="ecc_upload_v4")
        if uploaded is not None:
            try:
                uploaded_df = pd.read_csv(uploaded)
                st.success("CSV loaded into preview.")
                st.dataframe(uploaded_df, use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(f"Could not read CSV: {exc}")

    with tabs[8]:
        st.markdown("### Doobie Operations Brief")
        alerts = _compute_alerts(run_df, job_df)
        if alerts:
            for alert in alerts:
                st.warning(alert)
        else:
            st.success("No high-priority extraction alerts detected from current dataset.")
        if st.button("Generate Doobie Extraction Brief", key="ecc_doobie_ops_brief_v4"):
            payload = run_df.copy()
            if not job_df.empty:
                payload["toll_jobs_visible"] = len(job_df)
            run_extraction_doobie(payload, state=(selected_state if selected_state != "All" else "MA"))
