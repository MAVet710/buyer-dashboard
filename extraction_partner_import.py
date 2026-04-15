from __future__ import annotations

from io import BytesIO

import pandas as pd

# Signature fragment (non-functional owner mark).
# __  ______             __ ____________


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


def _detect_header_row(preview_df: pd.DataFrame) -> int:
    """Find likely header row for files that contain report metadata preamble."""
    header_tokens = {
        "run_date",
        "run date",
        "date",
        "batch_id_internal",
        "batch id",
        "batch",
        "method",
        "input_weight_g",
        "input weight",
        "finished_output_g",
        "finished output",
        "operator",
        "state",
    }
    best_idx = 0
    best_score = float("-inf")
    scan_rows = min(len(preview_df), 60)
    for idx in range(scan_rows):
        values = [str(v).strip() for v in preview_df.iloc[idx].tolist()]
        cleaned = [v for v in values if v and v.lower() != "nan"]
        normed = {_norm_col(v) for v in cleaned}
        header_hits = len(normed.intersection(header_tokens))
        non_empty = len(cleaned)
        numeric_like = 0
        for v in cleaned:
            try:
                float(str(v).replace(",", ""))
                numeric_like += 1
            except Exception:
                continue
        numeric_ratio = (numeric_like / non_empty) if non_empty else 1.0

        next_row_has_data = False
        if idx + 1 < scan_rows:
            next_vals = [str(v).strip() for v in preview_df.iloc[idx + 1].tolist()]
            next_non_empty = [v for v in next_vals if v and v.lower() != "nan"]
            next_row_has_data = len(next_non_empty) >= 2

        score = (header_hits * 4.0) + min(non_empty, 20) * 0.05 + (1.0 if next_row_has_data else 0.0)
        if numeric_ratio > 0.6:
            score -= 2.0
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx if best_score >= 2.5 else 0


def load_partner_file(uploaded_file) -> pd.DataFrame:
    """Read CSV/XLSX partner extraction uploads into a dataframe."""
    raw = uploaded_file.getvalue()
    name = str(getattr(uploaded_file, "name", "")).lower()
    if name.endswith((".xlsx", ".xls")):
        preview = pd.read_excel(BytesIO(raw), header=None, dtype=str)
        header_row = _detect_header_row(preview)
        return pd.read_excel(BytesIO(raw), header=header_row)
    preview = pd.read_csv(BytesIO(raw), header=None, dtype=str, on_bad_lines="skip")
    header_row = _detect_header_row(preview)
    return pd.read_csv(BytesIO(raw), header=header_row)


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
        "date in",
        "batch id",
        "yield %",
        "yield",
        "new metrc 1",
    }
    return len(cols.intersection(partner_markers)) >= 3


def _pick(df: pd.DataFrame, aliases: list[str], default=None):
    col_map = {_norm_col(c): c for c in df.columns}
    for alias in aliases:
        key = _norm_col(alias)
        if key in col_map:
            return df[col_map[key]]
    return default


def _pick_first_series(df: pd.DataFrame, aliases: list[str], default="") -> pd.Series:
    picked = _pick(df, aliases, default=None)
    if picked is None:
        return pd.Series([default] * len(df))
    if isinstance(picked, pd.Series):
        return picked
    return pd.Series([picked] * len(df))


