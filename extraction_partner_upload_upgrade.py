"""
=============================================================================
EXTRACTION PARTNER UPLOAD UPGRADE

Comprehensive refactor of the extraction partner file upload system for
Extraction Command Center (ECC) analytics.

Flow:
    upload → detect sheets/headers
           → normalize data
           → auto-map confidence check
           → if confident: append → success
           → if uncertain: show mapping UI
           → user maps columns
           → apply mapping
           → append to ECC
           → show results

CRITICAL:
- Do NOT remove existing extraction sections
- Do NOT modify session_state structure except to append to ecc_run_log
- Do NOT rewrite app architecture
- Preserve upload logic, column detection, ECC charts
=============================================================================
"""

import difflib
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st


# ─────────────────────────────────────────────────────────────────────────
# STEP 1: MULTI-SHEET WORKBOOK DETECTION & LOADING
# ─────────────────────────────────────────────────────────────────────────

def detect_header_row(df_no_header: pd.DataFrame, max_scan: int = 20) -> int:
    """
    Scan first N rows to find a likely header row.
    """
    max_scan = min(max_scan, len(df_no_header))
    header_keywords = {
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
        "stage",
        "metrc",
        "package",
        "coa",
        "status",
        "transfer",
        "manifest",
        "efficiency",
        "loss",
        "material",
        "processing",
        "fee",
        "revenue",
        "cogs",
        "notes",
        "hold",
        "toll",
    }
    best_score = -1
    best_row = 0
    for i in range(max_scan):
        row = df_no_header.iloc[i]
        row_text = " ".join(str(v).strip().lower() for v in row if pd.notna(v))
        if not row_text:
            continue
        keyword_score = sum(1 for kw in header_keywords if kw in row_text)
        numeric_count = sum(
            1
            for v in row
            if isinstance(v, (int, float))
            or (isinstance(v, str) and v.strip() and v.strip().replace(".", "").isdigit())
        )
        score = keyword_score * 10 - numeric_count
        if score > best_score:
            best_score = score
            best_row = i
    return best_row


def load_partner_file_multisheet(uploaded_file) -> Dict[str, pd.DataFrame]:
    file_name = str(getattr(uploaded_file, "name", "")).lower()
    uploaded_file.seek(0)
    raw = uploaded_file.read()
    uploaded_file.seek(0)
    sheets = {}
    if file_name.endswith((".xlsx", ".xls")):
        try:
            all_sheets = pd.read_excel(BytesIO(raw), sheet_name=None, header=None)
            for sheet_name, df in all_sheets.items():
                if df.empty:
                    continue
                header_row = detect_header_row(df, max_scan=20)
                uploaded_file.seek(0)
                sheet_df = pd.read_excel(BytesIO(raw), sheet_name=sheet_name, header=header_row)
                sheets[sheet_name] = sheet_df
        except Exception as e:
            st.error(f"Error reading Excel sheets: {e}")
            return {}
    else:
        try:
            df = pd.read_csv(BytesIO(raw))
            sheets["Data"] = df
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return {}
    return sheets


# ─────────────────────────────────────────────────────────────────────────
# STEP 2: COLUMN NAME NORMALIZATION & FUZZY MATCHING
# ─────────────────────────────────────────────────────────────────────────

def normalize_column_name(col: str) -> str:
    return (
        str(col)
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .replace(".", " ")
        .replace("(", " ")
        .replace(")", " ")
    )


def find_best_column_match(uploaded_col: str, target_col: str, threshold: float = 0.6) -> float:
    norm_uploaded = normalize_column_name(uploaded_col)
    norm_target = normalize_column_name(target_col)
    ratio = difflib.SequenceMatcher(None, norm_uploaded, norm_target).ratio()
    return ratio if ratio >= threshold else 0.0


def suggest_column_mapping(df_columns: List[str], target_columns: List[str]) -> Dict[str, str]:
    mapping = {}
    used_uploaded = set()
    for target_col in target_columns:
        best_match = None
        best_score = 0.0
        for uploaded_col in df_columns:
            if uploaded_col in used_uploaded:
                continue
            score = find_best_column_match(uploaded_col, target_col)
            if score > best_score:
                best_score = score
                best_match = uploaded_col
        if best_match and best_score >= 0.5:
            mapping[target_col] = best_match
            used_uploaded.add(best_match)
    return mapping


# ─────────────────────────────────────────────────────────────────────────
# STEP 3: WORKBOOK NORMALIZATION
# ─────────────────────────────────────────────────────────────────────────

