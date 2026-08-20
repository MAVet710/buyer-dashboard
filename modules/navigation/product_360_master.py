"""Canonical Product Master enrichment for the existing Product 360 experience.

The existing Product 360 module remains the compatibility fallback.  This module
wraps its read/search/render functions at package import time so mastered products
receive durable identity, vendor, external mapping, and value-history context
without duplicating the existing inventory/sales/PO action implementation.
"""

from __future__ import annotations

from datetime import date, timedelta
import math
from typing import Any, MutableMapping

import pandas as pd
import streamlit as st

from modules.product_master.resolver import resolve_product_master, search_product_master


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return " ".join(_clean(value).casefold().split())


def _load_master_context(
    state: MutableMapping[str, Any], product_name: str, sku: str = ""
) -> dict[str, Any]:
    organization_id = _clean(state.get("active_organization_id"))
    if not organization_id:
        return {}
    try:
        from modules.coman.db import create_coman_engine

        return resolve_product_master(
            create_coman_engine(),
            organization_id,
            product_name=product_name,
            sku=sku,
        )
    except Exception:
        return {}


def _load_master_search(
    state: MutableMapping[str, Any], query: str, *, limit: int
) -> list[dict[str, Any]]:
    organization_id = _clean(state.get("active_organization_id"))
    if not organization_id:
        return []
    try:
        from modules.coman.db import create_coman_engine

        return search_product_master(
            create_coman_engine(),
            organization_id,
            query,
            limit=limit,
        )
    except Exception:
        return []


def _apply_vendor_constraints(quantity: int, *, moq: float, case_pack: float) -> int:
    value = max(0, int(quantity))
    if value <= 0:
        return 0
    if moq > 0:
        value = max(value, int(math.ceil(moq)))
    if case_pack > 0:
        value = int(math.ceil(value / case_pack) * case_pack)
    return max(0, value)


def enrich_product_360_snapshot(
    snapshot: dict[str, Any], master: dict[str, Any]
) -> dict[str, Any]:
    """Overlay canonical master data while preserving report-derived operations data."""
    if not master:
        return snapshot
    enriched = dict(snapshot)
    enriched["product_master"] = dict(master)
    enriched["canonical_product_id"] = _clean(master.get("canonical_product_id"))

    for key in ("product_name", "sku", "brand", "category"):
        value = _clean(master.get(key))
        if value:
            enriched[key] = value
    for key in ("strain", "subcategory", "manufacturer", "product_format", "description"):
        enriched[key] = _clean(master.get(key))

    primary_vendor = _clean(master.get("primary_vendor"))
    if primary_vendor:
        enriched["vendor"] = primary_vendor
    enriched["vendor_sku"] = _clean(master.get("vendor_sku"))
    enriched["vendor_lead_time_days"] = int(master.get("vendor_lead_time_days") or 0)
    enriched["vendor_moq"] = float(master.get("vendor_moq") or 0)
    enriched["vendor_case_pack"] = float(master.get("vendor_case_pack") or 0)
    enriched["external_mappings"] = list(master.get("external_mappings") or [])
    enriched["product_aliases"] = list(master.get("aliases") or [])
    enriched["value_history"] = list(master.get("value_history") or [])

    canonical_cost = float(master.get("unit_cost") or 0)
    canonical_retail = float(master.get("retail_price") or 0)
    if canonical_cost > 0:
        enriched["unit_cost"] = canonical_cost
    if canonical_retail > 0:
        enriched["retail_price"] = canonical_retail

    unit_cost = max(0.0, float(enriched.get("unit_cost") or 0))
    retail_price = max(0.0, float(enriched.get("retail_price") or 0))
    on_hand = max(0.0, float(enriched.get("on_hand") or 0))
    enriched["margin_pct"] = (
        (retail_price - unit_cost) / retail_price * 100.0 if retail_price > 0 else None
    )
    enriched["inventory_value"] = on_hand * unit_cost
    enriched["retail_value"] = on_hand * retail_price
    enriched["gross_profit_value"] = on_hand * max(0.0, retail_price - unit_cost)

    raw_target = max(0, int(enriched.get("target_units") or 0))
    constrained_target = _apply_vendor_constraints(
        raw_target,
        moq=enriched["vendor_moq"],
        case_pack=enriched["vendor_case_pack"],
    )
    enriched["raw_target_units"] = raw_target
    enriched["target_units"] = constrained_target
    enriched["estimated_reorder_cost"] = constrained_target * unit_cost
    enriched["estimated_reorder_retail_value"] = constrained_target * retail_price
    enriched["estimated_reorder_gross_profit"] = constrained_target * max(
        0.0, retail_price - unit_cost
    )

    days_on_hand = float(enriched.get("days_on_hand") or math.inf)
    lead_time = enriched["vendor_lead_time_days"]
    safety_days = 2
    if lead_time > 0 and math.isfinite(days_on_hand):
        order_in_days = max(0, int(math.floor(days_on_hand - lead_time - safety_days)))
        enriched["recommended_order_date"] = (
            date.today() + timedelta(days=order_in_days)
        ).isoformat()
        if constrained_target > 0:
            constraint_text = ""
            if constrained_target != raw_target:
                constraint_text = (
                    f" Vendor MOQ/case pack rounds the {raw_target:,}-unit need "
                    f"to {constrained_target:,}."
                )
            if days_on_hand <= lead_time + safety_days:
                enriched["decision_signal"] = "ORDER NOW"
                enriched["decision_reason"] = (
                    f"Coverage is {days_on_hand:.1f} days versus a {lead_time}-day vendor lead time "
                    f"plus {safety_days} safety days.{constraint_text}"
                )
            else:
                enriched["decision_reason"] = (
                    f"{enriched.get('decision_reason', '')} Recommended order date: "
                    f"{enriched['recommended_order_date']} based on a {lead_time}-day vendor lead time."
                    f"{constraint_text}"
                ).strip()
    else:
        enriched.setdefault("recommended_order_date", "")

    return enriched