def _sum_numeric_columns(df: pd.DataFrame, aliases: list[str], startswith: tuple[str, ...] = ()) -> pd.Series:
    col_map = {_norm_col(c): c for c in df.columns}
    matched_cols: list[str] = []
    for alias in aliases:
        key = _norm_col(alias)
        if key in col_map:
            matched_cols.append(col_map[key])
    if startswith:
        for norm_name, original in col_map.items():
            if any(norm_name.startswith(prefix) for prefix in startswith):
                matched_cols.append(original)
    seen = set()
    unique_cols = [c for c in matched_cols if not (c in seen or seen.add(c))]
    if not unique_cols:
        return pd.Series([0.0] * len(df))
    numeric_df = df[unique_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    return numeric_df.sum(axis=1)


def _infer_downstream_product(df: pd.DataFrame) -> pd.Series:
    base = _pick_first_series(df, ["downstream_product", "downstream"], default="")
    if base.astype(str).str.strip().ne("").any():
        return base.replace("", "N/A").fillna("N/A")
    col_map = {_norm_col(c): c for c in df.columns}
    item_cols = [
        original
        for norm_name, original in col_map.items()
        if norm_name.startswith("new item name")
    ]
    if not item_cols:
        return pd.Series(["N/A"] * len(df))
    joined = (
        df[item_cols]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .str.lower()
    )
    downstream = pd.Series(["Bulk Distillate"] * len(df))
    carts_mask = joined.str.contains(r"\bcart|cartridge|vape", regex=True)
    disposable_mask = joined.str.contains(r"\bdisposable|dispo", regex=True)
    downstream[carts_mask] = "Disty Carts"
    downstream[disposable_mask] = "Disty Disposables"
    downstream[(~carts_mask) & (~disposable_mask) & joined.str.strip().eq("")] = "N/A"
    return downstream


def map_partner_runs_to_ecc_shape(df: pd.DataFrame) -> pd.DataFrame:
    """Map partner-normalized extraction runs into ECC run-log columns."""
    out = pd.DataFrame()
    out["run_date"] = pd.to_datetime(
        _pick(df, ["run_date", "run date", "date", "date in"]),
        errors="coerce",
    ).dt.date.astype(str)
    out["state"] = _pick(df, ["state"], default="Other")
    out["license_name"] = _pick(df, ["license_name", "facility", "facility_name"], default="")
    out["client_name"] = _pick(df, ["client_name", "client", "partner"], default="In House")
    out["batch_id_internal"] = _pick(
        df,
        ["batch_id_internal", "batch_id", "batch", "run_id", "new batch id 1", "new batch id"],
        default="",
    )
    out["metrc_package_id_input"] = _pick(df, ["metrc_package_id_input", "input_package_id", "metrc"], default="")
    out["metrc_package_id_output"] = _pick(
        df,
        ["metrc_package_id_output", "output_package_id", "new metrc 1", "metrc 1", "metrc.1"],
        default="",
    )
    out["metrc_manifest_or_transfer_id"] = _pick(df, ["metrc_manifest_or_transfer_id", "transfer_id"], default="")
    out["method"] = _pick(df, ["method", "extraction_method"], default="Ethanol")
    out["product_type"] = _pick(df, ["product_type", "output_type", "item", "new item name 1"], default="Other")
    out["downstream_product"] = _infer_downstream_product(df)
    out["process_stage"] = _pick(df, ["process_stage", "stage"], default="Intake")
    out["input_material_type"] = _pick(df, ["input_material_type", "input_type", "material", "item"], default="Other")
    out["input_weight_g"] = pd.to_numeric(
        _pick(df, ["input_weight_g", "input_weight", "input_g", "g"], default=0),
        errors="coerce",
    ).fillna(0)
    out["intermediate_output_g"] = pd.to_numeric(_pick(df, ["intermediate_output_g", "intermediate_g"], default=0), errors="coerce").fillna(0)
    explicit_finished = pd.to_numeric(
        _pick(df, ["finished_output_g", "finished_output", "output_g"], default=0),
        errors="coerce",
    ).fillna(0)
    new_output_sum = _sum_numeric_columns(
        df,
        aliases=["new g 1", "new g"],
        startswith=("new g",),
    )
    out["finished_output_g"] = explicit_finished.where(explicit_finished > 0, new_output_sum)
    out["residual_loss_g"] = pd.to_numeric(
        _pick(df, ["residual_loss_g", "residual_g", "waste_g", "waste"], default=0),
        errors="coerce",
    ).fillna(0)
    out["yield_pct"] = pd.to_numeric(_pick(df, ["yield_pct", "yield", "yield %", "yield (%)"], default=0), errors="coerce").fillna(0)
    out["post_process_efficiency_pct"] = pd.to_numeric(
        _pick(df, ["post_process_efficiency_pct", "post_efficiency_pct", "efficiency"], default=0),
        errors="coerce",
    ).fillna(0)
    out["operator"] = _pick(df, ["operator", "user"], default="")
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
