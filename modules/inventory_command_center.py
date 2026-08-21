"""Table-first Inventory v2 command center.

Retail and Production share one interaction model, but not one inventory model.
Retail remains product/SKU/sales driven. Production is facility-scoped durable
cannabis material inventory for manufacturing and cultivation licenses.
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

RETAIL_BUILTIN_VIEWS = (
    "All Inventory",
    "Low Stock",
    "Under 14 DOH",
    "Slow Movers",
    "Expiring 90 Days",
    "Bulk Packages",
    "Quarantine / Hold",
)

PRODUCTION_BUILTIN_VIEWS = (
    "All Material",
    "Bulk Flower",
    "Biomass / Trim",
    "Extraction Input",
    "WIP",
    "Finished Bulk",
    "Production Ready",
    "Low Balance",
    "Quarantine / Hold",
)

BUILTIN_VIEWS = RETAIL_BUILTIN_VIEWS


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
    local = pd.DataFrame({
        "_product_key": sales[product_col].fillna("").astype(str).map(_norm),
        "_sold": _numeric(sales[qty_col]),
    })
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
    expiry = pd.to_numeric(frame.get("Days to Expiry", pd.Series(math.inf, index=frame.index)), errors="coerce")
    attention[status.str.contains("quarantine|hold|failed", regex=True, na=False)] = "Hold"
    attention[(available <= 0) & ~status.str.contains("quarantine|hold|failed", regex=True, na=False)] = "Out of stock"
    attention[(reserved > available) & (available > 0)] = "Over-reserved"
    attention[(doh <= 7) & (available > 0)] = "Reorder now"
    attention[(expiry <= 90) & (expiry >= 0) & (available > 0)] = "Expiring"
    attention[(age >= 60) & (sold <= 2) & (available > 0)] = "Aging"
    return attention


def build_retail_inventory_table(state: MutableMapping[str, Any], *, grain: str = "Products") -> pd.DataFrame:
    source = _first_frame(state, "active_inventory_df", "inv_raw_df", "demo_inventory_df", "demo_catalog_df")
    product_col = _column(source, PRODUCT_ALIASES)
    if source.empty or not product_col:
        return pd.DataFrame()
    received_col = _column(source, RECEIVED_ALIASES)
    expiry_col = _column(source, EXPIRATION_ALIASES)
    now = pd.Timestamp.now().normalize()
    received = pd.to_datetime(source[received_col], errors="coerce") if received_col else pd.Series(pd.NaT, index=source.index)
    expiry = pd.to_datetime(source[expiry_col], errors="coerce") if expiry_col else pd.Series(pd.NaT, index=source.index)
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
    normalized = normalized.merge(_sales_summary(state), on="_product_key", how="left")
    normalized["30d Sold"] = pd.to_numeric(normalized["30d Sold"], errors="coerce").fillna(0.0)
    normalized["Daily Velocity"] = pd.to_numeric(normalized["Daily Velocity"], errors="coerce").fillna(0.0)
    if str(grain).casefold() == "products":
        normalized = normalized.groupby(["Product", "_product_key"], as_index=False).agg({
            "SKU": "first", "Strain": "first", "Vendor": "first", "Room": "first", "Category": "first",
            "Status": "first", "Tags": "first", "Available": "sum", "Reserved": "sum", "Cost": "median",
            "Retail": "median", "Age": "max", "Days to Expiry": "min", "30d Sold": "first",
            "Daily Velocity": "first", "Unit": "first",
        })
        normalized["Package ID"] = ""
        normalized["External Package ID"] = ""
        normalized["Durable Lot ID"] = ""
    velocity = pd.to_numeric(normalized["Daily Velocity"], errors="coerce").fillna(0.0)
    available = pd.to_numeric(normalized["Available"], errors="coerce").fillna(0.0)
    normalized["DOH"] = (available / velocity.replace(0, pd.NA)).astype("Float64")
    normalized["Margin"] = ((normalized["Retail"] - normalized["Cost"]) / normalized["Retail"].replace(0, pd.NA) * 100).astype("Float64")
    normalized["Attention"] = _derive_attention(normalized)
    return normalized.reset_index(drop=True)


def build_production_inventory_table(state: MutableMapping[str, Any]) -> pd.DataFrame:
    """Read durable cannabis-material packages only from the active facility/license."""
    import logging
    logger = logging.getLogger(__name__)

    organization_id = str(state.get("active_organization_id") or "")
    facility_id = str(state.get("active_facility_id") or "")
    if not organization_id or not facility_id:
        return pd.DataFrame()
    try:
        service = PackageStudioService(create_coman_engine())
        lots = service.list_available_lots(organization_id, facility_id)
        products = {item.product_id: item for item in service.list_products(organization_id)}
    except (ComanDatabaseConfigurationError, Exception) as e:
        logger.exception("Failed to load production inventory: %s", str(e))
        state["_inventory_load_error"] = f"Failed to load inventory: {type(e).__name__}"
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for lot in lots:
        product = products.get(lot.product_id)
        item_type = str(getattr(product, "item_type", "") or "")
        rows.append({
            "SKU": lot.sku,
            "Product": lot.product_name,
            "Material Type": item_type.replace("_", " ").title() or "Cannabis Material",
            "Category": item_type.replace("_", " ").title() or "Cannabis Material",
            "Package ID": lot.compliance_package_id or lot.lot_code,
            "External Package ID": lot.compliance_package_id or lot.lot_code,
            "Lot": lot.lot_code,
            "Source / Supplier": "",
            "Vendor": "",
            "Room": lot.location_code,
            "Status": "Available",
            "Available": lot.balance,
            "Unit": lot.unit,
            "Attention": "Production ready",
            "Durable Lot ID": lot.lot_id,
            "_product_key": _norm(lot.product_name),
        })
    return pd.DataFrame(rows)


def apply_inventory_filters(
    frame: pd.DataFrame,
    *, search: str = "", saved_view: str = "All Inventory", status: str = "All",
    vendor: str = "All", room: str = "All", category: str = "All",
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=list(frame.columns) if isinstance(frame, pd.DataFrame) else None)
    filtered = frame.copy()
    needle = _norm(search)
    if needle:
        searchable = [column for column in (
            "SKU", "Product", "Strain", "External Package ID", "Package ID", "Vendor",
            "Source / Supplier", "Room", "Category", "Material Type", "Tags"
        ) if column in filtered.columns]
        haystack = filtered[searchable].fillna("").astype(str).agg(" ".join, axis=1).map(_norm)
        filtered = filtered[haystack.str.contains(re.escape(needle), regex=True, na=False)]
    source_column = "Source / Supplier" if "Source / Supplier" in filtered.columns else "Vendor"
    category_column = "Material Type" if "Material Type" in filtered.columns else "Category"
    for column, value in (("Status", status), (source_column, vendor), ("Room", room), (category_column, category)):
        if value != "All" and column in filtered.columns:
            filtered = filtered[filtered[column].fillna("").astype(str) == value]

    view = str(saved_view or "All Inventory")
    status_text = filtered.get("Status", pd.Series("", index=filtered.index)).fillna("").astype(str).str.casefold()
    category_text = filtered.get(category_column, pd.Series("", index=filtered.index)).fillna("").astype(str).str.casefold()
    unit_text = filtered.get("Unit", pd.Series("", index=filtered.index)).fillna("").astype(str).str.casefold()
    available = pd.to_numeric(filtered.get("Available"), errors="coerce").fillna(0.0)

    if view in PRODUCTION_BUILTIN_VIEWS:
        if view == "Bulk Flower":
            filtered = filtered[category_text.str.contains("flower", regex=True, na=False)]
        elif view == "Biomass / Trim":
            filtered = filtered[category_text.str.contains("biomass|trim", regex=True, na=False)]
        elif view == "Extraction Input":
            filtered = filtered[category_text.str.contains("flower|trim|biomass|fresh frozen|material", regex=True, na=False)]
        elif view == "WIP":
            filtered = filtered[category_text.str.contains("wip|work in process|crude|oil|distillate|concentrate", regex=True, na=False)]
        elif view == "Finished Bulk":
            filtered = filtered[category_text.str.contains("finished|distillate|rosin|resin|concentrate", regex=True, na=False)]
        elif view == "Production Ready":
            filtered = filtered[status_text.str.contains("available|released", regex=True, na=False)]
        elif view == "Low Balance":
            filtered = filtered[(available > 0) & (available <= 10)]
        elif view == "Quarantine / Hold":
            filtered = filtered[status_text.str.contains("quarantine|hold|failed", regex=True, na=False)]
        return filtered.reset_index(drop=True)

    doh = pd.to_numeric(filtered.get("DOH"), errors="coerce")
    sold = pd.to_numeric(filtered.get("30d Sold"), errors="coerce").fillna(0.0)
    age = pd.to_numeric(filtered.get("Age"), errors="coerce").fillna(0.0)
    expiry = pd.to_numeric(filtered.get("Days to Expiry"), errors="coerce")
    if view == "Low Stock":
        filtered = filtered[(doh <= 7) | (available <= 0)]
    elif view == "Under 14 DOH":
        filtered = filtered[doh <= 14]
    elif view == "Slow Movers":
        filtered = filtered[(available > 0) & ((sold <= 2) | (age >= 60) | (doh >= 60))]
    elif view == "Expiring 90 Days":
        filtered = filtered[(expiry >= 0) & (expiry <= 90)]
    elif view == "Bulk Packages":
        filtered = filtered[unit_text.isin({"g", "gram", "grams", "kg", "oz", "ounce", "ounces", "lb", "pound", "pounds"}) | category_text.str.contains("bulk|flower|material", regex=True, na=False)]
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


def _route_audit(state: MutableMapping[str, Any], products: list[str]) -> None:
    state["inventory_audit_product_focus"] = products[0] if products else ""
    state["inventory_audit_scope_products"] = products
    queue_workspace_navigation(state, group=RETAIL_OPS, workspace=BUYER_WORKSPACE, buyer_section=INVENTORY_COUNTS_SECTION)
    st.rerun()


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
        queue_workspace_navigation(state, group=RETAIL_OPS, workspace=BUYER_WORKSPACE, buyer_section="🧾 PO Builder")
    return added


def _inventory_css() -> None:
    st.markdown("""
    <style>
    .inv2-kicker {color:#ff9a3c !important;font-size:.66rem;font-weight:820;letter-spacing:.14em;text-transform:uppercase}
    .inv2-title {margin:.2rem 0 .18rem;color:#f6f5f2 !important;font-size:2rem;font-weight:820;letter-spacing:-.045em}
    .inv2-subtitle {color:#aaa49e !important;font-size:.83rem}
    .inv2-count {color:#aaa49e !important;font-size:.73rem;white-space:nowrap}
    .st-key-inv2_toolbar,.st-key-inv2_filters,.st-key-inv2_selection_bar {padding:.58rem .62rem !important;border:1px solid rgba(255,255,255,.08) !important;border-radius:12px !important;background:#0f0f0f !important;margin-bottom:.55rem !important;}
    .inv2-legend {display:flex;gap:.55rem;flex-wrap:wrap;margin:.55rem 0;color:#8e8882 !important;font-size:.7rem}
    .inv2-legend span {padding:.2rem .42rem;border:1px solid rgba(255,255,255,.07);border-radius:999px;background:#0d0d0d}
    </style>
    """, unsafe_allow_html=True)


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
                    str(state.get("active_facility_id") or ""), limit=50,
                )
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True) if rows else st.info("No recent durable production activity was found.")
            except Exception as exc:
                st.info("Durable production activity is not available yet.")
                st.caption(str(exc))
        else:
            try:
                from modules.data_hub_repository import DataHubRepository
                history = DataHubRepository(create_coman_engine()).list_history(
                    str(state.get("active_organization_id") or ""), str(state.get("active_facility_id") or ""), limit=100,
                )
                rows = [{"Dataset": i.dataset_label, "File": i.filename, "Rows": i.row_count, "Quality": i.quality, "Imported by": i.imported_by, "Activated": i.activated_at, "Status": i.status} for i in history if str(i.dataset_key) == "inventory"]
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True) if rows else st.info("No durable inventory receive/import history was found for this facility.")
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


def _is_cultivation_facility(state: MutableMapping[str, Any]) -> bool:
    text = " ".join(str(state.get(key) or "") for key in (
        "active_license_type", "active_facility_type", "license_type", "facility_type", "active_facility_name"
    )).casefold()
    return any(token in text for token in ("cultivation", "cultivator", "grow"))


def render_inventory_command_center(state: MutableMapping[str, Any], *, operation_mode: str = RETAIL_OPERATION) -> None:
    _inventory_css()
    if error := state.get("_inventory_load_error"):
        st.error(f"⚠️ {error}. Try refreshing the page or contact support if this persists.")
        state.pop("_inventory_load_error", None)
        return
    is_production = operation_mode == PRODUCTION_OPERATION
    cultivation = is_production and _is_cultivation_facility(state)
    if is_production:
        grain_options = ["Packages", "Plants"] if cultivation else ["Packages"]
        grain = str(state.get("production_inventory_grain") or "Packages")
        if grain not in grain_options:
            grain = "Packages"
    else:
        grain_options = ["Products", "Packages"]
        grain = str(state.get("inventory_v2_grain") or "Products")
        if grain not in grain_options:
            grain = "Products"

    base = build_production_inventory_table(state) if is_production and grain == "Packages" else (
        pd.DataFrame() if is_production else build_retail_inventory_table(state, grain=grain)
    )

    left, right = st.columns([4.4, 1.6])
    with left:
        subtitle = "Bulk cannabis materials, lots, rooms, receiving, transformations, and audits." if is_production else "Search, decide, receive, transform, and audit without leaving Inventory."
        st.markdown(f'<div class="inv2-kicker">{operation_mode.upper()}</div><div class="inv2-title">Inventory</div><div class="inv2-subtitle">{subtitle}</div>', unsafe_allow_html=True)
    with right:
        st.markdown(f'<div class="inv2-count">{len(base):,} loaded row(s)</div>', unsafe_allow_html=True)

    with st.container(key="inv2_toolbar"):
        cols = st.columns([1.2, 1.0, 1.0, 1.0])
        if len(grain_options) > 1:
            key = "production_inventory_grain" if is_production else "inventory_v2_grain"
            grain = cols[0].segmented_control("View", grain_options, default=grain, key=key) or grain
            base = build_production_inventory_table(state) if is_production and grain == "Packages" else (pd.DataFrame() if is_production else build_retail_inventory_table(state, grain=grain))
        else:
            cols[0].text_input("View", value=grain_options[0], disabled=True, key="inv2_fixed_grain")
        if cols[1].button("Actions", width="stretch", key="inv2_actions"):
            state["inventory_actions_open"] = not bool(state.get("inventory_actions_open"))
        if cols[2].button("Receive history", width="stretch", key="inv2_receive_history"):
            state["inventory_receive_history_open"] = not bool(state.get("inventory_receive_history_open"))
        if cols[3].button("Receive inventory", type="primary", width="stretch", key="inv2_receive_inventory"):
            state["inventory_receive_open"] = True
            st.rerun()

    if is_production and grain == "Plants":
        st.info("Cultivation plant inventory is a separate grain from packages. The Plants surface is ready for a plant-tag ledger; packages remain fully operational below when you switch back to Packages.")
        return

    builtins = PRODUCTION_BUILTIN_VIEWS if is_production else RETAIL_BUILTIN_VIEWS
    saved_views = state.setdefault("inventory_saved_views", {})
    saved_names = list(builtins) + [name for name in saved_views if name not in builtins]
    default_view = "All Material" if is_production else "All Inventory"
    current_view = str(state.get("inventory_saved_view") or default_view)
    if current_view not in saved_names:
        current_view = default_view

    with st.container(key="inv2_filters"):
        cols = st.columns([2, 0.9, 0.9, 1])
        search = cols[0].text_input("Search", key="inventory_v2_search", placeholder=("Material, package, lot, room…" if is_production else "Product, SKU, package, strain, vendor…"), label_visibility="collapsed")
        status = cols[1].selectbox("Status", _option_values(base, "Status"), key="inventory_v2_status", label_visibility="collapsed")
        source_col = "Source / Supplier" if is_production else "Vendor"
        material_col = "Material Type" if is_production else "Category"
        vendor = cols[2].selectbox("Vendor" if not is_production else "Source", _option_values(base, source_col), key="inventory_v2_vendor", label_visibility="collapsed")
        view = cols[3].selectbox("View", saved_names, index=saved_names.index(current_view), key="inventory_saved_view", label_visibility="collapsed")

        cols2 = st.columns([0.9, 0.9, 1.2])
        room = cols2[0].selectbox("Room", _option_values(base, "Room"), key="inventory_v2_room", label_visibility="collapsed")
        category = cols2[1].selectbox("Type", _option_values(base, material_col), key="inventory_v2_category", label_visibility="collapsed")
        if cols2[2].button("Clear filters", width="stretch", key="inv2_clear_filters_quick"):
            for key in ("inventory_v2_search", "inventory_v2_status", "inventory_v2_vendor", "inventory_v2_room", "inventory_v2_category", "inventory_saved_view"):
                state.pop(key, None)
            st.rerun()

    filtered = apply_inventory_filters(base, search=search, saved_view=view if view in builtins else default_view, status=status, vendor=vendor, room=room, category=category)

    if state.get("inventory_actions_open"):
        with st.container(key="inv2_selection_bar"):
            action_cols = st.columns([1.2, 1.2, 1.2, 2.4])
            if action_cols[0].button("Open audits", width="stretch", key="inv2_open_audits"):
                _route_audit(state, [])
            if action_cols[1].button("Package Studio", width="stretch", key="inv2_open_studio"):
                state["package_studio_open"] = True
                st.rerun()
            if action_cols[2].button("Reset filters", width="stretch", key="inv2_reset_filters"):
                for key in ("inventory_v2_search", "inventory_v2_status", "inventory_v2_vendor", "inventory_v2_room", "inventory_v2_category", "inventory_saved_view"):
                    state.pop(key, None)
            with action_cols[3]:
                if st.button("💾 Save current view", key="inv2_open_save_dialog", width="stretch", use_container_width=True):
                    state["inventory_save_view_open"] = True
            if state.get("inventory_save_view_open"):
                with st.container(border=True):
                    st.markdown("**Save this view for quick access**")
                    view_name = st.text_input("View name", placeholder="My production-ready flower" if is_production else "My low-stock flower", key="inventory_v2_save_name_modal")
                    save_cols = st.columns([1, 1])
                    if save_cols[0].button("Save", key="inv2_save_view_confirm", type="primary"):
                        if view_name and view_name.strip():
                            saved_views[view_name.strip()] = {"status": status, "vendor": vendor, "room": room, "category": category}
                            state["inventory_saved_view"] = view_name.strip()
                            state["inventory_save_view_open"] = False
                            st.success(f"✓ Saved view '{view_name.strip()}'")
                        else:
                            st.warning("Enter a name for this view")
                    if save_cols[1].button("Cancel", key="inv2_save_view_cancel"):
                        state["inventory_save_view_open"] = False

    default_columns = ["SKU", "Product", "External Package ID", "Material Type", "Room", "Available", "Unit", "Status", "Attention"] if is_production else (
        ["SKU", "Product", "Strain", "Vendor", "Room", "Available", "Reserved", "30d Sold", "DOH", "Cost", "Retail", "Margin", "Age", "Attention"] if grain == "Products" else
        ["SKU", "Product", "External Package ID", "Strain", "Vendor", "Room", "Available", "Unit", "Reserved", "30d Sold", "DOH", "Category", "Status", "Attention"]
    )
    saved_columns = state.get("inventory_display_columns", {}).get(operation_mode, default_columns)
    available_columns = [col for col in filtered.columns if col not in {"_product_key", "Durable Lot ID"}]
    with st.expander("📊 Columns", expanded=False):
        cols = st.columns(3)
        if cols[0].button("Show all", width="stretch", key="inv2_show_all_cols"):
            state["inventory_display_columns"] = state.get("inventory_display_columns", {})
            state["inventory_display_columns"][operation_mode] = available_columns
        if cols[1].button("Show defaults", width="stretch", key="inv2_show_default_cols"):
            state["inventory_display_columns"] = state.get("inventory_display_columns", {})
            state["inventory_display_columns"][operation_mode] = default_columns
        if cols[2].button("Compact (essentials only)", width="stretch", key="inv2_show_compact_cols"):
            compact = ["SKU", "Product", "Available", "Room"] if is_production else ["SKU", "Product", "Available", "Vendor"]
            state["inventory_display_columns"] = state.get("inventory_display_columns", {})
            state["inventory_display_columns"][operation_mode] = [c for c in compact if c in filtered.columns]
    display_columns = [column for column in saved_columns if column in filtered.columns]
    display = filtered[display_columns].copy()
    for column in ("30d Sold", "DOH", "Cost", "Retail", "Margin"):
        if column in display.columns:
            display[column] = pd.to_numeric(display[column], errors="coerce").round(1 if column in {"30d Sold", "DOH", "Margin"} else 2)

    legend = '<div class="inv2-legend"><span>Production ready</span><span>Low balance</span><span>Hold</span></div>' if is_production else '<div class="inv2-legend"><span>Reorder now</span><span>Aging</span><span>Expiring</span><span>Hold</span></div>'
    st.markdown(legend, unsafe_allow_html=True)
    event = st.dataframe(display, width="stretch", height=min(680, max(300, 44 + len(display) * 36)), hide_index=True, on_select="rerun", selection_mode="multi-row", key=f"inv2_table_{operation_mode}_{grain}")
    positions = _selected_rows(event)
    selected = filtered.iloc[positions].copy() if positions else pd.DataFrame(columns=filtered.columns)

    flash = state.pop("inventory_adjustment_flash", "")
    if flash:
        st.success(str(flash))

    if not selected.empty:
        with st.container(key="inv2_selection_bar"):
            st.caption(f"{len(selected)} selected")
            cols = st.columns([1.0, 1.0, 1.0, 1.15, 1.0, 1.0, 1.15])
            products = [str(value) for value in selected["Product"].dropna().tolist() if str(value).strip()]
            if len(selected) == 1 and not is_production and cols[0].button("Product 360", type="primary", width="stretch", key="inv2_open_product"):
                state["product_360_selected_name"] = products[0]
                state["product_360_open"] = True
                st.rerun()
            if cols[1].button("Audit", width="stretch", key="inv2_audit_selected"):
                _route_audit(state, list(dict.fromkeys(products)))
            if not is_production and cols[2].button("Add to PO", width="stretch", key="inv2_add_po"):
                if _add_products_to_po(state, products):
                    st.rerun()
            durable_ids = [str(value) for value in selected.get("Durable Lot ID", pd.Series(dtype=str)).dropna().tolist() if str(value).strip()]
            if cols[3].button("Work on package", width="stretch", key="inv2_work_package", disabled=len(selected) != 1 or not durable_ids):
                state["package_studio_prefill_lot_id"] = durable_ids[0]
                state["package_studio_prefill_action"] = "Pack Down"
                state["package_studio_open"] = True
                st.rerun()
            external_ids = selected.get("External Package ID", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
            print_disabled = selected.empty or not external_ids.ne("").any()
            if cols[4].button("Print labels", width="stretch", key="inv2_print_labels", disabled=print_disabled):
                from modules.inventory_labels import open_inventory_label_dialog
                if open_inventory_label_dialog(state, selected):
                    st.rerun()
            try:
                from modules.inventory_adjustments import can_adjust_inventory
                adjust_allowed = can_adjust_inventory(state)
            except Exception:
                adjust_allowed = False
            if cols[5].button("Adjust", width="stretch", key="inv2_adjust_inventory", disabled=print_disabled or not adjust_allowed):
                from modules.inventory_adjustments import open_inventory_adjustment_dialog
                if open_inventory_adjustment_dialog(state, selected, operation_mode=operation_mode):
                    st.rerun()
            cols[6].download_button("Export selected", data=selected[display_columns].to_csv(index=False).encode("utf-8"), file_name="buyer_dash_inventory_selected.csv", mime="text/csv", width="stretch")

    if filtered.empty:
        st.info("No inventory matches the current view and filters.")
    else:
        total_available = pd.to_numeric(filtered["Available"], errors="coerce").fillna(0).sum()
        st.caption(f"Displaying {len(filtered):,} row(s) · {total_available:,.1f} available")

    _render_receive_history(state, operation_mode)
    if bool(state.get("inventory_receive_open", False)):
        if is_production:
            from modules.production_inventory_receiving import render_production_receive_inventory_dialog
            render_production_receive_inventory_dialog(state, create_coman_engine())
        else:
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
