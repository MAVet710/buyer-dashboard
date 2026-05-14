from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from html import unescape

import pandas as pd

NORMALIZED_SCHEMA = [
    "competitor_name","snapshot_date","menu_platform","source_type","source_file_name","source_url",
    "category","subcategory","product_name","normalized_product_name","brand","package_size_label",
    "package_size_g","package_size_mg","package_count","regular_price","sale_price","effective_price",
    "discount_pct","promo_text","thc_pct","thc_mg","thca_pct","cbd_pct","cbd_mg","cbg_pct","cbg_mg",
    "tac_pct","tac_mg","terpene_pct","strain_type","availability_status","product_url","raw_text",
    "capture_confidence","needs_review","missing_fields","duplicate_count","captured_at",
]

CATEGORY_MAP = {"flower": "Flower", "pre-rolls": "Pre-Rolls", "prerolls": "Pre-Rolls", "edibles": "Edibles", "concentrates": "Concentrates", "topicals": "Topicals", "vapes": "Vapes"}
BAD_NAME_TOKENS = ["thc potency", "price range", "sort by", "filter", "clear filters", "product type", "brand", "categories"]


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _detect_source_url(html: str) -> str:
    for p in [r"saved from url=\(\d+\)(https?://[^\s>]+)", r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)', r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)']:
        m = re.search(p, html, re.I)
        if m:
            return m.group(1)
    return ""


def detect_menu_platform(html_text: str, file_name: str, source_url: str | None = None, batch_context: dict[str, Any] | None = None) -> str:
    lowered = f"{html_text or ''} {file_name or ''} {source_url or ''}".lower()
    if any(x in lowered for x in ["window.jointecommerce", "joint-ecommerce-config", "joint-theme", "kushgroove.com", "/categories/flower/", "/categories/pre-rolls/", "/categories/edibles/", "/categories/concentrates/", "/categories/topicals/"]):
        return "joint_ecommerce"
    if any(x in lowered for x in ["sunnyside.shop", "productlistitem", "product-details", "brand-name", "product-name", "product-price-potency", "product-size", "product-price", "muichip-label"]):
        return "sunnyside_react"
    if any(x in lowered for x in ["dutchie--embed__container", "dutchie--iframe", "dutchie--embed__styles", "dtche[category]", "dtche%5bcategory%5d", 'platform="dutchie"', "newleafcanna.com/menu"]):
        return "dutchie_embedded"
    if (re.search(r"\b\d+\.html\b", file_name.lower()) and (batch_context or {}).get("has_dutchie_shell")) or ("add to cart" in lowered and "dutchie" in lowered and ("product-card" in lowered or "product-list" in lowered)):
        return "dutchie_iframe_saved"
    if file_name.lower().endswith(".csv"):
        return "structured_upload"
    if file_name.lower().endswith(".json"):
        return "browser_capture_upload"
    return "generic_html"


def detect_category(html_text: str, file_name: str, source_url: str | None = None, platform: str | None = None) -> str:
    lowered = f"{html_text} {file_name} {source_url or ''}".lower()
    checks = [(r"/categories/flower/|dtche(?:%5b|\[)category(?:%5d|\])=flower|new leaf_flower", "Flower"), (r"/categories/pre-rolls/|dtche(?:%5b|\[)category(?:%5d|\])=pre-rolls|new leaf_prj", "Pre-Rolls"), (r"/categories/edibles/|/products/edibles|cannabis edibles", "Edibles"), (r"/categories/concentrates/", "Concentrates"), (r"/categories/topicals/", "Topicals"), (r"/products/vapes|cannabis vape carts", "Vapes"), (r"/products/flower|cannabis flower", "Flower")]
    for pattern, val in checks:
        if re.search(pattern, lowered, re.I):
            return val
    return "Unspecified"


def detect_competitor(html_text: str, file_name: str, source_url: str | None = None, competitor_override: str | None = None) -> str:
    if competitor_override:
        return competitor_override
    lowered = f"{html_text} {file_name} {source_url or ''}".lower()
    if "kushgroove.com" in lowered or "kush groove" in lowered:
        return "Kush Groove"
    if "sunnyside.shop" in lowered or "sunnyside" in lowered:
        return "Sunnyside"
    if "newleafcanna.com" in lowered or "new leaf" in lowered:
        return "New Leaf"
    return "Unknown"


