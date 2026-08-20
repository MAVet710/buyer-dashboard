"""First-class Product Master workspace for the flat Buyer Dash shell.

Products is intentionally a board, not another edit-heavy admin page. The board
surfaces canonical identity/economics gaps and opens the existing Product 360
right-side drawer in one row selection.
"""
from __future__ import annotations

from typing import Any, MutableMapping

import pandas as pd
import streamlit as st
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.db import ComanDatabaseConfigurationError, create_coman_engine
from modules.coman.models import Product, TradePartner
from modules.navigation.product_360 import render_product_360_dialog
from modules.product_master.models import (
    ProductExternalMapping,
    ProductMasterProfile,
    ProductVendorLink,
)

PRODUCT_MASTER_SURFACE = "product_master"


def _scope(state: MutableMapping[str, Any]) -> str:
    return str(state.get("active_organization_id") or "").strip()


def _product_rows(organization_id: str) -> pd.DataFrame:
    engine = create_coman_engine()
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions() as session:
        products = list(
            session.scalars(
                select(Product)
                .where(
                    Product.organization_id == organization_id,
                    Product.active.is_(True),
                )
                .order_by(Product.name)
            )
        )
        if not products:
            return pd.DataFrame()

        product_ids = [row.id for row in products]
        profiles = {
            row.product_id: row
            for row in session.scalars(
                select(ProductMasterProfile).where(
                    ProductMasterProfile.organization_id == organization_id,
                    ProductMasterProfile.product_id.in_(product_ids),
                )
            )
        }
        mapping_counts = {
            str(product_id): int(count or 0)
            for product_id, count in session.execute(
                select(
                    ProductExternalMapping.product_id,
                    func.count(ProductExternalMapping.id),
                )
                .where(
                    ProductExternalMapping.organization_id == organization_id,
                    ProductExternalMapping.product_id.in_(product_ids),
                    ProductExternalMapping.active.is_(True),
                )
                .group_by(ProductExternalMapping.product_id)
            ).all()
        }
        primary_rows = session.execute(
            select(ProductVendorLink, TradePartner)
            .join(TradePartner, TradePartner.id == ProductVendorLink.partner_id)
            .where(
                ProductVendorLink.organization_id == organization_id,
                ProductVendorLink.product_id.in_(product_ids),
                ProductVendorLink.active.is_(True),
                ProductVendorLink.is_primary.is_(True),
            )
        ).all()
        primary_vendor = {
            link.product_id: partner.name for link, partner in primary_rows
        }

        rows: list[dict[str, Any]] = []
        for product in products:
            profile = profiles.get(product.id)
            mastered = bool(profile)
            mapped = mapping_counts.get(product.id, 0)
            has_economics = float(product.unit_cost or 0) > 0 and float(product.retail_price or 0) > 0
            gap_parts: list[str] = []
            if not mastered:
                gap_parts.append("identity")
            if mapped == 0:
                gap_parts.append("external ID")
            if not primary_vendor.get(product.id):
                gap_parts.append("vendor")
            if not has_economics:
                gap_parts.append("cost/price")
            rows.append(
                {
                    "product_id": product.id,
                    "Product": product.name,
                    "SKU": product.sku,
                    "Brand": getattr(profile, "brand", "") if profile else "",
                    "Category": getattr(profile, "category", "") if profile else "",
                    "Strain": getattr(profile, "strain", "") if profile else "",
                    "Type": product.item_type,
                    "Vendor": primary_vendor.get(product.id, ""),
                    "Unit Cost": float(product.unit_cost or 0),
                    "Retail": float(product.retail_price or 0),
                    "External IDs": mapped,
                    "Mastered": mastered,
                    "Needs setup": ", ".join(gap_parts),
                }
            )
        return pd.DataFrame(rows)


