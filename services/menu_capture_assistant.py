from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import re
import json
import logging
from html import unescape

import pandas as pd

logger = logging.getLogger(__name__)
MAX_HTML_FILE_BYTES = 20 * 1024 * 1024
MAX_FALLBACK_TEXT_BYTES = 5 * 1024 * 1024


_CAPTURE_COLUMNS = [
    "competitor_name","snapshot_date","menu_platform","source_file_name","source_url","category","subcategory",
    "product_name","normalized_product_name","brand","package_size_label","package_size_g",
    "regular_price","sale_price","effective_price","discount_pct","thc_pct","thca_pct","tac_pct","cbd_pct",
    "terpene_pct","strain_type","availability_status","promo_text","product_url","raw_text",
    "capture_confidence","needs_review","missing_fields","captured_at",
]


def _normalize_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", " ", text)


def _parse_price(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
    return float(m.group(1)) if m else None


def _to_percent(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def _extract_rows_from_text(content: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in [ln.strip() for ln in content.splitlines() if ln.strip()]:
        price_match = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", line)
        thc_match = re.search(r"THC\s*[:\-]?\s*(\d+(?:\.\d+)?)%", line, re.IGNORECASE)
        strain_match = re.search(r"\b(indica|sativa|hybrid)\b", line, re.IGNORECASE)
        availability = "In Stock" if re.search(r"in stock|available", line, re.IGNORECASE) else ("Out of Stock" if re.search(r"out of stock|sold out", line, re.IGNORECASE) else "Unknown")
        promo_match = re.search(r"(sale|deal|discount|bogo|\d+% off)", line, re.IGNORECASE)

        product_name = re.split(r"\s+-\s+|\s+\|\s+", line)[0][:200]
        rows.append({
            "product_name": product_name,
            "brand": "",
            "category": "",
            "package_size_label": "",
            "regular_price": price_match.group(1) if price_match else None,
            "sale_price": None,
            "thc_pct": _to_percent(thc_match.group(1) if thc_match else None),
            "strain_type": strain_match.group(1).title() if strain_match else "",
            "promo_text": promo_match.group(1) if promo_match else "",
            "availability": availability,
            "raw_text": line,
        })
    return rows


def _find_json_blocks(text: str) -> list[str]:
    return re.findall(r"<script[^>]*>(.*?)</script>", text or "", flags=re.IGNORECASE | re.DOTALL)


def parse_competitor_html_snapshot(file_bytes: bytes, file_name: str, competitor_name: str, snapshot_date: str, default_category: str | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    source_url = ""
    inferred_category = default_category or ""
    menu_platform = "Unknown"
    file_size = len(file_bytes or b"")

    if file_size > MAX_HTML_FILE_BYTES:
        warnings.append(f"Large file detected ({round(file_size / (1024 * 1024), 2)} MB). Running bounded parsing mode.")

    # Stage 1: decode safely
    try:
        content = (file_bytes or b"").decode("utf-8", errors="ignore")
        content = unescape(content)
    except Exception as exc:
        logger.exception("Failed to decode competitor HTML file: %s", file_name)
        warnings.append(f"Decode failure: {exc}")
        content = ""

    # Stage 2: metadata extraction
    try:
        title_match = re.search(r"<title>(.*?)</title>", content, flags=re.IGNORECASE | re.DOTALL)
        if not inferred_category and title_match:
            inferred_category = re.sub(r"\s+", " ", title_match.group(1)).strip()[:80]
        canonical = re.search(r'rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']', content, flags=re.IGNORECASE)
        if canonical:
            source_url = canonical.group(1).strip()
    except Exception as exc:
        logger.exception("Metadata extraction failed for file: %s", file_name)
        warnings.append(f"Metadata extraction warning: {exc}")

    lowered = content.lower()
    if "window.jointecommerce" in lowered or "joint-ecommerce-config" in lowered:
        menu_platform = "Joint"
    elif "dutchie" in lowered:
        menu_platform = "Dutchie"
    elif "weedmaps" in lowered:
        menu_platform = "Weedmaps"

    # Stage 3: structured parsers
    try:
        for block in _find_json_blocks(content):
            if "jointEcommerce" not in block and "product" not in block.lower():
                continue
            for name, price in re.findall(r'"name"\s*:\s*"([^"]+)"[^{}]{0,300}?"price"\s*:\s*"?(\d+(?:\.\d+)?)"?', block, flags=re.IGNORECASE | re.DOTALL):
                rows.append({"product_name": name, "price": price, "category": inferred_category, "raw_text": name})
    except Exception as exc:
        logger.exception("Structured JSON extraction failed for file: %s", file_name)
        warnings.append(f"Structured extraction warning: {exc}")

    # Stage 4: fallback visible text parser (bounded size, scripts stripped)
    if not rows:
        try:
            stripped = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", content, flags=re.IGNORECASE | re.DOTALL)
            bounded = stripped[:MAX_FALLBACK_TEXT_BYTES]
            if len(stripped) > MAX_FALLBACK_TEXT_BYTES:
                warnings.append("Fallback text parsing limited to first 5 MB.")
            text_only = re.sub(r"<[^>]+>", " ", bounded or "")
            rows = _extract_rows_from_text(text_only)
        except Exception as exc:
            logger.exception("Fallback text parsing failed for file: %s", file_name)
            warnings.append(f"Fallback parser warning: {exc}")

    # Stage 5: normalize rows
    session = MenuCaptureSession()
    df = session.extract_visible_product_cards(rows, competitor_name, snapshot_date, menu_platform, source_url, inferred_category)
    df["source_file_name"] = file_name
    df["snapshot_date"] = snapshot_date
    # Stage 6: return data + metadata + warnings
    meta = {
        "source_file_name": file_name,
        "source_type": file_name.split(".")[-1].lower() if "." in file_name else "unknown",
        "menu_platform": menu_platform,
        "source_url": source_url,
        "rows_extracted": int(len(df)),
        "category": inferred_category,
        "warnings": warnings,
    }
    return df, meta


@dataclass
class MenuCaptureSession:
    current_url: str | None = None
    started_at: datetime | None = None
    started: bool = False
    browser_supported: bool = False
    categories_captured: list[str] = field(default_factory=list)

    def start(self, url: str) -> dict[str, Any]:
        self.current_url = url.strip()
        self.started_at = datetime.utcnow()
        self.started = True
        try:
            import playwright  # noqa: F401
            self.browser_supported = True
        except Exception:
            self.browser_supported = False
        return {
            "started": self.started,
            "url": self.current_url,
            "browser_supported": self.browser_supported,
            "message": "Manual interaction required. Complete age gates/CAPTCHA/login yourself before capture.",
        }

    def get_current_url(self) -> str:
        return self.current_url or ""

    def capture_current_category(self, category_name: str) -> dict[str, Any]:
        category = (category_name or "").strip() or "Unspecified"
        self.categories_captured.append(category)
        return {
            "category": category,
            "captured_at": datetime.utcnow().isoformat(),
            "message": "Category checkpoint captured. Paste/upload visible product data for extraction.",
        }

    def scroll_current_category(self) -> dict[str, Any]:
        return {
            "supported": self.browser_supported,
            "message": "Manual scroll recommended. This assistant only captures user-visible menu content.",
        }

    def extract_visible_product_cards(self, rows: list[dict[str, Any]], competitor_name: str, snapshot_date: str, menu_platform: str, source_url: str, category: str) -> pd.DataFrame:
        cleaned: list[dict[str, Any]] = []
        for row in rows:
            product_name = str(row.get("product_name", "")).strip()
            regular_price = _parse_price(row.get("regular_price") or row.get("price"))
            sale_price = _parse_price(row.get("sale_price"))
            effective_price = sale_price if sale_price is not None else regular_price
            discount_pct = None
            if regular_price and sale_price is not None and regular_price > 0:
                discount_pct = round(max(0.0, (regular_price - sale_price) / regular_price * 100.0), 2)

            fields = {
                "competitor_name": competitor_name,
                "snapshot_date": snapshot_date,
                "menu_platform": menu_platform,
                "source_file_name": row.get("source_file_name", ""),
                "source_url": source_url,
                "category": row.get("category") or category,
                "subcategory": row.get("subcategory", ""),
                "product_name": product_name,
                "normalized_product_name": _normalize_name(product_name),
                "brand": row.get("brand", ""),
                "package_size_label": row.get("package_size_label") or row.get("package_size") or "",
                "package_size_g": row.get("package_size_g"),
                "regular_price": regular_price,
                "sale_price": sale_price,
                "effective_price": effective_price,
                "discount_pct": discount_pct,
                "thc_pct": row.get("thc_pct"),
                "thca_pct": row.get("thca_pct"),
                "tac_pct": row.get("tac_pct"),
                "cbd_pct": row.get("cbd_pct"),
                "terpene_pct": row.get("terpene_pct"),
                "strain_type": row.get("strain_type", ""),
                "availability_status": row.get("availability_status") or row.get("availability") or "Unknown",
                "promo_text": row.get("promo_text", ""),
                "product_url": row.get("product_url", ""),
                "raw_text": row.get("raw_text", ""),
                "captured_at": datetime.utcnow().isoformat(),
            }
            missing = [k for k in ["product_name", "effective_price", "category"] if not fields.get(k)]
            if not missing and (fields.get("package_size_label") or fields.get("subcategory")):
                fields["capture_confidence"] = "High"
            elif fields.get("product_name") and fields.get("effective_price"):
                fields["capture_confidence"] = "Medium"
            else:
                fields["capture_confidence"] = "Low"
            fields["needs_review"] = fields["capture_confidence"] == "Low"
            fields["missing_fields"] = ", ".join(missing)
            cleaned.append(fields)

        df = pd.DataFrame(cleaned)
        for col in _CAPTURE_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[_CAPTURE_COLUMNS]


    def parse_saved_html_or_text(self, content: str) -> list[dict[str, Any]]:
        text = re.sub(r"<[^>]+>", " ", content or "")
        return _extract_rows_from_text(text)

    def parse_browser_capture_payload(self, payload: str) -> list[dict[str, Any]]:
        payload = (payload or "").strip()
        if not payload:
            return []
        try:
            data = json.loads(payload)
        except Exception:
            return []
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict):
            rows = data.get("rows")
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return []

    def close(self) -> None:
        self.started = False
        self.current_url = None
        self.started_at = None
        self.categories_captured = []
