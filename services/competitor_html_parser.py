from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any
from html import unescape
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from services.category_normalizer import normalize_competitor_category

NORMALIZED_SCHEMA = [
    "competitor_name","snapshot_date","menu_platform","source_type","source_file_name","source_url",
    "category","subcategory","product_type","category_confidence","category_source","product_name","normalized_product_name","brand","package_size_label",
    "package_size_g","package_size_mg","package_count","regular_price","sale_price","effective_price",
    "discount_pct","promo_text","thc_pct","thc_mg","thca_pct","cbd_pct","cbd_mg","cbg_pct","cbg_mg",
    "tac_pct","tac_mg","terpene_pct","strain_type","availability_status","product_url","raw_text",
    "capture_confidence","needs_review","missing_fields","duplicate_count","captured_at",
]
BAD_NAME_TOKENS = ["add to cart", "featured", "special offer", "staff pick", "thc potency", "price range", "sort by", "filter", "clear filters", "product type", "brand", "categories"]


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _txt(node: Any) -> str:
    return re.sub(r"\s+", " ", (node.get_text(" ", strip=True) if node else "")).strip()


def _detect_source_url(html: str) -> str:
    for p in [r"saved from url=\(\d+\)(https?://[^\s>]+)", r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)', r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)']:
        m = re.search(p, html, re.I)
        if m:
            return m.group(1)
    return ""


def detect_menu_platform(html_text: str, file_name: str, source_url: str | None = None, batch_context: dict[str, Any] | None = None) -> str:
    lowered = f"{html_text or ''} {file_name or ''} {source_url or ''}".lower()
    sunnyside_markers = ["sunnyside.shop", "productlistitem", "product-details", "brand-name", "product-name", "product-size", "product-price", "muichip-label"]
    leafbridge_markers = ["leafbridge_product_card", "leafbridge_brand_name", "leafbridge_product_name", "leafbridge_strain_type_label", "lb-product-weight", "potency_card_view", "leafbridge_product_modal_add_to_cart", "leafbridge_product_modal"]
    joint_markers = ["window.jointecommerce", "joint-ecommerce-config", "joint-theme", "joint-product-card"]

    if any(x in lowered for x in sunnyside_markers): return "sunnyside_react"
    if any(x in lowered for x in leafbridge_markers): return "leafbridge"
    if any(x in lowered for x in joint_markers) or ("kushgroove.com" in lowered and any(x in lowered for x in ["window.jointecommerce", "joint-theme", "joint-product-card"])): return "joint_ecommerce"
    if any(x in lowered for x in ["dutchie--embed__container", "dutchie--iframe", "dtche[category]", "dtche%5bcategory%5d", 'platform="dutchie"', "newleafcanna.com/menu"]): return "dutchie_embedded"
    if (re.search(r"\b\d+\.html\b", file_name.lower()) and (batch_context or {}).get("has_dutchie_shell")) or ("dutchie" in lowered and "add to cart" in lowered): return "dutchie_iframe_saved"
    if file_name.lower().endswith(".csv"): return "structured_upload"
    if file_name.lower().endswith(".json"): return "browser_capture_upload"
    return "generic_html"


def detect_category(html_text: str, file_name: str, source_url: str | None = None, platform: str | None = None) -> str:
    lowered = f"{html_text} {file_name} {source_url or ''}".lower()
    checks = [
        (r"/categories/flower/|/products/flower|dtche(?:%5b|\[)category(?:%5d|\])=flower", "Flower"),
        (r"/categories/pre-rolls/|/categories/prerolls/|dtche(?:%5b|\[)category(?:%5d|\])=pre-rolls|dtche(?:%5b|\[)category(?:%5d|\])=prerolls", "Pre-Rolls"),
        (r"/categories/edibles/|/products/edibles|dtche(?:%5b|\[)category(?:%5d|\])=edibles", "Edibles"),
        (r"/categories/concentrates/|dtche(?:%5b|\[)category(?:%5d|\])=concentrates", "Concentrates"),
        (r"/categories/topicals/|dtche(?:%5b|\[)category(?:%5d|\])=topicals", "Topicals"),
        (r"/categories/vapes/|/products/vapes|dtche(?:%5b|\[)category(?:%5d|\])=vapes", "Vapes"),
    ]
    for p, v in checks:
        if re.search(p, lowered, re.I):
            return v
    keyword_checks = [
        (r"\bflower\b", "Flower"),
        (r"\bpre[-\s]?rolls?\b|\bprerolls?\b", "Pre-Rolls"),
        (r"\bedibles?\b", "Edibles"),
        (r"\bconcentrates?\b", "Concentrates"),
        (r"\btopicals?\b", "Topicals"),
        (r"\bvapes?\b", "Vapes"),
    ]
    for p, v in keyword_checks:
        if re.search(p, lowered, re.I):
            return v
    return "Unspecified"