def normalize_partner_extraction_workbook(
    sheets_dict: Dict[str, pd.DataFrame], confidence_threshold: float = 0.7
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict]:
    diagnostics = {
        "sheets_detected": list(sheets_dict.keys()),
        "sheets_processed": [],
        "header_rows_found": {},
        "columns_detected": {},
        "mapping_confidence": {},
        "rows_extracted": 0,
        "warnings": [],
    }
    ecc_run_columns = [
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
    partner_aliases = {
        "run_date": ["date in", "run date", "date", "extraction date", "start date"],
        "batch_id_internal": ["batch id", "batch", "run id", "internal batch"],
        "input_weight_g": ["input weight", "input weight (g)", "starting weight", "g"],
        "intermediate_output_g": ["intermediate output", "post extraction g"],
        "finished_output_g": ["output g", "finished output", "yield g", "final output"],
        "residual_loss_g": ["loss", "waste g", "residual loss"],
        "yield_pct": ["yield", "yield %", "yield pct", "efficiency"],
        "operator": ["operator", "tech", "technician"],
        "method": ["method", "extraction method", "process"],
        "product_type": ["product type", "output type", "product"],
        "process_stage": ["stage", "process stage", "step"],
        "status": ["status", "run status"],
        "notes": ["notes", "comments", "remarks"],
    }
    all_runs = []
    for sheet_name, df in sheets_dict.items():
        if df.empty:
            continue
        sheet_name_lower = sheet_name.lower()
        is_extraction = any(x in sheet_name_lower for x in ["extraction", "rotovap", "distillation"])
        is_waste = "waste" in sheet_name_lower
        if not (is_extraction or is_waste):
            diagnostics["warnings"].append(f"Skipped sheet '{sheet_name}' (unrecognized type)")
            continue
        diagnostics["sheets_processed"].append(sheet_name)
        diagnostics["columns_detected"][sheet_name] = list(df.columns)
        df.columns = [str(c).strip() for c in df.columns]
        norm_cols = {normalize_column_name(c): c for c in df.columns}
        sheet_mapping = {}
        confidence_scores = {}
        for ecc_col, aliases in partner_aliases.items():
            best_match = None
            best_score = 0.0
            for alias in aliases:
                norm_alias = normalize_column_name(alias)
                for norm_col, orig_col in norm_cols.items():
                    score = find_best_column_match(norm_col, norm_alias)
                    if score > best_score:
                        best_score = score
                        best_match = orig_col
            if best_match:
                sheet_mapping[ecc_col] = best_match
                confidence_scores[ecc_col] = best_score
        diagnostics["mapping_confidence"][sheet_name] = confidence_scores
        df_clean = df.dropna(how="all")
        run_data = {}
        for ecc_col, partner_col in sheet_mapping.items():
            if partner_col in df_clean.columns:
                if "date" in ecc_col:
                    run_data[ecc_col] = pd.to_datetime(df_clean[partner_col], errors="coerce")
                else:
                    run_data[ecc_col] = df_clean[partner_col]
        if run_data:
            run_df = pd.DataFrame(run_data)
            run_df = run_df.dropna(how="all")
            all_runs.append(run_df)
            diagnostics["rows_extracted"] += len(run_df)
    if all_runs:
        combined_runs = pd.concat(all_runs, ignore_index=True)
        for col in ecc_run_columns:
            if col not in combined_runs.columns:
                if col in ["state", "status", "method", "product_type"]:
                    combined_runs[col] = "Other"
                elif col in ["toll_processing", "qa_hold"]:
                    combined_runs[col] = False
                else:
                    combined_runs[col] = None
    else:
        combined_runs = pd.DataFrame(columns=ecc_run_columns)
    outputs_df = pd.DataFrame()
    waste_df = pd.DataFrame()
    return combined_runs, outputs_df, waste_df, pd.DataFrame(diagnostics), diagnostics


def compute_mapping_confidence(confidence_scores: Dict[str, float]) -> Tuple[float, bool]:
    if not confidence_scores:
        return 0.0, True
    scores = list(confidence_scores.values())
    avg_score = np.mean(scores) if scores else 0.0
    threshold = 0.75
    should_show_ui = avg_score < threshold
    return avg_score, should_show_ui


def render_manual_mapping_ui(df: pd.DataFrame, suggested_mapping: Dict[str, str], diagnostics: Dict) -> Dict[str, str]:
    st.warning("⚠️ Auto-mapping confidence is low. Please map columns manually below.")
    ecc_target_columns = [
        "run_date",
        "batch_id_internal",
        "input_weight_g",
        "intermediate_output_g",
        "finished_output_g",
        "yield_pct",
        "operator",
        "machine_line",
        "process_stage",
        "product_type",
        "downstream_product",
        "metrc_package_id_input",
        "metrc_package_id_output",
        "metrc_manifest_or_transfer_id",
        "method",
        "status",
        "coa_status",
        "qa_hold",
        "notes",
    ]
    uploaded_columns = list(df.columns)
    st.markdown("### 📋 Manual Column Mapping")
    st.caption("Select which uploaded column maps to each ECC field. (IGNORE if not applicable)")
    mapping = {}
    for ecc_col in ecc_target_columns:
        col1, col2, col3 = st.columns([2, 3, 1])
        with col1:
            st.write(f"**{ecc_col}**")
        with col2:
            suggested = suggested_mapping.get(ecc_col, "IGNORE")
            sample_text = ""
            if suggested != "IGNORE" and suggested in df.columns:
                sample_val = df[suggested].dropna().iloc[0] if len(df[suggested].dropna()) > 0 else ""
                sample_text = f" [sample: {sample_val}]"
            selected = st.selectbox(
                label=f"Map {ecc_col}",
                options=["IGNORE"] + uploaded_columns,
                index=0
                if suggested == "IGNORE"
                else (uploaded_columns.index(suggested) + 1 if suggested in uploaded_columns else 0),
                key=f"mapping_{ecc_col}",
                label_visibility="collapsed",
                help=f"Select the column to map to {ecc_col}{sample_text}",
            )
            mapping[ecc_col] = selected
        with col3:
            if suggested in uploaded_columns:
                st.caption("💡 suggested")
    return mapping


def render_default_field_selectors() -> Dict[str, str]:
    st.markdown("### 🏷️ Default Fields (if not in uploaded file)")
    col1, col2, col3 = st.columns(3)
    with col1:
        method = st.selectbox("Extraction Method", ["BHO", "CO2", "Rosin", "Ethanol"], key="default_method")
    with col2:
        state = st.selectbox("State / Jurisdiction", ["MA", "ME", "NY", "NJ", "MI", "NV", "CA", "Other"], key="default_state")
    with col3:
        client_name = st.text_input("Client Name", value="In House", key="default_client")
    col4, col5 = st.columns(2)
    with col4:
        status = st.selectbox("Status", ["Processing", "Complete", "Hold", "Failed"], key="default_status")
    with col5:
        coa_status = st.selectbox("COA Status", ["Pending", "Passed", "Failed", "Not Submitted"], key="default_coa_status")
    return {
        "method": method,
        "state": state,
        "client_name": client_name,
        "status": status,
        "coa_status": coa_status,
    }


def apply_mapping_to_dataframe(df: pd.DataFrame, mapping: Dict[str, str], defaults: Dict[str, str]) -> pd.DataFrame:
    ecc_df = pd.DataFrame()
    for ecc_col, uploaded_col in mapping.items():
        if uploaded_col == "IGNORE":
            if ecc_col in defaults:
                ecc_df[ecc_col] = defaults[ecc_col]
            else:
                ecc_df[ecc_col] = None
        else:
            if uploaded_col in df.columns:
                ecc_df[ecc_col] = df[uploaded_col]
            else:
                ecc_df[ecc_col] = None
    numeric_cols = [
        "input_weight_g",
        "intermediate_output_g",
        "finished_output_g",
        "residual_loss_g",
        "yield_pct",
        "post_process_efficiency_pct",
        "processing_fee_usd",
        "est_revenue_usd",
        "cogs_usd",
    ]
    for col in numeric_cols:
        if col in ecc_df.columns:
            ecc_df[col] = pd.to_numeric(ecc_df[col], errors="coerce")
    if "run_date" in ecc_df.columns:
        ecc_df["run_date"] = pd.to_datetime(ecc_df["run_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    ecc_df = ecc_df.dropna(how="all")
    return ecc_df


def deduplicate_and_append_to_ecc(
    new_runs: pd.DataFrame, existing_ecc_log: pd.DataFrame
) -> Tuple[pd.DataFrame, int, str]:
    if new_runs.empty:
        return existing_ecc_log, 0, "No rows to append."
    dedup_key = ["run_date", "batch_id_internal", "method"]
    new_runs = new_runs.copy()
    new_runs["_source"] = "uploaded"
    existing_ecc_log = existing_ecc_log.copy()
    existing_ecc_log["_source"] = "existing"
    combined = pd.concat([existing_ecc_log, new_runs], ignore_index=True)
    combined_deduped = combined.drop_duplicates(subset=dedup_key, keep="first")
    num_added = (combined_deduped["_source"] == "uploaded").sum()
    combined_deduped = combined_deduped.drop(columns=["_source"])
    msg = f"✅ Added {num_added} unique run(s) to Extraction Command Center."
    return combined_deduped, num_added, msg


def render_diagnostics_panel(diagnostics: Dict):
    with st.expander("🔍 Upload Diagnostics", expanded=False):
        st.markdown("#### Sheets Detected")
        st.write(", ".join(diagnostics.get("sheets_detected", [])))
        st.markdown("#### Sheets Processed")
        st.write(", ".join(diagnostics.get("sheets_processed", [])))
        st.markdown("#### Rows Extracted")
        st.write(diagnostics.get("rows_extracted", 0))
        if diagnostics.get("warnings"):
            st.warning("⚠️ Warnings:")
            for warn in diagnostics["warnings"]:
                st.write(f"- {warn}")
        if diagnostics.get("columns_detected"):
            st.markdown("#### Columns Detected Per Sheet")
            for sheet, cols in diagnostics["columns_detected"].items():
                st.write(f"**{sheet}**: {', '.join(cols[:10])}..." if len(cols) > 10 else f"**{sheet}**: {', '.join(cols)}")
        if diagnostics.get("mapping_confidence"):
            st.markdown("#### Mapping Confidence Scores")
            for sheet, scores in diagnostics["mapping_confidence"].items():
                avg = np.mean(list(scores.values())) if scores else 0
                st.write(f"**{sheet}**: {avg:.1%} average confidence")


def render_extraction_partner_upload_ui():
    st.markdown("### 📤 Extraction Partner File Upload")
    st.caption(
        "Upload extraction workbooks (Excel with multiple sheets, or CSV). Supports: Extraction, Rotovap, Distillation, Filling, Packaging sheets."
    )
    uploaded_file = st.file_uploader(
        "Choose extraction workbook (CSV, XLSX, XLS)", type=["csv", "xlsx", "xls"], key="ecc_partner_upload"
    )
    if uploaded_file is None:
        st.info("👆 Upload a file to begin")
        return
    with st.spinner("Loading and analyzing workbook…"):
        sheets_dict = load_partner_file_multisheet(uploaded_file)
        if not sheets_dict:
            st.error("❌ Could not read file. Check format.")
            return
        runs_df, outputs_df, waste_df, _, diagnostics = normalize_partner_extraction_workbook(sheets_dict)
        if runs_df.empty:
            st.error("❌ No extraction run data found in file.")
            return
    confidence_scores = {}
    for sheet, scores in diagnostics.get("mapping_confidence", {}).items():
        confidence_scores.update(scores)
    avg_confidence, show_manual_ui = compute_mapping_confidence(confidence_scores)
    st.info(f"Mapping confidence: **{avg_confidence:.0%}**")
    if show_manual_ui:
        st.warning("Low confidence: Please verify column mappings below.")
        first_sheet_df = list(sheets_dict.values())[0]
        target_cols = [
            "run_date",
            "batch_id_internal",
            "input_weight_g",
            "finished_output_g",
            "yield_pct",
            "operator",
            "method",
            "product_type",
            "status",
        ]
        suggested_mapping = suggest_column_mapping(list(first_sheet_df.columns), target_cols)
        manual_mapping = render_manual_mapping_ui(first_sheet_df, suggested_mapping, diagnostics)
        defaults = render_default_field_selectors()
        if st.button("Convert to ECC Run Log", type="primary", key="ecc_apply_mapping"):
            with st.spinner("Applying mapping…"):
                ecc_runs = apply_mapping_to_dataframe(first_sheet_df, manual_mapping, defaults)
            if "ecc_run_log" not in st.session_state:
                st.session_state.ecc_run_log = pd.DataFrame()
            existing = st.session_state.ecc_run_log.copy()
            updated, num_added, msg = deduplicate_and_append_to_ecc(ecc_runs, existing)
            st.session_state.ecc_run_log = updated
            st.success(msg)
            st.markdown("#### Preview of Added Rows")
            st.dataframe(ecc_runs.head(20), use_container_width=True, hide_index=True)
    else:
        st.success("✅ Auto-mapping successful. Appending to ECC…")
        defaults = {
            "state": "Other",
            "client_name": "In House",
            "status": "Processing",
            "method": "BHO",
            "coa_status": "Pending",
        }
        auto_mapping = {col: col for col in runs_df.columns if col != "IGNORE"}
        ecc_runs = apply_mapping_to_dataframe(runs_df, auto_mapping, defaults)
        if "ecc_run_log" not in st.session_state:
            st.session_state.ecc_run_log = pd.DataFrame()
        existing = st.session_state.ecc_run_log.copy()
        updated, num_added, msg = deduplicate_and_append_to_ecc(ecc_runs, existing)
        st.session_state.ecc_run_log = updated
        st.success(msg)
        st.markdown(f"#### {num_added} Runs Mapped & Added")
        st.dataframe(ecc_runs.head(20), use_container_width=True, hide_index=True)
    render_diagnostics_panel(diagnostics)
