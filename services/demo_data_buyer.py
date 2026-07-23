"""Deterministic Buyer, Delivery, Compliance, Budget, and White Label demo data."""
from __future__ import annotations

import math
import random
from datetime import date, datetime, time, timedelta
from typing import Any

import pandas as pd

DATASET_SCALES = {
    "small": {"products": 28, "sales_rows": 950, "days": 45},
    "medium": {"products": 96, "sales_rows": 6200, "days": 75},
    "enterprise": {"products": 280, "sales_rows": 24000, "days": 120},
}

_STRAINS = [
    ("Blue Dream", "hybrid"), ("GMO", "hybrid"), ("Strawberry Cough", "sativa"),
    ("Northern Lights", "indica"), ("Gastro Pop", "hybrid"), ("Wedding Cake", "indica"),
    ("Sour Diesel", "sativa"), ("Rainbow Belts", "hybrid"), ("Purple Punch", "indica"),
    ("Super Lemon Haze", "sativa"), ("Cereal Milk", "hybrid"), ("Ice Cream Cake", "indica"),
]
_BRANDS = ["Harbor House", "Bay State Botanicals", "Liberty Leaf", "Commonwealth Craft", "Veteran Grown", "South Coast Reserve"]
_VENDORS = ["Atlantic Cultivation", "Pioneer Valley Gardens", "Cape Cod Cannabis", "Berkshire Bloom", "Merrimack Organics"]
_COMPANIES = ["DoobieLogic Cannabis Group", "Commonwealth Cannabis Works", "South Coast Cannabis Co.", "Liberty Harbor Holdings"]
_CATEGORY_TEMPLATES = {
    "flower": [("Flower", "3.5g", 3.5, 38.0), ("Flower", "7g", 7.0, 66.0), ("Flower", "14g", 14.0, 112.0), ("Flower", "28g", 28.0, 190.0)],
    "pre rolls": [("Pre-Roll", "1g", 1.0, 12.0), ("Pre-Roll Pack", "2.5g", 2.5, 29.0)],
    "vapes": [("Live Resin Vape", "0.5g", 0.5, 42.0), ("Distillate Vape", "1g", 1.0, 48.0), ("Live Rosin Vape", "0.5g", 0.5, 58.0)],
    "edibles": [("Gummies", "100mg", 0.0, 24.0), ("High Dose Gummies", "500mg", 0.0, 46.0), ("Chocolate", "100mg", 0.0, 26.0)],
    "concentrates": [("Live Resin", "1g", 1.0, 48.0), ("Hash Rosin", "1g", 1.0, 68.0), ("Badder", "1g", 1.0, 44.0)],
    "beverages": [("Infused Seltzer", "5mg", 0.0, 8.0), ("Cannabis Shot", "20mg", 0.0, 12.0)],
    "topicals": [("Relief Balm", "500mg", 0.0, 38.0)],
    "tinctures": [("Full Spectrum Tincture", "500mg", 0.0, 42.0)],
}


def _scale(name: str) -> dict[str, int]:
    return DATASET_SCALES.get(str(name).casefold(), DATASET_SCALES["medium"])


