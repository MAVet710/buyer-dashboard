import streamlit as st
import pandas as pd
import numpy as np
import re
import json
import os
import sys
import hashlib
import requests
from collections.abc import Mapping
from typing import Any
from datetime import datetime, timedelta
from io import BytesIO
from dotenv import load_dotenv

from compliance_engine import ComplianceRepository, ComplianceSource, format_compliance_answer
from extraction_partner_upload_upgrade import render_extraction_partner_upload_ui
from services.license_client import validate_license_key
from services.doobie_client import DoobieClient
from services.doobie_config import (
    clear_session_doobie_config,
    get_default_doobie_config,
    mask_api_key,
    resolve_doobie_config,
    test_doobie_connection,
)
from services.metrc_client import get_default_metrc_integrator_key, test_metrc_connection
from services.license_session import (
    build_cached_license_session,
    clear_local_license_session,
    get_license_features,
    is_license_recheck_needed,
    license_in_grace_period,
    load_local_license_session,
    save_local_license_session,
)
from ui_polish import (
    load_polished_theme,
    render_section_header,
    render_metric_tiles,
    chart_card_start,
    chart_card_end,
    render_hero,
    render_ai_brief,
    render_sidebar_nav_css,
    render_action_button,
    render_extraction_kpi,
    render_inventory_table_css,
)
from ui_premium import load_premium_shell, render_commandbar, render_sidebar_identity
from user_integrations_store import UserIntegrationsStore
from global_integrations_store import GlobalIntegrationsStore
from services.app_user_store import AppUserStore
from services.auth_identity import resolve_legacy_identity
from services.auth_workflow import (
    apply_authenticated_session,
    authenticate_any_role,
    clear_authenticated_session,
)
from services.workspace_navigation import (
    COMAN_WORKSPACE,
    DATA_HUB_WORKSPACE,
    DATA_OPERATIONS,
    EXTRACTION_WORKSPACE,
    PRODUCTION_OPS,
    RETAIL_OPS,
    WHITE_LABEL_WORKSPACE,
    buyer_section_options,
    workspace_options as build_workspace_options,
)
from modules.coman.ui import render_coman_workspace
from modules.data_hub import render_data_hub_workspace
from modules.extraction_quick_entry import (
    build_quick_run_record,
    quick_stage_weight_updates,
    stage_completion_flags,
)
from modules.nomenclature_ui import render_nomenclature_mapper

load_dotenv()

USER_INTEGRATIONS_STORE = UserIntegrationsStore()
GLOBAL_INTEGRATIONS_STORE = GlobalIntegrationsStore()
APP_USER_STORE = AppUserStore()

# Owner mark (non-functional, intentional signature fragment).
# __  ______             __ ____________

# For PDF generation
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

import matplotlib.pyplot as plt

# ------------------------------------------------------------
# OPTIONAL / SAFE IMPORT FOR PLOTLY
# ------------------------------------------------------------
try:
    import plotly.express as px  # noqa: F401
    import plotly.graph_objects as go  # noqa: F401
    PLOTLY_AVAILABLE = True
except Exception:
    PLOTLY_AVAILABLE = False

# ------------------------------------------------------------
# DOOBIE AI STATUS (single AI backend)
# ------------------------------------------------------------
DOOBIE_PROVIDER_NAME = "DoobieLogic"
# Credential terminology:
# DOOBIE_SERVICE_API_KEY = admin-managed service key for app->Doobie runtime calls.
# DOOBIE_LICENSE_KEY = user/customer entitlement key.
# DOOBIE_ADMIN_API_KEY = Doobie internal admin tooling key (not used in Buyer Dashboard user flow).
# METRC_API_KEY = admin-managed METRC integration key.

# ------------------------------------------------------------
# OPTIONAL / SAFE IMPORT FOR BCRYPT (PASSWORD HASHING)
# ------------------------------------------------------------
try:
    import bcrypt as _bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    _bcrypt = None  # type: ignore
    BCRYPT_AVAILABLE = False

# ------------------------------------------------------------
# OPTIONAL / SAFE IMPORT FOR DUTCHIE LIVE CLIENT
# ------------------------------------------------------------
try:
    from dutchie_client import DutchieConfig, fetch_dutchie_data
    _DUTCHIE_CLIENT_AVAILABLE = True
except (ImportError, AttributeError):
    _DUTCHIE_CLIENT_AVAILABLE = False

# ------------------------------------------------------------
# EXTRACTION PARTNER INTEL MODULES
# ------------------------------------------------------------
try:
    from extraction_partner_import import (
        load_partner_file,
        map_partner_runs_to_ecc_shape,
        looks_like_partner_extraction_file,
    )
    from extraction_partner_intel import build_extraction_weekly_summary
    _EXTRACTION_PARTNER_INTEL_AVAILABLE = True