def _is_bad_product_name(name: str) -> bool:
    n = _norm(name)
    if not n:
        return True
    if any(t in n for t in BAD_NAME_TOKENS):
        return True
    if re.fullmatch(r"[\d\s$|.%mggozctpk,-]+", n):
        return True
    if re.search(r"\b\d+(?:\.\d+)?\s*(g|mg)\s*\|\s*\$", n):
        return True
    return False


def parse_price_fields(text_or_node: Any) -> dict[str, Any]:
    text = str(text_or_node or "")
    vals = [float(v.replace(",", "")) for v in re.findall(r"\$\s*([\d,]+(?:\.\d{1,2})?)", text)]
    vals = sorted(set(vals), reverse=True)
    out = {"regular_price": None, "sale_price": None, "effective_price": None, "discount_pct": None}
    if len(vals) == 1: out["regular_price"] = vals[0]; out["effective_price"] = vals[0]
    elif len(vals) >= 2:
        out["regular_price"] = max(vals[0], vals[1]); out["sale_price"] = min(vals[0], vals[1]); out["effective_price"] = out["sale_price"]
    return out

def parse_package_size(text: str) -> dict[str, Any]:
    t = str(text or ""); out = {"package_size_label": "", "package_size_g": None, "package_size_mg": None, "package_count": None}
    if m := re.search(r"(\d*\.?\d+)\s*g\b", t, re.I): out.update({"package_size_label": m.group(0), "package_size_g": float(m.group(1))})
    elif m := re.search(r"(\d*\.?\d+)\s*mg\b", t, re.I): out.update({"package_size_label": m.group(0), "package_size_mg": float(m.group(1))})
    return out

def parse_potency_fields(text: str) -> dict[str, Any]:
    t = str(text or ""); out = {k: None for k in ["thc_pct","thc_mg","thca_pct","cbd_pct","cbd_mg","cbg_pct","cbg_mg","tac_pct","tac_mg","terpene_pct"]}
    for key, pct, mg in [("thc","thc_pct","thc_mg"),("thca","thca_pct",None),("cbd","cbd_pct","cbd_mg"),("tac","tac_pct","tac_mg")]:
        if m:=re.search(rf"{key}\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*%", t, re.I): out[pct]=float(m.group(1))
        if mg and (m:=re.search(rf"{key}\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg", t, re.I)): out[mg]=float(m.group(1))
    return out

def _base_row(meta: dict[str, Any]) -> dict[str, Any]:
    row = {k: None for k in NORMALIZED_SCHEMA}
    row.update({"competitor_name": meta.get("competitor_name", "Unknown"), "snapshot_date": meta.get("snapshot_date"), "menu_platform": meta.get("menu_platform"), "source_type": "html", "source_file_name": meta.get("source_file_name"), "source_url": meta.get("source_url", ""), "category": meta.get("category", "Unspecified"), "duplicate_count": 1, "captured_at": datetime.utcnow().isoformat()})
    return row

def _finalize(rows):
    df = pd.DataFrame(rows or [])
    for c in NORMALIZED_SCHEMA:
        if c not in df.columns: df[c] = None
    return df[NORMALIZED_SCHEMA]

