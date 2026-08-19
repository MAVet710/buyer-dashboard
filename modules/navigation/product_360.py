"""Global search and Product 360 drawer for the flat Buyer Dash shell.

This module is intentionally additive: it reads the same session DataFrames used
by the existing workspaces and routes actions back to existing page identifiers.
It does not create a second inventory, sales, purchasing, or audit source of
truth.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, MutableMapping

import pandas as pd
import streamlit as st

from services.workspace_navigation import (
    BUYER_WORKSPACE,
    COMMERCIAL_OPS,
    COMMERCIAL_WORKSPACE,
    DATA_HUB_WORKSPACE,
    DATA_OPERATIONS,
    EXTRACTION_WORKSPACE,
    HOME_OPS,
    HOME_WORKSPACE,
    INVENTORY_COUNTS_SECTION,
    PRODUCTION_OPS,
    RETAIL_OPS,
    queue_workspace_navigation,
)


PRODUCT_ALIASES = (
    "product name",
    "product_name",
    "product",
    "item name",
    "item_name",
    "itemname",
    "name",
    "sku name",
)
SKU_ALIASES = ("sku", "sku id", "product id", "item id")
ON_HAND_ALIASES = (
    "available",
    "on hand",
    "onhand",
    "on hand units",
    "onhandunits",
    "quantity",
    "qty",
)
SALES_QTY_ALIASES = (
    "quantity sold",
    "quantity_sold",
    "units sold",
    "unitssold",
    "total inventory sold",
    "qty sold",
)
SALES_DATE_ALIASES = (
    "order time",
    "order_time",
    "sale date",
    "sales date",
    "transaction date",
    "transaction_date",
    "date",
)
REPORT_START_ALIASES = (
    "report start",
    "report_start",
    "start date",
    "start_date",
    "reporting start",
)
REPORT_END_ALIASES = (
    "report end",
    "report_end",
    "end date",
    "end_date",
    "reporting end",
)
CATEGORY_ALIASES = ("category", "subcategory", "master category", "mastercategory")
BRAND_ALIASES = ("brand", "brand name", "vendor", "vendor name", "manufacturer", "producer")
COST_ALIASES = ("unit cost", "unit_cost", "cost", "cogs", "wholesale")
PRICE_ALIASES = ("retail price", "retail_price", "price", "med price", "msrp")
PACKAGE_ALIASES = (
    "metrc package id",
    "package id",
    "packageid",
    "batch",
    "batch number",
    "lot number",
    "lot",
)


@dataclass(frozen=True)
class SearchResult:
    kind: str
    label: str
    subtitle: str
    product_name: str = ""
    route_group: str = ""
    route_workspace: str = ""
    route_section: str = ""


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().casefold()).strip()


def _column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    if frame is None or frame.empty:
        return None
    normalized = {_norm(column): str(column) for column in frame.columns}
    for alias in aliases:
        found = normalized.get(_norm(alias))
        if found:
            return found
    return None


def _first_frame(state: MutableMapping[str, Any], *keys: str) -> pd.DataFrame:
    for key in keys:
        frame = state.get(key)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            return frame
    return pd.DataFrame()


def _number(series: pd.Series | Any) -> pd.Series:
    if isinstance(series, pd.Series):
        cleaned = series.astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False)
        return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)
    return pd.Series(dtype=float)


def _inventory_frame(state: MutableMapping[str, Any]) -> pd.DataFrame:
    return _first_frame(
        state,
        "active_inventory_df",
        "inv_raw_df",
        "demo_inventory_df",
        "demo_catalog_df",
    )


def _sales_frame(state: MutableMapping[str, Any]) -> pd.DataFrame:
    return _first_frame(
        state,
        "active_sales_df",
        "sales_raw_df",
        "demo_sales_df",
        "extra_sales_df",
    )


def _sales_window_days(sales_rows: pd.DataFrame) -> int:
    """Infer the loaded reporting window without pretending all files are 30 days."""
    if sales_rows is None or sales_rows.empty:
        return 30

    start_col = _column(sales_rows, REPORT_START_ALIASES)
    end_col = _column(sales_rows, REPORT_END_ALIASES)
    if start_col and end_col:
        starts = pd.to_datetime(sales_rows[start_col], errors="coerce").dropna()
        ends = pd.to_datetime(sales_rows[end_col], errors="coerce").dropna()
        if not starts.empty and not ends.empty:
            days = int((ends.max().normalize() - starts.min().normalize()).days) + 1
            if days > 0:
                return days

    date_col = _column(sales_rows, SALES_DATE_ALIASES)
    if date_col:
        dates = pd.to_datetime(sales_rows[date_col], errors="coerce").dropna()
        normalized = dates.dt.normalize() if not dates.empty else dates
        if not dates.empty and normalized.nunique() >= 2:
            return max(1, int((normalized.max() - normalized.min()).days) + 1)

    # An aggregate export with no explicit start/end does not expose a reliable
    # time window. Thirty days is the conservative compatibility fallback used
    # only for display/velocity normalization, and Product 360 labels it.
    return 30


def _tool_results(query: str) -> list[SearchResult]:
    commands = (
        SearchResult("Tool", "Inventory", "Stock health, reorder risk, and aging", route_group=RETAIL_OPS, route_workspace=BUYER_WORKSPACE, route_section="📊 Inventory Dashboard"),
        SearchResult("Tool", "Inventory Audits", "Scan, pause, resume, and reconcile counts", route_group=RETAIL_OPS, route_workspace=BUYER_WORKSPACE, route_section=INVENTORY_COUNTS_SECTION),
        SearchResult("Tool", "Buying Recommendations", "Buyer Intelligence recommendations and risks", route_group=RETAIL_OPS, route_workspace=BUYER_WORKSPACE, route_section="🧠 Buyer Intelligence"),
        SearchResult("Tool", "Purchase Orders", "Build and review purchase orders", route_group=RETAIL_OPS, route_workspace=BUYER_WORKSPACE, route_section="🧾 PO Builder"),
        SearchResult("Tool", "Buying Budget", "Purchasing budget and committed spend", route_group=RETAIL_OPS, route_workspace=BUYER_WORKSPACE, route_section="💰 Purchasing Budget"),
        SearchResult("Tool", "Orders", "Customer orders and fulfillment", route_group=COMMERCIAL_OPS, route_workspace=COMMERCIAL_WORKSPACE),
        SearchResult("Tool", "Extraction", "Extraction runs, yield, QA, and economics", route_group=PRODUCTION_OPS, route_workspace=EXTRACTION_WORKSPACE),
        SearchResult("Tool", "Compliance Q&A", "Reviewed compliance source workflow", route_group=RETAIL_OPS, route_workspace=BUYER_WORKSPACE, route_section="🧭 Compliance Q&A"),
        SearchResult("Tool", "Product Name Mapper", "Map METRC items to facility nomenclature", route_group=RETAIL_OPS, route_workspace=BUYER_WORKSPACE, route_section="🏷️ Nomenclature Mapper"),
        SearchResult("Tool", "Imports & Data", "Upload, map, review, and publish operational files", route_group=DATA_OPERATIONS, route_workspace=DATA_HUB_WORKSPACE),
        SearchResult("Tool", "Home", "Role-aware operations command center", route_group=HOME_OPS, route_workspace=HOME_WORKSPACE),
    )
    needle = _norm(query)
    return [
        result
        for result in commands
        if needle in _norm(result.label) or needle in _norm(result.subtitle)
    ][:5]


def _search_product_frame(
    frame: pd.DataFrame,
    needle: str,
    *,
    seen: set[str],
    limit: int,
) -> list[SearchResult]:
    product_col = _column(frame, PRODUCT_ALIASES)
    if not product_col:
        return []
    sku_col = _column(frame, SKU_ALIASES)
    brand_col = _column(frame, BRAND_ALIASES)
    package_col = _column(frame, PACKAGE_ALIASES)
    fields = [product_col]
    for optional in (sku_col, brand_col, package_col):
        if optional and optional not in fields:
            fields.append(optional)
    haystack = frame[fields].fillna("").astype(str).agg(" ".join, axis=1).map(_norm)
    matches = frame[haystack.str.contains(re.escape(needle), regex=True, na=False)]
    results: list[SearchResult] = []
    for _, row in matches.head(limit * 3).iterrows():
        product = str(row.get(product_col) or "").strip()
        if not product or product in seen:
            continue
        seen.add(product)
        subtitle_parts = []
        if brand_col and str(row.get(brand_col) or "").strip():
            subtitle_parts.append(str(row.get(brand_col)).strip())
        if sku_col and str(row.get(sku_col) or "").strip():
            subtitle_parts.append(f"SKU {str(row.get(sku_col)).strip()}")
        results.append(
            SearchResult(
                "Product",
                product,
                " · ".join(subtitle_parts) or "Open Product 360",
                product_name=product,
            )
        )
        if len(results) >= limit:
            break
    return results


def search_buyer_dash(
    state: MutableMapping[str, Any],
    query: str,
    *,
    limit: int = 8,
) -> list[SearchResult]:
    """Search loaded products/packages and common tools without sending rows to AI."""
    needle = _norm(query)
    if len(needle) < 2:
        return []

    results: list[SearchResult] = []
    seen: set[str] = set()
    for frame in (_inventory_frame(state), _sales_frame(state)):
        if len(results) >= limit:
            break
        if frame is None or frame.empty:
            continue
        results.extend(
            _search_product_frame(
                frame,
                needle,
                seen=seen,
                limit=limit - len(results),
            )
        )

    remaining = max(0, limit - len(results))
    if remaining:
        results.extend(_tool_results(query)[:remaining])
    return results[:limit]


def build_product_360_snapshot(
    state: MutableMapping[str, Any],
    product_name: str,
) -> dict[str, Any]:
    """Build a read-only Product 360 snapshot from the existing session sources."""
    inventory = _inventory_frame(state)
    sales = _sales_frame(state)
    inv_name = _column(inventory, PRODUCT_ALIASES)
    sales_name = _column(sales, PRODUCT_ALIASES)

    inv_rows = pd.DataFrame()
    if inv_name:
        inv_rows = inventory[
            inventory[inv_name].astype(str).str.strip().str.casefold()
            == str(product_name).strip().casefold()
        ].copy()
    sales_rows = pd.DataFrame()
    if sales_name:
        sales_rows = sales[
            sales[sales_name].astype(str).str.strip().str.casefold()
            == str(product_name).strip().casefold()
        ].copy()

    on_hand_col = _column(inv_rows, ON_HAND_ALIASES)
    sold_col = _column(sales_rows, SALES_QTY_ALIASES)
    cost_col = _column(inv_rows, COST_ALIASES)
    price_col = _column(inv_rows, PRICE_ALIASES)
    sku_col = _column(inv_rows, SKU_ALIASES)
    brand_col = _column(inv_rows, BRAND_ALIASES)
    category_col = _column(inv_rows, CATEGORY_ALIASES)
    package_col = _column(inv_rows, PACKAGE_ALIASES)

    on_hand = float(_number(inv_rows[on_hand_col]).sum()) if on_hand_col else 0.0
    sold_window = float(_number(sales_rows[sold_col]).sum()) if sold_col else 0.0
    sales_window_days = _sales_window_days(sales_rows)
    daily_velocity = sold_window / max(sales_window_days, 1) if sold_window > 0 else 0.0
    units_sold_30d = daily_velocity * 30.0
    days_on_hand = on_hand / daily_velocity if daily_velocity > 0 else math.inf
    target_units = max(0, math.ceil(daily_velocity * 21.0 - on_hand)) if daily_velocity > 0 else 0

    unit_cost = float(_number(inv_rows[cost_col]).median()) if cost_col and not inv_rows.empty else 0.0
    retail_price = float(_number(inv_rows[price_col]).median()) if price_col and not inv_rows.empty else 0.0
    margin_pct = ((retail_price - unit_cost) / retail_price * 100.0) if retail_price > 0 else None

    def first_value(column: str | None) -> str:
        if not column or inv_rows.empty:
            return ""
        values = inv_rows[column].dropna().astype(str).str.strip()
        return str(values.iloc[0]) if not values.empty else ""

    package_values: list[str] = []
    if package_col and not inv_rows.empty:
        package_values = [
            value
            for value in inv_rows[package_col].dropna().astype(str).str.strip().unique().tolist()
            if value
        ]

    return {
        "product_name": product_name,
        "sku": first_value(sku_col),
        "brand": first_value(brand_col),
        "category": first_value(category_col),
        "on_hand": on_hand,
        "units_sold_window": sold_window,
        "sales_window_days": sales_window_days,
        "units_sold_30d": units_sold_30d,
        "daily_velocity": daily_velocity,
        "days_on_hand": days_on_hand,
        "target_units": target_units,
        "unit_cost": unit_cost,
        "retail_price": retail_price,
        "margin_pct": margin_pct,
        "estimated_reorder_cost": target_units * unit_cost,
        "packages": package_values,
        "inventory_rows": inv_rows,
        "sales_rows": sales_rows,
    }


def stage_product_for_po(
    state: MutableMapping[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Add one Product 360 recommendation to the existing PO Builder state."""
    quantity = max(1, int(snapshot.get("target_units") or 0))
    unit_cost = max(0.0, float(snapshot.get("unit_cost") or 0.0))
    item = {
        "SKU": str(snapshot.get("sku") or ""),
        "Description": str(snapshot.get("product_name") or "").strip(),
        "Strain": "",
        "Size": "",
        "Quantity": quantity,
        "Price": unit_cost,
        "Total": quantity * unit_cost,
    }
    items = state.setdefault("po_items", [])
    if not isinstance(items, list):
        items = []
        state["po_items"] = items

    duplicate = next(
        (
            row
            for row in items
            if isinstance(row, dict)
            and _norm(row.get("Description")) == _norm(item["Description"])
            and int(row.get("Quantity") or 0) == quantity
        ),
        None,
    )
    if duplicate is None:
        items.append(item)
        return item
    return dict(duplicate)


