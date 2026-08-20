"""Table-first Inventory v2 command center.

Inventory v2 is additive: retail rows are built from the same loaded Buyer Dash
sources, while production rows are read from the durable Co-Man inventory ledger.
Existing audits, PO Builder, Product 360, Package Studio, and Data Hub remain the
underlying action destinations and sources of truth.
"""

from __future__ import annotations

from collections.abc import MutableMapping
import math
import re
from typing import Any

import pandas as pd
import streamlit as st

from modules.coman.db import ComanDatabaseConfigurationError, create_coman_engine
from modules.navigation.operation_context_bar import PRODUCTION_OPERATION, RETAIL_OPERATION
from modules.navigation.product_360 import build_product_360_snapshot, stage_product_for_po
from modules.package_studio.service import PackageStudioService
from services.workspace_navigation import (
    BUYER_WORKSPACE,
    INVENTORY_COUNTS_SECTION,
    RETAIL_OPS,
    queue_workspace_navigation,
)


PRODUCT_ALIASES = ("product name", "product_name", "product", "item name", "item_name", "name")
SKU_ALIASES = ("sku", "sku id", "product id", "item id")
PACKAGE_ALIASES = ("metrc package id", "package id", "packageid", "package", "batch", "batch number", "lot", "lot number")
AVAILABLE_ALIASES = ("available", "on hand", "onhand", "on hand units", "quantity", "qty", "inventory")
RESERVED_ALIASES = ("reserved", "reserved quantity", "allocated", "committed")
VENDOR_ALIASES = ("vendor", "vendor name", "supplier", "producer", "manufacturer")
ROOM_ALIASES = ("room", "location", "location name", "storage location", "sales floor")
CATEGORY_ALIASES = ("category", "subcategory", "master category", "mastercategory", "product type")
STATUS_ALIASES = ("status", "inventory status", "package status")
TAGS_ALIASES = ("tags", "tag")
STRAIN_ALIASES = ("strain", "strain name")
COST_ALIASES = ("unit cost", "unit_cost", "cost", "wholesale", "cogs")
PRICE_ALIASES = ("retail price", "retail_price", "price", "msrp", "med price")
RECEIVED_ALIASES = ("received date", "received_at", "received", "inventory date", "created date")
EXPIRATION_ALIASES = ("expiration date", "expires", "expiration", "expiry date", "expiry")
SALES_QTY_ALIASES = ("quantity sold", "quantity_sold", "units sold", "unitssold", "qty sold", "total inventory sold")
SALES_DATE_ALIASES = ("order time", "order_time", "sale date", "sales date", "transaction date", "date")
REPORT_START_ALIASES = ("report start", "report_start", "start date", "reporting start")
REPORT_END_ALIASES = ("report end", "report_end", "end date", "reporting end")

BUILTIN_VIEWS = (
    "All Inventory",
    "Low Stock",
    "Under 14 DOH",
    "Slow Movers",
    "Expiring 90 Days",
    "Bulk Packages",
    "Quarantine / Hold",
)


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
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy()
    return pd.DataFrame()


def _numeric(series: pd.Series | Any) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series(dtype=float)
    clean = (
        series.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
    )
    return pd.to_numeric(clean, errors="coerce").fillna(0.0)


def _text(frame: pd.DataFrame, aliases: tuple[str, ...], default: str = "") -> pd.Series:
    column = _column(frame, aliases)
    if not column:
        return pd.Series(default, index=frame.index, dtype="object")
    return frame[column].fillna(default).astype(str).str.strip()


def _number(frame: pd.DataFrame, aliases: tuple[str, ...], default: float = 0.0) -> pd.Series:
    column = _column(frame, aliases)
    if not column:
        return pd.Series(default, index=frame.index, dtype="float64")
    return _numeric(frame[column])