def validate_cleaned_product_row(row: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons = []
    if _is_bad_product_name(row.get("product_name")): reasons.append("bad_product_name")
    for f in ["category", "competitor_name", "menu_platform"]:
        if not row.get(f): reasons.append(f"missing_{f}")
    if row.get("category") == "Unspecified": reasons.append("unspecified_category")
    if not any([row.get("brand"), row.get("package_size_label"), row.get("regular_price"), row.get("effective_price")]): reasons.append("no_product_indicators")
    return len(reasons) == 0, reasons

def _extract_blocks(html: str, marker: str) -> list[str]:
    if marker == "sunnyside":
        blocks = re.findall(r'(<(?:div|button)[^>]+data-cy=["\']ProductListItem["\'][\s\S]*?</(?:div|button)>)', html, re.I)
        return blocks
    return re.findall(r"([^\n]{20,400}add to cart[^\n]{0,220})", re.sub(r"<[^>]+>", " ", html, flags=re.S|re.I), re.I)

def _parse_blocks(blocks: list[str], meta: dict[str, Any]) -> list[dict[str, Any]]:
    rows=[]
    for b in blocks:
        txt = re.sub(r"<[^>]+>", " ", b)
        brand = re.search(r'brand-name[^>]*>([^<]+)', b, re.I)
        name = re.search(r'product-name[^>]*>([^<]+)', b, re.I)
        pname = (name.group(1).strip() if name else txt.strip()[:120])
        r = _base_row(meta); r["raw_text"]=txt; r["brand"]=(brand.group(1).strip() if brand else "")
        r["product_name"] = pname; r["normalized_product_name"]=_norm(pname)
        r.update(parse_price_fields(txt)); r.update(parse_package_size(txt)); r.update(parse_potency_fields(txt))
        r["capture_confidence"] = "Medium"
        rows.append(r)
    return rows

def parse_competitor_file(file_bytes, file_name, snapshot_date=None, competitor_override=None, batch_context=None):
    html = unescape((file_bytes or b"").decode("utf-8", errors="ignore"))
    source_url = _detect_source_url(html)
    platform = detect_menu_platform(html, file_name, source_url, batch_context)
    competitor = detect_competitor(html, file_name, source_url, competitor_override)
    category = detect_category(html, file_name, source_url, platform)
    meta = {"competitor_name": competitor, "snapshot_date": snapshot_date, "menu_platform": platform.replace("_", " ").title(), "source_file_name": file_name, "source_url": source_url, "category": category}
    warnings=[]
    if platform == "dutchie_embedded" and "iframe" in html.lower() and "add to cart" not in html.lower():
        return _finalize([]), pd.DataFrame(), pd.DataFrame(), {"source_file_name": file_name, "detected_competitor": competitor, "detected_platform": "Dutchie Embedded", "detected_category": category, "rows_extracted": 0, "rows_saved": 0, "rejected_candidates": 0, "status": "needs_companion_iframe_file", "warning": "Upload companion iframe HTML from saved _files folder.", "completeness_status": "incomplete"}, [{"source_file_name": file_name, "warning_type": "needs_companion_iframe_file", "warning_message": "Upload companion iframe HTML from saved _files folder."}]
    blocks = _extract_blocks(html, "sunnyside" if platform == "sunnyside_react" else "generic")
    parsed_rows = _parse_blocks(blocks, meta)
    cleaned, rejected = [], []
    for r in parsed_rows:
        ok, reasons = validate_cleaned_product_row(r)
        if ok: cleaned.append(r)
        else:
            rejected.append({"source_file_name": file_name, "competitor_name": competitor, "menu_platform": meta["menu_platform"], "category": category, "raw_product_block": r.get("raw_text"), "extracted_brand": r.get("brand"), "extracted_product_name": r.get("product_name"), "candidate_confidence": "Low", "rejected_from_cleaned": True, "rejection_reason": ",".join(reasons)})
    cleaned_df = _finalize(cleaned)
    candidates_df = pd.DataFrame(rejected)
    raw_text_df = pd.DataFrame([{"source_file_name": file_name, "detected_competitor": competitor, "detected_platform": meta["menu_platform"], "detected_category": category, "source_url": source_url, "raw_text_chunk": html[:20000], "chunk_index": 0, "parser_stage": "input_extract"}])
    status = "processed_no_rows" if len(cleaned_df) == 0 else "processed"
    fpr = {"source_file_name": file_name, "detected_competitor": competitor, "detected_platform": meta["menu_platform"], "detected_category": category, "rows_extracted": len(parsed_rows), "rows_saved": len(cleaned_df), "rejected_candidates": len(rejected), "status": status, "warning": "", "completeness_status": "complete" if len(cleaned_df) else "incomplete"}
    return cleaned_df, candidates_df, raw_text_df, fpr, warnings

# backward compatibility
def parse_competitor_snapshot(file_bytes, file_name, competitor_name, snapshot_date, default_category=None, source_url=None):
    cleaned, _cand, _raw, file_result, _warn = parse_competitor_file(file_bytes, file_name, snapshot_date=snapshot_date, competitor_override=competitor_name)
    meta = {"status": file_result.get("status"), "detected_platform": file_result.get("detected_platform"), "embedded_iframe_detected": file_result.get("status") == "needs_companion_iframe_file"}
    return cleaned, meta