def _route(state: MutableMapping[str, Any], *, group: str, workspace: str, section: str = "") -> None:
    queue_workspace_navigation(state, group=group, workspace=workspace, buyer_section=section)
    state["product_360_open"] = False
    st.rerun()


def _drawer_css() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stDialog"] > div[role="dialog"] {
            margin-left: auto !important;
            margin-right: 0 !important;
            min-height: 100vh !important;
            max-height: 100vh !important;
            border-radius: 18px 0 0 18px !important;
            border-left: 1px solid rgba(255,154,60,.28) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_product_body(state: MutableMapping[str, Any], snapshot: dict[str, Any]) -> None:
    product = snapshot["product_name"]
    close_col, _ = st.columns([1, 5])
    if close_col.button("Close", key="product_360_close"):
        state["product_360_open"] = False
        st.rerun()

    st.caption("PRODUCT 360 · operational context")
    st.markdown(f"## {product}")
    identity = " · ".join(value for value in [snapshot.get("brand"), snapshot.get("sku")] if value)
    if identity:
        st.caption(identity)

    metrics = st.columns(4)
    metrics[0].metric("On hand", f"{snapshot['on_hand']:,.0f}")
    metrics[1].metric("30d sold", f"{snapshot['units_sold_30d']:,.1f}")
    doh = snapshot["days_on_hand"]
    metrics[2].metric("Days on hand", "∞" if not math.isfinite(doh) else f"{doh:,.1f}")
    margin = snapshot.get("margin_pct")
    metrics[3].metric("Margin", "—" if margin is None else f"{margin:,.1f}%")
    st.caption(
        f"Sales velocity normalized from the loaded {snapshot['sales_window_days']}-day reporting window."
    )

    overview_tab, inventory_tab, sales_tab, purchasing_tab, packages_tab, audits_tab = st.tabs(
        ["Overview", "Inventory", "Sales", "Purchasing", "Packages", "Audits"]
    )
    with overview_tab:
        if snapshot["target_units"] > 0:
            st.error(
                f"Low-cover signal: current normalized velocity suggests approximately "
                f"{snapshot['target_units']:,} units to reach a 21-day target."
            )
        elif snapshot["daily_velocity"] <= 0 and snapshot["on_hand"] > 0:
            st.warning("No recent unit velocity was detected for the current on-hand inventory.")
        else:
            st.success("No immediate 21-day replenishment gap is visible from the loaded data.")
        st.write(
            f"**Category:** {snapshot.get('category') or 'Not available'}  \n"
            f"**Unit cost:** ${snapshot['unit_cost']:,.2f}  \n"
            f"**Retail price:** ${snapshot['retail_price']:,.2f}"
        )
    with inventory_tab:
        if snapshot["inventory_rows"].empty:
            st.info("No inventory rows are loaded for this product.")
        else:
            st.dataframe(snapshot["inventory_rows"], width="stretch", hide_index=True)
    with sales_tab:
        st.caption(
            f"Raw loaded sales: {snapshot['units_sold_window']:,.0f} units across the inferred "
            f"{snapshot['sales_window_days']}-day window."
        )
        if snapshot["sales_rows"].empty:
            st.info("No sales rows are loaded for this product.")
        else:
            st.dataframe(snapshot["sales_rows"].head(250), width="stretch", hide_index=True)
    with purchasing_tab:
        st.metric("Suggested 21-day fill", f"{snapshot['target_units']:,} units")
        st.metric("Estimated cost", f"${snapshot['estimated_reorder_cost']:,.2f}")
        st.caption("The quantity is a draft recommendation. The existing PO Builder remains the final review/export workflow.")
        if snapshot["target_units"] > 0:
            if st.button("Add to PO", type="primary", width="stretch", key="product_360_add_to_po"):
                stage_product_for_po(state, snapshot)
                _route(state, group=RETAIL_OPS, workspace=BUYER_WORKSPACE, section="🧾 PO Builder")
        elif st.button("Open PO Builder", width="stretch", key="product_360_open_po"):
            _route(state, group=RETAIL_OPS, workspace=BUYER_WORKSPACE, section="🧾 PO Builder")
    with packages_tab:
        packages = snapshot.get("packages") or []
        if packages:
            st.write("\n".join(f"• {value}" for value in packages[:50]))
        else:
            st.info("No package / batch identifiers were detected in the current inventory source.")
    with audits_tab:
        st.caption("Keep the Product 360 context and open the existing durable audit workflow.")
        if st.button("Audit this SKU", width="stretch", key="product_360_audit"):
            state["inventory_audit_product_focus"] = product
            _route(state, group=RETAIL_OPS, workspace=BUYER_WORKSPACE, section=INVENTORY_COUNTS_SECTION)

    st.markdown("#### Quick actions")
    actions = st.columns(3)
    if actions[0].button("Inventory", width="stretch", key="product_360_inventory"):
        _route(state, group=RETAIL_OPS, workspace=BUYER_WORKSPACE, section="📊 Inventory Dashboard")
    if actions[1].button("Sales", width="stretch", key="product_360_sales"):
        _route(state, group=RETAIL_OPS, workspace=BUYER_WORKSPACE, section="📈 Trends")
    if actions[2].button("Purchase Orders", width="stretch", key="product_360_po"):
        _route(state, group=RETAIL_OPS, workspace=BUYER_WORKSPACE, section="🧾 PO Builder")