def _sales_window_days(frame: pd.DataFrame) -> int:
    if frame is None or frame.empty:
        return 30
    start_col = _column(frame, REPORT_START_ALIASES)
    end_col = _column(frame, REPORT_END_ALIASES)
    if start_col and end_col:
        start = pd.to_datetime(frame[start_col], errors="coerce").dropna()
        end = pd.to_datetime(frame[end_col], errors="coerce").dropna()
        if not start.empty and not end.empty:
            return max(1, int((end.max().normalize() - start.min().normalize()).days) + 1)
    date_col = _column(frame, SALES_DATE_ALIASES)
    if date_col:
        values = pd.to_datetime(frame[date_col], errors="coerce").dropna()
        if not values.empty and values.dt.normalize().nunique() >= 2:
            return max(1, int((values.max().normalize() - values.min().normalize()).days) + 1)
    return 30


def _sales_summary(state: MutableMapping[str, Any]) -> pd.DataFrame:
    sales = _first_frame(state, "active_sales_df", "sales_raw_df", "demo_sales_df", "extra_sales_df")
    product_col = _column(sales, PRODUCT_ALIASES)
    qty_col = _column(sales, SALES_QTY_ALIASES)
    if sales.empty or not product_col or not qty_col:
        return pd.DataFrame(columns=["_product_key", "30d Sold", "Daily Velocity"])
    local = pd.DataFrame(
        {
            "_product_key": sales[product_col].fillna("").astype(str).map(_norm),
            "_sold": _numeric(sales[qty_col]),
        }
    )
    grouped = local.groupby("_product_key", as_index=False)["_sold"].sum()
    window = _sales_window_days(sales)
    grouped["Daily Velocity"] = grouped["_sold"] / max(window, 1)
    grouped["30d Sold"] = grouped["Daily Velocity"] * 30.0
    return grouped[["_product_key", "30d Sold", "Daily Velocity"]]


def _derive_attention(frame: pd.DataFrame) -> pd.Series:
    attention = pd.Series("Healthy", index=frame.index, dtype="object")
    status = frame["Status"].fillna("").astype(str).str.casefold()
    available = pd.to_numeric(frame["Available"], errors="coerce").fillna(0.0)
    reserved = pd.to_numeric(frame["Reserved"], errors="coerce").fillna(0.0)
    doh = pd.to_numeric(frame["DOH"], errors="coerce")
    age = pd.to_numeric(frame["Age"], errors="coerce").fillna(0.0)
    sold = pd.to_numeric(frame["30d Sold"], errors="coerce").fillna(0.0)
    expiry = pd.to_numeric(
        frame.get("Days to Expiry", pd.Series(math.inf, index=frame.index)),
        errors="coerce",
    )

    attention[status.str.contains("quarantine|hold|failed", regex=True, na=False)] = "Hold"
    attention[(available <= 0) & ~status.str.contains("quarantine|hold|failed", regex=True, na=False)] = "Out of stock"
    attention[(reserved > available) & (available > 0)] = "Over-reserved"
    attention[(doh <= 7) & (available > 0)] = "Reorder now"
    attention[(expiry <= 90) & (expiry >= 0) & (available > 0)] = "Expiring"
    attention[(age >= 60) & (sold <= 2) & (available > 0)] = "Aging"
    return attention


