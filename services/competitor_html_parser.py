from __future__ import annotations

from datetime import datetime
from io import BytesIO
import json
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

CATEGORY_MAP = {
    "flower": "Flower", "pre-rolls": "Pre-Rolls", "prerolls": "Pre-Rolls", "edibles": "Edibles",
    "concentrates": "Concentrates", "topicals": "Topicals", "vapes": "Vapes",
}


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def detect_menu_platform(html_text: str, file_name: str, source_url: str | None = None) -> str:
    lowered = f"{html_text or ''} {file_name or ''} {source_url or ''}".lower()
    if any(x in lowered for x in ["window.jointecommerce", "joint-ecommerce-config", "joint-product-card", "kushgroove.com", "/categories/flower/"]):
        return "joint_ecommerce"
    if any(x in lowered for x in ["sunnyside.shop", "productlistitem", "brand-name", "product-name", "muichip-label"]):
        return "sunnyside_react"
    if any(x in lowered for x in ["dutchie--embed__container", "dutchie--iframe", "dtche[category]", "dtche%5bcategory%5d", 'platform="dutchie"', "newleafcanna.com"]):
        return "dutchie_embedded"
    if any(x in lowered for x in ["dutchie", "add to cart", "product-card", "7997.html"]) and re.search(r"\b\d+\.html\b", file_name.lower()):
        return "dutchie_iframe_saved"
    return "generic_html"


def parse_price_fields(text_or_node: Any) -> dict[str, Any]:
    text = str(text_or_node or "")
    vals = [float(v.replace(",", "")) for v in re.findall(r"\$\s*([\d,]+(?:\.\d{1,2})?)", text)]
    vals = sorted(set(vals), reverse=True)
    out = {"regular_price": None, "sale_price": None, "effective_price": None, "discount_pct": None}
    if len(vals) == 1:
        out["regular_price"] = vals[0]; out["effective_price"] = vals[0]
    elif len(vals) >= 2:
        out["regular_price"] = max(vals[0], vals[1]); out["sale_price"] = min(vals[0], vals[1]); out["effective_price"] = out["sale_price"]
        if out["regular_price"] > 0:
            out["discount_pct"] = round((out["regular_price"] - out["sale_price"]) / out["regular_price"] * 100, 2)
    return out


def parse_package_size(text: str) -> dict[str, Any]:
    t = str(text or "")
    out = {"package_size_label": "", "package_size_g": None, "package_size_mg": None, "package_count": None}
    if m := re.search(r"(\d*\.?\d+)\s*g\b", t, re.I): out.update({"package_size_label": m.group(0), "package_size_g": float(m.group(1))})
    elif m := re.search(r"(\d*\.?\d+)\s*oz\b", t, re.I): out.update({"package_size_label": m.group(0), "package_size_g": round(float(m.group(1))*28.3495, 3)})
    elif m := re.search(r"(\d*\.?\d+)\s*mg\b", t, re.I): out.update({"package_size_label": m.group(0), "package_size_mg": float(m.group(1))})
    elif m := re.search(r"(\d+)\s*(?:ct|pk|pack)\b", t, re.I): out.update({"package_size_label": m.group(0), "package_count": int(m.group(1))})
    elif re.search(r"\b(each|unit)\b", t, re.I): out["package_size_label"] = re.search(r"\b(each|unit)\b", t, re.I).group(1)
    return out


def parse_potency_fields(text: str) -> dict[str, Any]:
    t = str(text or "")
    out = {k: None for k in ["thc_pct","thc_mg","thca_pct","cbd_pct","cbd_mg","cbg_pct","cbg_mg","tac_pct","tac_mg","terpene_pct"]}
    for key, pct, mg in [("thc","thc_pct","thc_mg"),("thca","thca_pct",None),("cbd","cbd_pct","cbd_mg"),("cbg","cbg_pct","cbg_mg"),("tac","tac_pct","tac_mg")]:
        if m:=re.search(rf"{key}\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*%", t, re.I): out[pct]=float(m.group(1))
        if mg and (m:=re.search(rf"{key}\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg", t, re.I)): out[mg]=float(m.group(1))
    if m:=re.search(r"terp(?:s|enes)?\s*[:\-]?\s*(\d+(?:\.\d+)?)%", t, re.I): out["terpene_pct"]=float(m.group(1))
    return out


def _availability(text: str) -> str:
    t = _norm(text)
    if any(x in t for x in ["add to cart", "in stock"]): return "Available"
    if any(x in t for x in ["only a few left", "low stock"]): return "Low stock"
    if any(x in t for x in ["out of stock", "unavailable"]): return "Out of stock"
    return "Unknown"