def render_product_360_dialog(state: MutableMapping[str, Any], product_name: str) -> None:
    snapshot = build_product_360_snapshot(state, product_name)
    _drawer_css()
    if hasattr(st, "dialog"):
        @st.dialog("Product 360", width="large")
        def _dialog() -> None:
            _render_product_body(state, snapshot)

        _dialog()
    else:
        with st.container(border=True):
            _render_product_body(state, snapshot)


def render_global_search(state: MutableMapping[str, Any]) -> None:
    """Render always-on local search and open Product 360 on demand."""
    st.markdown(
        """
        <style>
        .st-key-buyer_dash_global_search {position: relative; z-index: 30;}
        .st-key-buyer_dash_global_search input {font-size: .95rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="buyer_dash_global_search"):
        query = st.text_input(
            "Search Buyer Dash",
            key="buyer_dash_global_search_query",
            placeholder="Search products, packages, and tools…",
            label_visibility="collapsed",
            help="Local search across loaded product/package data and Buyer Dash tools. Row data is not sent to AI.",
        )
        if len(_norm(query)) >= 2:
            results = search_buyer_dash(state, query)
            with st.container(border=True):
                if not results:
                    st.caption("No matching products, packages, or tools found.")
                for index, result in enumerate(results):
                    label_col, action_col = st.columns([5, 1])
                    with label_col:
                        st.markdown(f"**{result.label}**")
                        st.caption(f"{result.kind} · {result.subtitle}")
                    with action_col:
                        if st.button("Open", key=f"global_search_open_{index}_{_norm(result.label)}", width="stretch"):
                            if result.kind == "Product" and result.product_name:
                                state["product_360_selected_name"] = result.product_name
                                state["product_360_open"] = True
                                st.rerun()
                            elif result.route_workspace:
                                _route(
                                    state,
                                    group=result.route_group,
                                    workspace=result.route_workspace,
                                    section=result.route_section,
                                )

    selected = str(state.get("product_360_selected_name") or "").strip()
    if selected and bool(state.get("product_360_open", False)):
        render_product_360_dialog(state, selected)
