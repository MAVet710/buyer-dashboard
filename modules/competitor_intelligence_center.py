from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
import json
import logging
import os
import re
import traceback
import zipfile

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from reports.competitor_report import _build_competitor_intelligence_report_pdf
from services.menu_capture_assistant import MenuCaptureSession
from services.competitor_html_parser import NORMALIZED_SCHEMA, process_competitor_files_batch
from services.inventory_normalizer import load_inventory_file, normalize_inventory_for_competitor_comparison
from services.inventory_state import get_active_inventory_df
from services.competitor_report_narrative import (
    build_assortment_narrative,
    build_data_quality_narrative,
    build_executive_recommendations,
    build_market_read,
    build_opportunity_risk_narrative,
    build_price_intelligence_narrative,
    build_promo_pressure_narrative,
)
from utils.dataframe_helpers import _safe_numeric_mean, _safe_numeric_series, _safe_numeric_sum

logger = logging.getLogger(__name__)
_DUTCHIE_MAX_COMPANION_SIZE = 3_000_000


def _category_from_name(value: str) -> str:
    s = (value or "").lower()
    if "pre-roll" in s or "preroll" in s:
        return "Pre-Rolls"
    if "flower" in s:
        return "Flower"
    if "concentrate" in s:
        return "Concentrates"
    if "edible" in s:
        return "Edibles"
    if "vape" in s:
        return "Vapes"
    return "Unspecified"


def _is_likely_product_resource(text: str, name: str) -> tuple[bool, list[str]]:
    lowered = f"{name} {text}".lower()
    markers = []
    for m in ['data-testid="product-list-item"', "add to cart", "product-list-item", "product-card", "thc", "cbd", "$"]:
        if m in lowered:
            markers.append(m)
    potency_pattern = bool(re.search(r"\b(thc|cbd|potency)\b", lowered))
    return bool(markers or potency_pattern), markers


def build_dutchie_capture_bundle(parent_files, companion_files_or_zips) -> dict:
    parents, companions, warnings = [], [], []
    allowed_ext = {".html", ".htm", ".txt", ".json"}
    for pf in parent_files or []:
        html = (pf.getvalue() or b"").decode("utf-8", errors="ignore")
        source_url_match = re.search(r"https?://[^\"'\\s>]+", html)
        source_url = source_url_match.group(0) if source_url_match else ""
        expected_folder = re.sub(r"\.html?$", "_files", pf.name, flags=re.IGNORECASE)
        parents.append(
            {
                "source_file_name": pf.name,
                "competitor_name": "Unknown",
                "category": _category_from_name(pf.name),
                "source_url": source_url,
                "detected_platform": "dutchie_embedded",
                "expected_folder_hint": expected_folder,
                "file_bytes": pf.getvalue(),
            }
        )
    for cf in companion_files_or_zips or []:
        name = cf.name
        if name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(BytesIO(cf.getvalue())) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        if ".." in info.filename or info.filename.startswith("/"):
                            warnings.append(f"Skipped unsafe ZIP path: {info.filename}")
                            continue
                        ext = os.path.splitext(info.filename)[1].lower()
                        if ext not in allowed_ext:
                            continue
                        if info.file_size > _DUTCHIE_MAX_COMPANION_SIZE:
                            warnings.append(f"Skipped large companion file: {info.filename}")
                            continue
                        payload = zf.read(info.filename)
                        text = payload.decode("utf-8", errors="ignore")
                        likely, markers = _is_likely_product_resource(text[:50000], info.filename)
                        companions.append({"source_file_name": os.path.basename(info.filename), "inside_zip_name": info.filename, "file_bytes": payload, "likely_product_resource": likely, "detected_product_card_markers": markers, "folder_hint": info.filename.split('/')[0]})
            except Exception as ex:
                warnings.append(f"ZIP could not be inspected: {name} ({ex})")
        else:
            payload = cf.getvalue()
            text = payload.decode("utf-8", errors="ignore")
            likely, markers = _is_likely_product_resource(text[:50000], name)
            companions.append({"source_file_name": name, "inside_zip_name": "", "file_bytes": payload, "likely_product_resource": likely, "detected_product_card_markers": markers, "folder_hint": name.split('/')[0]})

    matches, unmatched = [], []
    for c in companions:
        candidate_parent = None
        hay = f"{c.get('inside_zip_name','')} {c.get('source_file_name','')}".lower()
        for p in parents:
            if p["expected_folder_hint"].lower() in hay or re.sub(r"\.html?$", "", p["source_file_name"].lower()) in hay:
                candidate_parent = p["source_file_name"]
                break
        if not candidate_parent and len(parents) == 1 and c.get("likely_product_resource"):
            candidate_parent = parents[0]["source_file_name"]
        if candidate_parent:
            matches.append({"parent_file_name": candidate_parent, "companion_file_name": c["source_file_name"], "inside_zip_name": c.get("inside_zip_name", "")})
        else:
            unmatched.append(c["source_file_name"])
    return {"parents": parents, "companions": companions, "matches": matches, "unmatched_companions": unmatched, "warnings": warnings}


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
        "competitor_our_inventory_df": pd.DataFrame(),
        "competitor_our_inventory_source_name": "",
        "competitor_our_inventory_uploaded_at": "",
        "competitor_comparison_summary_df": pd.DataFrame(),
        "competitor_category_gap_df": pd.DataFrame(),
        "competitor_subcategory_gap_df": pd.DataFrame(),
        "competitor_brand_overlap_df": pd.DataFrame(),
        "competitor_package_size_gap_df": pd.DataFrame(),
        "competitor_price_gap_df": pd.DataFrame(),
        "competitor_opportunity_risk_df": pd.DataFrame(),
        "competitor_market_read_text": "",
        "competitor_executive_summary_text": "",
        "competitor_dutchie_bundle": {},
        "competitor_dutchie_bundle_results": [],
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