def build_retail_inventory_table(
    state: MutableMapping[str, Any], *, grain: str = "Products"
) -> pd.DataFrame:
    """Normalize loaded retail inventory into one table-first operating model."""

    source = _first_frame(
        state,
        "active_inventory_df",
        "inv_raw_df",
        "demo_inventory_df",
        "demo_catalog_df",
    )
    product_col = _column(source, PRODUCT_ALIASES)
    if source.empty or not product_col:
        return pd.DataFrame()

    received_col = _column(source, RECEIVED_ALIASES)
    expiry_col = _column(source, EXPIRATION_ALIASES)
    now = pd.Timestamp.now().normalize()
    received = (
        pd.to_datetime(source[received_col], errors="coerce")
        if received_col
        else pd.Series(pd.NaT, index=source.index)
    )
    expiry = (
        pd.to_datetime(source[expiry_col], errors="coerce")
        if expiry_col
        else pd.Series(pd.NaT, index=source.index)
    )

    normalized = pd.DataFrame(index=source.index)
    normalized["SKU"] = _text(source, SKU_ALIASES)
    normalized["Product"] = source[product_col].fillna("").astype(str).str.strip()
    normalized["Strain"] = _text(source, STRAIN_ALIASES)
    normalized["Package ID"] = _text(source, PACKAGE_ALIASES)
    normalized["External Package ID"] = normalized["Package ID"]
    normalized["Vendor"] = _text(source, VENDOR_ALIASES)
    normalized["Room"] = _text(source, ROOM_ALIASES)
    normalized["Category"] = _text(source, CATEGORY_ALIASES)
    normalized["Status"] = _text(source, STATUS_ALIASES, "Available").replace("", "Available")
    normalized["Tags"] = _text(source, TAGS_ALIASES)
    normalized["Available"] = _number(source, AVAILABLE_ALIASES)
    normalized["Reserved"] = _number(source, RESERVED_ALIASES)
    normalized["Cost"] = _number(source, COST_ALIASES)
    normalized["Retail"] = _number(source, PRICE_ALIASES)
    normalized["Age"] = (now - received.dt.normalize()).dt.days.clip(lower=0).fillna(0).astype(int)
    normalized["Days to Expiry"] = (expiry.dt.normalize() - now).dt.days
    normalized["Durable Lot ID"] = ""
    normalized["Unit"] = _text(source, ("inventory unit", "unit", "uom"), "unit").replace("", "unit")
    normalized["_product_key"] = normalized["Product"].map(_norm)

    sales = _sales_summary(state)
    normalized = normalized.merge(sales, on="_product_key", how="left")
    normalized["30d Sold"] = pd.to_numeric(normalized["30d Sold"], errors="coerce").fillna(0.0)
    normalized["Daily Velocity"] = pd.to_numeric(normalized["Daily Velocity"], errors="coerce").fillna(0.0)

    if str(grain).casefold() == "products":
        aggregations: dict[str, Any] = {
            "SKU": "first",
            "Strain": "first",
            "Vendor": "first",
            "Room": "first",
            "Category": "first",
            "Status": "first",
            "Tags": "first",
            "Available": "sum",
            "Reserved": "sum",
            "Cost": "median",
            "Retail": "median",
            "Age": "max",
            "Days to Expiry": "min",
            "30d Sold": "first",
            "Daily Velocity": "first",
            "Unit": "first",
        }
        normalized = normalized.groupby(["Product", "_product_key"], as_index=False).agg(aggregations)
        normalized["Package ID"] = ""
        normalized["External Package ID"] = ""
        normalized["Durable Lot ID"] = ""

    velocity = pd.to_numeric(normalized["Daily Velocity"], errors="coerce").fillna(0.0)
    available = pd.to_numeric(normalized["Available"], errors="coerce").fillna(0.0)
    normalized["DOH"] = (available / velocity.replace(0, pd.NA)).astype("Float64")
    normalized["Margin"] = (
        (normalized["Retail"] - normalized["Cost"])
        / normalized["Retail"].replace(0, pd.NA)
        * 100
    ).astype("Float64")
    normalized["Attention"] = _derive_attention(normalized)
    return normalized.reset_index(drop=True)


def build_production_inventory_table(state: MutableMapping[str, Any]) -> pd.DataFrame:
    """Read facility-scoped durable production packages from the shared ledger."""

    organization_id = str(state.get("active_organization_id") or "")
    facility_id = str(state.get("active_facility_id") or "")
    if not organization_id or not facility_id:
        return pd.DataFrame()
    try:
        service = PackageStudioService(create_coman_engine())
        lots = service.list_available_lots(organization_id, facility_id)
        products = {item.product_id: item for item in service.list_products(organization_id)}
    except (ComanDatabaseConfigurationError, Exception):
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for lot in lots:
        product = products.get(lot.product_id)
        item_type = str(getattr(product, "item_type", "") or "")
        rows.append(
            {
                "SKU": lot.sku,
                "Product": lot.product_name,
                "Strain": "",
                "Package ID": lot.compliance_package_id or lot.lot_code,
                "External Package ID": lot.compliance_package_id or lot.lot_code,
                "Lot": lot.lot_code,
                "Vendor": "",
                "Room": lot.location_code,
                "Category": item_type.replace("_", " ").title(),
                "Status": "Available",
                "Tags": "",
                "Available": lot.balance,
                "Reserved": 0.0,
                "Unit": lot.unit,
                "30d Sold": 0.0,
                "Daily Velocity": 0.0,
                "DOH": pd.NA,
                "Cost": 0.0,
                "Retail": 0.0,
                "Margin": pd.NA,
                "Age": 0,
                "Days to Expiry": pd.NA,
                "Attention": "Production ready",
                "Durable Lot ID": lot.lot_id,
                "_product_key": _norm(lot.product_name),
            }
        )
    return pd.DataFrame(rows)