def _base_row(meta: dict[str, Any]) -> dict[str, Any]:
    row = {k: None for k in NORMALIZED_SCHEMA}
    row.update({"competitor_name": meta.get("competitor_name", "Unknown"), "snapshot_date": meta.get("snapshot_date"), "menu_platform": meta.get("menu_platform"), "source_type": meta.get("source_type", "html"), "source_file_name": meta.get("source_file_name"), "source_url": meta.get("source_url", ""), "category": meta.get("category", "Unknown"), "duplicate_count": 1, "captured_at": datetime.utcnow().isoformat()})
    return row


def _finalize(rows):
    df = pd.DataFrame(rows or [])
    for c in NORMALIZED_SCHEMA:
        if c not in df.columns: df[c] = None
    return df[NORMALIZED_SCHEMA]


def parse_generic_html(file_bytes, file_name, competitor_name=None, snapshot_date=None, category=None, source_url=None):
    html = unescape((file_bytes or b"").decode("utf-8", errors="ignore"))
    stripped = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.I|re.S)
    lines = [re.sub(r"\s+", " ", x).strip() for x in re.split(r"<br|</p>|</div>|\n", stripped) if "$" in x]
    rows=[]
    for ln in lines[:500]:
        r=_base_row({"competitor_name": competitor_name or "Unknown", "snapshot_date": snapshot_date, "menu_platform": "Generic HTML", "source_file_name": file_name, "source_url": source_url, "category": category or "Unknown"})
        txt=re.sub(r"<[^>]+>"," ",ln)
        r["raw_text"]=txt; r["product_name"]=txt[:120]; r["normalized_product_name"]=_norm(r["product_name"])
        r.update(parse_price_fields(txt)); r.update(parse_package_size(txt)); r.update(parse_potency_fields(txt)); r["availability_status"]=_availability(txt)
        r["capture_confidence"]="Low"; r["needs_review"]=True; r["missing_fields"]="category"
        rows.append(r)
    return _finalize(rows), {"status":"ok","rows_extracted":len(rows),"detected_platform":"generic_html"}


def parse_joint_ecommerce_html(file_bytes, file_name, competitor_name=None, snapshot_date=None, category=None, source_url=None):
    return parse_generic_html(file_bytes, file_name, competitor_name or "Kush Groove", snapshot_date, category, source_url)

def parse_sunnyside_html(file_bytes, file_name, competitor_name=None, snapshot_date=None, category=None, source_url=None):
    df, meta = parse_generic_html(file_bytes, file_name, competitor_name or "Sunnyside", snapshot_date, category, source_url)
    df["menu_platform"] = "Sunnyside React"
    return df, meta

def parse_dutchie_embedded_html(file_bytes, file_name, competitor_name=None, snapshot_date=None, category=None, source_url=None):
    html = (file_bytes or b"").decode("utf-8", errors="ignore")
    iframe = re.search(r'<iframe[^>]+src=["\']([^"\']+)', html, re.I)
    df, _ = parse_generic_html(file_bytes, file_name, competitor_name or "New Leaf", snapshot_date, category, source_url)
    if df.empty:
        return df, {"status":"needs_companion_iframe_file","embedded_iframe_detected":bool(iframe),"embedded_iframe_src": iframe.group(1) if iframe else "","rows_extracted":0,"detected_platform":"Dutchie Embedded","warning":"This saved HTML appears to contain a Dutchie embedded menu shell. Product data may be inside the companion saved iframe file from the page’s _files folder. Upload the matching iframe HTML file if available."}
    return df, {"status":"ok","rows_extracted":len(df),"detected_platform":"Dutchie Embedded"}

def parse_dutchie_iframe_saved_html(file_bytes, file_name, competitor_name=None, snapshot_date=None, batch_context=None):
    ctx = batch_context or {}
    return parse_generic_html(file_bytes, file_name, competitor_name or ctx.get("competitor_name"), snapshot_date, ctx.get("category"), ctx.get("source_url"))


def parse_competitor_snapshot(file_bytes: bytes, file_name: str, competitor_name: str, snapshot_date: str, default_category: str | None = None, source_url: str | None = None):
    html = (file_bytes or b"").decode("utf-8", errors="ignore")
    platform = detect_menu_platform(html, file_name, source_url)
    if platform == "joint_ecommerce":
        return parse_joint_ecommerce_html(file_bytes, file_name, competitor_name, snapshot_date, default_category, source_url)
    if platform == "sunnyside_react":
        return parse_sunnyside_html(file_bytes, file_name, competitor_name, snapshot_date, default_category, source_url)
    if platform == "dutchie_embedded":
        return parse_dutchie_embedded_html(file_bytes, file_name, competitor_name, snapshot_date, default_category, source_url)
    if platform == "dutchie_iframe_saved":
        return parse_dutchie_iframe_saved_html(file_bytes, file_name, competitor_name, snapshot_date, {"category": default_category, "source_url": source_url})
    return parse_generic_html(file_bytes, file_name, competitor_name, snapshot_date, default_category, source_url)