def _ensure_competitor_snapshot_schema(df: pd.DataFrame) -> pd.DataFrame:
    required_columns = [
        "competitor_name","snapshot_date","menu_platform","source_type","source_file_name","source_url","category","subcategory","product_type","category_confidence","category_source","product_name","normalized_product_name","brand","package_size_label","package_size_g","package_size_mg","package_count","regular_price","sale_price","effective_price","discount_pct","promo_text","has_promo","thc_pct","thc_mg","thca_pct","cbd_pct","cbd_mg","cbg_pct","cbg_mg","tac_pct","tac_mg","terpene_pct","strain_type","availability_status","product_url","raw_text","capture_confidence","needs_review","missing_fields","duplicate_count","captured_at",
    ]
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=required_columns)
    out = df.copy()
    defaults = {
        "competitor_name": "Unknown",
        "snapshot_date": "",
        "menu_platform": "Unknown",
        "source_type": "",
        "source_file_name": "",
        "source_url": "",
        "category": "Unspecified",
        "subcategory": "Unspecified",
        "product_type": "",
        "category_confidence": "",
        "category_source": "",
        "product_name": "",
        "brand": "",
        "package_size_label": "",
        "promo_text": "",
        "has_promo": False,
        "strain_type": "",
        "availability_status": "",
        "product_url": "",
        "raw_text": "",
        "capture_confidence": "",
        "needs_review": False,
        "missing_fields": "",
        "duplicate_count": 0,
    }
    numeric_cols = ["package_size_g","package_size_mg","package_count","regular_price","sale_price","effective_price","discount_pct","thc_pct","thc_mg","thca_pct","cbd_pct","cbd_mg","cbg_pct","cbg_mg","tac_pct","tac_mg","terpene_pct"]
    for col in required_columns:
        if col not in out.columns:
            out[col] = defaults.get(col, 0.0 if col in numeric_cols else "")
    for col, default_value in defaults.items():
        out[col] = out[col].fillna(default_value)
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    out["has_promo"] = out["has_promo"].fillna(False).astype(bool)
    out["needs_review"] = out["needs_review"].fillna(False).astype(bool)
    out["duplicate_count"] = pd.to_numeric(out["duplicate_count"], errors="coerce").fillna(0).astype(int)
    out["normalized_product_name"] = out.get("normalized_product_name", "").fillna("")
    missing_norm = out["normalized_product_name"].astype(str).str.strip().eq("")
    out.loc[missing_norm, "normalized_product_name"] = out.loc[missing_norm, "product_name"].fillna("").astype(str).str.strip().str.lower()
    out["captured_at"] = out["captured_at"].fillna("")
    missing_captured_at = out["captured_at"].astype(str).str.strip().eq("")
    out.loc[missing_captured_at, "captured_at"] = datetime.utcnow().isoformat() + "Z"
    return out[required_columns]