def apply_inventory_filters(
    frame: pd.DataFrame,
    *,
    search: str = "",
    saved_view: str = "All Inventory",
    status: str = "All",
    vendor: str = "All",
    room: str = "All",
    category: str = "All",
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=list(frame.columns) if isinstance(frame, pd.DataFrame) else None)
    filtered = frame.copy()
    needle = _norm(search)
    if needle:
        searchable = [
            column
            for column in ("SKU", "Product", "Strain", "External Package ID", "Package ID", "Vendor", "Room", "Category", "Tags")
            if column in filtered.columns
        ]
        haystack = filtered[searchable].fillna("").astype(str).agg(" ".join, axis=1).map(_norm)
        filtered = filtered[haystack.str.contains(re.escape(needle), regex=True, na=False)]

    for column, value in (("Status", status), ("Vendor", vendor), ("Room", room), ("Category", category)):
        if value != "All" and column in filtered.columns:
            filtered = filtered[filtered[column].fillna("").astype(str) == value]

    view = str(saved_view or "All Inventory")
    doh = pd.to_numeric(filtered.get("DOH"), errors="coerce")
    sold = pd.to_numeric(filtered.get("30d Sold"), errors="coerce").fillna(0.0)
    available = pd.to_numeric(filtered.get("Available"), errors="coerce").fillna(0.0)
    age = pd.to_numeric(filtered.get("Age"), errors="coerce").fillna(0.0)
    expiry = pd.to_numeric(filtered.get("Days to Expiry"), errors="coerce")
    status_text = filtered.get("Status", pd.Series("", index=filtered.index)).fillna("").astype(str).str.casefold()
    category_text = filtered.get("Category", pd.Series("", index=filtered.index)).fillna("").astype(str).str.casefold()
    unit_text = filtered.get("Unit", pd.Series("", index=filtered.index)).fillna("").astype(str).str.casefold()

    if view == "Low Stock":
        filtered = filtered[(doh <= 7) | (available <= 0)]
    elif view == "Under 14 DOH":
        filtered = filtered[doh <= 14]
    elif view == "Slow Movers":
        filtered = filtered[(available > 0) & ((sold <= 2) | (age >= 60) | (doh >= 60))]
    elif view == "Expiring 90 Days":
        filtered = filtered[(expiry >= 0) & (expiry <= 90)]
    elif view == "Bulk Packages":
        filtered = filtered[
            unit_text.isin({"g", "gram", "grams", "kg", "oz", "ounce", "ounces", "lb", "pound", "pounds"})
            | category_text.str.contains("bulk|flower|material", regex=True, na=False)
        ]
    elif view == "Quarantine / Hold":
        filtered = filtered[status_text.str.contains("quarantine|hold|failed", regex=True, na=False)]
    return filtered.reset_index(drop=True)


def _option_values(frame: pd.DataFrame, column: str) -> list[str]:
    if frame.empty or column not in frame.columns:
        return ["All"]
    values = sorted({str(value).strip() for value in frame[column].dropna().tolist() if str(value).strip()})
    return ["All", *values]


def _selected_rows(event: Any) -> list[int]:
    try:
        return [int(value) for value in event.selection.rows]
    except Exception:
        pass
    try:
        return [int(value) for value in event.get("selection", {}).get("rows", [])]
    except Exception:
        return []


