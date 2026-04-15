import json
import pandas as pd

NEO_PARTNER_RUNS = json.loads(r"""[{"run_date":"2025-09-29","state":"MI","license_name":"NEO Partner","client_name":"NEO Partner","batch_id_internal":"092925CONC","metrc_package_id_input":"660/2868","metrc_package_id_output":"","metrc_manifest_or_transfer_id":"","method":"Ethanol","strain":"","product_type":"Cured Badder","downstream_product":"N/A","process_stage":"Ovens","intake_complete":true,"extraction_complete":true,"post_process_complete":false,"formulation_complete":false,"filling_complete":false,"packaging_complete":false,"ready_for_transfer":false,"input_material_type":"Cured","input_weight_g":795.5,"intermediate_output_g":0.0,"finished_output_g":0.0,"residual_loss_g":795.5,"yield_pct":0.0,"post_process_efficiency_pct":0.0,"operator":"JH","machine_line":"Ovens","status":"Complete","toll_processing":true,"processing_fee_usd":0.0,"est_revenue_usd":0.0,"cogs_usd":636.4,"coa_status":"Passed","qa_hold":false,"notes":"Imported from Ovens normalized partner workbook","source_sheet":"Ovens","primary_metric_name":"agitation","primary_metric_value":"-","output_slot_count":1,"output_total_g":0.0},{"run_date":"2026-02-02","state":"MI","license_name":"NEO Partner","client_name":"NEO Partner","batch_id_internal":"MaterialPrep:6","metrc_package_id_input":"","metrc_package_id_output":"","metrc_manifest_or_transfer_id":"","method":"Ethanol","strain":"","product_type":"Supersack","downstream_product":"N/A","process_stage":"Materialprep","intake_complete":false,"extraction_complete":false,"post_process_complete":false,"formulation_complete":false,"filling_complete":false,"packaging_complete":false,"ready_for_transfer":false,"input_material_type":"","input_weight_g":0.0,"intermediate_output_g":102875.0,"finished_output_g":102875.0,"residual_loss_g":0,"yield_pct":0.0,"post_process_efficiency_pct":0.0,"operator":"OLD","machine_line":"MaterialPrep","status":"Complete","toll_processing":true,"processing_fee_usd":0.0,"est_revenue_usd":823000.0,"cogs_usd":0.0,"coa_status":"Passed","qa_hold":false,"notes":"Imported from MaterialPrep normalized partner workbook","source_sheet":"MaterialPrep","primary_metric_name":"total_socks","primary_metric_value":"","output_slot_count":4,"output_total_g":102875.0},{"run_date":"2026-02-06","state":"MI","license_name":"NEO Partner","client_name":"NEO Partner","batch_id_internal":"JaMa120125FOIL","metrc_package_id_input":"1689","metrc_package_id_output":"","metrc_manifest_or_transfer_id":"","method":"Post-Process","strain":"","product_type":"Vape Oil","downstream_product":"Disty Carts","process_stage":"Filling","intake_complete":true,"extraction_complete":true,"post_process_complete":true,"formulation_complete":true,"filling_complete":true,"packaging_complete":false,"ready_for_transfer":false,"input_material_type":"Dis","input_weight_g":2691.5,"intermediate_output_g":4862.0,"finished_output_g":4862.0,"residual_loss_g":0,"yield_pct":180.625,"post_process_efficiency_pct":0.0,"operator":"TP/JW","machine_line":"Filling","status":"Complete","toll_processing":true,"processing_fee_usd":0.0,"est_revenue_usd":38896.0,"cogs_usd":2153.2,"coa_status":"Pending","qa_hold":false,"notes":"Imported from Filling normalized partner workbook","source_sheet":"Filling","primary_metric_name":"load_efficiency","primary_metric_value":"TBD","output_slot_count":3,"output_total_g":4862.0}]""")
NEO_PARTNER_WASTE = json.loads(r"""[{"source_sheet":"Waste Log","waste_metrc_id":"1503","item_name":"Heads","reason":"Volitiles","net_weight_g":58.6,"physical_destruction_date":"2026-04-02"},{"source_sheet":"Waste Log","waste_metrc_id":"2805","item_name":"Heads","reason":"Volitiles","net_weight_g":90.7,"physical_destruction_date":"2026-04-02"},{"source_sheet":"Waste Log","waste_metrc_id":"2248","item_name":"NL - AIO","reason":"DEFECTS, AIO","net_weight_g":74.0,"physical_destruction_date":"2026-04-02"},{"source_sheet":"Waste Log","waste_metrc_id":"2817","item_name":"Azulene","reason":"byproduct","net_weight_g":1006.0,"physical_destruction_date":"2026-04-02"}]""")

def load_partner_seed_runs():
    return pd.DataFrame(NEO_PARTNER_RUNS)

def load_partner_seed_waste():
    return pd.DataFrame(NEO_PARTNER_WASTE)