except (ImportError, AttributeError):
    _EXTRACTION_PARTNER_INTEL_AVAILABLE = False

if not _EXTRACTION_PARTNER_INTEL_AVAILABLE:
    def _partner_norm_col(name: str) -> str:
        return (
            str(name)
            .strip()
            .lower()
            .replace("/", " ")
            .replace("-", " ")
            .replace(".", " ")
            .replace("(", " ")
            .replace(")", " ")
        )


    def load_partner_file(uploaded_file) -> pd.DataFrame:
        raw = uploaded_file.getvalue()
        file_name = str(getattr(uploaded_file, "name", "")).lower()
        if file_name.endswith((".xlsx", ".xls")):
            return pd.read_excel(BytesIO(raw))
        return pd.read_csv(BytesIO(raw))


    def looks_like_partner_extraction_file(uploaded_file) -> bool:
        try:
            df = load_partner_file(uploaded_file)
        except Exception:
            return False
        cols = {_partner_norm_col(c) for c in df.columns}
        required = {
            "run_date",
            "run date",
            "input_weight_g",
            "input weight g",
            "finished_output_g",
            "finished output g",
        }
        return len(cols.intersection(required)) >= 3


    def _partner_pick(df: pd.DataFrame, aliases: list[str], default=None):
        col_map = {_partner_norm_col(c): c for c in df.columns}
        for alias in aliases:
            norm_alias = _partner_norm_col(alias)
            if norm_alias in col_map:
                return df[col_map[norm_alias]]
        return default


    def map_partner_runs_to_ecc_shape(df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame()
        out["run_date"] = pd.to_datetime(_partner_pick(df, ["run_date", "run date", "date"]), errors="coerce").dt.date.astype(str)
        out["state"] = _partner_pick(df, ["state"], default="Other")
        out["license_name"] = _partner_pick(df, ["license_name", "facility", "facility_name"], default="")
        out["client_name"] = _partner_pick(df, ["client_name", "client", "partner"], default="In House")
        out["batch_id_internal"] = _partner_pick(df, ["batch_id_internal", "batch_id", "batch", "run_id"], default="")
        out["metrc_package_id_input"] = _partner_pick(df, ["metrc_package_id_input", "input_package_id"], default="")
        out["metrc_package_id_output"] = _partner_pick(df, ["metrc_package_id_output", "output_package_id"], default="")
        out["metrc_manifest_or_transfer_id"] = _partner_pick(df, ["metrc_manifest_or_transfer_id", "transfer_id"], default="")
        out["method"] = _partner_pick(df, ["method", "extraction_method"], default="BHO")
        out["product_type"] = _partner_pick(df, ["product_type", "output_type"], default="Other")
        out["downstream_product"] = _partner_pick(df, ["downstream_product", "downstream"], default="N/A")
        out["process_stage"] = _partner_pick(df, ["process_stage", "stage"], default="Intake")
        out["input_material_type"] = _partner_pick(df, ["input_material_type", "input_type"], default="Other")
        out["input_weight_g"] = pd.to_numeric(_partner_pick(df, ["input_weight_g", "input_weight", "input_g"], default=0), errors="coerce").fillna(0)
        out["intermediate_output_g"] = pd.to_numeric(_partner_pick(df, ["intermediate_output_g", "intermediate_g"], default=0), errors="coerce").fillna(0)
        out["finished_output_g"] = pd.to_numeric(_partner_pick(df, ["finished_output_g", "finished_output", "output_g"], default=0), errors="coerce").fillna(0)
        out["residual_loss_g"] = pd.to_numeric(_partner_pick(df, ["residual_loss_g", "residual_g", "waste_g"], default=0), errors="coerce").fillna(0)
        out["yield_pct"] = pd.to_numeric(_partner_pick(df, ["yield_pct", "yield"], default=0), errors="coerce").fillna(0)
        out["post_process_efficiency_pct"] = pd.to_numeric(_partner_pick(df, ["post_process_efficiency_pct", "post_efficiency_pct"], default=0), errors="coerce").fillna(0)
        out["operator"] = _partner_pick(df, ["operator"], default="")
        out["machine_line"] = _partner_pick(df, ["machine_line", "line"], default="")
        out["status"] = _partner_pick(df, ["status"], default="Processing")
        out["toll_processing"] = pd.Series(_partner_pick(df, ["toll_processing", "is_toll"], default=False)).astype(bool)
        out["processing_fee_usd"] = pd.to_numeric(_partner_pick(df, ["processing_fee_usd", "processing_fee"], default=0), errors="coerce").fillna(0)
        out["est_revenue_usd"] = pd.to_numeric(_partner_pick(df, ["est_revenue_usd", "estimated_revenue_usd", "revenue_usd"], default=0), errors="coerce").fillna(0)
        out["estimated_revenue_usd"] = out["est_revenue_usd"]
        out["cogs_usd"] = pd.to_numeric(_partner_pick(df, ["cogs_usd", "total_cogs_usd", "cogs"], default=0), errors="coerce").fillna(0)
        out["total_cogs_usd"] = out["cogs_usd"]
        out["raw_material_cogs_usd"] = pd.to_numeric(_partner_pick(df, ["raw_material_cogs_usd"], default=0), errors="coerce").fillna(0)
        out["processing_cogs_usd"] = pd.to_numeric(_partner_pick(df, ["processing_cogs_usd"], default=0), errors="coerce").fillna(0)
        out["packaging_cogs_usd"] = pd.to_numeric(_partner_pick(df, ["packaging_cogs_usd"], default=0), errors="coerce").fillna(0)
        out["labor_cogs_usd"] = pd.to_numeric(_partner_pick(df, ["labor_cogs_usd"], default=0), errors="coerce").fillna(0)
        out["overhead_cogs_usd"] = pd.to_numeric(_partner_pick(df, ["overhead_cogs_usd"], default=0), errors="coerce").fillna(0)
        out["unit_size_g"] = pd.to_numeric(_partner_pick(df, ["unit_size_g"], default=0), errors="coerce").fillna(0)
        out["unit_price_usd"] = pd.to_numeric(_partner_pick(df, ["unit_price_usd"], default=0), errors="coerce").fillna(0)
        out["packaging_yield_loss_g"] = pd.to_numeric(_partner_pick(df, ["packaging_yield_loss_g"], default=0), errors="coerce").fillna(0)
        out["coa_status"] = _partner_pick(df, ["coa_status"], default="Pending")
        out["qa_hold"] = pd.Series(_partner_pick(df, ["qa_hold"], default=False)).astype(bool)
        out["notes"] = _partner_pick(df, ["notes"], default="")
        return out


    def build_extraction_weekly_summary(run_df: pd.DataFrame) -> pd.DataFrame:
        if run_df is None or run_df.empty:
            return pd.DataFrame()
        df = run_df.copy()
        dt = pd.to_datetime(df.get("run_date"), errors="coerce")
        df["week_start"] = (dt.dt.normalize() - pd.to_timedelta(dt.dt.weekday, unit="D")).dt.date.astype(str)
        df["finished_output_g"] = pd.to_numeric(df.get("finished_output_g", 0), errors="coerce").fillna(0)
        df["yield_pct"] = pd.to_numeric(df.get("yield_pct", 0), errors="coerce").fillna(0)
        df["est_revenue_usd"] = pd.to_numeric(df.get("estimated_revenue_usd", df.get("est_revenue_usd", 0)), errors="coerce").fillna(0)
        df["cogs_usd"] = pd.to_numeric(df.get("total_cogs_usd", df.get("cogs_usd", 0)), errors="coerce").fillna(0)
        df["qa_hold"] = pd.Series(df.get("qa_hold", False)).astype(bool)
        weekly = (
            df.groupby("week_start", dropna=True)
            .agg(
                extraction_runs=("batch_id_internal", "count"),
                finished_output_g=("finished_output_g", "sum"),
                avg_yield_pct=("yield_pct", "mean"),
                est_revenue_usd=("est_revenue_usd", "sum"),
                cogs_usd=("cogs_usd", "sum"),
                qa_hold_runs=("qa_hold", "sum"),
            )
            .reset_index()
            .sort_values("week_start", ascending=False)
        )
        weekly["gross_margin_pct"] = weekly.apply(
            lambda r: ((r["est_revenue_usd"] - r["cogs_usd"]) / r["est_revenue_usd"] * 100) if r["est_revenue_usd"] else 0.0,
            axis=1,
        )
        return weekly

# ------------------------------------------------------------
# DELIVERY IMPACT MODULE
# ------------------------------------------------------------
try:
    from delivery_impact import (
        parse_manifest_pdf_bytes,
        parse_manifest_csv_xlsx_bytes,
        parse_sales_report_bytes as _parse_sales_report_bytes,
        normalize_sales_report_dataframe as _normalize_sales_report_dataframe,
        match_manifest_to_sales,
        compute_delivery_kpis,
        compute_weekday_wow_kpis,
        build_time_series,
        build_wow_time_series,
        DELIVERY_WINDOW_DAYS,
    )
    _DELIVERY_IMPACT_AVAILABLE = True
except (ImportError, AttributeError, SyntaxError) as _di_import_err:
    _DELIVERY_IMPACT_AVAILABLE = False
    print(
        f"[buyer-dashboard] WARNING: delivery_impact could not be imported: "
        f"{type(_di_import_err).__name__}: {_di_import_err}",
        file=sys.stderr,
    )


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt. For admin/dev use only."""
    if not BCRYPT_AVAILABLE:
        raise RuntimeError("bcrypt is not installed. Run: pip install bcrypt>=4.0.0")
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    if not BCRYPT_AVAILABLE or not plain or not hashed:
        return False
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ============================================================
# PURCHASING-DIRECTOR UPGRADES (NO LOGIC CHANGE)
# - De-dupe upload logging (prevents repeated log spam on reruns)
# - Centralize common alias lists (less drift, easier maintenance)
# - Safer rerun helper (Streamlit version compatible)
# - Keep UI/images/functions the same; only harden behavior
# ============================================================

def _safe_rerun():
    """Streamlit version-safe rerun."""
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            # last resort: do nothing
            pass


def _render_sidebar_nav_mockup(app_mode: str, section: str | None = None) -> None:
    active_home = "active" if app_mode == "🛒 Buyer Operations" and section == "📊 Inventory Dashboard" else ""
    buyer_active = {
        "📊 Inventory Dashboard": "📦 Inventory Intelligence",
        "🧾 PO Builder": "📝 Purchase Orders",
        "📈 Trends": "📊 Category Analytics",
        "🐢 Slow Movers": "🔁 Reorder Planner",
    }.get(section, "")
    st.sidebar.markdown(
        f"""
        <div class="sidebar-brand">
          <img src="https://raw.githubusercontent.com/MAVet710/buyer-dashboard/main/IMG_7158.PNG" alt="logo" />
          🍁 BUYER DASHBOARD
        </div>
        <div class="sidebar-nav-label">HOME</div>
        <div class="sidebar-nav-item {active_home}">🏠 Home</div>
        <div class="sidebar-nav-label">BUYER OPERATIONS</div>
        <div class="sidebar-nav-item {'active' if buyer_active == '📦 Inventory Intelligence' else ''}">📦 Inventory Intelligence</div>
        <div class="sidebar-nav-item {'active' if buyer_active == '📝 Purchase Orders' else ''}">📝 Purchase Orders</div>
        <div class="sidebar-nav-item">🤝 Vendor Performance</div>
        <div class="sidebar-nav-item {'active' if buyer_active == '📊 Category Analytics' else ''}">📊 Category Analytics</div>
        <div class="sidebar-nav-item {'active' if buyer_active == '🔁 Reorder Planner' else ''}">🔁 Reorder Planner</div>
        <div class="sidebar-nav-label">EXTRACTION COMMAND CENTER</div>
        <div class="sidebar-nav-item {'active' if app_mode == '🧪 Extraction Command Center' else ''}">📈 Executive Overview</div>
        <div class="sidebar-nav-item">🧪 Run Analytics</div>
        <div class="sidebar-nav-item">🧭 Process Tracker</div>
        <div class="sidebar-nav-item">🧱 Extraction Inventory</div>
        <div class="sidebar-nav-item">🤝 Toll Processing</div>
        <div class="sidebar-nav-item">✅ Compliance / METRC</div>
        <div class="sidebar-nav-item">🗂 Data Input & Mapping</div>
        <div class="sidebar-nav-label">AI SUPPORT</div>
        <div class="sidebar-nav-item {'active' if section == '🧠 Buyer Intelligence' else ''}">💬 Ask Doobie</div>
        <div class="sidebar-nav-item" style="margin-top:8px;border:1px solid rgba(255,255,255,.08);background:rgba(0,0,0,.25);">
          <strong>Ask Doobie</strong><br/>
          <span style="opacity:.72">Assistant for buyer and extraction questions.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# Common alias sets (used repeatedly)
INV_NAME_ALIASES = [
    "product", "productname", "item", "itemname", "name", "skuname",
    "skuid", "product name", "product_name", "product title", "title"
]
INV_CAT_ALIASES = [
    "category", "subcategory", "productcategory", "department",
    "mastercategory", "product category", "cannabis", "product_category",
    "ecomm category", "ecommcategory",
]
INV_QTY_ALIASES = [
    "available", "onhand", "onhandunits", "quantity", "qty",
    "quantityonhand", "instock", "currentquantity", "current quantity",
    "inventoryavailable", "inventory available", "available quantity",
    "med total", "medtotal",
    "med sellable", "medsellable",
]
INV_SKU_ALIASES = ["sku", "skuid", "productid", "product_id", "itemid", "item_id"]
INV_BATCH_ALIASES = [
    "batch", "batchnumber", "batch number", "lot", "lotnumber", "lot number",
    "batchid", "batch id", "lotid", "lot id", "inventorybatch", "inventory batch",
    "packageid", "package id",
]

SALES_NAME_ALIASES = [
    "product", "productname", "product title", "producttitle",
    "productid", "name", "item", "itemname", "skuname",
    "sku", "description", "product name", "product_name"
]
SALES_QTY_ALIASES = [
    "quantitysold", "quantity sold",
    "qtysold", "qty sold",
    "itemsold", "item sold", "items sold",
    "unitssold", "units sold", "unit sold", "unitsold", "units",
    "totalunits", "total units",
    "totalinventorysold", "total inventory sold",
    "quantity", "qty",
]
SALES_CAT_ALIASES = [
    "mastercategory", "category", "master_category",
    "productcategory", "product category",
    "department", "dept", "subcategory", "productcategoryname",
    "product category name"
]
SALES_SKU_ALIASES = ["sku", "skuid", "productid", "product_id"]
SALES_REV_ALIASES = [
    "netsales", "net sales", "sales", "totalsales", "total …161994 tokens truncated…      available_to_buy = max(recommended_budget, 0)

        c1,c2,c3 = st.columns(3)
        c1.metric("Recommended Purchasing Budget", format_currency(available_to_buy))
        c2.metric("Current Active Inventory at Cost", format_currency(active_inventory_cost))
        c3.metric("Target Inventory at Cost", format_currency(target_inventory_cost))
        c4,c5,c6 = st.columns(3)
        over_under = f"Overbought by {format_currency(abs(recommended_budget))}" if recommended_budget < 0 else f"Available to Buy: {format_currency(recommended_budget)}"
        c4.metric("Over/Under Position", over_under)
        c5.metric("Avg Daily COGS", format_currency(avg_daily_cogs))
        c6.metric("On Order Cost", format_currency(on_order_cost))

        inv_cat_col = detect_column(active_inv_df.columns, [normalize_col(x) for x in ["mastercategory","subcategory","category"]])
        sales_cat_col = detect_column(sales_window_df.columns, [normalize_col(x) for x in ["mastercategory","subcategory","category"]])
        if inv_cat_col and sales_cat_col and sales_col is not None:
            sales_cat = sales_window_df.groupby(sales_cat_col, dropna=False)[sales_col].sum().reset_index().rename(columns={sales_cat_col:"Category","%s":"Sales"%sales_col})
            sales_cat = sales_cat.rename(columns={sales_col:"Sales Window Retail Sales"})
            inv_cat = active_inv_df.groupby(inv_cat_col, dropna=False)["_active_cost"].sum().reset_index().rename(columns={inv_cat_col:"Category","_active_cost":"Current Inventory at Cost"})
            cat_df = pd.merge(sales_cat, inv_cat, on="Category", how="outer").fillna(0)
            cat_df["Avg Daily Sales"] = cat_df["Sales Window Retail Sales"] / max(int(selected_days),1)
            cat_df["Avg Daily COGS"] = cat_df["Avg Daily Sales"] * cogs_pct_input
            cat_df["Target Inventory at Cost"] = cat_df["Avg Daily COGS"] * float(target_dos) * (1+safety_stock) * (1+growth_adj)
            cat_df["Recommended Budget"] = cat_df["Target Inventory at Cost"] - cat_df["Current Inventory at Cost"]
            cat_df["Budget Status"] = np.where(cat_df["Recommended Budget"] > 0, "Buy", np.where(cat_df["Recommended Budget"] < 0, "Overstocked", "Hold"))
            cat_df["Notes"] = np.where(cat_df["Budget Status"]=="Buy", "Allocate purchasing budget", np.where(cat_df["Budget Status"]=="Overstocked", "Reduce buys and sell-through", "Near target"))
            st.markdown("### Category-Level Recommended Budget")
            st.dataframe(cat_df, width="stretch")
            if PLOTLY_AVAILABLE and not cat_df.empty:
                st.plotly_chart(px.bar(cat_df, x="Category", y="Recommended Budget", title="Recommended Budget by Category"), width="stretch")
                melt_df = cat_df[["Category","Current Inventory at Cost","Target Inventory at Cost"]].melt(id_vars="Category", var_name="Metric", value_name="Value")
                st.plotly_chart(px.bar(melt_df, x="Category", y="Value", color="Metric", barmode="group", title="Current vs Target Inventory by Category"), width="stretch")

        scenario_rows=[]
        for name,dos,ss,gr in [("Conservative",30,0.05,0.0),("Balanced",float(target_dos),float(safety_stock),float(growth_adj)),("Aggressive",60,0.15,0.10)]:
            t=(avg_daily_cogs*dos)*(1+ss)*(1+gr)
            rb=t-active_inventory_cost-on_order_cost
            scenario_rows.append({"Scenario":name,"Target Inventory":t,"Current Active Inventory":active_inventory_cost,"On Order":on_order_cost,"Recommended Budget":rb,"Status":"Available to Buy" if rb>=0 else "Overbought"})
        st.markdown("### Budget Scenario Table")
        st.dataframe(pd.DataFrame(scenario_rows), width="stretch")
        if "po_items" in st.session_state:
            proposed_po_total = float(sum(float(i.get("Total",0) or 0) for i in st.session_state.po_items))
            remaining_budget_after_po = recommended_budget - proposed_po_total
            st.metric("Remaining Budget After PO", format_currency(remaining_budget_after_po))
            if remaining_budget_after_po < 0:
                st.warning(f"This PO exceeds the recommended purchasing budget by {format_currency(abs(remaining_budget_after_po))}.")

elif section == "🧾 PO Builder":
    st.subheader("Purchase Order Builder")
    st.write("Create professional purchase orders with automatic calculations and PDF export.")

    # =========================================================
    # REORDER CROSS-REFERENCE (from Inventory Dashboard data)
    # =========================================================
    _detail_cached = st.session_state.get("detail_cached_df")
    _detail_product_cached = st.session_state.get("detail_product_cached_df")

    if _detail_cached is not None and not _detail_cached.empty:
        reorder_rows = _detail_cached[_detail_cached["reorderpriority"] == "1 – Reorder ASAP"].copy()

        # Enrich with top_products if product-level data is available
        if _detail_product_cached is not None and not _detail_product_cached.empty:
            try:
                _dpxref = _detail_product_cached[["subcategory", "product_name", "strain_type", "packagesize", "unitssold"]].copy()
                _dpxref["unitssold"] = pd.to_numeric(_dpxref["unitssold"], errors="coerce").fillna(0)
                _dp_top = (
                    _dpxref.sort_values("unitssold", ascending=False)
                    .groupby(["subcategory", "strain_type", "packagesize"], dropna=False, sort=False)["product_name"]
                    .apply(lambda x: ", ".join(x.astype(str).head(5).tolist()))
                    .reset_index()
                    .rename(columns={"product_name": "top_products"})
                )
                reorder_rows = reorder_rows.merge(_dp_top, on=["subcategory", "strain_type", "packagesize"], how="left")
                reorder_rows["top_products"] = reorder_rows["top_products"].fillna("")
            except Exception:
                if "top_products" not in reorder_rows.columns:
                    reorder_rows["top_products"] = ""

        with st.expander("📊 Reorder Cross-Reference (from Inventory Dashboard)", expanded=True):
            if reorder_rows.empty:
                st.success("✅ No items flagged 'Reorder ASAP' in the current dashboard view.")
            else:
                _has_price = "unit_cost" in reorder_rows.columns and reorder_rows["unit_cost"].gt(0).any()
                st.caption(
                    f"**{len(reorder_rows)} line(s)** flagged as *Reorder ASAP* from your last Inventory Dashboard load. "
                    "Use the button below to bulk-add them to the PO, or review individual rows first."
                    + (
                        " 💲 **Current Price** = inventory 'Current price' ÷ 2 (wholesale adjustment)."
                        if _has_price else ""
                    )
                )
                _xref_cols = ["subcategory", "strain_type", "packagesize", "onhandunits", "avgunitsperday", "daysonhand", "reorderqty"]
                if _has_price:
                    reorder_rows = reorder_rows.copy()
                    reorder_rows["Current Price"] = (
                        pd.to_numeric(reorder_rows["unit_cost"], errors="coerce").fillna(0) / 2
                    ).round(2)
                    _xref_cols.append("Current Price")
                if "top_products" in reorder_rows.columns:
                    _xref_cols.append("top_products")
                _xref_cols = [c for c in _xref_cols if c in reorder_rows.columns]
                st.dataframe(reorder_rows[_xref_cols].reset_index(drop=True), width="stretch")

                if st.button("➕ Add All Reorder ASAP Lines to PO", key="po_xref_add_all"):
                    _added = 0
                    for _, _r in reorder_rows.iterrows():
                        _cat = str(_r.get("subcategory", ""))
                        _strain = str(_r.get("strain_type", ""))
                        _size = str(_r.get("packagesize", ""))
                        _desc = " ".join(filter(None, [_cat, _strain, _size]))
                        _top_raw = str(_r.get("top_products", "")).strip()
                        _top = _top_raw.split(",")[0].strip() if _top_raw else _desc
                        try:
                            _qty = int(_r.get("reorderqty", 0))
                            _qty = _qty if _qty > 0 else 1
                        except (ValueError, TypeError):
                            _qty = 1
                        try:
                            _raw_cost = pd.to_numeric(_r.get("unit_cost", 0), errors="coerce")
                            _price = float(_raw_cost) / 2 if pd.notna(_raw_cost) else 0.0
                        except (ValueError, TypeError):
                            _price = 0.0
                        st.session_state.po_items.append({
                            "SKU": "",
                            "Description": _top if _top else _desc,
                            "Strain": _strain,
                            "Size": _size,
                            "Quantity": _qty,
                            "Price": round(_price, 2),
                            "Total": 0.0,
                        })
                        _added += 1
                    st.success(f"Added {_added} item(s) to the PO. Fill in prices below.")
                    _safe_rerun()
    else:
        st.info(
            "💡 Go to **📊 Inventory Dashboard** and upload your files first — "
            "Reorder ASAP items will then appear here for quick PO creation."
        )

    st.markdown("---")
    
    # Initialize session state for PO
    if 'po_items' not in st.session_state:
        st.session_state.po_items = []
    
    # Store and Vendor Information
    st.markdown("### 📋 Order Information")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        store_name = st.text_input("Store Name", value="Cannabis Store")
        store_address = st.text_area("Store Address", value="123 Main St\nCity, State 12345", height=100)
    
    with col2:
        vendor_name = st.text_input("Vendor Name", value="")
        vendor_address = st.text_area("Vendor Address", value="", height=100)
    
    with col3:
        po_number = st.text_input("PO Number", value=f"PO-{datetime.now().strftime('%Y%m%d')}")
        po_date = st.date_input("PO Date", value=datetime.now().date())
    
    # Line Items
    st.markdown("### 📦 Line Items")
    
    with st.form("add_item_form"):
        col1, col2, col3, col4, col5, col6 = st.columns([2, 3, 2, 2, 1, 1])
        
        with col1:
            sku = st.text_input("SKU")
        with col2:
            description = st.text_input("Description")
        with col3:
            strain = st.text_input("Strain")
        with col4:
            size = st.text_input("Size")
        with col5:
            quantity = st.number_input("Qty", min_value=1, value=1)
        with col6:
            price = st.number_input("Price", min_value=0.0, value=0.0, step=0.01)
        
        submitted = st.form_submit_button("➕ Add Item")
        if submitted and description:
            st.session_state.po_items.append({
                'SKU': sku,
                'Description': description,
                'Strain': strain,
                'Size': size,
                'Quantity': quantity,
                'Price': price,
                'Total': quantity * price
            })
            _safe_rerun()
    
    # Display current items
    if st.session_state.po_items:
        st.markdown("#### Current Items")
        items_df = pd.DataFrame(st.session_state.po_items)

        # ---- Inventory cross-reference ----
        _inv_xref = _build_inv_xref_table()
        if _inv_xref is None:
            st.caption(
                "💡 Upload inventory on Inventory Dashboard to enable PO inventory cross-check."
            )

        on_hand_list = []
        review_list = []
        review_reason_list = []
        for _item in st.session_state.po_items:
            _on_hand = 0
            if _inv_xref is not None:
                _norm_desc = _normalize_for_match(_item.get("Description", ""))
                _po_size_raw = str(_item.get("Size", "")).strip()
                _size_present = bool(_po_size_raw)
                _norm_size = _normalize_size_for_match(_po_size_raw)
                _matches = _inv_xref[_inv_xref["norm_name"] == _norm_desc]
                if _size_present:
                    _matches = _matches[_matches["norm_size"] == _norm_size]
                _on_hand = int(_matches["onhand_total"].sum())
            on_hand_list.append(_on_hand)
            _review = _inv_xref is not None and _on_hand >= PO_REVIEW_THRESHOLD
            review_list.append(_review)
            review_reason_list.append(f">={PO_REVIEW_THRESHOLD} on hand" if _review else "")

        items_df["On Hand (Inv)"] = on_hand_list
        items_df["Review?"] = review_list
        items_df["Review Reason"] = review_reason_list

        if any(review_list):
            st.warning(
                f"⚠️ One or more PO line items already have >={PO_REVIEW_THRESHOLD} units on hand. "
                "Review flagged items before purchasing."
            )

        st.dataframe(items_df, width="stretch")
        
        # Subtotal
        subtotal = sum(item['Total'] for item in st.session_state.po_items)
        
        # Calculations
        st.markdown("### 💰 Totals")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            tax_rate = st.number_input("Tax Rate (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.1)
        with col2:
            discount = st.number_input("Discount ($)", min_value=0.0, value=0.0, step=1.0)
        with col3:
            shipping = st.number_input("Shipping ($)", min_value=0.0, value=0.0, step=1.0)
        
        tax_amount = subtotal * (tax_rate / 100)
        total = subtotal + tax_amount - discount + shipping
        st.session_state.proposed_po_total = float(total)
        
        # Display totals
        st.markdown("---")
        totals_col1, totals_col2 = st.columns([3, 1])
        with totals_col2:
            st.markdown(f"**Subtotal:** ${subtotal:,.2f}")
            if tax_rate > 0:
                st.markdown(f"**Tax ({tax_rate}%):** ${tax_amount:,.2f}")
            if discount > 0:
                st.markdown(f"**Discount:** -${discount:,.2f}")
            if shipping > 0:
                st.markdown(f"**Shipping:** ${shipping:,.2f}")
            st.markdown(f"### **Total:** ${total:,.2f}")
        
        # Action buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🗑️ Clear All Items"):
                st.session_state.po_items = []
                _safe_rerun()
        
        with col2:
            if st.button("📄 Generate PDF"):
                # Generate PDF
                pdf_buffer = BytesIO()
                c = canvas.Canvas(pdf_buffer, pagesize=letter)
                width, height = letter
                
                # Header
                c.setFont("Helvetica-Bold", 20)
                c.drawString(1*inch, height - 1*inch, "PURCHASE ORDER")
                
                # PO Info
                c.setFont("Helvetica", 10)
                c.drawString(1*inch, height - 1.3*inch, f"PO Number: {po_number}")
                c.drawString(1*inch, height - 1.5*inch, f"Date: {po_date}")
                
                # Store info
                c.setFont("Helvetica-Bold", 12)
                c.drawString(1*inch, height - 2*inch, "FROM:")
                c.setFont("Helvetica", 10)
                y = height - 2.2*inch
                c.drawString(1*inch, y, store_name)
                for line in store_address.split('\n'):
                    y -= 0.15*inch
                    c.drawString(1*inch, y, line)
                
                # Vendor info
                c.setFont("Helvetica-Bold", 12)
                c.drawString(4*inch, height - 2*inch, "TO:")
                c.setFont("Helvetica", 10)
                y = height - 2.2*inch
                c.drawString(4*inch, y, vendor_name)
                for line in vendor_address.split('\n'):
                    y -= 0.15*inch
                    c.drawString(4*inch, y, line)
                
                # Items table
                y = height - 3.5*inch
                c.setFont("Helvetica-Bold", 10)
                c.drawString(1*inch, y, "SKU")
                c.drawString(2*inch, y, "Description")
                c.drawString(4*inch, y, "Strain")
                c.drawString(5*inch, y, "Size")
                c.drawString(5.5*inch, y, "Qty")
                c.drawString(6*inch, y, "Price")
                c.drawString(6.7*inch, y, "Total")
                
                c.line(1*inch, y - 0.05*inch, 7.5*inch, y - 0.05*inch)
                
                y -= 0.25*inch
                c.setFont("Helvetica", 9)
                for item in st.session_state.po_items:
                    c.drawString(1*inch, y, str(item['SKU'])[:MAX_SKU_LENGTH_PDF])
                    c.drawString(2*inch, y, str(item['Description'])[:MAX_DESCRIPTION_LENGTH_PDF])
                    c.drawString(4*inch, y, str(item['Strain'])[:MAX_STRAIN_LENGTH_PDF])
                    c.drawString(5*inch, y, str(item['Size'])[:MAX_SIZE_LENGTH_PDF])
                    c.drawString(5.5*inch, y, str(item['Quantity']))
                    c.drawString(6*inch, y, f"${item['Price']:.2f}")
                    c.drawString(6.7*inch, y, f"${item['Total']:.2f}")
                    y -= 0.2*inch
                    if y < 2*inch:  # New page if needed
                        c.showPage()
                        y = height - 1*inch
                
                # Totals
                y -= 0.3*inch
                c.line(5.5*inch, y, 7.5*inch, y)
                y -= 0.25*inch
                c.setFont("Helvetica", 10)
                c.drawString(6*inch, y, "Subtotal:")
                c.drawString(6.7*inch, y, f"${subtotal:,.2f}")
                
                if tax_rate > 0:
                    y -= 0.2*inch
                    c.drawString(6*inch, y, f"Tax ({tax_rate}%):")
                    c.drawString(6.7*inch, y, f"${tax_amount:,.2f}")
                
                if discount > 0:
                    y -= 0.2*inch
                    c.drawString(6*inch, y, "Discount:")
                    c.drawString(6.7*inch, y, f"-${discount:,.2f}")
                
                if shipping > 0:
                    y -= 0.2*inch
                    c.drawString(6*inch, y, "Shipping:")
                    c.drawString(6.7*inch, y, f"${shipping:,.2f}")
                
                y -= 0.25*inch
                c.line(6*inch, y, 7.5*inch, y)
                y -= 0.25*inch
                c.setFont("Helvetica-Bold", 12)
                c.drawString(6*inch, y, "TOTAL:")
                c.drawString(6.7*inch, y, f"${total:,.2f}")
                
                c.save()
                pdf_buffer.seek(0)
                
                st.download_button(
                    label="📥 Download PDF",
                    data=pdf_buffer,
                    file_name=f"PO_{po_number}_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf"
                )
    else:
        st.info("👆 Add items to your purchase order using the form above")

# FOOTER
st.markdown("---")
year = datetime.now().year
st.markdown(f'<div class="footer">{LICENSE_FOOTER} • © {year}</div>', unsafe_allow_html=True)