def _open_product(state: MutableMapping[str, Any], product: str) -> None:
    state["product_360_selected_name"] = str(product)
    state["product_360_open"] = True
    st.rerun()


def _route_audit(state: MutableMapping[str, Any], products: list[str]) -> None:
    state["inventory_audit_product_focus"] = products[0] if products else ""
    state["inventory_audit_scope_products"] = products
    queue_workspace_navigation(
        state,
        group=RETAIL_OPS,
        workspace=BUYER_WORKSPACE,
        buyer_section=INVENTORY_COUNTS_SECTION,
    )
    st.rerun()


def _open_receive_inventory(state: MutableMapping[str, Any]) -> None:
    state["inventory_receive_open"] = True
    st.rerun()


def _package_rows_for_selected(
    state: MutableMapping[str, Any],
    selected: pd.DataFrame,
    *,
    is_production: bool,
    grain: str,
) -> pd.DataFrame:
    if selected is None or selected.empty:
        return pd.DataFrame()
    if is_production or str(grain).casefold() == "packages":
        return selected.copy()
    packages = build_retail_inventory_table(state, grain="Packages")
    if packages.empty:
        return pd.DataFrame()
    product_keys = {_norm(value) for value in selected.get("Product", pd.Series(dtype=str)).tolist() if _norm(value)}
    if not product_keys:
        return pd.DataFrame()
    return packages[packages["Product"].map(_norm).isin(product_keys)].reset_index(drop=True)


def _add_products_to_po(state: MutableMapping[str, Any], products: list[str]) -> int:
    added = 0
    seen: set[str] = set()
    for product in products:
        key = _norm(product)
        if not key or key in seen:
            continue
        seen.add(key)
        snapshot = build_product_360_snapshot(state, product)
        if not str(snapshot.get("product_name") or "").strip():
            continue
        stage_product_for_po(state, snapshot)
        added += 1
    if added:
        queue_workspace_navigation(
            state,
            group=RETAIL_OPS,
            workspace=BUYER_WORKSPACE,
            buyer_section="🧾 PO Builder",
        )
    return added


