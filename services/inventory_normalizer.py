from __future__ import annotations

from datetime import datetime
from io import BytesIO
import re

import pandas as pd

from pos_automap import automap_inventory, normalize_inventory_for_session, read_tabular_auto
from services.category_normalizer import normalize_competitor_category


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _extract_size_fields(text: str) -> tuple[str, float | None, float | None, float | None]:
    raw = str(text or "")
    low = raw.lower()
    g_match = re.search(r"(\d+(?:\.\d+)?)\s*g\b", low)
    mg_match = re.search(r"(\d+(?:\.\d+)?)\s*mg\b", low)
    ct_match = re.search(r"(\d+)\s*(?:ct|count|pk|pack)\b", low)
    label = ""
    if g_match:
        label = f"{g_match.group(1)}g"
    elif mg_match:
        label = f"{mg_match.group(1)}mg"
    elif "disposable" in low:
        label = "disposable"
    elif "pod" in low:
        label = "pod"
    elif ct_match:
        label = f"{ct_match.group(1)}ct"
    return label or "Unspecified", float(g_match.group(1)) if g_match else None, float(mg_match.group(1)) if mg_match else None, float(ct_match.group(1)) if ct_match else None


def load_inventory_file(uploaded_file) -> pd.DataFrame:
    if uploaded_file is None:
        return pd.DataFrame()
    return read_tabular_auto(uploaded_file, "inventory")


def normalize_inventory_for_competitor_comparison(raw_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
        return pd.DataFrame()

    mapped, _ = automap_inventory(raw_df)
    inv = normalize_inventory_for_session(raw_df, mapped)

    inv["product_name"] = inv.get("product_name", "").astype(str)
    inv["brand"] = inv.get("brand", "").astype(str)
    inv["category"] = inv.get("category", "").astype(str)

    inv["our_product_name"] = inv["product_name"]
    inv["our_normalized_product_name"] = inv["product_name"].str.lower().str.replace(r"\s+", " ", regex=True).str.strip()
    inv["our_brand"] = inv["brand"].replace({"nan": ""})
    inv["our_vendor"] = inv.get("vendor", inv.get("brand", "")).astype(str)

    classed = inv.apply(lambda r: normalize_competitor_category(product_name=r.get("product_name", ""), raw_text=f"{r.get('category', '')} {r.get('product_name', '')}", page_category=r.get("category", "")), axis=1, result_type="expand")
    inv["our_category"] = classed.get("category", "Other")
    inv["our_subcategory"] = classed.get("subcategory", "Other")
    inv["our_product_type"] = classed.get("product_type", "Other")

    size_df = inv["product_name"].apply(_extract_size_fields).apply(pd.Series)
    size_df.columns = ["our_package_size_label", "our_package_size_g", "our_package_size_mg", "our_package_count"]
    inv = pd.concat([inv, size_df], axis=1)

    inv["our_retail_price"] = _num(inv.get("retail_price", pd.Series(index=inv.index)))
    inv["our_sale_price"] = _num(inv.get("sale_price", pd.Series(index=inv.index)))
    inv["our_effective_price"] = inv["our_sale_price"].where(inv["our_sale_price"].notna(), inv["our_retail_price"])
    inv["our_cost"] = _num(inv.get("unit_cost", pd.Series(index=inv.index)))
    inv["our_margin_pct"] = ((inv["our_effective_price"] - inv["our_cost"]) / inv["our_effective_price"] * 100).where(inv["our_effective_price"] > 0)
    inv["our_quantity_on_hand"] = _num(inv.get("on_hand", pd.Series(index=inv.index))).fillna(0)
    inv["our_days_on_hand"] = _num(inv.get("days_on_hand", pd.Series(index=inv.index)))
    inv["our_inventory_value"] = (inv["our_quantity_on_hand"] * inv["our_cost"]).fillna(0)
    inv["our_strain_type"] = inv.get("strain_type", "")
    inv["our_thc_pct"] = _num(inv.get("thc_pct", pd.Series(index=inv.index)))
    inv["our_thc_mg"] = _num(inv.get("thc_mg", pd.Series(index=inv.index)))
    inv["our_cbd_pct"] = _num(inv.get("cbd_pct", pd.Series(index=inv.index)))
    inv["our_cbd_mg"] = _num(inv.get("cbd_mg", pd.Series(index=inv.index)))
    inv["our_availability_status"] = "In Stock"
    inv.loc[inv["our_quantity_on_hand"] <= 0, "our_availability_status"] = "Out of Stock"

    target_cols = [
        "our_product_name", "our_normalized_product_name", "our_brand", "our_vendor", "our_category", "our_subcategory", "our_product_type",
        "our_package_size_label", "our_package_size_g", "our_package_size_mg", "our_package_count", "our_retail_price", "our_sale_price", "our_effective_price", "our_cost", "our_margin_pct", "our_quantity_on_hand", "our_days_on_hand", "our_inventory_value", "our_strain_type", "our_thc_pct", "our_thc_mg", "our_cbd_pct", "our_cbd_mg", "our_availability_status",
    ]
    for c in target_cols:
        if c not in inv.columns:
            inv[c] = None
    return inv[target_cols]
