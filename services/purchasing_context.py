"""Canonical purchasing-data bridge for Buyer Dash.

Purchasing is a consumer of data Buyer Dash already owns.  This module turns the
active tenant's inventory, sales, Product Master, vendor terms, open purchase
orders, and production demand into the compatibility frames used by the current
Purchasing surfaces.  Uploads remain an ingestion path, never a prerequisite for
moving between modules once the data is already present in the app.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any
import re

import pandas as pd


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().casefold()).strip()


def _first_frame(state: Mapping[str, Any], *keys: str) -> pd.DataFrame:
    for key in keys:
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy()
    return pd.DataFrame()


def _column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    if frame.empty:
        return None
    normalized = {_norm(column): str(column) for column in frame.columns}
    for alias in aliases:
        found = normalized.get(_norm(alias))
        if found:
            return found
    return None


def _inventory_for_forecast(state: Mapping[str, Any]) -> pd.DataFrame:
    frame = _first_frame(
        state,
        "active_inventory_df",
        "inv_raw_df",
        "demo_inventory_df",
        "demo_catalog_df",
    )
    if frame.empty:
        return frame

    product = _column(frame, ("Product Name", "Product", "Item Name", "Name"))
    sku = _column(frame, ("SKU", "SKU ID", "Product ID", "Item ID"))
    available = _column(frame, ("Available", "On Hand", "On Hand Units", "Quantity", "Qty"))
    if not product or not available:
        return pd.DataFrame()

    normalized = frame.copy()
    rename: dict[str, str] = {product: "Product Name", available: "Available"}
    if sku:
        rename[sku] = "SKU"
    for aliases, target in (
        (("Category", "Product Category", "Subcategory"), "Category"),
        (("Brand", "Vendor", "Vendor Name", "Manufacturer"), "Brand"),
        (("Cost", "Unit Cost", "COGS", "Wholesale Price"), "Cost"),
        (("Med Price", "Retail Price", "Retail", "Price", "MSRP"), "Med Price"),
        (("Package Size", "Size", "Weight"), "Package Size"),
        (("EComm Strain Type", "Strain Type", "Strain"), "EComm Strain Type"),
        (("Batch", "Batch ID", "Lot"), "Batch"),
        (("Package ID", "METRC Package ID", "External Package ID"), "Package ID"),
        (("COA ID", "COA", "Certificate ID"), "COA ID"),
        (("Source Production Order", "Production Order"), "Source Production Order"),
        (("Source Extraction Batch", "Extraction Batch"), "Source Extraction Batch"),
    ):
        found = _column(frame, aliases)
        if found and found not in rename:
            rename[found] = target
    normalized = normalized.rename(columns=rename)
    if "SKU" not in normalized.columns:
        normalized["SKU"] = normalized["Product Name"].map(lambda value: f"APP-{abs(hash(str(value))) % 10_000_000:07d}")
    for column, default in (
        ("Category", ""),
        ("Brand", ""),
        ("Cost", 0.0),
        ("Med Price", 0.0),
        ("Package Size", ""),
        ("EComm Strain Type", ""),
        ("Batch", ""),
        ("Package ID", ""),
        ("COA ID", ""),
        ("Source Production Order", ""),
        ("Source Extraction Batch", ""),
    ):
        if column not in normalized.columns:
            normalized[column] = default
    return normalized


def _sales_for_forecast(state: Mapping[str, Any], inventory: pd.DataFrame) -> pd.DataFrame:
    frame = _first_frame(state, "active_sales_df", "sales_raw_df", "extra_sales_df", "demo_sales_df")
    if frame.empty:
        return pd.DataFrame(columns=["SKU", "Quantity Sold", "Net Sales"])

    sku = _column(frame, ("SKU", "SKU ID", "Product ID", "Item ID"))
    product = _column(frame, ("Product Name", "Product", "Item Name", "Name"))
    quantity = _column(frame, ("Quantity Sold", "Units Sold", "Qty Sold", "Quantity", "Qty"))
    net_sales = _column(frame, ("Net Sales", "Sales", "Revenue", "Gross Sales"))
    if not quantity or (not sku and not product):
        return pd.DataFrame(columns=["SKU", "Quantity Sold", "Net Sales"])

    normalized = frame.copy()
    rename: dict[str, str] = {quantity: "Quantity Sold"}
    if sku:
        rename[sku] = "SKU"
    if product:
        rename[product] = "Product Name"
    if net_sales:
        rename[net_sales] = "Net Sales"
    normalized = normalized.rename(columns=rename)

    if "SKU" not in normalized.columns and "Product Name" in normalized.columns:
        lookup = (
            inventory[["Product Name", "SKU"]]
            .drop_duplicates("Product Name")
            .set_index("Product Name")["SKU"]
        )
        normalized["SKU"] = normalized["Product Name"].map(lookup).fillna("")
    if "Net Sales" not in normalized.columns:
        normalized["Net Sales"] = 0.0
    normalized["Quantity Sold"] = pd.to_numeric(normalized["Quantity Sold"], errors="coerce").fillna(0.0)
    normalized["Net Sales"] = pd.to_numeric(normalized["Net Sales"], errors="coerce").fillna(0.0)
    return normalized


def _reporting_days(sales: pd.DataFrame) -> int:
    if sales.empty:
        return 60
    for alias in ("Order Time", "Sale Date", "Sales Date", "Transaction Date", "Date"):
        column = _column(sales, (alias,))
        if not column:
            continue
        values = pd.to_datetime(sales[column], errors="coerce").dropna()
        if not values.empty:
            return max(1, int((values.max().normalize() - values.min().normalize()).days) + 1)
    return 60


def _fallback_product_frame(inventory: pd.DataFrame, sales: pd.DataFrame, days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    sold = sales.groupby("SKU", as_index=False).agg(unitssold=("Quantity Sold", "sum"), net_sales=("Net Sales", "sum")) if not sales.empty else pd.DataFrame(columns=["SKU", "unitssold", "net_sales"])
    merged = inventory.merge(sold, on="SKU", how="left")
    merged["unitssold"] = pd.to_numeric(merged.get("unitssold"), errors="coerce").fillna(0.0)
    merged["net_sales"] = pd.to_numeric(merged.get("net_sales"), errors="coerce").fillna(0.0)
    merged["onhandunits"] = pd.to_numeric(merged.get("Available"), errors="coerce").fillna(0.0)
    merged["avgunitsperday"] = merged["unitssold"] / max(days, 1)
    velocity = merged["avgunitsperday"].replace(0, pd.NA)
    merged["daysonhand"] = (merged["onhandunits"] / velocity).fillna(999.0).clip(upper=999.0).round().astype(int)
    merged["reorderqty"] = ((21 - merged["daysonhand"]).clip(lower=0) * merged["avgunitsperday"]).round().astype(int)
    merged["reorderpriority"] = merged.apply(
        lambda row: "1 – Reorder ASAP" if 0 < row["daysonhand"] <= 7 else ("2 – Watch Closely" if row["daysonhand"] <= 21 and row["avgunitsperday"] > 0 else ("4 – Dead Item" if row["avgunitsperday"] == 0 else "3 – Comfortable Cover")),
        axis=1,
    )
    product = pd.DataFrame({
        "subcategory": merged.get("Category", ""),
        "product_name": merged.get("Product Name", ""),
        "strain_type": merged.get("EComm Strain Type", ""),
        "packagesize": merged.get("Package Size", ""),
        "onhandunits": merged["onhandunits"],
        "unitssold": merged["unitssold"],
        "avgunitsperday": merged["avgunitsperday"],
        "daysonhand": merged["daysonhand"],
        "reorderqty": merged["reorderqty"],
        "reorderpriority": merged["reorderpriority"],
        "brand": merged.get("Brand", ""),
        "sku": merged.get("SKU", ""),
        "unit_cost": pd.to_numeric(merged.get("Cost", 0), errors="coerce").fillna(0.0),
        "retail_price": pd.to_numeric(merged.get("Med Price", 0), errors="coerce").fillna(0.0),
        "net_sales": merged["net_sales"],
    })
    detail = product.groupby(["subcategory", "strain_type", "packagesize"], dropna=False, as_index=False).agg(
        onhandunits=("onhandunits", "sum"), unitssold=("unitssold", "sum"), avgunitsperday=("avgunitsperday", "sum"), net_sales=("net_sales", "sum")
    )
    detail_velocity = detail["avgunitsperday"].replace(0, pd.NA)
    detail["daysonhand"] = (detail["onhandunits"] / detail_velocity).fillna(999).clip(upper=999).round().astype(int)
    detail["reorderqty"] = ((21 - detail["daysonhand"]).clip(lower=0) * detail["avgunitsperday"]).round().astype(int)
    detail["reorderpriority"] = detail.apply(
        lambda row: "1 – Reorder ASAP" if 0 < row["daysonhand"] <= 7 else ("2 – Watch Closely" if row["daysonhand"] <= 21 and row["avgunitsperday"] > 0 else ("4 – Dead Item" if row["avgunitsperday"] == 0 else "3 – Comfortable Cover")),
        axis=1,
    )
    return detail, product


def _enrich_durable_context(state: Mapping[str, Any], product: pd.DataFrame) -> pd.DataFrame:
    organization_id = str(state.get("active_organization_id") or "").strip()
    facility_id = str(state.get("active_facility_id") or "").strip()
    if not organization_id or product.empty:
        return product
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import sessionmaker
        from modules.coman.db import create_coman_engine
        from modules.coman.models import CommercialOrder, CommercialOrderLine, Product, ProductionOrder, TradePartner
        from modules.product_master.models import ProductMasterProfile, ProductVendorLink

        sessions = sessionmaker(bind=create_coman_engine(), expire_on_commit=False, future=True)
        with sessions() as session:
            products = list(session.scalars(select(Product).where(Product.organization_id == organization_id, Product.active.is_(True))))
            profiles = {row.product_id: row for row in session.scalars(select(ProductMasterProfile).where(ProductMasterProfile.organization_id == organization_id))}
            links = list(session.scalars(select(ProductVendorLink).where(ProductVendorLink.organization_id == organization_id, ProductVendorLink.active.is_(True))))
            partners = {row.id: row for row in session.scalars(select(TradePartner).where(TradePartner.organization_id == organization_id))}
            primary_links: dict[str, Any] = {}
            for link in links:
                current = primary_links.get(link.product_id)
                if current is None or (link.is_primary and not current.is_primary):
                    primary_links[link.product_id] = link

            open_po: dict[str, float] = {}
            purchase_orders = list(session.scalars(select(CommercialOrder).where(
                CommercialOrder.organization_id == organization_id,
                CommercialOrder.order_type == "purchase",
                CommercialOrder.status.notin_(("fulfilled", "cancelled")),
            )))
            purchase_ids = {row.id for row in purchase_orders}
            if purchase_ids:
                for line in session.scalars(select(CommercialOrderLine).where(CommercialOrderLine.commercial_order_id.in_(purchase_ids))):
                    open_po[line.product_id] = open_po.get(line.product_id, 0.0) + max(float(line.quantity or 0) - float(line.fulfilled_quantity or 0), 0.0)

            production_demand: dict[str, float] = {}
            if facility_id:
                for order in session.scalars(select(ProductionOrder).where(
                    ProductionOrder.organization_id == organization_id,
                    ProductionOrder.facility_id == facility_id,
                    ProductionOrder.status.notin_(("complete", "completed", "cancelled")),
                )):
                    key = _norm(order.sku or order.product_name)
                    production_demand[key] = production_demand.get(key, 0.0) + float(order.requested_units or 0)

        rows: list[dict[str, Any]] = []
        for item in products:
            profile = profiles.get(item.id)
            link = primary_links.get(item.id)
            partner = partners.get(link.partner_id) if link is not None else None
            rows.append({
                "_sku_key": _norm(item.sku),
                "_name_key": _norm(item.name),
                "canonical_product_id": item.id,
                "canonical_product_name": item.name,
                "canonical_unit_cost": float(item.unit_cost or 0),
                "canonical_retail_price": float(item.retail_price or 0),
                "product_master_brand": str(getattr(profile, "brand", "") or ""),
                "product_master_category": str(getattr(profile, "category", "") or ""),
                "product_master_strain": str(getattr(profile, "strain", "") or ""),
                "primary_vendor": str(getattr(partner, "name", "") or ""),
                "vendor_lead_time_days": int(getattr(link, "lead_time_days", 0) or 0),
                "vendor_moq": float(getattr(link, "minimum_order_quantity", 0) or 0),
                "vendor_case_pack": float(getattr(link, "case_pack", 0) or 0),
                "open_po_units": float(open_po.get(item.id, 0.0)),
                "production_demand_units": float(production_demand.get(_norm(item.sku or item.name), 0.0)),
            })
        durable = pd.DataFrame(rows)
        if durable.empty:
            return product
        enriched = product.copy()
        enriched["_sku_key"] = enriched.get("sku", pd.Series("", index=enriched.index)).map(_norm)
        enriched["_name_key"] = enriched.get("product_name", pd.Series("", index=enriched.index)).map(_norm)
        merged = enriched.merge(durable, on="_sku_key", how="left", suffixes=("", "_durable"))
        missing = merged["canonical_product_id"].isna() if "canonical_product_id" in merged.columns else pd.Series(True, index=merged.index)
        if missing.any():
            name_map = durable.drop_duplicates("_name_key").set_index("_name_key").to_dict(orient="index")
            for idx in merged.index[missing]:
                row = name_map.get(str(merged.at[idx, "_name_key"]), {})
                for key, value in row.items():
                    if key in {"_sku_key", "_name_key"}:
                        continue
                    if key not in merged.columns or pd.isna(merged.at[idx, key]):
                        merged.at[idx, key] = value
        for target, source in (("unit_cost", "canonical_unit_cost"), ("retail_price", "canonical_retail_price"), ("brand", "product_master_brand"), ("subcategory", "product_master_category")):
            if source in merged.columns:
                current = merged.get(target, pd.Series(index=merged.index, dtype="object"))
                if target in {"unit_cost", "retail_price"}:
                    current_num = pd.to_numeric(current, errors="coerce").fillna(0.0)
                    source_num = pd.to_numeric(merged[source], errors="coerce").fillna(0.0)
                    merged[target] = current_num.where(current_num > 0, source_num)
                else:
                    current_text = current.fillna("").astype(str)
                    merged[target] = current_text.where(current_text.str.strip().ne(""), merged[source].fillna("").astype(str))
        return merged.drop(columns=["_sku_key", "_name_key"], errors="ignore")
    except Exception:
        # Purchasing must remain usable when the durable database is temporarily
        # unavailable; active session inventory + sales are still authoritative
        # for the current rendered tenant.
        return product


def prepare_purchasing_context(state: MutableMapping[str, Any]) -> dict[str, Any]:
    """Populate every compatibility frame consumed by Purchasing surfaces."""
    inventory = _inventory_for_forecast(state)
    sales = _sales_for_forecast(state, inventory)
    if inventory.empty:
        state.pop("purchasing_ready_df", None)
        return {"ready": False, "reason": "inventory_missing", "rows": 0}

    days = _reporting_days(sales)
    try:
        from services.demo_data import _recompute_detail
        detail, product = _recompute_detail(inventory, sales, days)
    except Exception:
        detail, product = _fallback_product_frame(inventory, sales, days)

    product = _enrich_durable_context(state, product)
    state["detail_cached_df"] = detail.copy()
    state["detail_product_cached_df"] = product.copy()
    state["purchasing_ready_df"] = product.copy()
    state["purchasing_context_reporting_days"] = days
    state["purchasing_context_source"] = "active_app_data"

    budget = _first_frame(state, "purchasing_budget_df", "demo_budget_df")
    if not budget.empty:
        state["purchasing_budget_df"] = budget.copy()
    if not _first_frame(state, "delivery_sales_df").empty:
        state["purchasing_delivery_ready"] = True
    elif not sales.empty:
        state["delivery_sales_df"] = sales.copy()
        state["purchasing_delivery_ready"] = bool(_first_frame(state, "delivery_manifest_df").shape[0])

    return {
        "ready": not product.empty,
        "rows": int(len(product)),
        "detail_rows": int(len(detail)),
        "reporting_days": days,
        "budget_rows": int(len(budget)),
        "source": "active_app_data",
    }


def purchasing_frame(state: MutableMapping[str, Any]) -> pd.DataFrame:
    frame = state.get("purchasing_ready_df")
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        return frame.copy()
    prepare_purchasing_context(state)
    frame = state.get("purchasing_ready_df")
    return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