def build_extraction_weekly_totals(run_df, waste_df=None):
    if run_df is None or run_df.empty:
        return pd.DataFrame()
    df = run_df.copy()
    df["run_date"] = pd.to_datetime(df["run_date"], errors="coerce")
    df["input_weight_g"] = pd.to_numeric(df.get("input_weight_g", 0), errors="coerce").fillna(0)
    df["finished_output_g"] = pd.to_numeric(df.get("finished_output_g", 0), errors="coerce").fillna(0)
    df["yield_pct"] = pd.to_numeric(df.get("yield_pct", 0), errors="coerce").fillna(0)
    df["est_revenue_usd"] = pd.to_numeric(df.get("est_revenue_usd", 0), errors="coerce").fillna(0)
    df["cogs_usd"] = pd.to_numeric(df.get("cogs_usd", 0), errors="coerce").fillna(0)
    df["week_start"] = df["run_date"].dt.to_period("W-MON").apply(lambda p: p.start_time if pd.notna(p) else pd.NaT)
    weekly = (df.groupby("week_start", dropna=True).agg(extraction_runs=("batch_id_internal", "count"), input_weight_g=("input_weight_g", "sum"), finished_output_g=("finished_output_g", "sum"), avg_yield_pct=("yield_pct", "mean"), est_revenue_usd=("est_revenue_usd", "sum"), cogs_usd=("cogs_usd", "sum"), toll_runs=("toll_processing", "sum"), qa_hold_runs=("qa_hold", "sum")).reset_index().sort_values("week_start", ascending=False))
    weekly["gross_margin_usd"] = weekly["est_revenue_usd"] - weekly["cogs_usd"]
    weekly["gross_margin_pct"] = weekly.apply(lambda r: ((r["gross_margin_usd"] / r["est_revenue_usd"]) * 100) if r["est_revenue_usd"] else 0, axis=1)
    if waste_df is not None and not waste_df.empty:
        wf = waste_df.copy()
        wf["physical_destruction_date"] = pd.to_datetime(wf["physical_destruction_date"], errors="coerce")
        wf["net_weight_g"] = pd.to_numeric(wf.get("net_weight_g", 0), errors="coerce").fillna(0)
        wf["week_start"] = wf["physical_destruction_date"].dt.to_period("W-MON").apply(lambda p: p.start_time if pd.notna(p) else pd.NaT)
        waste_weekly = wf.groupby("week_start", dropna=True)["net_weight_g"].sum().reset_index().rename(columns={"net_weight_g": "waste_weight_g"})
        weekly = weekly.merge(waste_weekly, on="week_start", how="left")
    else:
        weekly["waste_weight_g"] = 0.0
    weekly["waste_pct_of_input"] = weekly.apply(lambda r: ((r["waste_weight_g"] / r["input_weight_g"]) * 100) if r["input_weight_g"] else 0, axis=1)
    return weekly.fillna(0)

def build_executive_stage_rollup(run_df):
    if run_df is None or run_df.empty:
        return pd.DataFrame()
    df = run_df.copy()
    df["input_weight_g"] = pd.to_numeric(df.get("input_weight_g", 0), errors="coerce").fillna(0)
    df["finished_output_g"] = pd.to_numeric(df.get("finished_output_g", 0), errors="coerce").fillna(0)
    df["yield_pct"] = pd.to_numeric(df.get("yield_pct", 0), errors="coerce").fillna(0)
    return df.groupby("process_stage", dropna=False).agg(runs=("batch_id_internal", "count"), input_weight_g=("input_weight_g", "sum"), finished_output_g=("finished_output_g", "sum"), avg_yield_pct=("yield_pct", "mean")).reset_index().sort_values(["finished_output_g", "runs"], ascending=[False, False])

def build_operator_rollup(run_df):
    if run_df is None or run_df.empty:
        return pd.DataFrame()
    df = run_df.copy()
    df["finished_output_g"] = pd.to_numeric(df.get("finished_output_g", 0), errors="coerce").fillna(0)
    df["yield_pct"] = pd.to_numeric(df.get("yield_pct", 0), errors="coerce").fillna(0)
    return df.groupby("operator", dropna=False).agg(runs=("batch_id_internal", "count"), finished_output_g=("finished_output_g", "sum"), avg_yield_pct=("yield_pct", "mean")).reset_index().sort_values(["finished_output_g", "runs"], ascending=[False, False])

def build_waste_reason_rollup(waste_df):
    if waste_df is None or waste_df.empty:
        return pd.DataFrame()
    wf = waste_df.copy()
    wf["net_weight_g"] = pd.to_numeric(wf.get("net_weight_g", 0), errors="coerce").fillna(0)
    return wf.groupby("reason", dropna=False)["net_weight_g"].sum().reset_index().sort_values("net_weight_g", ascending=False)

def build_executive_snapshot(run_df, waste_df=None):
    weekly = build_extraction_weekly_totals(run_df, waste_df)
    if weekly.empty:
        return {}
    current = weekly.iloc[0]
    prior = weekly.iloc[1] if len(weekly) > 1 else None
    wow_output_delta = (current["finished_output_g"] - prior["finished_output_g"]) if prior is not None else 0.0
    wow_run_delta = (current["extraction_runs"] - prior["extraction_runs"]) if prior is not None else 0
    return {"week_start": str(pd.to_datetime(current["week_start"]).date()), "weekly_runs": int(current["extraction_runs"]), "weekly_input_g": float(current["input_weight_g"]), "weekly_output_g": float(current["finished_output_g"]), "weekly_avg_yield_pct": float(current["avg_yield_pct"]), "weekly_waste_g": float(current.get("waste_weight_g", 0)), "weekly_margin_pct": float(current.get("gross_margin_pct", 0)), "wow_output_delta_g": float(wow_output_delta), "wow_run_delta": int(wow_run_delta)}
