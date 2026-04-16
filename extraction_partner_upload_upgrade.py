from __future__ import annotations

import difflib
import re
from io import BytesIO
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st


ECC_TARGET_FIELDS = [
    "run_date",
    "batch_id_internal",
    "method",
    "state",
    "license_name",
    "client_name",
    "input_weight_g",
    "intermediate_output_g",
    "finished_output_g",
    "residual_loss_g",
    "yield_pct",
    "post_process_efficiency_pct",
    "operator",
    "machine_line",
    "status",
    "coa_status",
    "qa_hold",
    "notes",
]

ECC_REQUIRED_COLUMNS = [
    "run_date",
    "state",
    "license_name",
    "client_name",
    "batch_id_internal",
    "metrc_package_id_input",
    "metrc_package_id_output",
    "metrc_manifest_or_transfer_id",
    "method",
    "strain",
    "product_type",
    "downstream_product",
    "process_stage",
    "intake_complete",
    "extraction_complete",
    "post_process_complete",
    "formulation_complete",
    "filling_complete",
    "packaging_complete",
    "ready_for_transfer",
    "input_material_type",
    "input_weight_g",
    "intermediate_output_g",
    "finished_output_g",
    "residual_loss_g",
    "yield_pct",
    "post_process_efficiency_pct",
    "operator",
    "machine_line",
    "status",
    "toll_processing",
    "processing_fee_usd",
    "est_revenue_usd",
    "cogs_usd",
    "coa_status",
    "qa_hold",
    "notes",
]


def detect_header_row(sheet: pd.DataFrame) -> int:
    max_scan = min(20, len(sheet))
    keywords = {
        "date",
        "run",
        "input",
        "output",
        "weight",
        "yield",
        "operator",
        "method",
        "batch",
        "product",
        "metrc",
        "package",
        "coa",
        "status",
        "client",
        "state",
    }
    best_row = 0
    best_score = float("-inf")

    for idx in range(max_scan):
        row_vals = [str(v).strip() for v in sheet.iloc[idx].tolist() if str(v).strip() and str(v).strip().lower() != "nan"]
        if not row_vals:
            continue

        score = 0.0
        for val in row_vals:
            norm = normalize_column_name(val)
            if any(k in norm for k in keywords):
                score += 2.0
            if len(norm) >= 3 and not norm.isdigit():
                score += 0.3
            if norm.isdigit() or re.fullmatch(r"[\d\.\-\/]+", norm):
                score -= 1.2
        if row_vals and all(re.fullmatch(r"[\d\.\-\/]+", str(v).strip()) for v in row_vals):
            score -= 4.0

        if score > best_score:
            best_score = score
            best_row = idx
    return best_row


def load_partner_file_multisheet(uploaded_file: Any) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    file_name = str(getattr(uploaded_file, "name", "")).lower()
    raw = uploaded_file.getvalue()
    diagnostics: dict[str, Any] = {"sheets": {}, "warnings": []}
    sheet_frames: dict[str, pd.DataFrame] = {}

    if file_name.endswith(".csv"):
        df = pd.read_csv(BytesIO(raw))
        sheet_frames["CSV"] = df
        diagnostics["sheets"]["CSV"] = {
            "detected_header_row": 0,
            "rows": int(len(df)),
            "columns": [str(c) for c in df.columns],
        }
        return sheet_frames, diagnostics

    first_pass = pd.read_excel(BytesIO(raw), sheet_name=None, header=None)
    for sheet_name, raw_sheet in first_pass.items():
        header_idx = detect_header_row(raw_sheet)
        parsed = pd.read_excel(BytesIO(raw), sheet_name=sheet_name, header=header_idx)
        parsed = parsed.dropna(axis=1, how="all").dropna(axis=0, how="all")
        if parsed.empty:
            diagnostics["warnings"].append(f"{sheet_name}: no data after header normalization")
            continue
        sheet_frames[sheet_name] = parsed
        diagnostics["sheets"][sheet_name] = {
            "detected_header_row": int(header_idx),
            "rows": int(len(parsed)),
            "columns": [str(c) for c in parsed.columns],
        }
    return sheet_frames, diagnostics


def normalize_column_name(column: Any) -> str:
    text = str(column).strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def find_best_column_match(column: str, options: list[str]) -> tuple[str | None, float]:
    col_norm = normalize_column_name(column)
    best_name = None
    best_score = 0.0
    for option in options:
        opt_norm = normalize_column_name(option)
        score = difflib.SequenceMatcher(None, col_norm, opt_norm).ratio()
        if score > best_score:
            best_name = option
            best_score = score
    return best_name, best_score


def suggest_column_mapping(columns: list[str], options: list[str]) -> dict[str, dict[str, Any]]:
    suggestions: dict[str, dict[str, Any]] = {}
    for target in options:
        match, score = find_best_column_match(target, columns)
        suggestions[target] = {
            "source": match if score >= 0.5 else "IGNORE",
            "score": float(score),
        }
    return suggestions


