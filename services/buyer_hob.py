from __future__ import annotations
import json
import re
from datetime import datetime, timezone, date
from io import BytesIO
from pathlib import Path
from typing import Any
import pandas as pd

DEFAULT_HOUSE_BRANDS = ["Cresco", "High Supply", "Good News", "Mindy’s", "FloraCal", "Remedi", "Wonder Wellness"]
DEFAULT_CONFIG_PATH = Path("data/house_brands.json")
BRAND_COLUMN_ALIASES = ["brand","vendor","product brand","product_brand","brand name","brand_name"]
QTY_COLUMN_ALIASES = [
    "available",
    "quantity available",
    "qty available",
    "quantity_available",
    "available quantity",
    "on hand",
    "on_hand",
    "qty on hand",
    "quantity on hand",
    "quantity_on_hand",
    "stock",
    "inventory",
    "current inventory",
    "units",
    "unit count",
    "sellable",
    "sellable quantity",
]


def normalize_brand_name(brand: Any) -> str:
    if brand is None or (isinstance(brand, float) and pd.isna(brand)):
        return ""
    text = str(brand).strip().lower()
    text = text.replace("’", "'").replace("`", "'")
    text = text.replace("'", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_house_brands(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data.get("house_brands"), list):
            return data
    return {"house_brands": DEFAULT_HOUSE_BRANDS.copy(), "updated_at": datetime.now(timezone.utc).isoformat()}


def save_house_brands(brands: list[str], path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"house_brands": [b.strip() for b in brands if str(b).strip()], "updated_at": datetime.now(timezone.utc).isoformat()}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def detect_brand_column(columns: list[str]) -> str | None:
    lower = {str(c).strip().lower(): c for c in columns}
    for alias in BRAND_COLUMN_ALIASES:
        if alias in lower:
            return lower[alias]
    return None


def detect_quantity_column(columns: list[str]) -> str | None:
    lower = {str(c).strip().lower(): c for c in columns}
    for alias in QTY_COLUMN_ALIASES:
        if alias in lower:
            return lower[alias]
    for c in columns:
        n = str(c).strip().lower()
        if ("avail" in n) or ("on hand" in n) or ("quantity" in n) or n in {"qty", "stock", "units"}:
            return c
    return None


def _resolve_qty_column(df: pd.DataFrame, qty_col: str | None) -> tuple[pd.DataFrame, str]:
    out = df.copy()
    resolved = qty_col if qty_col in out.columns else None
    if not resolved and "_hob_qty_col_used" in out.columns:
        used = out["_hob_qty_col_used"].dropna().astype(str)
        first = used.iloc[0] if not used.empty else None
        if first in out.columns:
            resolved = first
    if not resolved:
        resolved = detect_quantity_column(list(out.columns))
    if not resolved:
        out["_hob_qty_fallback"] = 0
        resolved = "_hob_qty_fallback"
        out["_hob_warning"] = "No quantity column detected. Unit calculations defaulted to 0."
    out[resolved] = pd.to_numeric(out[resolved], errors="coerce").fillna(0)
    out["_hob_qty_col_used"] = resolved
    return out, resolved


def classify_inventory(df: pd.DataFrame, house_brands: list[str], qty_col: str | None, brand_col: str | None) -> pd.DataFrame:
    out = df.copy()
    out, qty_col = _resolve_qty_column(out, qty_col)
    normalized_hob = {normalize_brand_name(b) for b in house_brands if normalize_brand_name(b)}
    if not brand_col or brand_col not in out.columns:
        out["brand_group"] = "Unknown"
        return out
    out["_brand_norm"] = out[brand_col].apply(normalize_brand_name)
    out["brand_group"] = out["_brand_norm"].map(lambda x: "Unknown" if not x else ("HOB" if x in normalized_hob else "Third Party"))
    return out


def build_summary(df: pd.DataFrame, qty_col: str) -> dict[str, float]:
    df, qty_col = _resolve_qty_column(df, qty_col)
    total = float(df[qty_col].sum())
    hob = float(df.loc[df["brand_group"] == "HOB", qty_col].sum())
    third = float(df.loc[df["brand_group"] == "Third Party", qty_col].sum())
    unknown = float(df.loc[df["brand_group"] == "Unknown", qty_col].sum())
    return {"total_units": total, "hob_units": hob, "third_units": third, "unknown_units": unknown, "hob_pct": (hob/total if total else 0), "third_pct": (third/total if total else 0), "hob_sku_count": int((df["brand_group"]=="HOB").sum()), "third_sku_count": int((df["brand_group"]=="Third Party").sum())}


def build_category_coverage(df: pd.DataFrame, qty_col: str, category_col: str) -> pd.DataFrame:
    df, qty_col = _resolve_qty_column(df, qty_col)
    if not category_col or category_col not in df.columns:
        df = df.copy()
        df["_hob_category_fallback"] = "Unspecified"
        category_col = "_hob_category_fallback"
    rows = []
    for category, g in df.groupby(category_col, dropna=False):
        total = float(g[qty_col].sum())
        hob = float(g.loc[g["brand_group"]=="HOB", qty_col].sum())
        third = float(g.loc[g["brand_group"]=="Third Party", qty_col].sum())
        hob_pct = (hob/total if total else 0)
        status = "Critical Gap" if hob_pct < 0.25 else "Under-Stocked" if hob_pct < 0.40 else "Balanced" if hob_pct <= 0.60 else "HOB Heavy"
        rows.append({"Category": category, "HOB Units": hob, "Third Party Units": third, "Total Units": total, "HOB %": hob_pct, "Third Party %": (third/total if total else 0), "HOB SKU Count": int((g["brand_group"]=="HOB").sum()), "Third Party SKU Count": int((g["brand_group"]=="Third Party").sum()), "Coverage Status": status})
    return pd.DataFrame(rows)


def analyze_deals(df: pd.DataFrame, deals: list[dict[str, Any]], qty_col: str, category_col: str, brand_col: str | None, price_col: str | None, name_col: str | None) -> pd.DataFrame:
    df, qty_col = _resolve_qty_column(df, qty_col)
    effective_category_col = category_col if category_col in df.columns else None
    out = []
    now = date.today()
    for d in deals:
        g = df.copy()
        if not effective_category_col:
            g["_hob_category_fallback"] = "Unspecified"
            effective_category_col = "_hob_category_fallback"
        if d.get("category") and effective_category_col in g.columns:
            g = g[g[effective_category_col].astype(str).str.lower() == str(d["category"]).lower()]
        if d.get("brands") and brand_col and brand_col in g.columns:
            allowed = {normalize_brand_name(x) for x in d["brands"]}
            g = g[g[brand_col].apply(normalize_brand_name).isin(allowed)]
        if d.get("price_threshold") is not None and price_col and price_col in g.columns:
            g = g[pd.to_numeric(g[price_col], errors="coerce").fillna(0) <= float(d["price_threshold"])]
        if d.get("keyword") and name_col and name_col in g.columns:
            g = g[g[name_col].astype(str).str.contains(str(d["keyword"]), case=False, na=False)]
        active = (not d.get("start_date") or pd.to_datetime(d["start_date"]).date() <= now) and (not d.get("end_date") or pd.to_datetime(d["end_date"]).date() >= now)
        hob = float(g.loc[g["brand_group"]=="HOB", qty_col].sum()); total = float(g[qty_col].sum()); third = float(g.loc[g["brand_group"]=="Third Party", qty_col].sum()); share = (hob/total if total else 0)
        risk = "Supported" if share >= 0.4 else "Medium Risk" if share >= 0.2 else "High Risk"
        if active and (hob <= 0 or share < 0.2): risk = "High Risk"
        out.append({"Deal Name": d.get("name","Unnamed"), "Active": active, "Eligible HOB Units": hob, "Eligible Third Party Units": third, "Eligible Total Units": total, "HOB Share of Eligible Units": share, "Eligible HOB SKU Count": int((g["brand_group"]=="HOB").sum()), "Eligible Third Party SKU Count": int((g["brand_group"]=="Third Party").sum()), "Risk Flag": risk})
    return pd.DataFrame(out)


def export_workbook(summary: dict[str, Any], cat: pd.DataFrame, promo: pd.DataFrame, settings: dict[str, Any], raw: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame([summary]).to_excel(w, index=False, sheet_name="Summary")
        cat.to_excel(w, index=False, sheet_name="Category Coverage")
        promo.to_excel(w, index=False, sheet_name="Promo Support")
        pd.DataFrame([settings]).to_excel(w, index=False, sheet_name="Brand Settings")
        raw.to_excel(w, index=False, sheet_name="Raw Inventory With Brand Group")
    return buf.getvalue()