def _company_profile(rng: random.Random, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    return {
        "company_name": overrides.get("company_name") or rng.choice(_COMPANIES),
        "store_name": overrides.get("store_name") or "New Bedford Flagship",
        "facility_name": overrides.get("facility_name") or "South Coast Production Campus",
        "license_number": overrides.get("license_number") or "MP281999",
        "state": overrides.get("state") or "MA",
    }


def _catalog(product_count: int, rng: random.Random, profile: dict[str, Any]) -> list[dict[str, Any]]:
    categories = list(_CATEGORY_TEMPLATES)
    rows: list[dict[str, Any]] = []
    for idx in range(product_count):
        category = categories[idx % len(categories)]
        kind, size_label, grams, retail = rng.choice(_CATEGORY_TEMPLATES[category])
        strain, strain_type = rng.choice(_STRAINS)
        brand = rng.choice(_BRANDS)
        vendor = rng.choice(_VENDORS)
        sku = f"DL-{category[:2].upper().replace(' ', '')}-{idx + 1:04d}"
        batch = f"BATCH-{idx // 4 + 1:04d}"
        extraction_run = f"EXT-{idx // 8 + 1:04d}"
        production_order = f"CO-{idx // 6 + 1:05d}"
        package_id = f"1A406030000{idx + 100000:09d}"
        coa_id = f"COA-{idx // 4 + 1:05d}"
        velocity_class = ["fast", "healthy", "slow", "dead"][idx % 4]
        if velocity_class == "fast":
            on_hand, expected_daily = rng.randint(4, 18), rng.uniform(2.2, 5.0)
        elif velocity_class == "healthy":
            on_hand, expected_daily = rng.randint(28, 90), rng.uniform(0.8, 2.1)
        elif velocity_class == "slow":
            on_hand, expected_daily = rng.randint(80, 220), rng.uniform(0.10, 0.45)
        else:
            on_hand, expected_daily = rng.randint(40, 160), rng.uniform(0.0, 0.08)
        product_name = f"{brand} {strain} {kind} {size_label}"
        rows.append({
            "sku": sku,
            "product_name": product_name,
            "category": category,
            "size_label": size_label,
            "unit_size_g": grams,
            "strain": strain,
            "strain_type": strain_type,
            "brand": brand,
            "vendor": vendor,
            "batch": batch,
            "package_id": package_id,
            "coa_id": coa_id,
            "source_extraction_batch": extraction_run,
            "source_production_order": production_order,
            "retail_price": round(retail * rng.uniform(0.92, 1.10), 2),
            "unit_cost": round(retail * rng.uniform(0.34, 0.48), 2),
            "on_hand": on_hand,
            "expected_daily": expected_daily,
            "velocity_class": velocity_class,
            "room": "Vault",
            "company_name": profile["company_name"],
        })
    return rows


def _inventory(catalog: list[dict[str, Any]], today: date, problems: set[str]) -> pd.DataFrame:
    rows = []
    for idx, p in enumerate(catalog):
        expiry_days = 20 + (idx * 17) % 360
        if "expiring_inventory" in problems and idx % 11 == 0:
            expiry_days = 8 + idx % 18
        rows.append({
            "Product Name": p["product_name"], "Category": p["category"], "Available": p["on_hand"],
            "Batch": p["batch"], "Room": p["room"], "SKU": p["sku"], "Cost": p["unit_cost"],
            "Med Price": p["retail_price"], "Brand": p["brand"],
            "Expiration Date": (today + timedelta(days=expiry_days)).isoformat(),
            "EComm Strain Type": p["strain_type"], "Package ID": p["package_id"],
            "Source Production Order": p["source_production_order"],
            "Source Extraction Batch": p["source_extraction_batch"], "COA ID": p["coa_id"],
        })
    return pd.DataFrame(rows)


def _weighted_choice(catalog: list[dict[str, Any]], rng: random.Random) -> dict[str, Any]:
    weights = [{"fast": 12.0, "healthy": 6.0, "slow": 1.5, "dead": 0.15}[p["velocity_class"]] for p in catalog]
    return rng.choices(catalog, weights=weights, k=1)[0]


def _sales(catalog: list[dict[str, Any]], today: date, count: int, days: int,
           rng: random.Random, delivery_products: set[str]) -> pd.DataFrame:
    start = today - timedelta(days=days - 1)
    rows: list[dict[str, Any]] = []
    for idx in range(count):
        p = _weighted_choice(catalog, rng)
        sold_date = start + timedelta(days=rng.randrange(days))
        delivery_boost = p["sku"] in delivery_products and sold_date >= today - timedelta(days=14)
        qty = rng.choices([1, 2, 3, 4], [68, 22, 8, 2], k=1)[0]
        if delivery_boost:
            qty += rng.choice([0, 1, 1, 2])
        discount = rng.uniform(0.78, 1.0)
        order_time = datetime.combine(sold_date, time(rng.randint(9, 20), rng.randrange(0, 60)))
        rows.append({
            "Product Name": p["product_name"], "Master Category": p["category"],
            "Quantity Sold": qty, "Net Sales": round(p["retail_price"] * qty * discount, 2),
            "Order ID": f"ORD-{idx // rng.choice([1, 1, 2, 3]) + 100000:07d}",
            "Order Time": order_time.isoformat(sep=" "), "SKU": p["sku"], "Batch ID": p["batch"],
            "Package ID": p["package_id"], "Brand": p["brand"],
            "Source Production Order": p["source_production_order"],
            "Source Extraction Batch": p["source_extraction_batch"], "COA ID": p["coa_id"],
        })
    return pd.DataFrame(rows)


def _detail(catalog: list[dict[str, Any]], sales: pd.DataFrame, days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    sold = sales.groupby("SKU", as_index=False).agg(unitssold=("Quantity Sold", "sum"), net_sales=("Net Sales", "sum"))
    rows = []
    for p in catalog:
        match = sold[sold["SKU"] == p["sku"]]
        units = float(match["unitssold"].iloc[0]) if not match.empty else 0.0
        revenue = float(match["net_sales"].iloc[0]) if not match.empty else 0.0
        daily = units / max(days, 1)
        doh = p["on_hand"] / daily if daily > 0 else 999.0
        reorder = max(0, math.ceil((21 - doh) * daily)) if doh < 21 else 0
        priority = "1 – Reorder ASAP" if 0 < doh <= 7 else ("2 – Watch Closely" if doh <= 21 and daily > 0 else ("4 – Dead Item" if daily == 0 else "3 – Comfortable Cover"))
        rows.append({
            "subcategory": p["category"], "product_name": p["product_name"], "strain_type": p["strain_type"],
            "packagesize": p["size_label"], "onhandunits": p["on_hand"], "unitssold": units,
            "avgunitsperday": daily, "daysonhand": int(round(doh)), "reorderqty": reorder,
            "reorderpriority": priority, "brand": p["brand"], "sku": p["sku"],
            "unit_cost": p["unit_cost"], "retail_price": p["retail_price"], "net_sales": revenue,
            "batch_id": p["batch"], "package_id": p["package_id"], "coa_id": p["coa_id"],
            "source_production_order": p["source_production_order"],
            "source_extraction_batch": p["source_extraction_batch"],
        })
    product = pd.DataFrame(rows)
    detail = product.groupby(["subcategory", "strain_type", "packagesize"], as_index=False).agg(
        onhandunits=("onhandunits", "sum"), unitssold=("unitssold", "sum"),
        avgunitsperday=("avgunitsperday", "sum"), net_sales=("net_sales", "sum"),
    )
    safe_velocity = detail["avgunitsperday"].where(detail["avgunitsperday"] != 0)
    detail["daysonhand"] = (detail["onhandunits"] / safe_velocity).fillna(999).round().astype(int)
    detail["reorderqty"] = ((21 - detail["daysonhand"]).clip(lower=0) * detail["avgunitsperday"]).apply(math.ceil)
    detail["reorderpriority"] = detail.apply(lambda r: "1 – Reorder ASAP" if 0 < r["daysonhand"] <= 7 else ("2 – Watch Closely" if r["daysonhand"] <= 21 and r["avgunitsperday"] > 0 else ("4 – Dead Item" if r["avgunitsperday"] == 0 else "3 – Comfortable Cover")), axis=1)
    return detail, product


def _manifest(catalog: list[dict[str, Any]], today: date, rng: random.Random, problems: set[str]) -> pd.DataFrame:
    delivered = [p for p in catalog if p["velocity_class"] in {"fast", "healthy"}][: max(8, len(catalog) // 8)]
    received = today - timedelta(days=14)
    rows = []
    for p in delivered:
        qty = rng.randint(24, 140)
        row_received = today - timedelta(days=3) if "late_po" in problems and p is delivered[0] else received
        rows.append({
            "Manifest #": "MAN-DEMO-2026-071", "Received Date": datetime.combine(row_received, time(10, 30)).isoformat(sep=" "),
            "Vendor": p["vendor"], "Product": p["product_name"], "Received Qty": qty,
            "Package ID": p["package_id"], "Batch": p["batch"], "License Number": "MP281999",
            "Location": "Vault", "SKU": p["sku"], "COA ID": p["coa_id"],
        })
    return pd.DataFrame(rows)


def _compliance(today: date) -> pd.DataFrame:
    items = [
        ("packaging", "Demo source: child-resistant packaging and required label review are tracked before release."),
        ("testing", "Demo source: finished cannabis products remain on hold until the associated COA is passed."),
        ("traceability", "Demo source: source package, production lot, and finished package identifiers must remain linked."),
        ("transport", "Demo source: transfers require manifest records and custody documentation."),
        ("inventory", "Demo source: inventory adjustments require a reason, actor, and traceable transaction record."),
        ("white label", "Demo source: white-label products retain source material and testing traceability."),
    ]
    return pd.DataFrame([{
        "state": "MA", "scope": "adult-use", "topic": topic, "answer": answer,
        "source_citation": f"SYNTHETIC-DEMO-{idx + 1:02d}", "source_url": "https://example.invalid/demo",
        "last_updated": today.isoformat(), "review_status": "demo-only",
    } for idx, (topic, answer) in enumerate(items)])


def _white_label(catalog: list[dict[str, Any]], today: date, profile: dict[str, Any]) -> dict[str, Any]:
    flower = next(p for p in catalog if p["category"] == "flower")
    plan = [
        {"enabled": True, "package_size_g": 3.5, "allocation_pct": 50.0, "bag_or_container_cost_per_unit": 0.18, "label_cost_per_unit": 0.06, "tamper_seal_cost_per_unit": 0.03, "humidity_pack_cost_per_unit": 0.07, "compliance_sticker_cost_per_unit": 0.04, "other_packaging_cost_per_unit": 0.02, "target_retail_price_per_unit": 32.0},
        {"enabled": True, "package_size_g": 7.0, "allocation_pct": 30.0, "bag_or_container_cost_per_unit": 0.25, "label_cost_per_unit": 0.06, "tamper_seal_cost_per_unit": 0.03, "humidity_pack_cost_per_unit": 0.09, "compliance_sticker_cost_per_unit": 0.04, "other_packaging_cost_per_unit": 0.02, "target_retail_price_per_unit": 56.0},
        {"enabled": True, "package_size_g": 14.0, "allocation_pct": 20.0, "bag_or_container_cost_per_unit": 0.34, "label_cost_per_unit": 0.06, "tamper_seal_cost_per_unit": 0.03, "humidity_pack_cost_per_unit": 0.12, "compliance_sticker_cost_per_unit": 0.04, "other_packaging_cost_per_unit": 0.02, "target_retail_price_per_unit": 96.0},
    ]
    return {
        "wl_strain_name": flower["strain"], "wl_strain_type": flower["strain_type"],
        "wl_cultivator_name": flower["vendor"], "wl_vendor_name": flower["vendor"],
        "wl_bulk_weight_value": 10.0, "wl_bulk_weight_unit": "lb", "wl_bulk_total_cost_usd": 7200.0,
        "wl_coa_link": "https://example.invalid/demo-coa.pdf", "wl_thca_pct": 26.4, "wl_total_thc_pct": 28.1,
        "wl_terpene_pct": 2.7, "wl_cultivator_license_number": profile["license_number"],
        "wl_source_metrc_package_id": flower["package_id"], "wl_batch_or_lot_number": flower["batch"],
        "wl_harvest_date": today - timedelta(days=45), "wl_testing_date": today - timedelta(days=28),
        "wl_coa_status": "Passed", "wl_label_review_status": "Ready", "wl_trim_loss_pct": 4.5,
        "wl_labor_cost_total_usd": 1650.0, "wl_other_costs_usd": 420.0, "wl_compliance_admin_cost_usd": 275.0,
        "white_label_active_scenario_name": "Demo Launch Mix", "white_label_package_plan": plan,
        "white_label_saved_scenarios": {"Demo Launch Mix": {"white_label_package_plan": plan}},
    }


def build_buyer_demo(today: date, *, scale: str = "medium", seed: int = 710,
                     company_seed: int | None = None, catalog_seed: int | None = None,
                     history_seed: int | None = None, company: dict[str, Any] | None = None,
                     problems: set[str] | None = None) -> dict[str, Any]:
    cfg, problems = _scale(scale), set(problems or set())
    company_rng = random.Random(seed if company_seed is None else company_seed)
    catalog_rng = random.Random(seed + 101 if catalog_seed is None else catalog_seed)
    history_rng = random.Random(seed + 202 if history_seed is None else history_seed)
    profile = _company_profile(company_rng, company)
    catalog = _catalog(cfg["products"], catalog_rng, profile)
    manifest = _manifest(catalog, today, history_rng, problems)
    delivered_skus = set(manifest.get("SKU", pd.Series(dtype=str)).astype(str))
    sales = _sales(catalog, today, cfg["sales_rows"], cfg["days"], history_rng, delivered_skus)
    inventory = _inventory(catalog, today, problems)
    detail, detail_product = _detail(catalog, sales, cfg["days"])
    quarantine_products = [p["product_name"] for i, p in enumerate(catalog) if i % 37 == 0]
    if "qa_hold" in problems:
        quarantine_products += [p["product_name"] for i, p in enumerate(catalog) if i % 19 == 0]
    quarantine = pd.DataFrame({"Product": sorted(set(quarantine_products))})
    budget = pd.DataFrame([
        {"Budget Category": "Core replenishment", "Budget": 42000, "Committed": 31500, "Actual": 28400},
        {"Budget Category": "New products", "Budget": 14000, "Committed": 9200, "Actual": 7600},
        {"Budget Category": "Promotions", "Budget": 9000, "Committed": 6700, "Actual": 5300},
        {"Budget Category": "Emergency buys", "Budget": 10000, "Committed": 2200, "Actual": 880},
    ])
    return {
        "company_profile": profile, "catalog": pd.DataFrame(catalog), "inventory": inventory,
        "sales": sales, "manifest": manifest, "quarantine": quarantine, "compliance": _compliance(today),
        "detail": detail, "detail_product": detail_product, "white_label": _white_label(catalog, today, profile),
        "budget": budget, "reporting_days": cfg["days"],
    }