def normalize_partner_extraction_workbook(uploaded_file: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
    sheets, diagnostics = load_partner_file_multisheet(uploaded_file)
    normalized_sheets = []
    for sheet_name, sheet_df in sheets.items():
        df = sheet_df.copy()
        df.columns = [normalize_column_name(c) for c in df.columns]
        df["__source_sheet"] = sheet_name
        normalized_sheets.append(df)

    if not normalized_sheets:
        return pd.DataFrame(), diagnostics

    combined = pd.concat(normalized_sheets, ignore_index=True, sort=False)
    combined = combined.dropna(axis=0, how="all")
    diagnostics["rows_extracted"] = int(len(combined))
    diagnostics["normalized_columns"] = [str(c) for c in combined.columns]
    return combined, diagnostics


def compute_mapping_confidence(mapping: dict[str, dict[str, Any]]) -> float:
    scores = [float(v.get("score", 0.0)) for v in mapping.values()]
    if not scores:
        return 0.0
    return float(np.mean(scores))


def render_manual_mapping_ui(
    source_df: pd.DataFrame,
    suggested_mapping: dict[str, dict[str, Any]],
    target_fields: list[str],
) -> dict[str, str]:
    st.warning("Auto-mapping confidence is low. Please confirm field mapping.")
    source_cols = [str(c) for c in source_df.columns]
    mapping: dict[str, str] = {}
    opts = ["IGNORE"] + source_cols

    for field in target_fields:
        suggested = str(suggested_mapping.get(field, {}).get("source", "IGNORE"))
        default_idx = opts.index(suggested) if suggested in opts else 0
        selected = st.selectbox(f"{field} → source column", opts, index=default_idx, key=f"ecc_map_{field}")
        mapping[field] = selected

        if selected != "IGNORE" and selected in source_df.columns:
            sample_vals = source_df[selected].dropna().astype(str).head(3).tolist()
            if sample_vals:
                st.caption(f"Sample values: {', '.join(sample_vals)}")
    return mapping


def render_default_field_selectors() -> dict[str, Any]:
    st.markdown("#### Default values for missing mapped fields")
    c1, c2, c3 = st.columns(3)
    with c1:
        method = st.selectbox("Default Method", ["BHO", "CO2", "Rosin", "Ethanol"], index=0, key="ecc_default_method")
        state = st.selectbox("Default State", ["MA", "ME", "NY", "NJ", "MI", "NV", "CA", "Other"], index=0, key="ecc_default_state")
    with c2:
        client_name = st.text_input("Default Client Name", value="In House", key="ecc_default_client")
        status = st.selectbox("Default Status", ["Processing", "Queued", "Complete", "Hold", "Failed"], index=0, key="ecc_default_status")
    with c3:
        coa_status = st.selectbox("Default COA Status", ["Pending", "Passed", "Failed", "Not Submitted"], index=0, key="ecc_default_coa")
    return {
        "method": method,
        "state": state,
        "client_name": client_name,
        "status": status,
        "coa_status": coa_status,
    }


def apply_mapping_to_dataframe(source_df: pd.DataFrame, mapping: dict[str, str], defaults: dict[str, Any]) -> pd.DataFrame:
    out = pd.DataFrame(index=source_df.index)
    for target in ECC_TARGET_FIELDS:
        src = mapping.get(target, "IGNORE")
        if src != "IGNORE" and src in source_df.columns:
            out[target] = source_df[src]
        elif target in defaults:
            out[target] = defaults[target]
        else:
            out[target] = np.nan

    out["run_date"] = pd.to_datetime(out["run_date"], errors="coerce").dt.date.astype(str)
    out["run_date"] = out["run_date"].replace("NaT", "")
    for num_col in ["input_weight_g", "intermediate_output_g", "finished_output_g", "residual_loss_g", "yield_pct", "post_process_efficiency_pct"]:
        out[num_col] = pd.to_numeric(out[num_col], errors="coerce").fillna(0.0)

    out["yield_pct"] = np.where(
        out["yield_pct"] > 0,
        out["yield_pct"],
        np.where(out["input_weight_g"] > 0, (out["finished_output_g"] / out["input_weight_g"]) * 100.0, 0.0),
    )
    out["post_process_efficiency_pct"] = np.where(
        out["post_process_efficiency_pct"] > 0,
        out["post_process_efficiency_pct"],
        np.where(out["intermediate_output_g"] > 0, (out["finished_output_g"] / out["intermediate_output_g"]) * 100.0, 0.0),
    )

    out["process_stage"] = "Intake"
    out["intake_complete"] = False
    out["extraction_complete"] = False
    out["post_process_complete"] = False
    out["formulation_complete"] = False
    out["filling_complete"] = False
    out["packaging_complete"] = False
    out["ready_for_transfer"] = False
    out["metrc_package_id_input"] = ""
    out["metrc_package_id_output"] = ""
    out["metrc_manifest_or_transfer_id"] = ""
    out["strain"] = ""
    out["product_type"] = "Other"
    out["downstream_product"] = "N/A"
    out["input_material_type"] = "Other"
    out["license_name"] = out["license_name"].fillna("")
    out["toll_processing"] = False
    out["processing_fee_usd"] = 0.0
    out["est_revenue_usd"] = 0.0
    out["cogs_usd"] = 0.0
    out["qa_hold"] = out["qa_hold"].fillna(False).astype(bool)
    out["notes"] = out["notes"].fillna("")
    out["batch_id_internal"] = out["batch_id_internal"].fillna("").astype(str)
    out["method"] = out["method"].fillna(defaults.get("method", "BHO")).replace("", defaults.get("method", "BHO"))
    out["state"] = out["state"].fillna(defaults.get("state", "Other")).replace("", defaults.get("state", "Other"))
    out["client_name"] = out["client_name"].fillna(defaults.get("client_name", "In House")).replace("", defaults.get("client_name", "In House"))
    out["status"] = out["status"].fillna(defaults.get("status", "Processing")).replace("", defaults.get("status", "Processing"))
    out["coa_status"] = out["coa_status"].fillna(defaults.get("coa_status", "Pending")).replace("", defaults.get("coa_status", "Pending"))

    return out[ECC_REQUIRED_COLUMNS].copy()


def deduplicate_and_append_to_ecc(mapped_df: pd.DataFrame) -> tuple[int, int]:
    if "ecc_run_log" not in st.session_state or not isinstance(st.session_state.ecc_run_log, pd.DataFrame):
        st.session_state.ecc_run_log = pd.DataFrame(columns=ECC_REQUIRED_COLUMNS)

    existing = st.session_state.ecc_run_log.copy()
    for col in ECC_REQUIRED_COLUMNS:
        if col not in existing.columns:
            existing[col] = np.nan

    key_cols = ["run_date", "batch_id_internal", "method"]
    existing_keys = (
        existing[key_cols]
        .fillna("")
        .astype(str)
        .drop_duplicates()
        .assign(_join_key=lambda d: d["run_date"] + "|" + d["batch_id_internal"] + "|" + d["method"])
    )

    incoming = mapped_df.copy()
    for col in ECC_REQUIRED_COLUMNS:
        if col not in incoming.columns:
            incoming[col] = np.nan
    incoming["_join_key"] = (
        incoming["run_date"].fillna("").astype(str)
        + "|"
        + incoming["batch_id_internal"].fillna("").astype(str)
        + "|"
        + incoming["method"].fillna("").astype(str)
    )
    new_rows = incoming[~incoming["_join_key"].isin(existing_keys["_join_key"])].drop(columns=["_join_key"])
    merged = pd.concat([existing[ECC_REQUIRED_COLUMNS], new_rows[ECC_REQUIRED_COLUMNS]], ignore_index=True)
    st.session_state.ecc_run_log = merged
    return int(len(new_rows)), int(len(mapped_df) - len(new_rows))


def render_diagnostics_panel(diagnostics: dict[str, Any]) -> None:
    with st.expander("Upload diagnostics", expanded=False):
        st.write("Detected sheets:", list(diagnostics.get("sheets", {}).keys()))
        if diagnostics.get("sheets"):
            st.json(diagnostics["sheets"])
        if diagnostics.get("mapping_confidence") is not None:
            st.write("Mapping confidence:", round(float(diagnostics["mapping_confidence"]), 3))
        if diagnostics.get("warnings"):
            for warning in diagnostics["warnings"]:
                st.warning(warning)
        st.write("Rows extracted:", diagnostics.get("rows_extracted", 0))


def render_extraction_partner_upload_ui() -> None:
    st.subheader("Raw Data Upload Staging")
    uploaded = st.file_uploader("Upload extraction runs file", type=["csv", "xlsx", "xls"], key="ecc_upload")
    if uploaded is None:
        return

    try:
        source_df, diagnostics = normalize_partner_extraction_workbook(uploaded)
    except Exception as exc:
        st.error(f"Could not read uploaded run log: {exc}")
        return

    if source_df.empty:
        st.warning("No rows found in uploaded workbook.")
        render_diagnostics_panel(diagnostics)
        return

    suggestions = suggest_column_mapping([str(c) for c in source_df.columns], ECC_TARGET_FIELDS)
    mapping_confidence = compute_mapping_confidence(suggestions)
    diagnostics["mapping_confidence"] = mapping_confidence
    defaults = render_default_field_selectors()

    if mapping_confidence < 0.75:
        mapping = render_manual_mapping_ui(source_df, suggestions, ECC_TARGET_FIELDS)
    else:
        st.success(f"Auto-mapping confidence: {mapping_confidence:.2f}")
        mapping = {k: str(v.get("source", "IGNORE")) for k, v in suggestions.items()}

    mapped_df = apply_mapping_to_dataframe(source_df, mapping, defaults)
    st.caption("Mapped run preview")
    st.dataframe(mapped_df.head(100), use_container_width=True, hide_index=True)

    if st.button("Append mapped runs to Extraction Command Center", type="primary", key="ecc_append_partner_rows"):
        added, duplicates = deduplicate_and_append_to_ecc(mapped_df)
        st.success(f"Added {added} runs to Extraction Command Center")
        if duplicates:
            st.info(f"Skipped {duplicates} duplicate runs based on run_date + batch_id_internal + method.")
        st.dataframe(mapped_df.head(100), use_container_width=True, hide_index=True)

    render_diagnostics_panel(diagnostics)