def _inventory_css() -> None:
    st.markdown(
        """
        <style>
        .inv2-kicker {color:#ff9a3c !important;font-size:.66rem;font-weight:820;letter-spacing:.14em;text-transform:uppercase}
        .inv2-title {margin:.2rem 0 .18rem;color:#f6f5f2 !important;font-size:2rem;font-weight:820;letter-spacing:-.045em}
        .inv2-subtitle {color:#aaa49e !important;font-size:.83rem}
        .inv2-count {color:#aaa49e !important;font-size:.73rem;white-space:nowrap}
        .st-key-inv2_toolbar,.st-key-inv2_filters,.st-key-inv2_selection_bar {
          padding:.58rem .62rem !important;border:1px solid rgba(255,255,255,.08) !important;
          border-radius:12px !important;background:#0f0f0f !important;margin-bottom:.55rem !important;
        }
        .st-key-inv2_toolbar [data-testid="stHorizontalBlock"],.st-key-inv2_filters [data-testid="stHorizontalBlock"] {align-items:end !important;gap:.45rem !important;}
        .inv2-legend {display:flex;gap:.55rem;flex-wrap:wrap;margin:.55rem 0;color:#8e8882 !important;font-size:.7rem}
        .inv2-legend span {padding:.2rem .42rem;border:1px solid rgba(255,255,255,.07);border-radius:999px;background:#0d0d0d}
        @media (max-width:768px) {
          .inv2-title {font-size:1.7rem}
          .st-key-inv2_toolbar [data-testid="column"],.st-key-inv2_filters [data-testid="column"] {min-width:min(100%,135px) !important;flex:1 1 135px !important;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_receive_history(state: MutableMapping[str, Any], operation_mode: str) -> None:
    if not state.get("inventory_receive_history_open"):
        return

    def body() -> None:
        if st.button("Close", key="inv2_history_close"):
            state["inventory_receive_history_open"] = False
            st.rerun()
        st.caption("INVENTORY ACTIVITY")
        st.markdown("## Receive / source history")
        if operation_mode == PRODUCTION_OPERATION:
            try:
                rows = PackageStudioService(create_coman_engine()).recent_runs(
                    str(state.get("active_organization_id") or ""),
                    str(state.get("active_facility_id") or ""),
                    limit=50,
                )
                if rows:
                    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                else:
                    st.info("No recent durable Package Studio activity was found.")
            except Exception as exc:
                st.info("Durable production activity is not available yet.")
                st.caption(str(exc))
        else:
            try:
                from modules.data_hub_repository import DataHubRepository

                history = DataHubRepository(create_coman_engine()).list_history(
                    str(state.get("active_organization_id") or ""),
                    str(state.get("active_facility_id") or ""),
                    limit=100,
                )
                rows = [
                    {
                        "Dataset": item.dataset_label,
                        "File": item.filename,
                        "Rows": item.row_count,
                        "Quality": item.quality,
                        "Imported by": item.imported_by,
                        "Activated": item.activated_at,
                        "Status": item.status,
                    }
                    for item in history
                    if str(item.dataset_key) == "inventory"
                ]
                if rows:
                    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                else:
                    st.info("No durable inventory receive/import history was found for this facility.")
            except Exception as exc:
                st.info("Durable inventory history is not available yet.")
                st.caption(str(exc))

    if hasattr(st, "dialog"):
        @st.dialog("Inventory history", width="large")
        def dialog() -> None:
            body()
        dialog()
    else:
        with st.container(border=True):
            body()


def render_inventory_command_center(
    state: MutableMapping[str, Any], *, operation_mode: str = RETAIL_OPERATION
) -> None:
    """Render the Dutchie-fast / Buyer-Dash-smart Inventory workspace."""

    _inventory_css()
    is_production = operation_mode == PRODUCTION_OPERATION
    grain = "Packages" if is_production else str(state.get("inventory_v2_grain") or "Products")
    if grain not in {"Products", "Packages"}:
        grain = "Products"

    base = build_production_inventory_table(state) if is_production else build_retail_inventory_table(state, grain=grain)

    left, right = st.columns([4.4, 1.6])
    with left:
        st.markdown(
            f'<div class="inv2-kicker">{operation_mode.upper()}</div><div class="inv2-title">Inventory</div>'
            '<div class="inv2-subtitle">Search, decide, receive, transform, and audit without leaving Inventory.</div>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(f'<div class="inv2-count">{len(base):,} loaded row(s)</div>', unsafe_allow_html=True)

    with st.container(key="inv2_toolbar"):
        cols = st.columns([1.2, 1.0, 1.0, 1.0])
        if not is_production:
            grain = cols[0].segmented_control(
                "View", ["Products", "Packages"], default=grain, key="inventory_v2_grain"
            ) or grain
            base = build_retail_inventory_table(state, grain=grain)
        else:
            cols[0].text_input("View", value="Packages", disabled=True, key="inv2_production_grain")
        if cols[1].button("Actions", width="stretch", key="inv2_actions"):
            state["inventory_actions_open"] = not bool(state.get("inventory_actions_open"))
        if cols[2].button("Receive history", width="stretch", key="inv2_receive_history"):
            state["inventory_receive_history_open"] = True
            st.rerun()
        if cols[3].button(
            "Receive inventory",
            type="primary",
            width="stretch",
            key="inv2_receive_inventory",
            disabled=is_production,
            help="Retail inbound receiving uses the Inbound Queue. Production materials use the durable production/package workflows.",
        ):
            _open_receive_inventory(state)

    saved_views = state.setdefault("inventory_saved_views", {})
    saved_names = list(BUILTIN_VIEWS) + [name for name in saved_views if name not in BUILTIN_VIEWS]
    current_view = str(state.get("inventory_saved_view") or "All Inventory")
    if current_view not in saved_names:
        current_view = "All Inventory"

    with st.container(key="inv2_filters"):
        cols = st.columns([2.6, 1.05, 1.05, 1.05, 1.05, 1.15])
        search = cols[0].text_input(
            "Search inventory",
            key="inventory_v2_search",
            placeholder="Product, SKU, package, strain, vendor…",
            label_visibility="collapsed",
        )
        status = cols[1].selectbox("Status", _option_values(base, "Status"), key="inventory_v2_status")
        vendor = cols[2].selectbox("Vendor", _option_values(base, "Vendor"), key="inventory_v2_vendor")
        room = cols[3].selectbox("Room", _option_values(base, "Room"), key="inventory_v2_room")
        category = cols[4].selectbox("Category", _option_values(base, "Category"), key="inventory_v2_category")
        view = cols[5].selectbox(
            "Saved view",
            saved_names,
            index=saved_names.index(current_view),
            key="inventory_saved_view",
        )

    if view in saved_views:
        payload = saved_views.get(view) or {}
        status = str(payload.get("status") or status)
        vendor = str(payload.get("vendor") or vendor)
        room = str(payload.get("room") or room)
        category = str(payload.get("category") or category)

    filtered = apply_inventory_filters(
        base,
        search=search,
        saved_view=view if view in BUILTIN_VIEWS else "All Inventory",
        status=status,
        vendor=vendor,
        room=room,
        category=category,
    )

    if state.get("inventory_actions_open"):
        with st.container(key="inv2_selection_bar"):
            action_cols = st.columns([1.2, 1.2, 1.2, 2.4])
            if action_cols[0].button("Open audits", width="stretch", key="inv2_open_audits"):
                _route_audit(state, [])
            if action_cols[1].button("Package Studio", width="stretch", key="inv2_open_studio"):
                state["package_studio_open"] = True
                st.rerun()
            if action_cols[2].button("Reset filters", width="stretch", key="inv2_reset_filters"):
                for key in (
                    "inventory_v2_search",
                    "inventory_v2_status",
                    "inventory_v2_vendor",
                    "inventory_v2_room",
                    "inventory_v2_category",
                    "inventory_saved_view",
                ):
                    state.pop(key, None)
                st.rerun()
            new_name = action_cols[3].text_input(
                "Save current view",
                key="inventory_v2_save_name",
                placeholder="My low-stock flower",
            )
            if new_name and st.button("Save view", key="inventory_v2_save_view"):
                saved_views[str(new_name).strip()] = {
                    "status": status,
                    "vendor": vendor,
                    "room": room,
                    "category": category,
                }
                state["inventory_saved_view"] = str(new_name).strip()
                st.rerun()

    display_columns = (
        ["SKU", "Product", "External Package ID", "Category", "Room", "Available", "Unit", "Status", "Attention"]
        if is_production
        else (
            ["SKU", "Product", "Strain", "Vendor", "Room", "Available", "Reserved", "30d Sold", "DOH", "Cost", "Retail", "Margin", "Age", "Attention"]
            if grain == "Products"
            else ["SKU", "Product", "External Package ID", "Strain", "Vendor", "Room", "Available", "Unit", "Reserved", "30d Sold", "DOH", "Category", "Status", "Attention"]
        )
    )
    display_columns = [column for column in display_columns if column in filtered.columns]
    display = filtered[display_columns].copy()
    for column in ("30d Sold", "DOH", "Cost", "Retail", "Margin"):
        if column in display.columns:
            display[column] = pd.to_numeric(display[column], errors="coerce").round(
                1 if column in {"30d Sold", "DOH", "Margin"} else 2
            )

    st.markdown(
        '<div class="inv2-legend"><span>Reorder now</span><span>Aging</span><span>Expiring</span><span>Hold</span><span>Production ready</span></div>',
        unsafe_allow_html=True,
    )
    event = st.dataframe(
        display,
        width="stretch",
        height=min(680, max(300, 44 + len(display) * 36)),
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        key=f"inv2_table_{operation_mode}_{grain}",
    )
    positions = _selected_rows(event)
    selected = filtered.iloc[positions].copy() if positions else pd.DataFrame(columns=filtered.columns)

    adjustment_flash = state.pop("inventory_adjustment_flash", "")
    if adjustment_flash:
        st.success(str(adjustment_flash))

    if not selected.empty:
        with st.container(key="inv2_selection_bar"):
            st.caption(f"{len(selected)} selected")
            cols = st.columns([1.0, 1.0, 1.0, 1.15, 1.0, 1.0, 1.15])
            products = [str(value) for value in selected["Product"].dropna().tolist() if str(value).strip()]
            package_rows = _package_rows_for_selected(
                state, selected, is_production=is_production, grain=grain
            )
            if len(selected) == 1 and cols[0].button(
                "Product 360", type="primary", width="stretch", key="inv2_open_product"
            ):
                _open_product(state, products[0])
            if cols[1].button("Audit", width="stretch", key="inv2_audit_selected"):
                _route_audit(state, list(dict.fromkeys(products)))
            if not is_production and cols[2].button("Add to PO", width="stretch", key="inv2_add_po"):
                if _add_products_to_po(state, products):
                    st.rerun()
            durable_ids = [
                str(value)
                for value in selected.get("Durable Lot ID", pd.Series(dtype=str)).dropna().tolist()
                if str(value).strip()
            ]
            studio_disabled = len(selected) != 1 or not durable_ids
            if cols[3].button(
                "Work on package",
                width="stretch",
                key="inv2_work_package",
                disabled=studio_disabled,
            ):
                state["package_studio_prefill_lot_id"] = durable_ids[0]
                state["package_studio_prefill_action"] = "Pack Down"
                state["package_studio_open"] = True
                st.rerun()
            external_ids = (
                package_rows.get("External Package ID", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
                if not package_rows.empty
                else pd.Series(dtype=str)
            )
            print_disabled = package_rows.empty or not external_ids.ne("").any()
            if cols[4].button(
                "Print labels", width="stretch", key="inv2_print_labels", disabled=print_disabled
            ):
                from modules.inventory_labels import open_inventory_label_dialog

                if open_inventory_label_dialog(state, package_rows):
                    st.rerun()
            try:
                from modules.inventory_adjustments import can_adjust_inventory

                adjust_allowed = can_adjust_inventory(state)
            except Exception:
                adjust_allowed = False
            if cols[5].button(
                "Adjust",
                width="stretch",
                key="inv2_adjust_inventory",
                disabled=print_disabled or not adjust_allowed,
            ):
                from modules.inventory_adjustments import open_inventory_adjustment_dialog

                if open_inventory_adjustment_dialog(state, package_rows, operation_mode=operation_mode):
                    st.rerun()
            cols[6].download_button(
                "Export selected",
                data=selected[display_columns].to_csv(index=False).encode("utf-8"),
                file_name="buyer_dash_inventory_selected.csv",
                mime="text/csv",
                width="stretch",
            )

    if filtered.empty:
        st.info("No inventory matches the current view and filters.")
    else:
        total_available = pd.to_numeric(filtered["Available"], errors="coerce").fillna(0).sum()
        at_risk = (
            int(filtered["Attention"].isin({"Reorder now", "Out of stock", "Hold", "Expiring", "Aging"}).sum())
            if "Attention" in filtered.columns
            else 0
        )
        st.caption(
            f"Displaying {len(filtered):,} row(s) · {total_available:,.1f} available · {at_risk:,} need attention"
        )

    _render_receive_history(state, operation_mode)
    if bool(state.get("inventory_receive_open", False)):
        from modules.inventory_receiving import render_receive_inventory_dialog

        render_receive_inventory_dialog(state)
    if bool(state.get("package_studio_open", False)):
        from modules.package_studio.ui import render_package_studio_dialog

        render_package_studio_dialog(state)
    if bool(state.get("inventory_label_open", False)):
        from modules.inventory_labels import render_inventory_label_dialog

        render_inventory_label_dialog(state)
    if bool(state.get("inventory_adjustment_open", False)):
        from modules.inventory_adjustments import render_inventory_adjustment_dialog

        render_inventory_adjustment_dialog(state)