def detect_competitor(html_text: str, file_name: str, source_url: str | None = None, competitor_override: str | None = None) -> str:
    if competitor_override:
        return competitor_override

    soup = BeautifulSoup(html_text or "", "html.parser")
    og_site = soup.select_one('meta[property="og:site_name"]')
    if og_site and og_site.get("content"):
        return og_site.get("content").strip()

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text() or "{}")
        except Exception:
            continue
        blobs = data if isinstance(data, list) else [data]
        for blob in blobs:
            if isinstance(blob, dict) and str(blob.get("@type", "")).lower() == "organization" and blob.get("name"):
                return str(blob["name"]).strip()

    title = _txt(soup.title)
    if title:
        cleaned = re.split(r"\||-", title)[-1 if "cannabis near you" in title.lower() else 0].strip()
        cleaned = re.sub(r"(cannabis near you|menu|shop)", "", cleaned, flags=re.I).strip(" -|")
        if cleaned:
            return cleaned

    domain = ""
    if source_url:
        m = re.search(r"https?://(?:www\.)?([^/]+)", source_url)
        domain = (m.group(1) if m else "").lower()
    if domain:
        root = domain.split(".")[0].replace("-", " ").strip()
        if root:
            return root.title()

    lowered = f"{html_text} {file_name} {source_url or ''}".lower()
    known = {
        "kushgroove.com": "Kush Groove",
        "sunnyside.shop": "Sunnyside",
        "newleafcanna.com": "New Leaf",
        "goodnaturema.com": "Good Nature Cannabis",
    }
    for key, name in known.items():
        if key in lowered:
            return name
    return Path(file_name).stem.replace("_", " ").strip() or "Unknown"


def parse_price_fields(text: str) -> dict[str, Any]:
    vals = [float(v.replace(",", "")) for v in re.findall(r"\$\s*([\d,]+(?:\.\d{1,2})?)", str(text or ""))]
    vals = sorted(set(vals), reverse=True)
    out = {"regular_price": None, "sale_price": None, "effective_price": None, "discount_pct": None}
    if len(vals) == 1: out["regular_price"] = vals[0]; out["effective_price"] = vals[0]
    elif len(vals) >= 2: out["regular_price"] = max(vals[:2]); out["sale_price"] = min(vals[:2]); out["effective_price"] = out["sale_price"]
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


def _apply_category_normalization(row: dict[str, Any], detected_category: str) -> dict[str, Any]:
    info = normalize_competitor_category(product_name=row.get("product_name") or "", raw_text=row.get("raw_text") or "", page_category=detected_category or "", existing_category=row.get("category") or "", existing_subcategory=row.get("subcategory") or "")
    row["category"] = info["category"]
    row["subcategory"] = info["subcategory"]
    row["product_type"] = info["product_type"]
    row["category_confidence"] = info["category_confidence"]
    row["category_source"] = info["category_source"]
    return row

def _finalize(rows):
    df = pd.DataFrame(rows or [])
    for c in NORMALIZED_SCHEMA:
        if c not in df.columns: df[c] = None
    return df[NORMALIZED_SCHEMA]


def _invalid_name(name: str) -> bool:
    n = _norm(name)
    if not n or len(n) > 140 or any(t in n for t in BAD_NAME_TOKENS): return True
    if re.fullmatch(r"[\d\s$|.%mggozctpk,-]+", n): return True
    if len(re.findall(r"\$\s*\d", n)) > 1: return True
    return False


