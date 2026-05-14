from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
import logging
import os
import traceback

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from reports.competitor_report import _build_competitor_intelligence_report_pdf
from services.menu_capture_assistant import MenuCaptureSession
from services.competitor_html_parser import NORMALIZED_SCHEMA, process_competitor_files_batch
from utils.dataframe_helpers import _safe_numeric_mean, _safe_numeric_series, _safe_numeric_sum

logger = logging.getLogger(__name__)


def _init_state() -> None:
    defaults = {
        "competitor_menu_snapshots_df": pd.DataFrame(),
        "competitor_file_processing_results": [],
        "competitor_current_snapshot_metadata": {},
        "competitor_data_quality": {},
        "competitor_last_processed_at": "",
        "competitor_price_summary_df": pd.DataFrame(),
        "competitor_assortment_summary_df": pd.DataFrame(),
        "competitor_promo_summary_df": pd.DataFrame(),
        "competitor_recommendations": [],
        "competitor_uploaded_files_cache": [],
        "competitor_capture_menu_url": "",
        "competitor_review_workbook_bytes": b"",
        "competitor_product_candidates_df": pd.DataFrame(),
        "competitor_raw_extracted_text_df": pd.DataFrame(),
        "competitor_category_summary_df": pd.DataFrame(),
        "competitor_parser_warnings_df": pd.DataFrame(),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _has_snapshot() -> bool:
    df = st.session_state.get("competitor_menu_snapshots_df")
    return isinstance(df, pd.DataFrame) and not df.empty


def _ensure_cleaned_schema(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    for col in NORMALIZED_SCHEMA:
        if col not in out.columns:
            out[col] = None
    return out[NORMALIZED_SCHEMA]


def _build_review_workbook_payload(files: list[dict], competitor_override: str, snap_date: str, default_category: str) -> dict:
    batch = process_competitor_files_batch(files, snapshot_date=snap_date, competitor_override=competitor_override)
    cleaned = _ensure_cleaned_schema(batch["cleaned_df"])
    raw_df = batch["raw_df"]
    cand_df = batch["candidate_df"]
    file_df = batch["file_df"]
    warnings_df = batch["warnings_df"]

    if file_df.empty:
        file_df = pd.DataFrame(columns=["source_file_name","detected_competitor","detected_platform","detected_category","rows_extracted","rows_saved","rejected_candidates","status","warning","completeness_status"])
    cat_summary = cleaned.groupby(["competitor_name", "category", "subcategory", "menu_platform"], dropna=False).agg(rows_saved=("product_name", "count")).reset_index() if not cleaned.empty else pd.DataFrame(columns=["competitor_name","category","subcategory","menu_platform","rows_saved"])
    dq = {"files_processed": len(file_df), "total_rows_extracted": int(file_df["rows_extracted"].sum()) if "rows_extracted" in file_df else 0, "rows_saved": len(cleaned), "missing_category_count": int(cleaned["category"].fillna("").isin(["", "Unspecified"]).sum()) if "category" in cleaned else 0, "missing_brand_count": int(cleaned["brand"].fillna("").eq("").sum()) if "brand" in cleaned else 0, "low_confidence_count": int(cleaned["capture_confidence"].astype(str).str.lower().eq("low").sum()) if "capture_confidence" in cleaned else 0}
    dq_rows = [{"metric": k, "value": v, "notes": ""} for k, v in dq.items()]

    uploaded_count = len(files)
    competitor_count = int(cleaned["competitor_name"].nunique()) if not cleaned.empty else 0
    category_count = int(cleaned["category"].nunique()) if not cleaned.empty else 0
    if uploaded_count > 3 and competitor_count <= 1:
        dq_rows.append({"metric": "batch_warning", "value": 1, "notes": "Batch processing may have dropped files. Only one competitor was found."})
    if uploaded_count > 3 and category_count <= 1:
        dq_rows.append({"metric": "batch_warning", "value": 1, "notes": "Batch processing may have dropped categories. Only one category was found."})
    if len(cand_df) > max(20, len(cleaned) * 2):
        dq_rows.append({"metric": "batch_warning", "value": 1, "notes": "Parser extracted candidates but rejected most rows. Review parser warnings."})
    if len(file_df) < uploaded_count:
        dq_rows.append({"metric": "batch_error", "value": 1, "notes": "Some uploaded files were not processed."})

    dq_df = pd.DataFrame(dq_rows)
    out = BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        raw_df.to_excel(writer, index=False, sheet_name="Raw_Extracted_Text")
        cand_df.to_excel(writer, index=False, sheet_name="Product_Candidates")
        cleaned.to_excel(writer, index=False, sheet_name="Cleaned_Competitor_Snapshot")
        file_df.to_excel(writer, index=False, sheet_name="File_Processing_Results")
        dq_df.to_excel(writer, index=False, sheet_name="Data_Quality")
        cat_summary.to_excel(writer, index=False, sheet_name="Category_Summary")
        warnings_df.to_excel(writer, index=False, sheet_name="Parser_Warnings")
    return {"workbook_bytes": out.getvalue(), "cleaned_df": cleaned, "raw_df": raw_df, "candidate_df": cand_df, "file_df": file_df, "dq": dq, "cat_summary": cat_summary}


def _build_analysis_tables() -> None:
    snap = st.session_state.get("competitor_menu_snapshots_df")
    if not isinstance(snap, pd.DataFrame) or snap.empty:
        st.session_state["competitor_price_summary_df"] = pd.DataFrame()
        st.session_state["competitor_assortment_summary_df"] = pd.DataFrame()
        st.session_state["competitor_promo_summary_df"] = pd.DataFrame()
        return
    df = snap.copy()
    df["effective_price"] = _safe_numeric_series(df, "effective_price")
    df["regular_price"] = _safe_numeric_series(df, "regular_price")
    df["discount_pct"] = _safe_numeric_series(df, "discount_pct")
    price_cols = [c for c in ["competitor_name", "category", "subcategory", "package_size_label"] if c in df.columns]
    if price_cols and "effective_price" in df.columns:
        st.session_state["competitor_price_summary_df"] = df.groupby(price_cols, dropna=False).agg(
            sku_count=("product_name", "count"),
            avg_regular_price=("regular_price", "mean"),
            avg_effective_price=("effective_price", "mean"),
            avg_discount_pct=("discount_pct", "mean"),
            lowest_price=("effective_price", "min"),
            highest_price=("effective_price", "max"),
        ).reset_index()
    if "category" in df.columns:
        st.session_state["competitor_assortment_summary_df"] = df.groupby(["competitor_name", "category", "subcategory", "package_size_label"], dropna=False).agg(
            rows_saved=("product_name", "count"),
            brand_count=("brand", "nunique"),
            package_sizes=("package_size_label", "nunique"),
        ).reset_index()
    promo = df[df["discount_pct"] > 0] if "discount_pct" in df.columns else pd.DataFrame()
    if isinstance(promo, pd.DataFrame) and not promo.empty:
        st.session_state["competitor_promo_summary_df"] = promo.groupby(["competitor_name", "category", "subcategory"], dropna=False).agg(
            promo_count=("product_name", "count"),
            avg_discount=("discount_pct", "mean"),
            max_discount=("discount_pct", "max"),
        ).reset_index()


def render_competitor_intelligence_center() -> None:
    _init_state()
    st.header("🕵️ Competitor Intelligence Center")
    tabs = st.tabs(["Overview", "Upload + Process", "Parsed Data Review", "Price Intelligence", "Assortment Gaps", "Promo Pressure", "Strategic Recommendations", "Data Quality", "Export Report"])

    with tabs[0]:
        snap = st.session_state.get("competitor_menu_snapshots_df")
        dq = st.session_state.get("competitor_data_quality", {})
        files = st.session_state.get("competitor_file_processing_results", [])
        k = st.columns(5)
        k[0].metric("Competitors Detected", int(snap["competitor_name"].nunique()) if isinstance(snap, pd.DataFrame) and "competitor_name" in snap.columns and not snap.empty else 0)
        k[1].metric("Files Processed", sum(1 for r in files if r.get("status") == "processed"))
        k[2].metric("Categories Captured", int(snap["category"].nunique()) if isinstance(snap, pd.DataFrame) and "category" in snap.columns and not snap.empty else 0)
        k[3].metric("Products Captured", len(snap) if isinstance(snap, pd.DataFrame) else 0)
        k[4].metric("Rows Needing Review", int(dq.get("rows_needing_review", 0)))
        k2 = st.columns(5)
        k2[0].metric("Average Effective Price", round(_safe_numeric_mean(snap, "effective_price"), 2) if isinstance(snap, pd.DataFrame) else 0)
        k2[1].metric("Promo Count", int(_safe_numeric_sum(snap, "has_promo")) if isinstance(snap, pd.DataFrame) else 0)
        k2[2].metric("Categories With Incomplete Data", int(dq.get("missing_category_count", 0)))
        k2[3].metric("Shell Files Needing Companion HTML", int(sum(1 for r in files if any("shell" in str(w).lower() for w in r.get("warnings", [])))))
        k2[4].metric("Last Processed", st.session_state.get("competitor_last_processed_at") or "N/A")
        st.info(f"Workflow: {'✅ Upload' if st.session_state.get('competitor_uploaded_files_cache') else '⬜ Upload'} → {'✅ Process' if files else '⬜ Process'} → {'✅ Review' if _has_snapshot() else '⬜ Review'} → {'✅ Analyze' if isinstance(st.session_state.get('competitor_price_summary_df'), pd.DataFrame) and not st.session_state.get('competitor_price_summary_df').empty else '⬜ Analyze'} → {'✅ Export' if _has_snapshot() else '⬜ Export'}")

    with tabs[1]:
        st.markdown("Recommended workflow:\n1. Open competitor menu in browser.\n2. Confirm age gate manually.\n3. Select one menu category.\n4. Save page as HTML.\n5. Repeat for other categories.\n6. Upload all files here.\n7. Convert HTML to Review Workbook.")
        st.caption("For Dutchie embedded menus, the parent page may only contain the menu shell. If detected, upload companion iframe HTML from the saved page _files folder.")
        snap_date = st.date_input("Snapshot Date", value=date.today())
        competitor_override = st.text_input("Competitor Override (optional)")
        behavior = st.radio("Replace or Merge", ["Replace", "Merge"], horizontal=True)
        uploaded_files = st.file_uploader("Saved HTML Upload", type=["html", "htm", "mhtml", "txt", "csv", "xlsx", "xls", "json"], accept_multiple_files=True)
        if uploaded_files:
            st.session_state["competitor_uploaded_files_cache"] = [{"file_name": f.name, "file_bytes": f.getvalue(), "file_size": f.size} for f in uploaded_files]
        c1, c2, c3 = st.columns(3)
        convert = c1.button("Convert HTML to Review Workbook")
        if c2.button("Clear Upload Cache"):
            st.session_state["competitor_uploaded_files_cache"] = []
        if c3.button("Clear Saved Snapshot"):
            st.session_state["competitor_menu_snapshots_df"] = pd.DataFrame()
            st.session_state["competitor_review_workbook_bytes"] = b""
        if convert:
            payload = _build_review_workbook_payload(st.session_state.get("competitor_uploaded_files_cache", []), competitor_override, str(snap_date), "Unspecified")
            st.session_state["competitor_review_workbook_bytes"] = payload["workbook_bytes"]
            st.session_state["competitor_menu_snapshots_df"] = payload["cleaned_df"]
            st.session_state["competitor_product_candidates_df"] = payload["candidate_df"]
            st.session_state["competitor_raw_extracted_text_df"] = payload["raw_df"]
            st.session_state["competitor_file_processing_results"] = payload["file_df"].to_dict("records")
            st.session_state["competitor_data_quality"] = payload["dq"]
            st.session_state["competitor_category_summary_df"] = payload["cat_summary"]
            st.session_state["competitor_last_processed_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            _build_analysis_tables()
        if st.session_state.get("competitor_review_workbook_bytes"):
            st.download_button("Download Review Workbook XLSX", st.session_state["competitor_review_workbook_bytes"], "competitor_review_workbook.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if st.button("Use Cleaned Snapshot for Analysis"):
            _build_analysis_tables()

        imported_workbook = st.file_uploader("Upload Previously Cleaned Review Workbook", type=["xlsx"], key="review_workbook_import")
        if imported_workbook is not None:
            try:
                imported_cleaned = pd.read_excel(BytesIO(imported_workbook.getvalue()), sheet_name="Cleaned_Competitor_Snapshot")
                imported_cleaned = _ensure_cleaned_schema(imported_cleaned)
                st.session_state["competitor_menu_snapshots_df"] = imported_cleaned
                _build_analysis_tables()
                st.success("Loaded Cleaned_Competitor_Snapshot from workbook.")
            except Exception as ex:
                st.error(f"Workbook import failed: {ex}")


    with tabs[2]:
        st.subheader("Parsed Data Review")
        snap = st.session_state.get("competitor_menu_snapshots_df")
        if not isinstance(snap, pd.DataFrame) or snap.empty:
            st.info("No competitor snapshot has been processed yet. Upload and process files first.")
        else:
            df = snap.copy()
            for col in ["needs_review", "has_promo", "missing_price", "missing_package_size"]:
                if col in df.columns:
                    df[col] = df[col].fillna(False).astype(bool)
            c = st.columns(7)
            c[0].metric("total rows", len(df)); c[1].metric("rows needing review", int(df["needs_review"].sum()) if "needs_review" in df.columns else 0)
            c[2].metric("missing price rows", int(df["missing_price"].sum()) if "missing_price" in df.columns else 0); c[3].metric("missing size rows", int(df["missing_package_size"].sum()) if "missing_package_size" in df.columns else 0)
            c[4].metric("missing category rows", int((df["category"].fillna("") == "").sum()) if "category" in df.columns else 0); c[5].metric("low-confidence rows", int((df["capture_confidence"].astype(str).str.lower() == "low").sum()) if "capture_confidence" in df.columns else 0)
            c[6].metric("duplicates merged", int(st.session_state.get("competitor_data_quality", {}).get("duplicate_rows_merged", 0)))
            if "needs_review" in df.columns and int(df["needs_review"].sum()) > 0:
                st.warning("Some parsed rows need review before using this data for final decisions.")
            q = st.text_input("Search product name / brand / raw text")
            if q:
                mask = pd.Series(False, index=df.index)
                for col in ["product_name", "brand", "raw_text"]:
                    if col in df.columns:
                        mask = mask | df[col].astype(str).str.contains(q, case=False, na=False)
                df = df[mask]
            if "category" in df.columns:
                cat_filter = st.multiselect("Filter category", sorted([x for x in df["category"].dropna().astype(str).unique() if x]))
                if cat_filter:
                    df = df[df["category"].isin(cat_filter)]
            if "subcategory" in df.columns:
                sub_filter = st.multiselect("Filter subcategory", sorted([x for x in df["subcategory"].dropna().astype(str).unique() if x]))
                if sub_filter:
                    df = df[df["subcategory"].isin(sub_filter)]
            if "category_confidence" in df.columns:
                conf_filter = st.multiselect("Filter category confidence", sorted([x for x in df["category_confidence"].dropna().astype(str).unique() if x]))
                if conf_filter:
                    df = df[df["category_confidence"].isin(conf_filter)]
            keep = ["competitor_name","category","subcategory","product_type","category_confidence","category_source","brand","product_name","package_size_label","regular_price","sale_price","effective_price","discount_pct","promo_text","thc_pct","thc_mg","thca_pct","cbd_pct","cbd_mg","cbg_mg","tac_pct","tac_mg","terpene_pct","strain_type","availability_status","menu_platform","source_file_name","capture_confidence","needs_review","missing_fields"]
            show = [c for c in keep if c in df.columns]
            edited = st.data_editor(df[show], use_container_width=True, num_rows="dynamic")
            b1, b2 = st.columns(2)
            if b1.button("Save Review Edits"):
                st.session_state["competitor_menu_snapshots_df"] = edited
            if b2.button("Recalculate Snapshot Analysis"):
                _build_analysis_tables()
            out = BytesIO();
            with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
                edited.to_excel(writer, index=False, sheet_name="cleaned_snapshot")
            st.download_button("Download Cleaned Snapshot XLSX", out.getvalue(), "competitor_snapshot_cleaned.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with tabs[3]:
        st.subheader("Price Intelligence")
        _build_analysis_tables()
        price = st.session_state.get("competitor_price_summary_df")
        if not isinstance(price, pd.DataFrame) or price.empty:
            st.info("No price intelligence available yet.")
        else:
            st.dataframe(price, use_container_width=True)

    with tabs[4]:
        assort = st.session_state.get("competitor_assortment_summary_df")
        if isinstance(assort, pd.DataFrame) and not assort.empty:
            st.dataframe(assort, use_container_width=True)
        else:
            st.info("Assortment depth may be incomplete because one or more category captures are incomplete or unknown.")

    with tabs[5]:
        promo = st.session_state.get("competitor_promo_summary_df")
        if isinstance(promo, pd.DataFrame) and not promo.empty:
            st.dataframe(promo, use_container_width=True)
        else:
            st.info("No promo rows detected in saved snapshot.")

    with tabs[6]:
        recs = []
        snap = st.session_state.get("competitor_menu_snapshots_df")
        if isinstance(snap, pd.DataFrame) and not snap.empty:
            if "discount_pct" in snap.columns and _safe_numeric_mean(snap, "discount_pct") >= 10:
                recs.append("[Pricing] Flower pricing has heavy promo pressure. Review eighth and 14g positioning before new buys.")
            if "subcategory" in snap.columns:
                sub_mix = snap.groupby(["category", "subcategory"], dropna=False).size().reset_index(name="sku_count").sort_values("sku_count", ascending=False)
                if not sub_mix.empty:
                    top = sub_mix.iloc[0]
                    recs.append(f"[Subcategory] {top['category']} shows strongest depth in {top['subcategory']} ({int(top['sku_count'])} SKUs).")
            if "package_size_label" in snap.columns and int((snap["package_size_label"].fillna("") == "").sum()) > 0:
                recs.append("[Data Quality] Several rows are missing package size, so package-size comparison needs review.")
        if not recs:
            recs.append("[Opportunity Plays] Continue capturing complete category snapshots to improve recommendation confidence.")
        st.session_state["competitor_recommendations"] = recs
        for rec in recs:
            st.write(f"- {rec}")

    with tabs[7]:
        st.subheader("Data Quality")
        result_df = pd.DataFrame(st.session_state.get("competitor_file_processing_results", []))
        if not result_df.empty:
            st.dataframe(result_df, use_container_width=True)
        snap = st.session_state.get("competitor_menu_snapshots_df")
        if isinstance(snap, pd.DataFrame) and not snap.empty and "category" in snap.columns:
            cat = snap.groupby(["competitor_name", "category", "subcategory"], dropna=False).agg(rows_saved=("product_name", "count")).reset_index()
            st.dataframe(cat, use_container_width=True)

    with tabs[8]:
        if not _has_snapshot():
            st.info("Process competitor files before exporting a report.")
        else:
            payload = {
                "competitor_snapshot_df": st.session_state.get("competitor_menu_snapshots_df"),
                "file_processing_results": st.session_state.get("competitor_file_processing_results"),
                "data_quality": st.session_state.get("competitor_data_quality", {}),
                "category_summary": st.session_state.get("competitor_assortment_summary_df"),
                "price_summary": st.session_state.get("competitor_price_summary_df"),
                "promo_summary": st.session_state.get("competitor_promo_summary_df"),
                "assortment_summary": st.session_state.get("competitor_assortment_summary_df"),
                "recommendations": st.session_state.get("competitor_recommendations", []),
                "snapshot_metadata": st.session_state.get("competitor_current_snapshot_metadata", {}),
                "last_processed": st.session_state.get("competitor_last_processed_at", ""),
            }
            st.download_button("Export Competitor Intelligence Report", data=_build_competitor_intelligence_report_pdf(payload), file_name=f"competitor_intelligence_report_{datetime.utcnow().strftime('%Y%m%d')}.pdf", mime="application/pdf")