def _merge_into_competitor_snapshot(new_rows_df, source_label: str = "unknown", mode: str = "merge") -> pd.DataFrame:
    st.session_state["competitor_last_merge_skipped"] = False
    existing = _ensure_competitor_snapshot_schema(st.session_state.get("competitor_menu_snapshots_df"))
    if not isinstance(new_rows_df, pd.DataFrame):
        st.warning("No valid competitor rows were available to merge.")
        st.session_state["competitor_last_merge_skipped"] = True
        return existing
    inventory_like_cols = {"our_product_name", "our_category", "our_brand", "our_effective_price", "quantity_on_hand", "days_on_hand", "cost", "inventory_value"}
    incoming_cols = set(new_rows_df.columns)
    if len(inventory_like_cols.intersection(incoming_cols)) >= 2 and not ({"product_name", "competitor_name"} & incoming_cols):
        st.error("Inventory data cannot be merged into competitor snapshot. It was saved for comparison only.")
        st.session_state["competitor_last_merge_skipped"] = True
        return existing
    incoming = _ensure_competitor_snapshot_schema(new_rows_df)
    if incoming.empty:
        st.warning("No valid competitor rows were available to merge.")
        st.session_state["competitor_last_merge_skipped"] = True
        return existing
    mode = (mode or "merge").strip().lower()
    dedupe_cols = ["competitor_name", "snapshot_date", "category", "subcategory", "normalized_product_name", "brand", "package_size_label", "effective_price"]
    completeness_cols = ["product_name", "normalized_product_name", "brand", "package_size_label", "effective_price", "raw_text", "product_url", "source_file_name"]
    incoming["source_type"] = incoming["source_type"].fillna("").replace("", source_label)
    incoming["captured_at"] = incoming["captured_at"].fillna(datetime.utcnow().isoformat() + "Z")

    base = existing.copy()
    if mode == "replace_entire":
        base = pd.DataFrame(columns=existing.columns)
    elif mode == "replace_matching_competitor_category" and not incoming.empty:
        candidate_keys = incoming[["competitor_name", "category"]].copy()
        reliable = ~(
            candidate_keys["competitor_name"].astype(str).str.strip().isin(["", "Unknown"])
            | candidate_keys["category"].astype(str).str.strip().isin(["", "Unspecified"])
        )
        keys = candidate_keys[reliable].drop_duplicates()
        if keys.empty:
            st.warning("Replace matching competitor/category skipped because incoming rows do not have reliable competitor/category values.")
            mode = "merge"
        else:
            keep_mask = pd.Series(True, index=base.index)
            for _, row in keys.iterrows():
                keep_mask &= ~((base["competitor_name"] == row["competitor_name"]) & (base["category"] == row["category"]))
            base = base[keep_mask].copy()

    combined = pd.concat([base, incoming], ignore_index=True)
    dedupe_key_parts = []
    for c in dedupe_cols:
        if c not in combined.columns:
            combined[c] = ""
        dedupe_key_parts.append(combined[c].fillna("").astype(str).str.strip())
    combined["_dedupe_key"] = pd.concat(dedupe_key_parts, axis=1).agg("||".join, axis=1)
    filled_completeness = combined[completeness_cols].fillna("").astype(str).apply(lambda s: s.str.strip())
    combined["_completeness"] = filled_completeness.ne("").sum(axis=1)
    combined["_dup_size"] = combined.groupby("_dedupe_key")["_dedupe_key"].transform("size")
    combined["duplicate_count"] = pd.to_numeric(combined["duplicate_count"], errors="coerce").fillna(0).astype(int)
    deduped = (
        combined.sort_values(["_dedupe_key", "_completeness"], ascending=[True, False])
        .drop_duplicates("_dedupe_key", keep="first")
        .copy()
    )
    deduped["duplicate_count"] = (
        pd.to_numeric(deduped.get("duplicate_count", 0), errors="coerce").fillna(0).astype(int)
        + pd.to_numeric(deduped["_dup_size"], errors="coerce").fillna(1).astype(int)
        - 1
    )
    if "source_file_name" in deduped.columns:
        sources = combined.groupby("_dedupe_key", dropna=False)["source_file_name"].apply(
            lambda s: " | ".join(sorted({x.strip() for x in s.fillna("").astype(str) if x.strip()}))
        )
        deduped = deduped.drop(columns=["source_file_name"]).join(sources, on="_dedupe_key").rename(columns={"source_file_name": "source_file_name"})
    deduped = deduped.drop(columns=[c for c in ["_dedupe_key", "_completeness", "_dup_size"] if c in deduped.columns], errors="ignore")
    deduped = _ensure_competitor_snapshot_schema(deduped)
    st.session_state["competitor_menu_snapshots_df"] = deduped
    st.session_state["competitor_last_processed_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    st.session_state["competitor_snapshot_dirty"] = True
    return deduped


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


def _prepare_competitor_comparison_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    defaults = {
        "competitor_name": "",
        "category": "Unspecified",
        "subcategory": "Unspecified",
        "brand": "",
        "product_name": "",
        "package_size_label": "",
        "effective_price": 0.0,
        "regular_price": 0.0,
        "sale_price": 0.0,
        "discount_pct": 0.0,
        "promo_text": "",
        "capture_confidence": "Unknown",
        "needs_review": False,
    }
    for col, value in defaults.items():
        if col not in out.columns:
            out[col] = value
    out["effective_price"] = pd.to_numeric(out["effective_price"], errors="coerce").fillna(0.0)
    out["regular_price"] = pd.to_numeric(out["regular_price"], errors="coerce").fillna(0.0)
    out["sale_price"] = pd.to_numeric(out["sale_price"], errors="coerce").fillna(0.0)
    out["discount_pct"] = pd.to_numeric(out["discount_pct"], errors="coerce").fillna(0.0)
    out["promo_text"] = out["promo_text"].fillna("").astype(str)
    out["needs_review"] = out["needs_review"].fillna(False).astype(bool)
    has_existing_promo = "has_promo" in df.columns if isinstance(df, pd.DataFrame) else False
    if not has_existing_promo:
        promo_regex = r"(sale|deal|special|offer|promo|2\s*for|bundle|discount)"
        out["has_promo"] = (
            (out["discount_pct"] > 0)
            | ((out["sale_price"] > 0) & (out["regular_price"] > 0) & (out["sale_price"] < out["regular_price"]))
            | (out["promo_text"].str.strip() != "")
            | (out["promo_text"].str.contains(promo_regex, case=False, na=False, regex=True))
        )
    else:
        out["has_promo"] = out["has_promo"].fillna(False).astype(bool)
    out["has_promo"] = out["has_promo"].fillna(False).astype(bool)
    return out


def _prepare_our_inventory_comparison_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    aliases = {
        "our_category": ["category"],
        "our_subcategory": ["subcategory"],
        "our_brand": ["brand"],
        "our_product_name": ["product_name", "name", "sku_name"],
        "our_package_size_label": ["package_size_label", "package_size", "size"],
        "our_effective_price": ["effective_price", "price", "unit_price"],
        "our_regular_price": ["regular_price", "list_price"],
        "our_sale_price": ["sale_price"],
        "our_discount_pct": ["discount_pct", "discount_percent"],
        "our_has_promo": ["has_promo"],
        "our_quantity_on_hand": ["quantity_on_hand", "qty_on_hand", "quantity", "on_hand"],
    }
    for target, source_cols in aliases.items():
        if target not in out.columns:
            for source in source_cols:
                if source in out.columns:
                    out[target] = out[source]
                    break
    defaults = {
        "our_category": "Unspecified",
        "our_subcategory": "Unspecified",
        "our_brand": "",
        "our_product_name": "",
        "our_package_size_label": "",
        "our_effective_price": 0.0,
        "our_regular_price": 0.0,
        "our_sale_price": 0.0,
        "our_discount_pct": 0.0,
        "our_has_promo": False,
        "our_quantity_on_hand": 0.0,
    }
    for col, value in defaults.items():
        if col not in out.columns:
            out[col] = value
    for col in ["our_effective_price", "our_regular_price", "our_sale_price", "our_discount_pct", "our_quantity_on_hand"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    out["our_has_promo"] = out["our_has_promo"].fillna(False).astype(bool)
    return out




def _build_comparison_tables() -> None:
    comp = st.session_state.get("competitor_menu_snapshots_df")
    our = st.session_state.get("competitor_our_inventory_df")
    if not isinstance(comp, pd.DataFrame) or comp.empty:
        for k in ["competitor_category_gap_df","competitor_subcategory_gap_df","competitor_brand_overlap_df","competitor_package_size_gap_df","competitor_price_gap_df","competitor_opportunity_risk_df","competitor_comparison_summary_df"]:
            st.session_state[k]=pd.DataFrame()
        return
    cdf = _prepare_competitor_comparison_df(comp)
    odf = _prepare_our_inventory_comparison_df(our)
    cdf["effective_price"] = _safe_numeric_series(cdf, "effective_price")
    odf["our_effective_price"] = _safe_numeric_series(odf, "our_effective_price")

    ccat = cdf.groupby("category", dropna=False).agg(competitor_sku_count=("product_name","count"), competitor_brand_count=("brand","nunique"), competitor_avg_effective_price=("effective_price","mean"), competitor_promo_count=("has_promo","sum")).reset_index()
    ocat = odf.groupby("our_category", dropna=False).agg(our_sku_count=("our_product_name","count"), our_brand_count=("our_brand","nunique"), our_avg_effective_price=("our_effective_price","mean")).reset_index().rename(columns={"our_category":"category"})
    cat = ocat.merge(ccat, on="category", how="outer").fillna(0)
    cat["sku_gap"] = cat["competitor_sku_count"] - cat["our_sku_count"]
    cat["brand_gap"] = cat["competitor_brand_count"] - cat["our_brand_count"]
    cat["price_gap_dollars"] = cat["competitor_avg_effective_price"] - cat["our_avg_effective_price"]
    cat["price_gap_pct"] = (cat["price_gap_dollars"] / cat["our_avg_effective_price"].replace(0, pd.NA))*100
    cat["our_promo_count"] = 0
    cat["promo_pressure"] = cat["competitor_promo_count"]
    cat["risk_level"] = cat.apply(lambda r: "High" if r["competitor_sku_count"] > (r["our_sku_count"]*1.5 if r["our_sku_count"] else 0) else "Low", axis=1)
    cat["recommendation"] = cat["risk_level"].map({"High":"Competitors have deeper category coverage. Review whether this is intentional or a menu gap.","Low":"We appear stronger in category depth. Consider featuring this category if margin supports it."})
    st.session_state["competitor_category_gap_df"] = cat

    sub_c = cdf.groupby(["category","subcategory"], dropna=False).agg(competitor_sku_count=("product_name","count"), competitor_avg_price=("effective_price","mean"), competitor_brand_count=("brand","nunique")).reset_index()
    sub_o = odf.groupby(["our_category","our_subcategory"], dropna=False).agg(our_sku_count=("our_product_name","count"), our_avg_price=("our_effective_price","mean"), our_brand_count=("our_brand","nunique")).reset_index().rename(columns={"our_category":"category","our_subcategory":"subcategory"})
    sub = sub_o.merge(sub_c, on=["category","subcategory"], how="outer").fillna(0)
    sub["sku_gap"]=sub["competitor_sku_count"]-sub["our_sku_count"]; sub["price_gap_dollars"]=sub["competitor_avg_price"]-sub["our_avg_price"]
    sub["gap_type"] = sub.apply(lambda r: "Missing From Our Menu" if r["our_sku_count"]==0 and r["competitor_sku_count"]>0 else ("Competitor Heavy" if r["sku_gap"]>3 else "Balanced"), axis=1)
    sub["risk_level"] = sub["gap_type"].map({"Missing From Our Menu":"High","Competitor Heavy":"Medium","Balanced":"Low"}).fillna("Medium")
    sub["opportunity_note"] = "Review subcategory depth and pricing position."
    st.session_state["competitor_subcategory_gap_df"] = sub

    ob = set(odf["our_brand"].fillna("").astype(str)); cb = set(cdf["brand"].fillna("").astype(str)); allb=sorted((ob|cb)-{""})
    rows=[]
    for b in allb:
        rows.append({"brand":b,"our_sku_count":int((odf["our_brand"]==b).sum()),"competitor_sku_count":int((cdf["brand"]==b).sum()),"shared_brand":b in ob and b in cb,"only_us":b in ob and b not in cb,"only_competitor":b in cb and b not in ob,"categories_seen":", ".join(sorted(set(cdf.loc[cdf["brand"]==b,"category"].dropna().astype(str))))[:120],"risk_or_opportunity":"Competitor-only brand may be a buying opportunity." if b in cb and b not in ob else "Shared brand: verify price competitiveness."})
    brand_df=pd.DataFrame(rows); st.session_state["competitor_brand_overlap_df"]=brand_df

    pkg_c = cdf.groupby(["category","subcategory","package_size_label"], dropna=False).agg(competitor_sku_count=("product_name","count"), competitor_avg_price=("effective_price","mean")).reset_index()
    pkg_o = odf.groupby(["our_category","our_subcategory","our_package_size_label"], dropna=False).agg(our_sku_count=("our_product_name","count"), our_avg_price=("our_effective_price","mean")).reset_index().rename(columns={"our_category":"category","our_subcategory":"subcategory","our_package_size_label":"package_size_label"})
    pkg = pkg_o.merge(pkg_c, on=["category","subcategory","package_size_label"], how="outer").fillna(0)
    pkg["gap_type"]=pkg.apply(lambda r: "Missing From Our Menu" if r["our_sku_count"]==0 and r["competitor_sku_count"]>0 else "Balanced", axis=1); pkg["recommendation"]="Expand missing sizes where velocity supports."
    st.session_state["competitor_package_size_gap_df"]=pkg

    price = sub[["category","subcategory","our_avg_price","competitor_avg_price"]].copy(); price["comparison_level"]="subcategory"; price["package_size_label"]=""; price["brand"]=""; price["market_low"]=price[["our_avg_price","competitor_avg_price"]].min(axis=1); price["market_high"]=price[["our_avg_price","competitor_avg_price"]].max(axis=1); price["price_gap_dollars"]=price["competitor_avg_price"]-price["our_avg_price"]; price["price_gap_pct"]=(price["price_gap_dollars"]/price["our_avg_price"].replace(0,pd.NA))*100
    def _pos(v):
        if pd.isna(v): return "Missing Data"
        if -5 <= v <= 5: return "At Market"
        if v < -5: return "Below Market"
        if 5 < v <= 15: return "Above Market"
        return "Premium"
    price["our_position"]=price["price_gap_pct"].apply(_pos); price["recommendation"]="Validate against velocity and margin before any broad move."
    st.session_state["competitor_price_gap_df"]=price

    opp = sub[["category","subcategory","gap_type","risk_level"]].copy(); opp["signal"]=opp["gap_type"]; opp["evidence"]="SKU and pricing comparison"; opp["opportunity_score"]=(50 + (opp["gap_type"].eq("Missing From Our Menu")*30) + (opp["gap_type"].eq("Competitor Heavy")*15)).astype(int); opp["recommended_action"]="Prioritize close of high-confidence gaps."
    st.session_state["competitor_opportunity_risk_df"]=opp[["category","subcategory","signal","evidence","risk_level","opportunity_score","recommended_action"]]

    overlap = (brand_df["shared_brand"].sum()/max(1,len(set(cb)-{""})))*100 if not brand_df.empty else 0
    st.session_state["competitor_comparison_summary_df"] = pd.DataFrame([{"our_categories":int(odf["our_category"].nunique()),"competitor_categories":int(cdf["category"].nunique()),"shared_categories":int(len(set(odf["our_category"]).intersection(set(cdf["category"])))),"missing_categories":int(len(set(cdf["category"]) - set(odf["our_category"]))),"our_skus":len(odf),"competitor_skus":len(cdf),"assortment_gap_count":int((sub["gap_type"]!="Balanced").sum()),"price_gap_count":int(price["price_gap_pct"].notna().sum()),"brand_overlap_pct":round(overlap,1),"promo_pressure_score":round(float(cdf.get("has_promo",pd.Series(dtype=float)).sum()),1),"opportunity_score":int(opp["opportunity_score"].mean() if not opp.empty else 0)}])
def render_competitor_intelligence_center() -> None:
    _init_state()
    st.header("🕵️ Competitor Intelligence Center")
    tabs = st.tabs(["Overview", "Upload Competitor Menu HTML", "Review Parsed Competitor Data", "Compare Against Our Inventory", "Price Intelligence", "Assortment Gaps", "Promo Pressure", "Strategic Recommendations", "Data Quality", "Export Executive Intelligence Report"])

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
        st.subheader("Dutchie Folder Packager")
        st.caption("Dutchie menus often save product data inside a companion _files folder. If the parent HTML shows zero products, upload the matching _files folder contents or ZIP the folder and upload it here. The app will search for saved_resource.html and product-card files automatically.")
        st.caption("Folder upload may not be supported by your browser or Streamlit. If you cannot upload a folder, select the files inside the folder or zip the folder first.")
        dutchie_parent_files = st.file_uploader("Upload Dutchie Parent HTML", type=["html", "htm"], accept_multiple_files=True, key="dutchie_parent_upload")
        dutchie_companion_files = st.file_uploader("Upload Companion Files or ZIP", type=["html", "htm", "txt", "zip"], accept_multiple_files=True, key="dutchie_companion_upload")
        dutchie_merge_behavior = st.selectbox(
            "Dutchie bundle save behavior",
            [
                "Merge into current competitor snapshot",
                "Replace matching competitor/category",
                "Replace entire competitor snapshot",
            ],
            index=0,
        )
        merge_mode_map = {
            "Merge into current competitor snapshot": "merge",
            "Replace matching competitor/category": "replace_matching_competitor_category",
            "Replace entire competitor snapshot": "replace_entire",
        }
        d1, d2, d3 = st.columns(3)
        if d1.button("Build Dutchie Capture Bundle"):
            st.session_state["competitor_dutchie_bundle"] = build_dutchie_capture_bundle(dutchie_parent_files, dutchie_companion_files)
        if d2.button("Process Dutchie Bundle"):
            payload = None
            merged_snapshot = None
            try:
                bundle = st.session_state.get("competitor_dutchie_bundle", {})
                files_to_process = []
                for p in bundle.get("parents", []):
                    files_to_process.append({"file_name": p["source_file_name"], "file_bytes": p["file_bytes"], "file_size": len(p["file_bytes"])})
                for c in bundle.get("companions", []):
                    if c.get("likely_product_resource"):
                        files_to_process.append({"file_name": c.get("inside_zip_name") or c["source_file_name"], "file_bytes": c["file_bytes"], "file_size": len(c["file_bytes"])})
                if files_to_process:
                    payload = _build_review_workbook_payload(files_to_process, competitor_override, str(snap_date), "Unspecified")
                    before_rows = len(st.session_state.get("competitor_menu_snapshots_df", pd.DataFrame()))
                    merged_snapshot = _merge_into_competitor_snapshot(
                        payload["cleaned_df"],
                        source_label="dutchie_bundle",
                        mode=merge_mode_map.get(dutchie_merge_behavior, "merge"),
                    )
            except Exception as ex:
                if payload is not None:
                    st.session_state["competitor_dutchie_bundle_results"] = payload["file_df"].to_dict("records")
                st.error("Competitor snapshot merge failed.")
                with st.expander("Debug Details"):
                    st.exception(ex)
            if payload is not None:
                existing_results = pd.DataFrame(st.session_state.get("competitor_file_processing_results", []))
                dutchie_results = payload["file_df"].copy()
                for col in ["companion_file", "parent_file"]:
                    if col not in dutchie_results.columns:
                        dutchie_results[col] = ""
                merged_results = pd.concat([existing_results, dutchie_results], ignore_index=True) if not existing_results.empty else dutchie_results
                st.session_state["competitor_file_processing_results"] = merged_results.to_dict("records")
                dq = payload["dq"].copy()
                dq["rows_saved"] = len(st.session_state.get("competitor_menu_snapshots_df", pd.DataFrame()))
                st.session_state["competitor_data_quality"] = dq
                st.session_state["competitor_category_summary_df"] = payload["cat_summary"]
                st.session_state["competitor_dutchie_bundle_results"] = payload["file_df"].to_dict("records")
                if not st.session_state.get("competitor_last_merge_skipped", False):
                    _build_analysis_tables()
                    _build_comparison_tables()
                if merged_snapshot is not None:
                    after_rows = len(merged_snapshot)
                    if int(payload["file_df"].get("rows_saved", pd.Series(dtype=int)).sum()) > 0 and after_rows <= before_rows:
                        st.warning("Dutchie rows were parsed but not added to the main snapshot.")
                    else:
                        st.success("Dutchie bundle processed and added to Competitor Intelligence snapshot.")
                        n1, n2, n3 = st.columns(3)
                        n1.caption("Go to Parsed Data Review")
                        n2.caption("Go to Data Quality")
                        n3.caption("Go to Export Report")
        if d3.button("Clear Dutchie Bundle"):
            st.session_state["competitor_dutchie_bundle"] = {}
            st.session_state["competitor_dutchie_bundle_results"] = []

        bundle = st.session_state.get("competitor_dutchie_bundle", {})
        if bundle:
            st.write(f"Parents detected: {len(bundle.get('parents', []))}")
            st.write(f"Companion files detected: {len(bundle.get('companions', []))}")
            st.write(f"Matched pairs: {len(bundle.get('matches', []))}")
            st.write(f"Unmatched companions: {len(bundle.get('unmatched_companions', []))}")
            missing = max(0, len(bundle.get("parents", [])) - len({m['parent_file_name'] for m in bundle.get("matches", [])}))
            st.write(f"Missing companion resources: {missing}")
            st.write(f"Product rows extracted: {len(st.session_state.get('competitor_menu_snapshots_df', pd.DataFrame()))}")
            if bundle.get("warnings"):
                st.warning("\n".join(bundle["warnings"]))
            manifest = {"parent_files": [p["source_file_name"] for p in bundle.get("parents", [])], "companion_files": [c["source_file_name"] for c in bundle.get("companions", [])], "matched_pairs": bundle.get("matches", []), "created_at": datetime.utcnow().isoformat() + "Z"}
            zbuf = BytesIO()
            with zipfile.ZipFile(zbuf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for p in bundle.get("parents", []):
                    zf.writestr(p["source_file_name"], p["file_bytes"])
                for c in bundle.get("companions", []):
                    zf.writestr(c.get("inside_zip_name") or c["source_file_name"], c["file_bytes"])
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            st.download_button("Download Dutchie Capture Bundle ZIP", data=zbuf.getvalue(), file_name="dutchie_capture_bundle.zip", mime="application/zip")
            dq_rows = []
            grouped = {}
            for m in bundle.get("matches", []):
                grouped.setdefault(m["parent_file_name"], []).append(m)
            for p in bundle.get("parents", []):
                matched = grouped.get(p["source_file_name"], [])
                dq_rows.append({"Parent File": p["source_file_name"], "Competitor": p["competitor_name"], "Category": p["category"], "Companion Found": bool(matched), "Companion File": ", ".join(x["companion_file_name"] for x in matched), "Rows Extracted": 0, "Status": "companion_found" if matched else "needs_companion_resource", "Warning": "" if matched else "Upload the matching _files folder ZIP or saved_resource.html"})
            for u in bundle.get("unmatched_companions", []):
                dq_rows.append({"Parent File": "", "Competitor": "Unknown", "Category": "Unknown", "Companion Found": False, "Companion File": u, "Rows Extracted": 0, "Status": "unmatched_companion", "Warning": "Companion file has no matched parent."})
            st.dataframe(pd.DataFrame(dq_rows), use_container_width=True)
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
            try:
                st.session_state["competitor_review_workbook_bytes"] = payload["workbook_bytes"]
                _merge_into_competitor_snapshot(payload["cleaned_df"], source_label="html_upload", mode="merge" if behavior == "Merge" else "replace_entire")
                st.session_state["competitor_product_candidates_df"] = payload["candidate_df"]
                st.session_state["competitor_raw_extracted_text_df"] = payload["raw_df"]
                st.session_state["competitor_file_processing_results"] = payload["file_df"].to_dict("records")
                st.session_state["competitor_data_quality"] = payload["dq"]
                st.session_state["competitor_category_summary_df"] = payload["cat_summary"]
                st.session_state["competitor_last_processed_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                if not st.session_state.get("competitor_last_merge_skipped", False):
                    _build_analysis_tables()
            except Exception as ex:
                st.error("Competitor snapshot merge failed.")
                with st.expander("Debug Details"):
                    st.exception(ex)
        if st.session_state.get("competitor_review_workbook_bytes"):
            st.download_button("Download Review Workbook XLSX", st.session_state["competitor_review_workbook_bytes"], "competitor_review_workbook.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if st.button("Use Cleaned Snapshot for Analysis"):
            _build_analysis_tables()

        imported_workbook = st.file_uploader("Upload Previously Cleaned Review Workbook", type=["xlsx"], key="review_workbook_import")
        if imported_workbook is not None:
            try:
                imported_cleaned = pd.read_excel(BytesIO(imported_workbook.getvalue()), sheet_name="Cleaned_Competitor_Snapshot")
                imported_cleaned = _ensure_cleaned_schema(imported_cleaned)
                _merge_into_competitor_snapshot(imported_cleaned, source_label="cleaned_workbook", mode="replace_entire")
                if not st.session_state.get("competitor_last_merge_skipped", False):
                    _build_analysis_tables()
                st.success("Loaded Cleaned_Competitor_Snapshot from workbook.")
            except Exception as ex:
                st.error("Competitor snapshot merge failed.")
                with st.expander("Debug Details"):
                    st.exception(ex)


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
        st.subheader("Our Menu / Inventory Comparison")
        data_quality_notes = []
        comp_snapshot = st.session_state.get("competitor_menu_snapshots_df")
        if isinstance(comp_snapshot, pd.DataFrame) and not comp_snapshot.empty and "has_promo" not in comp_snapshot.columns:
            data_quality_notes.append("has_promo was derived from discount_pct, sale_price, regular_price, and promo_text.")
        if isinstance(comp_snapshot, pd.DataFrame) and not comp_snapshot.empty and (("promo_text" not in comp_snapshot.columns) or ("sale_price" not in comp_snapshot.columns)):
            data_quality_notes.append("Promo detection is limited because promo_text/sale_price fields are missing.")
        for note in data_quality_notes:
            st.caption(note)
        if st.button("Use Active Buyer Inventory"):
            source_df, source_meta = get_active_inventory_df()
            if isinstance(source_df, pd.DataFrame) and not source_df.empty:
                st.session_state["competitor_our_inventory_df"] = normalize_inventory_for_competitor_comparison(source_df)
                st.session_state["competitor_our_inventory_source_name"] = source_meta.get("source_name") or "Buyer Dashboard Session"
                st.session_state["competitor_our_inventory_uploaded_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                st.success(f"Using active inventory: {st.session_state['competitor_our_inventory_source_name']}")
            else:
                st.warning("No active buyer inventory found. Upload inventory in Buyer Dashboard Inventory Upload first.")
        inv_upload = st.file_uploader("Upload Inventory File", type=["xlsx","csv"], key="competitor_inventory_upload")
        if inv_upload is not None:
            raw_inv = load_inventory_file(inv_upload)
            st.session_state["competitor_our_inventory_df"] = normalize_inventory_for_competitor_comparison(raw_inv)
            st.session_state["competitor_our_inventory_source_name"] = inv_upload.name
            st.session_state["competitor_our_inventory_uploaded_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        if st.button("Clear Inventory Comparison File"):
            st.session_state["competitor_our_inventory_df"] = pd.DataFrame()
        if not isinstance(comp_snapshot, pd.DataFrame) or comp_snapshot.empty:
            st.info("Process competitor files before comparison.")
        if not isinstance(st.session_state.get("competitor_our_inventory_df"), pd.DataFrame) or st.session_state["competitor_our_inventory_df"].empty:
            st.info("Upload or select our inventory to unlock comparison.")
        _build_comparison_tables()
        summary = st.session_state.get("competitor_comparison_summary_df")
        if isinstance(summary, pd.DataFrame) and not summary.empty:
            r = summary.iloc[0].to_dict(); cols = st.columns(6); keys=list(r.keys())
            for i,k in enumerate(keys[:6]): cols[i].metric(k.replace("_"," ").title(), r[k])
            cols2 = st.columns(5)
            for i,k in enumerate(keys[6:11]): cols2[i].metric(k.replace("_"," ").title(), r[k])
            for label,key in [("Category Comparison","competitor_category_gap_df"),("Subcategory Comparison","competitor_subcategory_gap_df"),("Brand Overlap","competitor_brand_overlap_df"),("Package Size Comparison","competitor_package_size_gap_df"),("Price Gap Comparison","competitor_price_gap_df"),("Opportunity / Risk Matrix","competitor_opportunity_risk_df")]:
                st.markdown(f"**{label}**")
                st.dataframe(st.session_state.get(key, pd.DataFrame()), use_container_width=True)

    with tabs[9]:
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
            recs = build_executive_recommendations({})
        st.session_state["competitor_market_read_text"] = build_market_read({"data_quality": st.session_state.get("competitor_data_quality", {})})
        st.session_state["competitor_executive_summary_text"] = build_opportunity_risk_narrative({})
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
                "category_gap_df": st.session_state.get("competitor_category_gap_df"),
                "subcategory_gap_df": st.session_state.get("competitor_subcategory_gap_df"),
                "price_gap_df": st.session_state.get("competitor_price_gap_df"),
                "brand_overlap_df": st.session_state.get("competitor_brand_overlap_df"),
                "package_size_gap_df": st.session_state.get("competitor_package_size_gap_df"),
                "opportunity_risk_df": st.session_state.get("competitor_opportunity_risk_df"),
                "market_read_text": st.session_state.get("competitor_market_read_text", ""),
            }
            st.download_button("Export Executive Intelligence Report", data=_build_competitor_intelligence_report_pdf(payload), file_name=f"competitor_intelligence_report_{datetime.utcnow().strftime('%Y%m%d')}.pdf", mime="application/pdf")