def _master_subtitle(row: dict[str, Any]) -> str:
    details = [
        _clean(row.get("brand")),
        f"SKU {_clean(row.get('sku'))}" if _clean(row.get("sku")) else "",
        _clean(row.get("category")),
        _clean(row.get("strain")),
    ]
    return " · ".join(value for value in details if value) or "Canonical Product Master"


def _render_master_details(snapshot: dict[str, Any]) -> None:
    master = snapshot.get("product_master")
    if not isinstance(master, dict) or not master:
        return
    st.markdown("#### Product Master")
    with st.expander("Canonical identity, vendor & value history", expanded=False):
        identity_cols = st.columns(3)
        identity_cols[0].metric("Primary vendor", master.get("primary_vendor") or "—")
        lead = int(master.get("vendor_lead_time_days") or 0)
        identity_cols[1].metric("Lead time", f"{lead} days" if lead else "—")
        order_date = _clean(snapshot.get("recommended_order_date"))
        identity_cols[2].metric("Order by", order_date or "—")

        st.write(
            f"**Canonical ID:** {master.get('canonical_product_id') or '—'}  \n"
            f"**Brand:** {master.get('brand') or '—'}  \n"
            f"**Category:** {master.get('category') or '—'}  \n"
            f"**Subcategory:** {master.get('subcategory') or '—'}  \n"
            f"**Strain:** {master.get('strain') or '—'}  \n"
            f"**Manufacturer:** {master.get('manufacturer') or '—'}  \n"
            f"**Format:** {master.get('product_format') or '—'}  \n"
            f"**Vendor SKU:** {master.get('vendor_sku') or '—'}  \n"
            f"**MOQ:** {float(master.get('vendor_moq') or 0):g}  \n"
            f"**Case pack:** {float(master.get('vendor_case_pack') or 0):g}"
        )

        mappings = list(master.get("external_mappings") or [])
        if mappings:
            st.caption("External system mappings")
            st.dataframe(pd.DataFrame(mappings), width="stretch", hide_index=True)

        history = list(master.get("value_history") or [])
        if history:
            st.caption("Cost / price history")
            frame = pd.DataFrame(history)
            columns = [
                column
                for column in (
                    "effective_at",
                    "value_type",
                    "amount",
                    "previous_amount",
                    "currency",
                    "source",
                    "source_reference",
                )
                if column in frame.columns
            ]
            st.dataframe(frame[columns].head(50), width="stretch", hide_index=True)


def install_product_360_master_patch() -> None:
    """Patch Product 360 once, retaining every original function as fallback."""
    from modules.navigation import product_360 as p360

    if bool(getattr(p360, "_product_master_patch_installed", False)):
        return

    original_build = p360.build_product_360_snapshot
    original_search = p360.search_buyer_dash
    original_render_body = p360._render_product_body

    def build_product_360_snapshot(
        state: MutableMapping[str, Any], product_name: str
    ) -> dict[str, Any]:
        base = original_build(state, product_name)
        master = _load_master_context(state, product_name, _clean(base.get("sku")))
        return enrich_product_360_snapshot(base, master)

    def search_buyer_dash(
        state: MutableMapping[str, Any], query: str, *, limit: int = 8
    ) -> list[Any]:
        master_rows = _load_master_search(state, query, limit=limit)
        canonical = [
            p360.SearchResult(
                "Product",
                _clean(row.get("product_name")) or _clean(row.get("sku")),
                _master_subtitle(row),
                product_name=_clean(row.get("product_name")),
            )
            for row in master_rows
            if _clean(row.get("product_name")) or _clean(row.get("sku"))
        ]
        fallback = original_search(state, query, limit=limit)
        combined: list[Any] = []
        seen: set[tuple[str, str]] = set()
        for result in [*canonical, *fallback]:
            identity = (
                _norm(getattr(result, "kind", "")),
                _norm(getattr(result, "product_name", "") or getattr(result, "label", "")),
            )
            if identity in seen:
                continue
            seen.add(identity)
            combined.append(result)
            if len(combined) >= limit:
                break
        return combined

    def render_product_body(
        state: MutableMapping[str, Any], snapshot: dict[str, Any]
    ) -> None:
        original_render_body(state, snapshot)
        _render_master_details(snapshot)

    p360.build_product_360_snapshot = build_product_360_snapshot
    p360.search_buyer_dash = search_buyer_dash
    p360._render_product_body = render_product_body
    p360._product_master_patch_installed = True