def render_product_master_workspace(state: MutableMapping[str, Any] | None = None) -> None:
    """Render Product Master as a searchable one-tap Product 360 board."""
    state = state or st.session_state
    organization_id = _scope(state)
    st.markdown("## Products")
    st.caption(
        "Canonical Product Master · one product identity shared by inventory, purchasing, "
        "production, extraction, wholesale and traceability. Select a row to open Product 360."
    )
    if not organization_id:
        st.info("Select an organization before using Products.")
        return

    try:
        frame = _product_rows(organization_id)
    except ComanDatabaseConfigurationError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error(f"Product Master could not load: {exc}")
        return

    if frame.empty:
        st.info("No canonical products exist yet. Import products or create them through production / migration workflows.")
        return

    mastered_count = int(frame["Mastered"].fillna(False).astype(bool).sum())
    mapped_count = int((pd.to_numeric(frame["External IDs"], errors="coerce").fillna(0) > 0).sum())
    gaps_count = int(frame["Needs setup"].astype(str).str.strip().ne("").sum())
    metrics = st.columns(4)
    metrics[0].metric("Products", f"{len(frame):,}")
    metrics[1].metric("Mastered", f"{mastered_count / max(1, len(frame)) * 100:.0f}%")
    metrics[2].metric("Externally mapped", f"{mapped_count:,}")
    metrics[3].metric("Needs setup", f"{gaps_count:,}")

    search_col, gaps_col = st.columns([4, 1.25])
    search = search_col.text_input(
        "Search products",
        placeholder="Product, SKU, brand, category, strain, vendor…",
        label_visibility="collapsed",
        key="product_master_search",
    )
    gaps_only = gaps_col.toggle("Needs setup", value=False, key="product_master_gaps_only")

    filtered = frame.copy()
    if str(search or "").strip():
        needle = str(search).strip().casefold()
        columns = ["Product", "SKU", "Brand", "Category", "Strain", "Vendor", "Needs setup"]
        haystack = filtered[columns].fillna("").astype(str).agg(" ".join, axis=1).str.casefold()
        filtered = filtered[haystack.str.contains(needle, regex=False)]
    if gaps_only:
        filtered = filtered[filtered["Needs setup"].astype(str).str.strip().ne("")]

    if filtered.empty:
        st.info("No products match the current filters.")
    else:
        display_columns = [
            "Product",
            "SKU",
            "Brand",
            "Category",
            "Strain",
            "Vendor",
            "Unit Cost",
            "Retail",
            "External IDs",
            "Needs setup",
        ]
        selected_id = ""
        selected_name = ""
        try:
            event = st.dataframe(
                filtered[display_columns],
                hide_index=True,
                width="stretch",
                on_select="rerun",
                selection_mode="single-row",
                key="product_master_table",
            )
            positions = list(getattr(getattr(event, "selection", None), "rows", []) or [])
            if positions:
                position = int(positions[0])
                if 0 <= position < len(filtered):
                    selected = filtered.iloc[position]
                    selected_id = str(selected["product_id"])
                    selected_name = str(selected["Product"])
        except TypeError:
            st.dataframe(filtered[display_columns], hide_index=True, width="stretch")
            labels = filtered["Product"].astype(str).tolist()
            chosen = st.selectbox("Product", labels, key="product_master_fallback_product")
            if st.button("Open Product 360", type="primary", use_container_width=True):
                selected_name = chosen
                selected_id = str(filtered.loc[filtered["Product"].astype(str) == chosen, "product_id"].iloc[0])

        # One row selection opens once. Remembering the selection prevents the dialog
        # from immediately reopening after the user closes it on a Streamlit rerun.
        if selected_id and state.get("_product_master_last_selection") != selected_id:
            state["_product_master_last_selection"] = selected_id
            state["product_360_selected_name"] = selected_name
            state["product_360_open"] = True

    selected_product = str(state.get("product_360_selected_name") or "").strip()
    if selected_product and bool(state.get("product_360_open", False)):
        render_product_360_dialog(state, selected_product)
