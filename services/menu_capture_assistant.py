from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import re
import json

import pandas as pd


_CAPTURE_COLUMNS = [
    "competitor_name","snapshot_date","menu_platform","source_url","category","subcategory",
    "product_name","normalized_product_name","brand","package_size_label","package_size_g",
    "regular_price","sale_price","effective_price","discount_pct","thc_pct","thca_pct","cbd_pct",
    "terpene_pct","strain_type","availability_status","promo_text","product_url","raw_text",
    "capture_confidence","needs_review","captured_at",
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