def validate_cleaned_product_row(row: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons = []
    for f in ["competitor_name", "menu_platform", "category", "product_name"]:
        if not str(row.get(f) or "").strip(): reasons.append(f"missing_{f}")
    if row.get("category") == "Unspecified": reasons.append("unspecified_category")
    if _invalid_name(str(row.get("product_name") or "")): reasons.append("bad_product_name")
    indicators = [bool(str(row.get("brand") or "").strip()), bool(str(row.get("package_size_label") or "").strip()), row.get("regular_price") is not None or row.get("effective_price") is not None, any(row.get(k) is not None for k in ["thc_pct", "thc_mg", "thca_pct", "cbd_pct", "cbd_mg", "tac_pct", "tac_mg"]), bool(str(row.get("availability_status") or "").strip())]
    if sum(1 for x in indicators if x) < 2: reasons.append("insufficient_indicators")
    return len(reasons) == 0, reasons


def parse_sunnyside_html(html: str, meta: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select('[data-cy="ProductListItem"], .product-details')
    if not cards:
        cards = [x.parent for x in soup.select('.brand-name + .product-name') if x.parent]
    rows, candidates = [], []
    for c in cards:
        name = _txt(c.select_one('.product-name'))
        brand = _txt(c.select_one('.brand-name'))
        if not name:
            continue
        text = _txt(c)
        r = _base_row(meta); r["product_name"] = name; r["brand"] = brand; r["normalized_product_name"] = _norm(name)
        r.update(parse_package_size(_txt(c.select_one('.product-size')) or text)); r.update(parse_price_fields(" ".join(_txt(x) for x in c.select('.product-price')) or text)); r.update(parse_potency_fields(" ".join(_txt(x) for x in c.select('.text-info, .MuiChip-label')) or text))
        r["strain_type"] = next((t for t in [_txt(x) for x in c.select('.MuiChip-label')] if _norm(t) in ["indica", "sativa", "hybrid"]), None)
        r["promo_text"] = _txt(c.select_one('.promo-text'))
        r["raw_text"] = text; r["capture_confidence"] = "High"
        ok, rs = validate_cleaned_product_row(r)
        (rows if ok else candidates).append(r if ok else {"source_file_name": meta["source_file_name"], "raw_product_block": text, "extracted_product_name": name, "rejection_reason": ",".join(rs)})
    return rows, candidates


def parse_joint_ecommerce_html(html: str, meta: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows, candidates = [], []
    for m in re.finditer(r"window\.jointEcommerce\s*=\s*(\{.*?\});", html, re.S):
        try: data = json.loads(m.group(1))
        except Exception: continue
        for p in data.get("products", []):
            r = _base_row(meta); r["product_name"] = str(p.get("name") or "").strip(); r["brand"] = str(p.get("brand") or "").strip(); r["normalized_product_name"] = _norm(r["product_name"])
            if p.get("price"): r["regular_price"] = float(p["price"]); r["effective_price"] = float(p["price"])
            r.update(parse_package_size(str(p.get("size") or ""))); r.update(parse_potency_fields(json.dumps(p))); r["raw_text"] = json.dumps(p); r["capture_confidence"] = "High"
            ok, rs = validate_cleaned_product_row(r)
            (rows if ok else candidates).append(r if ok else {"source_file_name": meta["source_file_name"], "raw_product_block": r["raw_text"], "extracted_product_name": r["product_name"], "rejection_reason": ",".join(rs)})
    soup = BeautifulSoup(html, "html.parser")
    for c in soup.select("[class*='product'], [class*='card']"):
        name = _txt(c.select_one("[class*='name'], h2, h3"))
        if not name: continue
        text = _txt(c)
        r = _base_row(meta); r["product_name"] = name; r["brand"] = _txt(c.select_one("[class*='brand']")); r["normalized_product_name"] = _norm(name); r.update(parse_package_size(text)); r.update(parse_price_fields(text)); r.update(parse_potency_fields(text)); r["raw_text"] = text; r["capture_confidence"] = "Medium"
        ok, rs = validate_cleaned_product_row(r)
        (rows if ok else candidates).append(r if ok else {"source_file_name": meta["source_file_name"], "raw_product_block": text, "extracted_product_name": name, "rejection_reason": ",".join(rs)})
    return rows, candidates




def parse_leafbridge_html(html: str, meta: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    soup = BeautifulSoup(html, "html.parser")
    rows, candidates = [], []
    for c in soup.select('.leafbridge_product_card'):
        name = _txt(c.select_one('.leafbridge_product_name'))
        brand = _txt(c.select_one('.leafbridge_brand_name'))
        text = _txt(c)
        if not name:
            continue
        r = _base_row(meta)
        r["product_name"] = name
        r["brand"] = brand
        r["normalized_product_name"] = _norm(name)
        link = c.select_one('.leafbridge_product_name a')
        if link and link.get('href'):
            r["product_url"] = link.get('href')
        r["subcategory"] = _txt(c.select_one('.pos_cat_name'))
        r["promo_text"] = _txt(c.select_one('.pos_tag_name'))
        r["strain_type"] = _txt(c.select_one('.leafbridge_strain_type_label span'))
        r.update(parse_package_size(_txt(c.select_one('.lb-product-weight')) or text))
        r.update(parse_potency_fields(" ".join(_txt(x) for x in c.select('.potency_card_view span')) or text))
        prices = [float(v.replace(',', '')) for v in re.findall(r"\$\s*([\d,]+(?:\.\d{1,2})?)", text)]
        if prices:
            uniq = sorted(set(prices))
            has_range = bool(re.search(r"\$\s*[\d,.]+\s*-\s*\$\s*[\d,.]+", text))
            has_discount = "off" in text.lower() or len(uniq) > 1
            if has_range:
                r["regular_price"] = uniq[0]
                r["effective_price"] = uniq[0]
                r["missing_fields"] = "multiple_variants"
            elif has_discount and len(uniq) > 1:
                r["regular_price"] = max(uniq)
                r["sale_price"] = min(uniq)
                r["effective_price"] = min(uniq)
            else:
                r["regular_price"] = uniq[0]
                r["effective_price"] = uniq[0]
        if c.select_one('button') and 'add to cart' in text.lower():
            r["availability_status"] = "Available"
        r["raw_text"] = text
        fields = [bool(name), bool(brand), bool(r.get("subcategory")), bool(r.get("package_size_label")), r.get("effective_price") is not None]
        if all(fields): r["capture_confidence"] = "High"
        elif bool(name) and bool(r.get("subcategory")) and r.get("effective_price") is not None: r["capture_confidence"] = "Medium"
        else: r["capture_confidence"] = "Low"
        ok, rs = validate_cleaned_product_row(r)
        (rows if ok else candidates).append(r if ok else {"source_file_name": meta["source_file_name"], "raw_product_block": text, "extracted_product_name": name, "rejection_reason": ",".join(rs)})
    return rows, candidates


def parse_dutchie_embedded_html(html: str, meta: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("iframe") and not soup.select("[class*='product-card'], [data-testid*='product']"):
        return [], [], "needs_companion_iframe_file"
    return [], [], None


def parse_dutchie_iframe_saved_html(html: str, meta: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    soup = BeautifulSoup(html, "html.parser")
    rows, candidates = [], []
    for c in soup.select("[class*='product-card'], [data-testid*='product'], [class*='product']"):
        name = _txt(c.select_one("[class*='name'], h2, h3"))
        if not name: continue
        text = _txt(c)
        r = _base_row(meta); r["product_name"] = name; r["brand"] = _txt(c.select_one("[class*='brand']")); r["normalized_product_name"] = _norm(name); r.update(parse_package_size(text)); r.update(parse_price_fields(text)); r.update(parse_potency_fields(text)); r["raw_text"] = text; r["capture_confidence"] = "Medium"
        ok, rs = validate_cleaned_product_row(r)
        (rows if ok else candidates).append(r if ok else {"source_file_name": meta["source_file_name"], "raw_product_block": text, "extracted_product_name": name, "rejection_reason": ",".join(rs)})
    return rows, candidates


def _is_dutchie_shell_file(html: str, file_name: str) -> bool:
    lowered = f"{html or ''} {file_name or ''}".lower()
    return bool(
        ("dutchie--embed__container" in lowered or "dutchie--iframe" in lowered or "dtche%5bcategory%5d" in lowered)
        and "iframe" in lowered
    )


def _folder_hints_from_text(value: str) -> list[str]:
    s = str(value or "").lower()
    matches = re.findall(r"([a-z0-9-]+)_files", s)
    return list(dict.fromkeys(matches))


def _build_parent_context_map(files: list[dict[str, Any]], snapshot_date: str | None, competitor_override: str | None) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for cf in files:
        html = unescape((cf.get("file_bytes", b"") or b"").decode("utf-8", errors="ignore"))
        fname = str(cf.get("file_name") or "")
        if not _is_dutchie_shell_file(html, fname):
            continue
        source_url = _detect_source_url(html)
        contexts.append(
            {
                "competitor_name": detect_competitor(html, fname, source_url, competitor_override),
                "category": detect_category(html, fname, source_url, "dutchie_embedded"),
                "source_url": source_url,
                "parent_file_name": fname,
                "snapshot_date": snapshot_date,
                "hints": list(
                    dict.fromkeys(
                        _folder_hints_from_text(fname)
                        + _folder_hints_from_text(source_url)
                        + _folder_hints_from_text(html[:12000])
                    )
                ),
            }
        )
    return contexts


def _closest_parent_context(file_name: str, html: str, parent_contexts: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not parent_contexts:
        return None
    combined = f"{file_name} {html[:12000]}"
    hints = set(_folder_hints_from_text(combined))
    if hints:
        for ctx in parent_contexts:
            if hints.intersection(set(ctx.get("hints", []))):
                return ctx
    f_norm = _norm(file_name)
    scored = []
    for idx, ctx in enumerate(parent_contexts):
        score = 0
        parent_hint = re.sub(r"\.html?$", "", _norm(ctx.get("parent_file_name", "")))
        if parent_hint and parent_hint in f_norm:
            score += 2
        if str(ctx.get("category") or "").lower() in combined.lower():
            score += 1
        if str(ctx.get("source_url") or "").lower() and str(ctx.get("source_url")).lower() in combined.lower():
            score += 1
        scored.append((score, idx, ctx))
    best = max(scored, key=lambda x: x[0]) if scored else None
    if best and best[0] > 0:
        return best[2]
    return parent_contexts[0] if len(parent_contexts) == 1 else None


def parse_competitor_file(file_bytes, file_name, snapshot_date=None, competitor_override=None, batch_context=None):
    html = unescape((file_bytes or b"").decode("utf-8", errors="ignore"))
    source_url = _detect_source_url(html)
    platform = detect_menu_platform(html, file_name, source_url, batch_context)
    competitor = detect_competitor(html, file_name, source_url, competitor_override)
    category = detect_category(html, file_name, source_url, platform)
    parent_ctx = (batch_context or {}).get("parent_context_by_file", {}).get(file_name)
    matched_parent = _closest_parent_context(file_name, html, (batch_context or {}).get("parent_contexts", []))
    inherit_ctx = parent_ctx or matched_parent
    if inherit_ctx and platform == "dutchie_iframe_saved":
        # Saved Dutchie resource files are commonly named with a numeric ID.
        # The matched parent shell is the authoritative identity and category.
        competitor = str(inherit_ctx.get("competitor_name") or competitor)
        category = str(inherit_ctx.get("category") or category)
        if not source_url:
            source_url = str(inherit_ctx.get("source_url") or "")
    platform_labels = {
        "sunnyside_react": "Sunnyside React/MUI",
        "leafbridge": "LeafBridge",
        "joint_ecommerce": "Joint E-Commerce",
        "dutchie_embedded": "Dutchie Embedded Parent Shell",
        "dutchie_iframe_saved": "Dutchie Companion Resource",
        "structured_upload": "Structured Upload",
        "generic_html": "Generic HTML",
    }
    meta = {"competitor_name": competitor, "snapshot_date": snapshot_date, "menu_platform": platform_labels.get(platform, platform.replace("_", " ").title()), "source_file_name": file_name, "source_url": source_url, "category": category}
    warnings, parsed_rows, rejected = [], [], []
    status = "processed"

    if platform == "sunnyside_react": parsed_rows, rejected = parse_sunnyside_html(html, meta)
    elif platform == "joint_ecommerce": parsed_rows, rejected = parse_joint_ecommerce_html(html, meta)
    elif platform == "leafbridge": parsed_rows, rejected = parse_leafbridge_html(html, meta)
    elif platform == "dutchie_embedded":
        parsed_rows, rejected, dutchie_status = parse_dutchie_embedded_html(html, meta)
        if dutchie_status == "needs_companion_iframe_file":
            status = dutchie_status
            warnings.append({"source_file_name": file_name, "warning_type": dutchie_status, "warning_message": "Upload companion iframe HTML from saved _files folder"})
    elif platform == "dutchie_iframe_saved":
        parsed_rows, rejected = parse_dutchie_iframe_saved_html(html, meta)
        if not inherit_ctx:
            for r in parsed_rows:
                r["needs_review"] = True
                r["capture_confidence"] = "Low"
            warnings.append({"source_file_name": file_name, "warning_type": "unmatched_companion_file", "warning_message": "Companion file could not be matched to a parent shell. Marked for review."})

    parsed_rows = [_apply_category_normalization(r, category) for r in parsed_rows]
    cleaned = _finalize(parsed_rows)
    candidates_df = pd.DataFrame(rejected)
    raw_text_df = pd.DataFrame([{"source_file_name": file_name, "detected_competitor": competitor, "detected_platform": meta["menu_platform"], "detected_category": category, "source_url": source_url, "raw_text_chunk": html[:20000], "chunk_index": 0, "parser_stage": "input_extract"}])
    if not len(cleaned) and status == "processed": status = "processed_no_rows"
    file_result = {"source_file_name": file_name, "detected_competitor": competitor, "detected_platform": meta["menu_platform"], "detected_category": category, "rows_extracted": len(parsed_rows) + len(rejected), "rows_saved": len(cleaned), "rejected_candidates": len(rejected), "status": status, "warning": warnings[0]["warning_message"] if warnings else ("Known platform parser returned no clean rows" if platform in {"joint_ecommerce", "sunnyside_react", "dutchie_iframe_saved", "dutchie_embedded", "leafbridge"} and len(cleaned) == 0 else ""), "completeness_status": "complete" if len(cleaned) else "incomplete"}
    if file_result["warning"] and not warnings:
        warnings.append({"source_file_name": file_name, "warning_type": "no_clean_rows", "warning_message": file_result["warning"]})
    return cleaned, candidates_df, raw_text_df, file_result, warnings


def process_competitor_files_batch(files: list[dict[str, Any]], snapshot_date: str | None = None, competitor_override: str | None = None) -> dict[str, Any]:
    cleaned_parts, raw_parts, cand_parts, file_results, warning_rows = [], [], [], [], []
    parent_contexts = _build_parent_context_map(files, snapshot_date, competitor_override)
    batch_context = {
        "uploaded_file_count": len(files),
        "has_dutchie_shell": len(parent_contexts) > 0,
        "parent_contexts": parent_contexts,
        "parent_context_by_file": {},
    }
    for cf in files:
        cleaned_df, candidates_df, raw_df, file_result, parser_warnings = parse_competitor_file(cf["file_bytes"], cf["file_name"], snapshot_date=snapshot_date, competitor_override=competitor_override, batch_context=batch_context)
        # Never create junk rows from Dutchie parent shell files.
        if file_result.get("status") == "needs_companion_iframe_file":
            cleaned_df = cleaned_df.iloc[0:0]
            file_result["rows_saved"] = 0
        cleaned_parts.append(cleaned_df); raw_parts.append(raw_df); file_results.append(file_result); warning_rows.extend(parser_warnings)
        if not candidates_df.empty: cand_parts.append(candidates_df)
    cleaned = _finalize(pd.concat(cleaned_parts, ignore_index=True).drop_duplicates(subset=["competitor_name", "category", "subcategory", "normalized_product_name", "brand", "package_size_label", "effective_price"]).to_dict("records") if cleaned_parts else [])
    if batch_context["uploaded_file_count"] > 3 and (cleaned["competitor_name"].nunique() <= 1 or cleaned["category"].nunique() <= 1):
        warning_rows.append({"source_file_name": "_batch_", "warning_type": "quality_guardrail", "warning_message": "Multiple files uploaded but cleaned output collapsed to one competitor/category"})
    return {"cleaned_df": cleaned, "candidate_df": pd.concat(cand_parts, ignore_index=True) if cand_parts else pd.DataFrame(columns=["source_file_name","rejection_reason"]), "raw_df": pd.concat(raw_parts, ignore_index=True) if raw_parts else pd.DataFrame(columns=["source_file_name","raw_text_chunk"]), "file_df": pd.DataFrame(file_results), "warnings_df": pd.DataFrame(warning_rows)}


# backward compatibility
def parse_competitor_snapshot(file_bytes, file_name, competitor_name, snapshot_date, default_category=None, source_url=None):
    cleaned, _cand, _raw, file_result, _warn = parse_competitor_file(file_bytes, file_name, snapshot_date=snapshot_date, competitor_override=competitor_name)
    meta = {"status": file_result.get("status"), "detected_platform": file_result.get("detected_platform"), "embedded_iframe_detected": file_result.get("status") == "needs_companion_iframe_file"}
    return cleaned, meta
