from __future__ import annotations

from io import BytesIO

import pandas as pd


def _norm_col(name: str) -> str:
    return (
        str(name)
        .strip()
        .lower()
        .replace("/", " ")
        .replace("-", " ")
        .replace(".", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace("__", "_")
    )


def load_partner_file(uploaded_file) -> pd.DataFrame:
    """Read CSV/XLSX partner extraction uploads into a dataframe."""
    raw = uploaded_file.getvalue()
    name = str(getattr(uploaded_file, "name", "")).lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(raw))
    return pd.read_csv(BytesIO(raw))


def looks_like_partner_extraction_file(uploaded_file) -> bool:
    """Heuristic check for normalized extraction partner workbook exports."""
    try:
        df = load_partner_file(uploaded_file)
    except Exception:
        return False
    cols = {_norm_col(c) for c in df.columns}
    partner_markers = {
        "run_date",
        "run date",
        "input_weight_g",
        "input weight g",
        "finished_output_g",
        "finished output g",
    }
    return len(cols.intersection(partner_markers)) >= 3


def _pick(df: pd.DataFrame, aliases: list[str], default=None):
    col_map = {_norm_col(c): c for c in df.columns}
    for alias in aliases:
        key = _norm_col(alias)
        if key in col_map:
            return df[col_map[key]]
    return default


def map_partner_runs_to_ecc_shape(df: pd.DataFrame) -> pd.DataFrame:
    """Map partner-normalized extraction runs into ECC run-log columns."""
    out = pd.DataFrame()
    out["run_date"] = pd.to_datetime(_pick(df, ["run_date", "run date", "date"])).dt.date.astype(str)
    out["state"] = _pick(df, ["state"], default="Other")
    out["license_name"] = _pick(df, ["license_name", "facility", "facility_name"], default="")
    out["client_name"] = _pick(df, ["client_name", "client", "partner"], default="In House")
    out["batch_id_internal"] = _pick(df, ["batch_id_internal", "batch_id", "batch", "run_id"], default="")
    out["metrc_package_id_input"] = _pick(df, ["metrc_package_id_input", "input_package_id"], default="")
    out["metrc_package_id_output"] = _pick(df, ["metrc_package_id_output", "output_package_id"], default="")
    out["metrc_manifest_or_transfer_id"] = _pick(df, ["metrc_manifest_or_transfer_id", "transfer_id"], default="")
    out["method"] = _pick(df, ["method", "extraction_method"], default="BHO")
    out["product_type"] = _pick(df, ["product_type", "output_type"], default="Other")
    out["downstream_product"] = _pick(df, ["downstream_product", "downstream"], default="N/A")
    out["process_stage"] = _pick(df, ["process_stage", "stage"], default="Intake")
    out["input_material_type"] = _pick(df, ["input_material_type", "input_type"], default="Other")
    out["input_weight_g"] = pd.to_numeric(_pick(df, ["input_weight_g", "input_weight", "input_g"], default=0), errors="coerce").fillna(0)
    out["intermediate_output_g"] = pd.to_numeric(_pick(df, ["intermediate_output_g", "intermediate_g"], default=0), errors="coerce").fillna(0)
    out["finished_output_g"] = pd.to_numeric(_pick(df, ["finished_output_g", "finished_output", "output_g"], default=0), errors="coerce").fillna(0)
    out["residual_loss_g"] = pd.to_numeric(_pick(df, ["residual_loss_g", "residual_g", "waste_g"], default=0), errors="coerce").fillna(0)
    out["yield_pct"] = pd.to_numeric(_pick(df, ["yield_pct", "yield"], default=0), errors="coerce").fillna(0)
    out["post_process_efficiency_pct"] = pd.to_numeric(_pick(df, ["post_process_efficiency_pct", "post_efficiency_pct"], default=0), errors="coerce").fillna(0)
    out["operator"] = _pick(df, ["operator"], default="")
    out["machine_line"] = _pick(df, ["machine_line", "line"], default="")
    out["status"] = _pick(df, ["status"], default="Processing")
    out["toll_processing"] = pd.Series(_pick(df, ["toll_processing", "is_toll"], default=False)).astype(bool)
    out["processing_fee_usd"] = pd.to_numeric(_pick(df, ["processing_fee_usd", "processing_fee"], default=0), errors="coerce").fillna(0)
    out["est_revenue_usd"] = pd.to_numeric(_pick(df, ["est_revenue_usd", "revenue_usd"], default=0), errors="coerce").fillna(0)
    out["cogs_usd"] = pd.to_numeric(_pick(df, ["cogs_usd", "cogs"], default=0), errors="coerce").fillna(0)
    out["coa_status"] = _pick(df, ["coa_status"], default="Pending")
    out["qa_hold"] = pd.Series(_pick(df, ["qa_hold"], default=False)).astype(bool)
    out["notes"] = _pick(df, ["notes"], default="")

    stage_order = ["Intake", "Extraction", "Post-Process", "Formulation", "Filling", "Packaged", "Transferred"]

    def _stage_done(stage_name: str, current: str) -> bool:
        try:
            return stage_order.index(str(current)) >= stage_order.index(stage_name)
        except ValueError:
            return False

    out["intake_complete"] = out["process_stage"].apply(lambda s: _stage_done("Intake", s))
    out["extraction_complete"] = out["process_stage"].apply(lambda s: _stage_done("Extraction", s))
    out["post_process_complete"] = out["process_stage"].apply(lambda s: _stage_done("Post-Process", s))
    out["formulation_complete"] = out["process_stage"].apply(lambda s: _stage_done("Formulation", s))
    out["filling_complete"] = out["process_stage"].apply(lambda s: _stage_done("Filling", s))
    out["packaging_complete"] = out["process_stage"].apply(lambda s: _stage_done("Packaged", s))
    out["ready_for_transfer"] = out["process_stage"].apply(lambda s: str(s) == "Transferred")
    return out
