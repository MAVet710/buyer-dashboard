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

from ai_providers import build_provider
from compliance_engine import ComplianceRepository, ComplianceSource, format_compliance_answer
from extraction_partner_upload_upgrade import render_extraction_partner_upload_ui
from ui_polish import (
    load_polished_theme,
    render_section_header,
    render_metric_tiles,
    chart_card_start,
    chart_card_end,
    render_topbar,
    render_hero,
    render_ai_brief,
    render_sidebar_nav_css,
    render_action_button,
    render_extraction_kpi,
    render_inventory_table_css,
)

load_dotenv()

# Owner mark (non-functional, intentional signature fragment).
# __  ______             __ ____________

# For PDF generation
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

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
# AI PROVIDER ABSTRACTION (AI INVENTORY CHECK)
# ------------------------------------------------------------
OPENAI_AVAILABLE = False
ai_client = None
ai_provider = None

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
        out["est_revenue_usd"] = pd.to_numeric(_partner_pick(df, ["est_revenue_usd", "revenue_usd"], default=0), errors="coerce").fillna(0)
        out["cogs_usd"] = pd.to_numeric(_partner_pick(df, ["cogs_usd", "cogs"], default=0), errors="coerce").fillna(0)
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
        df["est_revenue_usd"] = pd.to_numeric(df.get("est_revenue_usd", 0), errors="coerce").fillna(0)
        df["cogs_usd"] = pd.to_numeric(df.get("cogs_usd", 0), errors="coerce").fillna(0)
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
    "netsales", "net sales", "sales", "totalsales", "total sales",
    "revenue", "grosssales", "gross sales"
]
SALES_BATCH_ALIASES = [
    "batchid", "batch id", "batch", "batchnumber", "batch number",
    "lotid", "lot id", "lot", "lotnumber", "lot number",
]
SALES_PACKAGE_ALIASES = [
    "packageid", "package id", "packagenumber", "package number",
]
SALES_ORDER_ID_ALIASES = ["orderid", "order id", "ordernumber", "order number", "order"]
SALES_ORDER_TIME_ALIASES = ["ordertime", "order time", "orderdate", "order date", "datetime"]

# Constants for slow movers analysis
UNKNOWN_DAYS_OF_SUPPLY = 999
DEFAULT_SALES_PERIOD_DAYS = 30  # Default assumption when date range cannot be determined
SLOW_MOVER_VELOCITY_WINDOWS = [28, 56, 84]  # Available velocity window choices (days)
SLOW_MOVER_DEFAULT_DOH_THRESHOLD = 60  # Default Days-on-Hand threshold to flag a slow mover
SLOW_MOVER_TOP_N_OPTIONS = [25, 50, 100, 0]  # 0 = All
SLOW_MOVER_SORT_OPTIONS = [
    "Days of Supply ↓",
    "Weeks of Supply ↓",
    "$ On-Hand ↓",
    "Days Since Last Sale ↓",
]

# Aliases for optional inventory columns used in Slow Movers
INV_COST_ALIASES = [
    "cost", "unitcost", "unit cost", "cogs", "costprice", "cost price",
    "wholesale", "wholesaleprice", "wholesale price",
    "currentprice", "current price",
]
INV_RETAIL_PRICE_ALIASES = [
    "medprice", "med price", "retail", "retailprice", "retail price", "msrp",
]
INV_STRAIN_TYPE_ALIASES = [
    "straintype", "strain type", "strain", "ecommstraintype", "ecomm strain type",
    "producttype", "product type",
]
INV_BRAND_ALIASES = [
    "brand", "brandname", "brand name", "vendor", "vendorname", "vendor name",
    "manufacturer", "producer", "supplier",
]
INV_SKU_COL_ALIASES = INV_SKU_ALIASES  # reuse existing list

# Expiration date aliases for inventory
INV_EXPIRY_ALIASES = [
    "expirationdate", "expiration date", "expiry", "expirydate", "expiry date",
    "bestby", "best by", "bestbydate", "best by date", "usebydate", "use by date",
    "expires", "exp", "expdate", "exp date",
]

# Fraction of retail price used to derive unit_cost when no explicit cost column is present
INV_COST_RETAIL_RATIO = 0.5

# Recognized strain type values from explicit column (prefer these over inferred extraction)
VALID_STRAIN_TYPES = frozenset([
    "indica", "sativa", "hybrid", "cbd",
    "indica dominant hybrid", "sativa dominant hybrid",
])

# Inventory Dashboard – Buyer View constants
# Sort options for buyer-focused inventory view
INVENTORY_SORT_OPTIONS = [
    "$ on hand ↓",
    "DOH (high→low) ↓",
    "DOH (low→high) ↑",
    "Expiring soonest",
    "Avg weekly sales ↓",
]
# DOH ≤ this value → flagged as Reorder (configurable)
INVENTORY_REORDER_DOH_THRESHOLD = 21
# DOH ≥ this value → flagged as Overstock (configurable)
INVENTORY_OVERSTOCK_DOH_THRESHOLD = 90
# Days until expiry ≤ this → flagged as Expiring (configurable)
INVENTORY_EXPIRING_SOON_DAYS = 60

# Constants for PDF generation
MAX_SKU_LENGTH_PDF = 10
MAX_DESCRIPTION_LENGTH_PDF = 20
MAX_STRAIN_LENGTH_PDF = 10
MAX_SIZE_LENGTH_PDF = 8

# Maximum allowed upload size per file (50 MB)
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Maximum rows to display in product-level detail table (performance guard)
PRODUCT_TABLE_DISPLAY_LIMIT = 2000

# Minimum on-hand units threshold for flagging a PO line for review
PO_REVIEW_THRESHOLD = 15

# Optional external market references for buyer workflows.
# These links are informational only; buyer recommendations should still be grounded
# in uploaded operational data and/or retrieved internal context.
BUYER_MARKET_REFERENCES = [
    {
        "name": "Headset Brand Marketplace",
        "url": "https://www.headset.io/brands",
        "notes": "Live, frequently updated brand-level market visibility across U.S. cannabis markets.",
    },
]

# Local app URL for self-hosted deployment links
LOCAL_APP_URL = os.environ.get("LOCAL_APP_URL", "http://localhost:8501")


def _find_openai_key():
    """
    Robust key lookup for AI provider credentials.

    Search order supports both legacy and project-specific key names:
    1) st.secrets["AI_API_KEY"] / st.secrets["OPENAI_API_KEY"] at top-level
    2) Any nested table containing either key name
    3) os.environ["AI_API_KEY"] / os.environ["OPENAI_API_KEY"]
    Returns (key or None, where_found_str)
    """
    key_names = ["AI_API_KEY", "OPENAI_API_KEY"]

    # 1) top-level
    try:
        for key_name in key_names:
            if key_name in st.secrets:
                k = str(st.secrets[key_name]).strip()
                if k:
                    return k, f"secrets:top:{key_name}"
    except Exception:
        pass

    # 2) nested
    try:
        for k0 in list(st.secrets.keys()):
            try:
                v = st.secrets.get(k0)
                if isinstance(v, dict):
                    for key_name in key_names:
                        if key_name in v:
                            k = str(v[key_name]).strip()
                            if k:
                                return k, f"secrets:{k0}:{key_name}"
            except Exception:
                continue
    except Exception:
        pass

    # 3) env
    for key_name in key_names:
        envk = os.environ.get(key_name, "").strip()
        if envk:
            return envk, f"env:{key_name}"

    return None, None


def init_openai_client():
    global OPENAI_AVAILABLE, ai_client, ai_provider

    key, _where = _find_openai_key()
    preferred_provider = st.session_state.get("preferred_ai_provider")
    if not preferred_provider:
        preferred_provider = os.environ.get("AI_PROVIDER", "").strip().lower() or None

    ai_provider = build_provider(preferred_provider, key)
    OPENAI_AVAILABLE = ai_provider is not None
    ai_client = ai_provider


# =========================
# FREE STRAIN LOOKUP DATABASE
# =========================
# Comprehensive database of cannabis strains and their types (completely free, no API needed)
STRAIN_DATABASE = {
    # Popular Indica Strains
    "granddaddy purple": "indica", "gdp": "indica", "purple kush": "indica",
    "northern lights": "indica", "afghani": "indica", "blueberry": "indica",
    "bubba kush": "indica", "master kush": "indica", "og kush": "indica",
    "skywalker og": "indica", "kosher kush": "indica", "la confidential": "indica",
    "purple punch": "indica", "ice cream cake": "indica", "wedding cake": "indica",
    "do si dos": "indica", "dosidos": "indica", "zkittlez": "indica",
    "gelato": "indica", "sherbet": "indica", "sunset sherbet": "indica",
    "purple urkle": "indica", "grape ape": "indica", "blackberry kush": "indica",
    "death star": "indica", "romulan": "indica", "critical kush": "indica",
    "chocolate og": "indica", "motorbreath": "indica", "slurricane": "indica",
    "sundae driver": "indica", "candy rain": "indica", "cherry pie": "indica",
    
    # Popular Sativa Strains
    "sour diesel": "sativa", "jack herer": "sativa", "durban poison": "sativa",
    "green crack": "sativa", "super lemon haze": "sativa", "tangie": "sativa",
    "strawberry cough": "sativa", "trainwreck": "sativa", "maui wowie": "sativa",
    "acapulco gold": "sativa", "panama red": "sativa", "super silver haze": "sativa",
    "amnesia haze": "sativa", "ghost train haze": "sativa", "candyland": "sativa",
    "lemon skunk": "sativa", "chemdog": "sativa", "chem dawg": "sativa",
    "cherry ak": "sativa", "j1": "sativa", "lamb's bread": "sativa",
    "red congolese": "sativa", "thai": "sativa", "colombian gold": "sativa",
    "malawi": "sativa", "super sour diesel": "sativa", "clementine": "sativa",
    
    # Popular Hybrid Strains
    "blue dream": "hybrid", "girl scout cookies": "hybrid", "gsc": "hybrid",
    "gorilla glue": "hybrid", "gg4": "hybrid", "white widow": "hybrid",
    "pineapple express": "hybrid", "ak-47": "hybrid", "sour og": "hybrid",
    "golden goat": "hybrid", "headband": "hybrid", "chernobyl": "hybrid",
    "bruce banner": "hybrid", "fire og": "hybrid", "gmo cookies": "hybrid",
    "mac": "hybrid", "miracle alien cookies": "hybrid", "wedding crasher": "hybrid",
    "mimosa": "hybrid", "runtz": "hybrid", "biscotti": "hybrid",
    "cookies and cream": "hybrid", "animal cookies": "hybrid", "platinum cookies": "hybrid",
    "thin mint": "hybrid", "thin mint cookies": "hybrid", "scooby snacks": "hybrid",
    "london pound cake": "hybrid", "apples and bananas": "hybrid",
    "cereal milk": "hybrid", "rainbow belts": "hybrid", "jealousy": "hybrid",
    "grape gasoline": "hybrid", "oreoz": "hybrid", "gary payton": "hybrid",
    "obama kush": "hybrid", "tahoe og": "hybrid", "sfv og": "hybrid",
    "larry og": "hybrid", "triple og": "hybrid", "wifi og": "hybrid",
    
    # Generic strain-related terms (with word boundaries to avoid false positives)
    # These match only when appearing as standalone words
    "kush": "indica", "haze": "sativa", "cookies": "hybrid",
    "diesel": "sativa", "skunk": "sativa", "cheese": "hybrid", "punch": "indica",
    "cake": "indica", "pie": "indica", "breath": "hybrid", "sherb": "indica",
}

# Pre-compile regex patterns for performance
SIZE_PATTERN = re.compile(r'\b\d+\.?\d*\s*(g|mg|oz|ml|ct|count|pk|pack)\b')
PRODUCT_TYPE_PATTERN = re.compile(r'\b(flower|pre[-\s]?roll|joint|blunt|eighth|quarter|half|ounce)\b')

# Pre-sort strain names by length (longest first) for matching priority
SORTED_STRAIN_NAMES = sorted(STRAIN_DATABASE.keys(), key=len, reverse=True)

# Pre-compile strain matching patterns for performance
STRAIN_PATTERNS = {
    strain: re.compile(r'\b' + re.escape(strain) + r'\b')
    for strain in STRAIN_DATABASE.keys()
}

# Cache for strain lookups
strain_lookup_cache = {}


def free_strain_lookup(product_name, category):
    """
    Free strain type lookup using a comprehensive strain database and pattern matching.
    No API calls, completely free and works offline.
    
    Args:
        product_name: The product name to analyze
        category: The product category (e.g., "flower", "pre rolls")
    
    Returns:
        str: The detected strain type (indica, sativa, hybrid) or "unspecified"
    """
    if not product_name:
        return "unspecified"
    
    # Check cache first
    cache_key = f"{product_name.lower().strip()}|{category.lower().strip()}"
    if cache_key in strain_lookup_cache:
        return strain_lookup_cache[cache_key]
    
    # Normalize the product name for matching
    name_lower = product_name.lower().strip()
    
    # Remove common size indicators and product types to focus on strain name
    # Uses pre-compiled regex patterns for better performance
    clean_name = SIZE_PATTERN.sub('', name_lower)
    clean_name = PRODUCT_TYPE_PATTERN.sub('', clean_name)
    clean_name = clean_name.strip()
    
    # Try exact match first (most accurate)
    if clean_name in STRAIN_DATABASE:
        result = STRAIN_DATABASE[clean_name]
        strain_lookup_cache[cache_key] = result
        return result
    
    # Try partial matching - uses pre-compiled patterns and pre-sorted list
    # Longer strain names are checked first to prefer specific over generic matches
    for strain_name in SORTED_STRAIN_NAMES:
        # Use pre-compiled word boundary pattern to avoid false matches
        # e.g., "og" should match "OG Kush" but not "dOGfood"
        if STRAIN_PATTERNS[strain_name].search(clean_name):
            result = STRAIN_DATABASE[strain_name]
            strain_lookup_cache[cache_key] = result
            return result
    
    # No match found
    strain_lookup_cache[cache_key] = "unspecified"
    return "unspecified"


def ai_lookup_strain_type(product_name, category):
    """
    DEPRECATED (v2.0): Use free_strain_lookup() instead for cost-free strain detection.
    
    This function is kept for backward compatibility but now redirects to the free lookup.
    Will be removed in v3.0 (planned for Q2 2026).
    
    Migration: Replace `ai_lookup_strain_type(name, cat)` with `free_strain_lookup(name, cat)`
    """
    return free_strain_lookup(product_name, category)


# =========================
# CONFIG & BRANDING (MAVet)
# =========================
CLIENT_NAME = "MAVet710"
APP_TITLE = "BUYER DASHBOARD"
APP_TAGLINE = "Streamlined purchasing visibility powered by Dutchie / BLAZE data."
LICENSE_FOOTER = "Semper Paratus • Powered by Good Weed and Data"

# 🔐 TRIAL SETTINGS
TRIAL_DURATION_HOURS = 24

# =========================
# SECRETS-BASED AUTH LOADING
# =========================
# Credentials are loaded from st.secrets["auth"] or environment variables.
# Plaintext credentials are NOT stored in source code.
# See SECURITY.md for configuration instructions.

def _load_auth_secrets():
    """
    Load admin users, regular users, and trial key hash from Streamlit secrets
    or environment variable fallback.

    Returns (admin_users_dict, user_users_dict, trial_key_hash_or_plain).
    Each dict maps username -> bcrypt_hash (or plaintext if
    st.secrets["auth"]["use_plaintext"] is explicitly True).
    """
    admins: dict = {}
    users: dict = {}
    trial_value: str = ""

    try:
        auth = st.secrets.get("auth", {})
    except Exception:
        auth = {}

    use_plaintext = bool(auth.get("use_plaintext", False)) if isinstance(auth, Mapping) else False

    # --- admins ---
    raw_admins = auth.get("admins", {}) if isinstance(auth, Mapping) else {}
    if isinstance(raw_admins, Mapping):
        for k, v in raw_admins.items():
            try:
                admins[str(k)] = str(v)
            except Exception:
                pass

    # --- users ---
    raw_users = auth.get("users", {}) if isinstance(auth, Mapping) else {}
    if isinstance(raw_users, Mapping):
        for k, v in raw_users.items():
            try:
                users[str(k)] = str(v)
            except Exception:
                pass

    # --- trial key ---
    trial_value = str(auth.get("trial_key_hash", "")).strip() if isinstance(auth, Mapping) else ""

    # Env-var fallback (single admin / single user / trial key)
    env_admin_user = os.environ.get("ADMIN_USERNAME", "").strip()
    env_admin_pass = os.environ.get("ADMIN_PASSWORD_HASH", "").strip()
    env_user_name = os.environ.get("USER_USERNAME", "").strip()
    env_user_pass = os.environ.get("USER_PASSWORD_HASH", "").strip()
    env_trial = os.environ.get("TRIAL_KEY_HASH", "").strip()

    if env_admin_user and env_admin_pass and env_admin_user not in admins:
        admins[env_admin_user] = env_admin_pass
    if env_user_name and env_user_pass and env_user_name not in users:
        users[env_user_name] = env_user_pass
    if env_trial and not trial_value:
        trial_value = env_trial

    return admins, users, trial_value, use_plaintext


ADMIN_USERS, USER_USERS, _TRIAL_VALUE, _AUTH_PLAINTEXT = _load_auth_secrets()

if not BCRYPT_AVAILABLE and not st.session_state.get("_bcrypt_warning_shown"):
    st.warning(
        "⚠️ bcrypt is not installed. Password verification is disabled. "
        "Please add `bcrypt>=4.0.0` to your requirements.txt and redeploy."
    )
    st.session_state["_bcrypt_warning_shown"] = True


def _check_password(plain: str, stored: str) -> bool:
    """
    Verify a password against a stored value.
    Uses bcrypt when available; falls back to plaintext only when
    use_plaintext mode is explicitly enabled or bcrypt is unavailable.
    """
    if not plain or not stored:
        return False
    if BCRYPT_AVAILABLE and not _AUTH_PLAINTEXT:
        return verify_password(plain, stored)
    # Plaintext fallback (legacy / dev only)
    return plain == stored


def _check_trial_key(plain: str) -> bool:
    """Verify a trial key against the stored hash or plaintext value."""
    if not plain or not _TRIAL_VALUE:
        return False
    if BCRYPT_AVAILABLE and not _AUTH_PLAINTEXT:
        return verify_password(plain, _TRIAL_VALUE)
    return plain == _TRIAL_VALUE


def _validate_auth_config() -> list:
    """
    Runtime self-check for auth configuration.
    Returns a list of (severity, message) tuples ('ok', 'warn', 'error').
    Never reveals secret values or hashes.
    """
    issues = []
    if not BCRYPT_AVAILABLE:
        issues.append(("error", "bcrypt is not installed. Add `bcrypt>=4.0.0` to requirements.txt and redeploy."))
    if not ADMIN_USERS:
        issues.append(("error", "No admin users loaded. Check that [auth.admins] is present in Streamlit secrets."))
    else:
        issues.append(("ok", f"{len(ADMIN_USERS)} admin user(s) loaded: {', '.join(sorted(ADMIN_USERS.keys()))}"))
    if not USER_USERS:
        issues.append(("warn", "No standard users loaded. Check that [auth.users] is present in Streamlit secrets if user login is expected."))
    else:
        issues.append(("ok", f"{len(USER_USERS)} standard user(s) loaded: {', '.join(sorted(USER_USERS.keys()))}"))
    for uname, stored_hash in ADMIN_USERS.items():
        if not stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
            issues.append(("warn", f"Admin '{uname}': stored value does not look like a bcrypt hash (should start with $2a$, $2b$, or $2y$)."))
    for uname, stored_hash in USER_USERS.items():
        if not stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
            issues.append(("warn", f"User '{uname}': stored value does not look like a bcrypt hash (should start with $2a$, $2b$, or $2y$)."))
    return issues

# ✅ Canonical category names (values, not column names)
REB_CATEGORIES = [
    "flower",
    "pre rolls",
    "vapes",
    "edibles",
    "beverages",
    "concentrates",
    "tinctures",
    "topicals",
]

# Tab icon (favicon) – MAVet image
page_icon_url = "https://raw.githubusercontent.com/MAVet710/buyer-dashboard/main/IMG_7158.PNG"

st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
    page_icon=page_icon_url,
)

# Background image – MAVet image
background_url = "https://raw.githubusercontent.com/MAVet710/buyer-dashboard/main/IMG_7158.PNG"

# =========================
# DAILY DATA PERSISTENCE
# Persists uploaded file bytes across session timeouts for the current calendar day.
# Uses @st.cache_resource so the store lives in server memory for the process lifetime.
# Keyed by {YYYY-MM-DD}::{username} so data is isolated per user and auto-expires at midnight.
# =========================
_DAILY_CACHE_KEYS = ["_cache_inv", "_cache_sales", "_cache_extra_sales", "_cache_quarantine"]


@st.cache_resource
def _get_daily_store() -> dict:
    """Return the server-wide mutable dict used for daily file-cache persistence."""
    return {}


def _daily_store_key(username: str) -> str:
    # Use | as delimiter since it cannot appear in typical usernames
    return f"{datetime.now().strftime('%Y-%m-%d')}|{username}"


def _save_to_daily_store(username: str) -> None:
    """Persist the current session's file caches to the cross-session daily store."""
    if not username:
        return
    store = _get_daily_store()
    key = _daily_store_key(username)
    if key not in store:
        store[key] = {}
    for ck in _DAILY_CACHE_KEYS:
        val = st.session_state.get(ck)
        if isinstance(val, dict) and val.get("bytes"):
            store[key][ck] = {"name": val.get("name", ""), "bytes": val["bytes"]}
    store[key]["_saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Purge entries from previous days to avoid unbounded memory growth
    today = datetime.now().strftime("%Y-%m-%d")
    for k in list(store.keys()):
        if not k.startswith(today):
            del store[k]


def _load_from_daily_store(username: str) -> bool:
    """
    Restore today's file caches from the daily store into session state.
    Only restores keys that are not already set in session state.
    Returns True if at least one file cache was restored.
    """
    if not username:
        return False
    store = _get_daily_store()
    data = store.get(_daily_store_key(username), {})
    restored = False
    for ck in _DAILY_CACHE_KEYS:
        if ck in data and not st.session_state.get(ck):
            st.session_state[ck] = data[ck]
            restored = True
    return restored


def _clear_daily_store(username: str) -> None:
    """Remove today's stored file caches for this user from both the store and session state."""
    if not username:
        return
    store = _get_daily_store()
    key = _daily_store_key(username)
    if key in store:
        del store[key]
    for ck in _DAILY_CACHE_KEYS:
        st.session_state.pop(ck, None)
    # Also reset processed DataFrames so the UI prompts for new uploads
    for sk in ["inv_raw_df", "sales_raw_df", "extra_sales_df",
               "detail_cached_df", "detail_product_cached_df"]:
        st.session_state[sk] = None


# =========================
# SESSION STATE DEFAULTS
# =========================
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "admin_user" not in st.session_state:
    st.session_state.admin_user = None
if "user_authenticated" not in st.session_state:
    st.session_state.user_authenticated = False
if "user_user" not in st.session_state:
    st.session_state.user_user = None
if "trial_start" not in st.session_state:
    st.session_state.trial_start = None
if "metric_filter" not in st.session_state:
    st.session_state.metric_filter = "All"  # All / Reorder ASAP
if "inv_raw_df" not in st.session_state:
    st.session_state.inv_raw_df = None
if "sales_raw_df" not in st.session_state:
    st.session_state.sales_raw_df = None
if "extra_sales_df" not in st.session_state:
    st.session_state.extra_sales_df = None
if "delivery_raw_df" not in st.session_state:
    st.session_state.delivery_raw_df = None
if "daily_sales_raw_df" not in st.session_state:
    st.session_state.daily_sales_raw_df = None
if "detail_cached_df" not in st.session_state:
    st.session_state.detail_cached_df = None
if "detail_product_cached_df" not in st.session_state:
    st.session_state.detail_product_cached_df = None
if "theme" not in st.session_state:
    st.session_state.theme = "Dark"  # Dark by default
if "strain_lookup_enabled" not in st.session_state:
    st.session_state.strain_lookup_enabled = True  # Enable free strain database lookup by default
if "data_mode" not in st.session_state:
    st.session_state.data_mode = "📁 Uploads"  # Default to manual upload mode
if "di_comparison_mode" not in st.session_state:
    st.session_state.di_comparison_mode = "📅 Before/After (±N days)"  # Default analysis mode

# Upload tracking (God-only viewer)
if "upload_log" not in st.session_state:
    st.session_state.upload_log = []  # list of dicts
if "uploaded_files_store" not in st.session_state:
    # key: upload_id -> {"name":..., "bytes":..., "uploader":..., "ts":...}
    st.session_state.uploaded_files_store = {}

# Upload de-dupe signature store (prevents repeated logging on reruns)
if "_upload_sig_seen" not in st.session_state:
    st.session_state._upload_sig_seen = set()

# Daily persistence restore flags (prevent re-restoring on every rerun)
if "_daily_restored" not in st.session_state:
    st.session_state._daily_restored = False
if "_daily_restore_msg" not in st.session_state:
    st.session_state._daily_restore_msg = False

# Brute-force login protection counters
_LOCKOUT_MAX_ATTEMPTS = 5
_LOCKOUT_MINUTES = 10
if "_admin_fail_count" not in st.session_state:
    st.session_state._admin_fail_count = 0
if "_admin_lockout_until" not in st.session_state:
    st.session_state._admin_lockout_until = None
if "_user_fail_count" not in st.session_state:
    st.session_state._user_fail_count = 0
if "_user_lockout_until" not in st.session_state:
    st.session_state._user_lockout_until = None

theme = st.session_state.theme

# =========================
# GLOBAL STYLING (theme-aware) — DO NOT CHANGE LOOK
# =========================
main_bg = "rgba(0, 0, 0, 0.85)" if theme == "Dark" else "rgba(255, 255, 255, 0.94)"
main_text = "#ffffff" if theme == "Dark" else "#111111"

st.markdown(
    f"""
    <style>
    .stApp {{
        background-image: url('{background_url}');
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}

    /* Main content area (center) */
    .block-container {{
        background-color: {main_bg};
        padding: 2rem;
        border-radius: 12px;
        color: {main_text} !important;
    }}

    /* Force almost all text in main area to theme text, but keep input text default */
    .block-container *:not(input):not(textarea):not(select) {{
        color: {main_text} !important;
    }}

    /* Keep tables readable on dark background */
    .dataframe td {{
        color: {main_text} !important;
    }}

    .stButton>button {{
        background-color: rgba(255, 255, 255, 0.08);
        color: {main_text};
        border: 1px solid rgba(255, 255, 255, 0.8);
        border-radius: 6px;
    }}

    .stButton>button:hover {{
        background-color: rgba(255, 255, 255, 0.25);
    }}

    .footer {{
        text-align: center;
        font-size: 0.75rem;
        opacity: 0.7;
        margin-top: 2rem;
        color: {main_text} !important;
    }}

    /* Sidebar: high-contrast, readable (fixes white/hard-to-see issues) */
    [data-testid="stSidebar"] {{
        background-color: #f3f4f6 !important;
    }}
    [data-testid="stSidebar"] * {{
        color: #111111 !important;
        font-size: 0.9rem;
    }}
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea,
    [data-testid="stSidebar"] select {{
        background-color: #ffffff !important;
        color: #111111 !important;
        border-radius: 4px;
    }}

    /* PO-only labels in main content */
    .po-label {{
        color: {main_text} !important;
        font-weight: 600;
        font-size: 0.9rem;
        margin-bottom: 0.1rem;
    }}

    /* ---- Slow Movers filter bar + KPI tiles (contrast/readability) ---- */
    .sm-filter-bar {{
        background-color: {"rgba(30,30,40,0.92)" if theme == "Dark" else "rgba(240,242,246,0.98)"};
        border: 1px solid {"rgba(255,255,255,0.18)" if theme == "Dark" else "rgba(0,0,0,0.12)"};
        border-radius: 10px;
        padding: 0.75rem 1rem 0.5rem 1rem;
        margin-bottom: 1rem;
    }}

    /* Input widgets inside the filter bar */
    .sm-filter-bar input,
    .sm-filter-bar select,
    .sm-filter-bar textarea {{
        background-color: {"rgba(255,255,255,0.12)" if theme == "Dark" else "#ffffff"} !important;
        color: {main_text} !important;
        border: 1px solid {"rgba(255,255,255,0.35)" if theme == "Dark" else "rgba(0,0,0,0.25)"} !important;
        border-radius: 5px;
    }}
    .sm-filter-bar input:focus,
    .sm-filter-bar select:focus {{
        outline: 2px solid #4da6ff !important;
    }}

    /* KPI tile cards */
    .sm-kpi-tile {{
        background-color: {"rgba(255,255,255,0.10)" if theme == "Dark" else "rgba(255,255,255,0.95)"};
        border: 1px solid {"rgba(255,255,255,0.22)" if theme == "Dark" else "rgba(0,0,0,0.12)"};
        border-radius: 8px;
        padding: 0.65rem 1rem;
        text-align: center;
    }}
    .sm-kpi-tile .kpi-value {{
        font-size: 1.6rem;
        font-weight: 700;
        color: {main_text} !important;
    }}
    .sm-kpi-tile .kpi-label {{
        font-size: 0.78rem;
        opacity: 0.78;
        color: {main_text} !important;
    }}

    /* Table header and zebra rows */
    .sm-table-wrap .dataframe thead th {{
        background-color: {"rgba(60,80,120,0.85)" if theme == "Dark" else "rgba(220,230,245,0.95)"} !important;
        color: {main_text} !important;
        font-weight: 700;
        border-bottom: 2px solid {"rgba(255,255,255,0.3)" if theme == "Dark" else "rgba(0,0,0,0.2)"};
    }}
    .sm-table-wrap .dataframe tbody tr:nth-child(even) td {{
        background-color: {"rgba(255,255,255,0.05)" if theme == "Dark" else "rgba(245,247,252,0.85)"} !important;
    }}
    .sm-table-wrap .dataframe tbody tr:hover td {{
        background-color: {"rgba(255,255,255,0.12)" if theme == "Dark" else "rgba(210,220,240,0.7)"} !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(load_polished_theme(background_url), unsafe_allow_html=True)
render_sidebar_nav_css()
render_inventory_table_css()

# =========================
# HELPER FUNCTIONS
# =========================
def normalize_col(col: str) -> str:
    """Lower + strip non-alphanumerics for matching (no spaces, etc.)."""
    return re.sub(r"[^a-z0-9]", "", str(col).lower())


def detect_column(columns, aliases):
    """
    Auto-detect a column by comparing normalized names
    against a list of alias keys (already normalized).
    """
    norm_map = {normalize_col(c): c for c in columns}
    for alias in aliases:
        if alias in norm_map:
            return norm_map[alias]
    return None


def parse_currency_to_float(series: "pd.Series") -> "pd.Series":
    """
    Parse a pandas Series that may contain currency strings like ``"$45.00"``
    or ``"$1,234.56"`` into float values.

    - Strips leading ``$`` and embedded commas before calling ``pd.to_numeric``.
    - Non-parseable values (blanks, ``None``, other strings) become ``NaN``.
    """
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"^\$", "", regex=True)
        .str.replace(",", "", regex=False)
        .pipe(lambda s: pd.to_numeric(s, errors="coerce"))
    )


def normalize_rebelle_category(raw):
    """
    Map similar names to canonical categories.
    Case-insensitive with whitespace trimming.
    """
    if pd.isna(raw) or raw is None:
        return "unknown"
    
    s = str(raw).lower().strip()
    
    if not s:
        return "unknown"

    # Flower
    if any(k in s for k in ["flower", "bud", "buds", "cannabis flower"]):
        return "flower"

    # Pre Rolls
    if any(k in s for k in ["pre roll", "preroll", "pre-roll", "joint", "joints"]):
        return "pre rolls"

    # Vapes
    if any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"]):
        return "vapes"

    # Edibles
    if any(k in s for k in ["edible", "gummy", "gummies", "chocolate", "chew", "cookies"]):
        return "edibles"

    # Beverages
    if any(k in s for k in ["beverage", "drink", "drinkable", "shot", "beverages"]):
        return "beverages"

    # Concentrates
    if any(k in s for k in ["concentrate", "wax", "shatter", "crumble", "resin", "rosin", "dab", "rso"]):
        return "concentrates"

    # Tinctures
    if any(k in s for k in ["tincture", "tinctures", "drops", "sublingual", "dropper"]):
        return "tinctures"

    # Topicals
    if any(k in s for k in ["topical", "lotion", "cream", "salve", "balm"]):
        return "topicals"

    return s  # unchanged if not matched


def extract_size(text, context=None):
    """
    Parse package size:
    - mg doses: "500mg"
    - grams/oz: normalize 1oz/28g to "28g"
    - vapes: detect 0.5g if appears as ".5" etc
    Handles null values safely.
    """
    if pd.isna(text) or text is None:
        return "unspecified"
    
    s = str(text).lower().strip()
    
    if not s:
        return "unspecified"

    # mg
    mg = re.search(r"(\d+(\.\d+)?\s?mg)\b", s)
    if mg:
        return mg.group(1).replace(" ", "")

    # g / oz
    g = re.search(r"((?:\d+\.?\d*|\.\d+)\s?(g|oz))\b", s)
    if g:
        val = g.group(1).replace(" ", "").lower()
        if val in ["1oz", "1.0oz", "28g", "28.0g"]:
            return "28g"
        return val

    # vapes .5
    if any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"]):
        half = re.search(r"\b0\.5\b|\b\.5\b", s)
        if half:
            return "0.5g"

    return "unspecified"


def _stack_parts(*parts):
    parts_clean = [p.strip() for p in parts if p and str(p).strip() and str(p).strip() != "unspecified"]
    if not parts_clean:
        return "unspecified"
    return " ".join(parts_clean)


def extract_strain_type(name, subcat):
    """
    Stacked strain/type logic:
    - Base: indica / sativa / hybrid / cbd / unspecified
    - Flower: add Shake/Popcorn/Small Buds/Super Shake (stacked)
    - Flower: Rise/Refresh/Rest mapping (rise=sativa, refresh=hybrid, rest=indica) stacked
    - Vapes: detect oil type (distillate, live resin / LLR, cured resin, rosin) stacked with base
    - Edibles: detect form (gummy, chocolate) stacked with base
    - Concentrates: detect RSO stacked with base
    - Pre-rolls: infused
    - Disposables: disposable (vapes)
    Handles null values safely.
    """
    if pd.isna(name):
        name = ""
    if pd.isna(subcat):
        subcat = ""
    
    s = str(name).lower().strip()
    cat = str(subcat).lower().strip()

    base = "unspecified"
    if "indica" in s:
        base = "indica"
    elif "sativa" in s:
        base = "sativa"
    elif "hybrid" in s:
        base = "hybrid"
    elif "cbd" in s:
        base = "cbd"

    # Rise/Refresh/Rest mapping for flower (only if base not already explicit)
    rr_tag = None
    if "flower" in cat:
        if re.search(r"\brise\b", s):
            rr_tag = "rise"
            if base == "unspecified":
                base = "sativa"
        elif re.search(r"\brefresh\b", s):
            rr_tag = "refresh"
            if base == "unspecified":
                base = "hybrid"
        elif re.search(r"\brest\b", s):
            rr_tag = "rest"
            if base == "unspecified":
                base = "indica"

    vape_flag = ("vape" in cat) or any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"])
    preroll_flag = ("pre roll" in cat) or ("pre rolls" in cat) or any(k in s for k in ["pre roll", "preroll", "pre-roll", "joint"])

    # Flower: special buckets stacked
    flower_bucket = None
    if "flower" in cat:
        if "super shake" in s:
            flower_bucket = "super shake"
        elif re.search(r"\bshake\b", s):
            flower_bucket = "shake"
        elif any(k in s for k in ["small buds", "smalls", "small bud"]):
            flower_bucket = "small buds"
        elif "popcorn" in s:
            flower_bucket = "popcorn"

    # Vapes: oil type detection
    oil = None
    if vape_flag:
        if any(k in s for k in ["liquid live resin", "live resin", "llr"]):
            oil = "live resin"
        elif "cured resin" in s:
            oil = "cured resin"
        elif "rosin" in s:
            oil = "rosin"
        elif any(k in s for k in ["distillate", "disty"]):
            oil = "distillate"

    # Disposable handling
    is_disposable = ("disposable" in s) or ("dispos" in s)
    if vape_flag and is_disposable:
        oil = _stack_parts(oil, "disposable")

    # Pre-roll infused
    infused = None
    if preroll_flag and "infused" in s:
        infused = "infused"

    # Edibles: form detection
    edible_form = None
    if "edible" in cat:
        if any(k in s for k in ["gummy", "gummies", "chew", "fruit chew"]):
            edible_form = "gummy"
        elif any(k in s for k in ["chocolate", "choc"]):
            edible_form = "chocolate"

    # Concentrates: RSO
    conc_tag = None
    if "concentrate" in cat and ("rso" in s or "rick simpson" in s):
        conc_tag = "rso"

    # Free strain database lookup for flower and pre-rolls when base is unspecified
    if base == "unspecified" and ("flower" in cat or preroll_flag):
        # Check if strain lookup is enabled in settings
        try:
            if st.session_state.strain_lookup_enabled:
                # Use free database to determine the strain type from the product name
                lookup_result = free_strain_lookup(name, subcat)
                if lookup_result != "unspecified":
                    base = lookup_result
        except AttributeError:
            # Session state not available yet (app initialization), skip lookup
            pass
        except Exception as e:
            # Unexpected error in strain lookup - log but don't fail
            # This ensures product processing continues even if lookup has a bug
            import sys
            print(f"Warning: Strain lookup error for '{name}': {type(e).__name__}", file=sys.stderr)

    # Compose stacked type
    if "flower" in cat:
        return _stack_parts(base, flower_bucket, rr_tag)

    if vape_flag:
        return _stack_parts(base, oil)

    if "edible" in cat:
        return _stack_parts(base, edible_form)

    if "concentrate" in cat:
        return _stack_parts(base, conc_tag)

    if preroll_flag:
        return _stack_parts(base, infused)

    return base


def _normalize_for_match(text: str) -> str:
    """Lowercase, strip, collapse whitespace, remove punctuation for PO cross-reference matching."""
    s = re.sub(r"[^\w\s]", "", str(text).lower())
    return re.sub(r"\s+", " ", s).strip()


def _normalize_size_for_match(size: str) -> str:
    """Normalize size string for matching: lowercase and remove all internal spaces (e.g. '3.5 g' -> '3.5g')."""
    return re.sub(r"\s+", "", str(size).lower().strip())


def _build_inv_xref_table():
    """
    Build a cross-reference table from st.session_state.inv_raw_df using the same
    normalization/parsing as the Inventory Dashboard.

    Returns a DataFrame with columns:
        product_name, packagesize, norm_name, norm_size, onhand_total
    or None if inventory is unavailable / cannot be parsed.
    """
    raw = st.session_state.get("inv_raw_df")
    if raw is None or (hasattr(raw, "empty") and raw.empty):
        return None
    try:
        inv = raw.copy()
        inv.columns = inv.columns.astype(str).str.strip().str.lower()

        name_col = detect_column(inv.columns, [normalize_col(a) for a in INV_NAME_ALIASES])
        cat_col = detect_column(inv.columns, [normalize_col(a) for a in INV_CAT_ALIASES])
        qty_col = detect_column(inv.columns, [normalize_col(a) for a in INV_QTY_ALIASES])
        batch_col = detect_column(inv.columns, [normalize_col(a) for a in INV_BATCH_ALIASES])

        if not (name_col and qty_col):
            return None

        rename_map = {qty_col: "onhandunits", name_col: "itemname"}
        if cat_col:
            rename_map[cat_col] = "subcategory"
        if batch_col:
            rename_map[batch_col] = "batch"
        inv = inv.rename(columns=rename_map)

        if "subcategory" not in inv.columns:
            inv["subcategory"] = ""

        inv["itemname"] = inv["itemname"].astype(str).str.strip()
        inv["onhandunits"] = pd.to_numeric(inv["onhandunits"], errors="coerce").fillna(0)

        if "batch" in inv.columns:
            inv, _, _ = deduplicate_inventory(inv)

        inv["product_name"] = inv["itemname"]
        inv["packagesize"] = inv.apply(
            lambda x: extract_size(x.get("itemname", ""), x.get("subcategory", "")), axis=1
        )

        # Sum across all batches at (product_name, packagesize)
        agg = (
            inv.groupby(["product_name", "packagesize"], dropna=False)["onhandunits"]
            .sum()
            .reset_index()
            .rename(columns={"onhandunits": "onhand_total"})
        )
        agg["norm_name"] = agg["product_name"].apply(_normalize_for_match)
        agg["norm_size"] = agg["packagesize"].apply(_normalize_size_for_match)
        return agg
    except Exception:
        return None


def read_inventory_file(uploaded_file):
    """
    Read inventory CSV or Excel while being robust to 3–10 line headers
    (e.g., Dutchie exports with Export Date / filters at the top).
    """
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)

    if name.endswith(".csv"):
        tmp = pd.read_csv(uploaded_file, header=None)
    else:
        tmp = pd.read_excel(uploaded_file, header=None)

    header_row = 0
    max_scan = min(15, len(tmp))
    for i in range(max_scan):
        row_text = " ".join(str(v) for v in tmp.iloc[i].tolist()).lower()
        if any(tok in row_text for tok in ["product", "item", "sku", "name", "available"]):
            header_row = i
            break

    uploaded_file.seek(0)
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file, header=header_row)
    else:
        df = pd.read_excel(uploaded_file, header=header_row)

    return df


def filter_vault_inventory(df):
    """
    Filter inventory DataFrame to only include rows where Room == "Vault"
    (case-insensitive).

    Args:
        df: Raw inventory DataFrame (column names not yet normalized).

    Returns:
        tuple: (filtered_df, n_included, n_excluded)
            filtered_df  – DataFrame containing only Vault rows.
            n_included   – Number of rows kept (Vault).
            n_excluded   – Number of rows dropped (non-Vault).

    Raises:
        ValueError: If the Room column is not present in the file.
    """
    norm_cols = {str(c).strip().lower(): c for c in df.columns}
    room_col = norm_cols.get("room")

    if room_col is None:
        raise ValueError(
            "The inventory file is missing a 'Room' column. "
            "Please upload the correct inventory report that includes a 'Room' column "
            "(expected values: Vault, Quarantine, Employee Stock, …). "
            "Only Vault rows are used by this dashboard."
        )

    room_norm = df[room_col].apply(lambda v: str(v).strip().lower())
    mask = room_norm == "vault"
    n_included = int(mask.sum())
    n_excluded = int((~mask).sum())
    return df[mask].copy(), n_included, n_excluded


def deduplicate_inventory(inv_df):
    """
    Consolidate inventory by Product Name + Batch ID.
    Groups duplicate entries and SUMS quantities (not max).
    
    Args:
        inv_df: DataFrame with columns: itemname, batch (optional), onhandunits, etc.
        
    Returns:
        tuple: (deduplicated_df, num_duplicates_removed, log_message)
    """
    if inv_df is None or inv_df.empty:
        return inv_df, 0, "No inventory data to deduplicate."
    
    original_count = len(inv_df)
    
    try:
        # Clean and normalize batch column if it exists
        if "batch" in inv_df.columns:
            # Handle NaN values before converting to string
            inv_df["batch"] = inv_df["batch"].fillna("")
            # Trim whitespace and normalize batch IDs
            inv_df["batch"] = inv_df["batch"].astype(str).str.strip()
            # Replace empty strings and common invalid string representations with NaN
            inv_df["batch"] = inv_df["batch"].replace({
                "": np.nan, 
                "nan": np.nan, 
                "NaN": np.nan,
                "NAN": np.nan,
                "none": np.nan, 
                "None": np.nan,
                "NONE": np.nan,
                "<NA>": np.nan,
            })
            
            has_batch = inv_df["batch"].notna()
            
            if has_batch.any():
                # Separate records with and without batch IDs
                inv_with = inv_df[has_batch].copy()
                inv_without = inv_df[~has_batch].copy()
                
                # Determine deduplication keys
                # Use itemname + batch for products with batch IDs
                dedupe_keys = ["itemname", "batch"]
                
                # Build aggregation map - SUM quantities, keep first of other columns
                agg_map = {"onhandunits": "sum"}  # CRITICAL FIX: Changed from "max" to "sum"
                
                # Preserve other columns
                for c in ["subcategory", "sku"]:
                    if c in inv_with.columns and c not in dedupe_keys:
                        agg_map[c] = "first"
                
                # Group and aggregate
                inv_with_deduped = (
                    inv_with.groupby(dedupe_keys, dropna=False, as_index=False)
                    .agg(agg_map)
                )
                
                # Combine deduplicated records with non-batch records
                inv_df = pd.concat([inv_with_deduped, inv_without], ignore_index=True)
                
                deduplicated_count = len(inv_df)
                num_removed = original_count - deduplicated_count
                
                if num_removed > 0:
                    log_msg = (
                        f"✅ Deduplication complete: Consolidated {num_removed} duplicate "
                        f"inventory entries (Product Name + Batch ID). "
                        f"Original: {original_count} rows → Deduplicated: {deduplicated_count} rows"
                    )
                else:
                    log_msg = "No duplicate inventory entries found."
                    
                return inv_df, num_removed, log_msg
        
        # No batch column or no batch data
        return inv_df, 0, "No batch data available for deduplication."
        
    except Exception as e:
        # If deduplication fails, return original data with error message
        error_msg = f"⚠️ Deduplication encountered an error: {str(e)}. Using original data."
        return inv_df, 0, error_msg


def read_sales_file(uploaded_file):
    """
    Read sales report (CSV or Excel) with smart header detection.
    Supports:
    - CSV files with metadata rows (Export Date, From Date, To Date, Location)
    - Excel files with or without metadata rows
    Looks for a row that contains something like 'category' and 'product'
    (Dutchie 'Product Sales Report' style).
    
    Args:
        uploaded_file: File-like object with .name attribute and standard read methods
    
    Returns:
        pd.DataFrame: Sales data with detected header row, or empty DataFrame if uploaded_file is None
    """
    if uploaded_file is None:
        return pd.DataFrame()
    
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)
    
    # Determine file type and read accordingly
    if name.endswith(".csv"):
        # For CSV, read without header first to detect metadata rows
        tmp = pd.read_csv(uploaded_file, header=None)
    elif name.endswith((".xlsx", ".xls")):
        # For Excel, use existing logic
        tmp = pd.read_excel(uploaded_file, header=None)
    else:
        # Unsupported format - try Excel as fallback for backward compatibility
        # (some Excel files might have non-standard extensions)
        try:
            tmp = pd.read_excel(uploaded_file, header=None)
        except (ValueError, FileNotFoundError, OSError, Exception) as e:
            # If Excel parsing fails, provide helpful error message
            raise ValueError(
                f"Unsupported file format or unable to read file: {name}. "
                "Please upload a CSV or Excel file (.csv, .xlsx, .xls). "
                f"Error: {str(e)}"
            )
    
    # Detect header row by looking for actual column names
    # Skip metadata rows that typically have format "Key:,Value,..."
    header_row = 0
    max_scan = min(20, len(tmp))
    
    for i in range(max_scan):
        row_values = tmp.iloc[i].tolist()
        row_text = " ".join(str(v) for v in row_values).lower()
        
        # Skip metadata rows (rows where first cell ends with colon)
        first_cell = row_values[0]
        if pd.notna(first_cell):
            first_cell_str = str(first_cell).strip()
            if first_cell_str.endswith(':'):
                continue
        
        # Look for header row containing 'category' and 'product' or 'name'
        if "category" in row_text and ("product" in row_text or "name" in row_text):
            header_row = i
            break
    
    # Re-read with the correct header row
    uploaded_file.seek(0)
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file, header=header_row)
    else:
        # Excel or fallback format
        df = pd.read_excel(uploaded_file, header=header_row)
    
    return df


def read_delivery_file(uploaded_file):
    """
    Read a delivery/receiving report.
    Supported: CSV/XLSX preferred. PDF is best-effort (may fail if the PDF is image-based).
    Expected fields (any names, auto-detected):
      - received date (or delivery date)
      - product name (or item)
      - quantity received
      - optional: category, batch/lot
    Returns a DataFrame (may be empty if parsing fails).
    """
    if uploaded_file is None:
        return pd.DataFrame()

    name = uploaded_file.name.lower()
    uploaded_file.seek(0)
    raw_bytes = uploaded_file.read()
    uploaded_file.seek(0)

    if name.endswith((".csv", ".xlsx", ".xls")):
        if _DELIVERY_IMPACT_AVAILABLE:
            _recv_dt, items_df, _debug = parse_manifest_csv_xlsx_bytes(
                raw_bytes, filename=uploaded_file.name
            )
            if not items_df.empty:
                return items_df
        # Fallback: naive read for files that don't match the manifest format.
        if name.endswith(".csv"):
            return pd.read_csv(BytesIO(raw_bytes))
        return pd.read_excel(BytesIO(raw_bytes))

    if name.endswith(".pdf"):
        return _extract_delivery_from_pdf(uploaded_file)

    return pd.DataFrame()


def _extract_delivery_from_pdf(uploaded_file):
    """
    Best-effort PDF parsing:
    - Tries pdfplumber tables first (works if the PDF has selectable text tables).
    - Falls back to PyPDF2 text extraction and simple row heuristics.
    """
    uploaded_file.seek(0)
    pdf_bytes = uploaded_file.read()
    uploaded_file.seek(0)

    # 1) pdfplumber table extraction
    try:
        import pdfplumber  # type: ignore
        rows = []
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for t in tables:
                    if not t or len(t) < 2:
                        continue
                    for r in t[1:]:
                        rows.append([str(x).strip() if x is not None else "" for x in r])
        if rows:
            return pd.DataFrame(rows)
    except Exception:
        pass

    # 2) PyPDF2 text extraction
    try:
        from PyPDF2 import PdfReader  # type: ignore
        reader = PdfReader(BytesIO(pdf_bytes))
        text = ""
        for p in reader.pages:
            try:
                text += (p.extract_text() or "") + "\n"
            except Exception:
                continue
        if not text.strip():
            return pd.DataFrame()

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        parsed = []
        for ln in lines:
            if re.search(r"\b\d{1,4}\b", ln) and len(ln.split()) >= 3:
                parsed.append([ln])
        return pd.DataFrame(parsed, columns=["raw"])
    except Exception:
        return pd.DataFrame()


def read_daily_sales_file(uploaded_file):
    """
    Read a daily sales report for spike analysis (recommended).
    Supported: CSV/XLSX.
    Expected fields (auto-detected):
      - date (sale date, day, business date)
      - category (optional but strongly recommended)
      - product name (optional if you want SKU-level)
      - units/qty sold
      - revenue/net sales (optional)
    """
    if uploaded_file is None:
        return pd.DataFrame()

    name = uploaded_file.name.lower()
    uploaded_file.seek(0)

    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file)

    if name.endswith((".xlsx", ".xls")):
        tmp = pd.read_excel(uploaded_file, header=None)
        header_row = 0
        max_scan = min(25, len(tmp))
        for i in range(max_scan):
            row_text = " ".join(str(v) for v in tmp.iloc[i].tolist()).lower()
            if any(tok in row_text for tok in ["date", "day", "business"]) and any(tok in row_text for tok in ["sales", "revenue", "qty", "quantity", "units", "product"]):
                header_row = i
                break
        uploaded_file.seek(0)
        return pd.read_excel(uploaded_file, header=header_row)

    return pd.DataFrame()


def _parse_grams_from_size(size_str):
    """
    Convert '3.5g' -> 3.5
            '1g' -> 1
            '28g' -> 28
            '1oz' -> 28
    Return float grams or None
    """
    s = str(size_str).lower().strip()
    if s == "28g":
        return 28.0
    if s in ("1oz", "1.0oz"):
        return 28.0
    m = re.match(r"^(\d+(\.\d+)?)g$", s)
    if m:
        return float(m.group(1))
    m2 = re.match(r"^(\d+(\.\d+)?)oz$", s)
    if m2:
        return float(m2.group(1)) * 28.0
    return None


def _parse_mg_from_size(size_str):
    """
    Convert '100mg' -> 100
    Return float mg or None
    """
    s = str(size_str).lower().strip()
    m = re.match(r"^(\d+(\.\d+)?)mg$", s)
    if m:
        return float(m.group(1))
    return None


def _file_signature(file_obj, uploader_username: str, file_role: str):
    """Cheap signature to prevent repeated upload logging on reruns."""
    try:
        name = getattr(file_obj, "name", "upload")
        file_obj.seek(0)
        b = file_obj.read()
        file_obj.seek(0)
        size = len(b)
        head = b[:2048]
        tail = b[-2048:] if size > 2048 else b
        return f"{uploader_username}|{file_role}|{name}|{size}|{hash(head)}|{hash(tail)}"
    except Exception:
        return None


def track_upload(uploaded_file, uploader_username: str, file_role: str):
    """
    Store uploaded file bytes in session_state so 'God' can view/download later.

    Purchasing-director fix:
    - Prevent duplicate log spam: only log a given file once per session.
    - Reject files exceeding MAX_UPLOAD_BYTES.
    """
    if uploaded_file is None:
        return

    sig = _file_signature(uploaded_file, uploader_username, file_role)
    if sig and sig in st.session_state._upload_sig_seen:
        return

    try:
        uploaded_file.seek(0)
        b = uploaded_file.read()
        uploaded_file.seek(0)
    except Exception:
        return

    if len(b) > MAX_UPLOAD_BYTES:
        st.error(
            f"❌ File '{getattr(uploaded_file, 'name', 'upload')}' exceeds the "
            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB size limit and was not stored."
        )
        return

    if sig:
        st.session_state._upload_sig_seen.add(sig)

    upload_id = f"{datetime.now().isoformat()}::{uploader_username}::{file_role}::{uploaded_file.name}"
    st.session_state.uploaded_files_store[upload_id] = {
        "name": uploaded_file.name,
        "bytes": b,
        "uploader": uploader_username,
        "role": file_role,
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    st.session_state.upload_log.append({
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "uploader": uploader_username,
        "role": file_role,
        "filename": uploaded_file.name,
        "upload_id": upload_id,
    })


# =========================
# PDF GENERATION FOR PO
# =========================
def generate_po_pdf(
    store_name,
    store_number,
    store_address,
    store_phone,
    store_contact,
    vendor_name,
    vendor_license,
    vendor_address,
    vendor_contact,
    po_number,
    po_date,
    terms,
    notes,
    po_df,
    subtotal,
    discount,
    tax_amount,
    shipping,
    total,
):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    left_margin = 0.7 * inch
    right_margin = width - 0.7 * inch
    top_margin = height - 0.75 * inch

    # Header Title
    y = top_margin
    c.setFont("Helvetica-Bold", 16)
    c.drawString(left_margin, y, f"{CLIENT_NAME} - Purchase Order")
    y -= 0.25 * inch

    # PO Number and Date
    c.setFont("Helvetica", 10)
    c.drawString(left_margin, y, f"PO Number: {po_number}")
    c.drawRightString(right_margin, y, f"Date: {po_date.strftime('%m/%d/%Y')}")
    y -= 0.35 * inch

    # Store (Ship-To) block
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left_margin, y, "Ship To:")
    c.setFont("Helvetica", 10)
    y -= 0.18 * inch
    c.drawString(left_margin, y, store_name or "")
    y -= 0.16 * inch
    if store_number:
        c.drawString(left_margin, y, f"Store #: {store_number}")
        y -= 0.16 * inch
    if store_address:
        c.drawString(left_margin, y, store_address)
        y -= 0.16 * inch
    if store_phone:
        c.drawString(left_margin, y, f"Phone: {store_phone}")
        y -= 0.16 * inch
    if store_contact:
        c.drawString(left_margin, y, f"Buyer: {store_contact}")
        y -= 0.2 * inch

    # Vendor block
    vend_y = top_margin - 0.35 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(width / 2, vend_y, "Vendor:")
    vend_y -= 0.18 * inch
    c.setFont("Helvetica", 10)
    if vendor_name:
        c.drawString(width / 2, vend_y, vendor_name)
        vend_y -= 0.16 * inch
    if vendor_license:
        c.drawString(width / 2, vend_y, f"License #: {vendor_license}")
        vend_y -= 0.16 * inch
    if vendor_address:
        c.drawString(width / 2, vend_y, vendor_address)
        vend_y -= 0.16 * inch
    if vendor_contact:
        c.drawString(width / 2, vend_y, f"Contact: {vendor_contact}")
        vend_y -= 0.2 * inch

    # Terms
    y = min(y, vend_y) - 0.15 * inch
    if terms:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left_margin, y, "Payment Terms:")
        c.setFont("Helvetica", 10)
        c.drawString(left_margin + 90, y, terms)
        y -= 0.25 * inch

    # Notes
    if notes:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left_margin, y, "Notes:")
        y -= 0.16 * inch
        c.setFont("Helvetica", 9)
        text_obj = c.beginText()
        text_obj.setTextOrigin(left_margin, y)
        text_obj.setLeading(12)
        for line in notes.splitlines():
            text_obj.textLine(line)
        c.drawText(text_obj)
        y = text_obj.getY() - 0.25 * inch

    # Table header
    c.setFont("Helvetica-Bold", 10)
    header_y = y
    if header_y < 2.5 * inch:
        c.showPage()
        width, height = letter
        left_margin = 0.7 * inch
        right_margin = width - 0.7 * inch
        header_y = height - 1 * inch
        c.setFont("Helvetica-Bold", 16)
        c.drawString(left_margin, header_y, f"{CLIENT_NAME} - Purchase Order")
        header_y -= 0.4 * inch
        c.setFont("Helvetica-Bold", 10)

    y = header_y
    col_x = {
        "line": left_margin,
        "sku": left_margin + 0.4 * inch,
        "desc": left_margin + 1.4 * inch,
        "strain": left_margin + 3.8 * inch,
        "size": left_margin + 4.6 * inch,
        "qty": left_margin + 5.2 * inch,
        "unit": left_margin + 6.0 * inch,
        "total": left_margin + 7.0 * inch,
    }

    c.drawString(col_x["line"], y, "Ln")
    c.drawString(col_x["sku"], y, "SKU")
    c.drawString(col_x["desc"], y, "Description")
    c.drawString(col_x["strain"], y, "Strain")
    c.drawString(col_x["size"], y, "Size")
    c.drawRightString(col_x["qty"] + 0.3 * inch, y, "Qty")
    c.drawRightString(col_x["unit"] + 0.7 * inch, y, "Unit Price")
    c.drawRightString(col_x["total"] + 0.8 * inch, y, "Line Total")
    y -= 0.2 * inch

    c.setLineWidth(0.5)
    c.line(left_margin, y, right_margin, y)
    y -= 0.18 * inch
    c.setFont("Helvetica", 9)

    # Table rows
    for idx, row in po_df.reset_index(drop=True).iterrows():
        if y < 1.2 * inch:
            c.showPage()
            width, height = letter
            left_margin = 0.7 * inch
            right_margin = width - 0.7 * inch
            y = height - 1 * inch
            c.setFont("Helvetica-Bold", 10)
            c.drawString(left_margin, y, "SKU Line Items (cont.)")
            y -= 0.25 * inch
            c.setFont("Helvetica-Bold", 10)
            c.drawString(col_x["line"], y, "Ln")
            c.drawString(col_x["sku"], y, "SKU")
            c.drawString(col_x["desc"], y, "Description")
            c.drawString(col_x["strain"], y, "Strain")
            c.drawString(col_x["size"], y, "Size")
            c.drawRightString(col_x["qty"] + 0.3 * inch, y, "Qty")
            c.drawRightString(col_x["unit"] + 0.7 * inch, y, "Unit Price")
            c.drawRightString(col_x["total"] + 0.8 * inch, y, "Line Total")
            y -= 0.2 * inch
            c.line(left_margin, y, right_margin, y)
            y -= 0.18 * inch
            c.setFont("Helvetica", 9)

        line_no = idx + 1
        c.drawString(col_x["line"], y, str(line_no))
        c.drawString(col_x["sku"], y, str(row.get("SKU", ""))[:10])
        c.drawString(col_x["desc"], y, str(row.get("Description", ""))[:30])
        c.drawString(col_x["strain"], y, str(row.get("Strain", ""))[:10])
        c.drawString(col_x["size"], y, str(row.get("Size", ""))[:8])
        c.drawRightString(col_x["qty"] + 0.3 * inch, y, f"{int(row.get('Qty', 0))}")
        c.drawRightString(col_x["unit"] + 0.7 * inch, y, f"${row.get('Unit Price', 0):,.2f}")
        c.drawRightString(col_x["total"] + 0.8 * inch, y, f"${row.get('Line Total', 0):,.2f}")
        y -= 0.18 * inch

    # Totals
    if y < 1.8 * inch:
        c.showPage()
        width, height = letter
        left_margin = 0.7 * inch
        right_margin = width - 0.7 * inch
        y = height - 1.5 * inch

    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(col_x["total"] + 0.8 * inch, y, f"Subtotal: ${subtotal:,.2f}")
    y -= 0.2 * inch
    if discount > 0:
        c.drawRightString(col_x["total"] + 0.8 * inch, y, f"Discount: -${discount:,.2f}")
        y -= 0.2 * inch
    if tax_amount > 0:
        c.drawRightString(col_x["total"] + 0.8 * inch, y, f"Tax: ${tax_amount:,.2f}")
        y -= 0.2 * inch
    if shipping > 0:
        c.drawRightString(col_x["total"] + 0.8 * inch, y, f"Shipping / Fees: ${shipping:,.2f}")
        y -= 0.2 * inch

    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(col_x["total"] + 0.8 * inch, y, f"TOTAL: ${total:,.2f}")

    c.showPage()
    c.save()
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


def _load_compliance_sources_from_df(df):
    """Convert a structured compliance dataframe into repository records."""
    from datetime import date

    required = [
        "state",
        "scope",
        "topic",
        "answer",
        "source_citation",
        "source_url",
        "last_updated",
        "review_status",
    ]

    cols = {str(c).strip().lower(): c for c in df.columns}
    missing = [c for c in required if c not in cols]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    repo = ComplianceRepository()
    for _, row in df.iterrows():
        raw_date = row[cols["last_updated"]]
        parsed_date = pd.to_datetime(raw_date, errors="coerce")
        if pd.isna(parsed_date):
            parsed_date = pd.Timestamp(date.today())
        repo.add(
            ComplianceSource(
                state=str(row[cols["state"]]).strip(),
                scope=str(row[cols["scope"]]).strip().lower(),
                topic=str(row[cols["topic"]]).strip(),
                answer=str(row[cols["answer"]]).strip(),
                source_citation=str(row[cols["source_citation"]]).strip(),
                source_url=str(row[cols["source_url"]]).strip(),
                last_updated=parsed_date.date(),
                review_status=str(row[cols["review_status"]]).strip(),
            )
        )

    return repo


def _audit_compliance_source_df(df):
    """Return admin validation results for a compliance source dataframe."""
    required = [
        "state",
        "scope",
        "topic",
        "answer",
        "source_citation",
        "source_url",
        "last_updated",
        "review_status",
    ]
    cols = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in required if c not in cols]

    report = {
        "missing_columns": missing,
        "row_count": int(len(df)),
        "duplicate_rows": 0,
        "blank_critical_rows": 0,
    }

    if not missing and not df.empty:
        local_df = df.copy()
        local_df.columns = cols

        dup_subset = ["state", "scope", "topic", "source_citation"]
        report["duplicate_rows"] = int(local_df.duplicated(subset=dup_subset, keep=False).sum())

        critical = local_df[["state", "scope", "topic", "answer", "source_citation", "source_url"]].copy()
        blank_mask = critical.applymap(lambda x: str(x).strip() == "" or str(x).strip().lower() == "nan").any(axis=1)
        report["blank_critical_rows"] = int(blank_mask.sum())

    return report


def _generate_grounded_compliance_response(repo, state, scope, topic, question):
    """Return a structured compliance answer grounded in source records."""
    matches = repo.query(state=state, scope=scope, topic=topic)
    base_answer = format_compliance_answer(matches)

    if not matches:
        return base_answer

    # Optional synthesis, still constrained by retrieved source rows.
    if OPENAI_AVAILABLE and ai_client is not None:
        context = "\n\n".join(
            [
                (
                    f"State: {m.state}\n"
                    f"Scope: {m.scope}\n"
                    f"Topic: {m.topic}\n"
                    f"Answer: {m.answer}\n"
                    f"Citation: {m.source_citation}\n"
                    f"URL: {m.source_url}\n"
                    f"Last Updated: {m.last_updated.isoformat()}\n"
                    f"Review: {m.review_status}"
                )
                for m in matches
            ]
        )
        prompt = f"""
Use only the provided source rows to answer the compliance question.
Do not invent regulations.

Question: {question}
State: {state}
Scope: {scope}
Topic: {topic}

Sources:
{context}

Output format:
- Short answer
- Bullet list of source-backed requirements
- Include citation tags exactly as written in source rows
- Include source URLs
- Include last updated date and review status
"""
        try:
            resp = _generate_ai_with_quota_fallback(
                system_prompt=(
                    "You are a cannabis compliance analyst. "
                    "Only answer from provided structured sources."
                ),
                user_prompt=prompt,
                max_tokens=700,
            )
            return f"{resp.text}\n\n---\n\nSource Records\n\n{base_answer}"
        except Exception:
            return base_answer

    return base_answer



# =========================
# SIMPLE AI INVENTORY CHECK
# =========================


def _generate_ai_with_quota_fallback(system_prompt, user_prompt, max_tokens=700):
    """Generate AI output and fallback to Ollama if OpenAI quota is exceeded."""
    global ai_client, ai_provider, OPENAI_AVAILABLE

    if not OPENAI_AVAILABLE or ai_client is None:
        raise RuntimeError("AI provider unavailable")

    try:
        return ai_client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "insufficient_quota" in msg or "error code: 429" in msg:
            try:
                fallback = build_provider("ollama", None)
                if fallback is not None:
                    ai_provider = fallback
                    ai_client = fallback
                    OPENAI_AVAILABLE = True
                    return ai_client.generate(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        max_tokens=max_tokens,
                    )
            except Exception:
                pass
            raise RuntimeError(
                "OpenAI quota exceeded (429 insufficient_quota). "
                "Switched to local fallback if available; otherwise configure Ollama "
                "or set AI_API_KEY with available quota."
            )

        # If local Ollama is selected but not running, try OpenAI as fallback.
        if "connection refused" in msg or "max retries exceeded" in msg:
            try:
                key, _ = _find_openai_key()
                fallback = build_provider("openai", key)
                if fallback is not None:
                    ai_provider = fallback
                    ai_client = fallback
                    OPENAI_AVAILABLE = True
                    return ai_client.generate(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        max_tokens=max_tokens,
                    )
            except Exception:
                pass
            raise RuntimeError(
                "Local Ollama is not reachable at localhost:11434. "
                "Start Ollama or switch provider to OpenAI in Main AI Copilot settings."
            )
        raise


def _build_copilot_context(app_mode, section):
    context_lines = [
        f"App mode: {app_mode}",
        f"Section: {section}",
        f"Date: {datetime.utcnow().date().isoformat()}",
    ]

    inv_df = st.session_state.get("inv_raw_df")
    sales_df = st.session_state.get("sales_raw_df")

    if isinstance(inv_df, pd.DataFrame):
        context_lines.append(f"Inventory rows loaded: {len(inv_df)}")
        context_lines.append(f"Inventory columns: {', '.join(list(inv_df.columns[:20]))}")
    if isinstance(sales_df, pd.DataFrame):
        context_lines.append(f"Sales rows loaded: {len(sales_df)}")
        context_lines.append(f"Sales columns: {', '.join(list(sales_df.columns[:20]))}")

    return "\n".join(context_lines)


def _compute_buyer_intelligence(inv_df_raw, sales_df_raw, lookback_days=60):
    """Compute buyer-focused demand and risk signals from uploaded data."""
    sales = sales_df_raw.copy()
    sales.columns = sales.columns.astype(str).str.lower()

    inv = None
    if isinstance(inv_df_raw, pd.DataFrame):
        inv = inv_df_raw.copy()
        inv.columns = inv.columns.astype(str).str.lower()

    sales_name_col = detect_column(sales.columns, [normalize_col(a) for a in SALES_NAME_ALIASES])
    sales_qty_col = detect_column(sales.columns, [normalize_col(a) for a in SALES_QTY_ALIASES])
    sales_cat_col = detect_column(sales.columns, [normalize_col(a) for a in SALES_CAT_ALIASES])
    sales_rev_col = detect_column(sales.columns, [normalize_col(a) for a in SALES_REV_ALIASES])

    if not (sales_name_col and sales_qty_col and sales_cat_col):
        raise ValueError("Could not detect required sales columns (name, quantity, category).")

    rename_map = {
        sales_name_col: "product_name",
        sales_qty_col: "units_sold",
        sales_cat_col: "category",
    }
    if sales_rev_col:
        rename_map[sales_rev_col] = "revenue"

    sales = sales.rename(columns=rename_map)
    sales["units_sold"] = pd.to_numeric(sales["units_sold"], errors="coerce").fillna(0)
    if "revenue" in sales.columns:
        sales["revenue"] = pd.to_numeric(sales["revenue"], errors="coerce").fillna(0)
    else:
        sales["revenue"] = 0.0

    by_product = (
        sales.groupby(["product_name", "category"], as_index=False)[["units_sold", "revenue"]]
        .sum()
        .sort_values("units_sold", ascending=False)
    )

    by_product["avg_daily_units"] = by_product["units_sold"] / max(int(lookback_days), 1)

    if inv is not None:
        inv_name_col = detect_column(inv.columns, [normalize_col(a) for a in INV_NAME_ALIASES])
        inv_qty_col = detect_column(inv.columns, [normalize_col(a) for a in INV_QTY_ALIASES])
        if inv_name_col and inv_qty_col:
            inv = inv.rename(columns={inv_name_col: "product_name", inv_qty_col: "on_hand_units"})
            inv["on_hand_units"] = pd.to_numeric(inv["on_hand_units"], errors="coerce").fillna(0)
            inv_rollup = inv.groupby("product_name", as_index=False)["on_hand_units"].sum()
            by_product = by_product.merge(inv_rollup, on="product_name", how="left")
            by_product["on_hand_units"] = by_product["on_hand_units"].fillna(0)
            by_product["days_of_cover"] = np.where(
                by_product["avg_daily_units"] > 0,
                by_product["on_hand_units"] / by_product["avg_daily_units"],
                np.nan,
            )
        else:
            by_product["on_hand_units"] = np.nan
            by_product["days_of_cover"] = np.nan
    else:
        by_product["on_hand_units"] = np.nan
        by_product["days_of_cover"] = np.nan

    by_product["risk_flag"] = np.where(
        by_product["days_of_cover"].notna() & (by_product["days_of_cover"] <= 14),
        "Reorder Risk",
        "Monitor",
    )

    by_category = (
        by_product.groupby("category", as_index=False)[["units_sold", "revenue"]]
        .sum()
        .sort_values("units_sold", ascending=False)
    )

    summary = {
        "total_units_sold": float(by_product["units_sold"].sum()),
        "total_revenue": float(by_product["revenue"].sum()),
        "at_risk_skus": int((by_product["risk_flag"] == "Reorder Risk").sum()),
        "tracked_skus": int(len(by_product)),
    }

    return summary, by_category, by_product


def _generate_buyer_brief_ai(summary, by_category, by_product, lookback_days):
    if not OPENAI_AVAILABLE or ai_client is None:
        return "AI buyer brief unavailable. Configure an AI provider in the Main AI Copilot panel."

    top_categories = by_category.head(8).to_dict(orient="records")
    top_risks = by_product[by_product["risk_flag"] == "Reorder Risk"].head(20).to_dict(orient="records")

    prompt = f"""
Create a concise weekly buyer brief for a cannabis retail team.

Lookback window: {lookback_days} days
Summary: {json.dumps(summary, indent=2)}
Top categories: {json.dumps(top_categories, indent=2)}
At-risk SKUs: {json.dumps(top_risks, indent=2)}

Output sections:
1) Executive summary (3 bullets)
2) Reorder now (top 5)
3) Overstock/monitor watchouts
4) Suggested buyer actions for next 7 days
"""
    try:
        resp = _generate_ai_with_quota_fallback(
            system_prompt="You are a senior cannabis retail inventory strategist.",
            user_prompt=prompt,
            max_tokens=700,
        )
        return resp.text
    except Exception as exc:
        return f"AI buyer brief failed: {exc}"


def _run_main_ai_copilot(question, app_mode, section):
    if not OPENAI_AVAILABLE or ai_client is None:
        return (
            "AI copilot is unavailable. Configure AI_API_KEY (or OPENAI_API_KEY) or local Ollama, "
            "then select a provider in AI Copilot settings."
        )

    context = _build_copilot_context(app_mode, section)
    prompt = f"""
You are the primary AI copilot for this private cannabis operations platform.
Help with buying intelligence, extraction support, and compliance workflow guidance.

Rules:
- Keep answers actionable and concise.
- Never invent regulations from memory.
- If compliance is asked, require structured source evidence and cite missing fields.
- Preserve current app workflows when suggesting operational changes.

Workspace context:
{context}

User question:
{question}
"""

    try:
        resp = _generate_ai_with_quota_fallback(
            system_prompt=(
                "You are the main cannabis operations copilot for this app. "
                "Ground recommendations in supplied context."
            ),
            user_prompt=prompt,
            max_tokens=700,
        )
        return resp.text
    except Exception as exc:
        return f"AI copilot failed: {exc}"


def render_main_ai_copilot(app_mode, section):
    with st.sidebar.expander("🧠 Main AI Copilot", expanded=False):
        st.caption("Use this assistant across buyer, compliance, and extraction workflows.")

        provider_choice = st.selectbox(
            "Provider",
            ["auto", "openai", "ollama"],
            index=["auto", "openai", "ollama"].index(st.session_state.get("preferred_ai_provider", "auto") if st.session_state.get("preferred_ai_provider", "auto") in ["auto", "openai", "ollama"] else "auto"),
            key="preferred_ai_provider_selector",
            help="auto tries OpenAI first (if key exists) then Ollama.",
        )

        if provider_choice == "auto":
            st.session_state["preferred_ai_provider"] = None
        else:
            st.session_state["preferred_ai_provider"] = provider_choice

        if st.button("Reconnect AI Provider", key="reconnect_ai_provider"):
            init_openai_client()

        st.write(f"Connected: {'Yes' if OPENAI_AVAILABLE else 'No'}")
        if ai_provider is not None:
            st.write(f"Provider: {getattr(ai_provider, 'provider_name', 'unknown')}")

        question = st.text_area(
            "Ask the AI copilot",
            value="What should I focus on next in this section?",
            key="main_ai_copilot_question",
            height=100,
        )
        if st.button("Run Copilot", key="run_main_ai_copilot"):
            answer = _run_main_ai_copilot(question, app_mode, section)
            st.markdown(answer)


def ai_inventory_check(detail_view, doh_threshold, data_source):
    """
    Send a small slice of the current table to the AI so it can
    comment on obvious issues: zero on-hand, crazy DOH, etc.
    """
    if not OPENAI_AVAILABLE or ai_client is None:
        return (
            "AI is not enabled. Add AI_API_KEY (or OPENAI_API_KEY) to Streamlit secrets "
            "to turn on the buyer-assist checks."
        )

    sample = detail_view.copy()
    if "reorderpriority" in sample.columns:
        sample = sample.sort_values(["reorderpriority", "daysonhand"], ascending=[True, True])
    sample = sample.head(80)

    cols = [
        c
        for c in [
            "mastercategory",
            "subcategory",
            "strain_type",
            "packagesize",
            "onhandunits",
            "unitssold",
            "avgunitsperday",
            "daysonhand",
            "reorderqty",
            "reorderpriority",
        ]
        if c in sample.columns
    ]
    sample_records = sample[cols].to_dict(orient="records")

    prompt = f"""
You are an expert cannabis retail buyer and inventory strategist.

You are looking at a slice of an inventory dashboard for a store using {data_source}.
Each row is a category/size/type combo with its sales and coverage.

Fields:
- mastercategory / subcategory
- strain_type (stacked; e.g. indica live resin, hybrid gummy, indica popcorn, etc.)
- packagesize (like 3.5g, 1g, 5mg, 28g, 500mg)
- onhandunits (current inventory units)
- unitssold (units sold in lookback window)
- avgunitsperday
- daysonhand
- reorderqty
- reorderpriority (1=ASAP, 2=Watch, 3=Comfortable, 4=Dead)

Target days on hand: {doh_threshold}

Data (JSON list of rows):
{json.dumps(sample_records, indent=2)}

Tasks:
1. Call out any rows that look obviously wrong or risky (0 onhand but strong sales, etc.)
2. Top 3 categories in danger + anything dead/overbought.
3. Keep it short, punchy, buyer-friendly.
"""

    try:
        response = _generate_ai_with_quota_fallback(
            system_prompt="You are a sharp, no-BS cannabis retail buyer coach.",
            user_prompt=prompt,
            max_tokens=600,
        )
        return response.text
    except Exception as e:
        return f"AI check failed: {e}"


# =========================
# INIT OPENAI + SHOW DEBUG (admin-only)
# =========================
init_openai_client()

# Debug panel is gated behind admin access to avoid exposing internals.
if st.session_state.get("is_admin", False):
    with st.sidebar.expander("🔍 AI Debug Info", expanded=False):
        key1 = False
        key2 = False
        where = None
        try:
            key, where = _find_openai_key()
            key1 = bool(key)
        except Exception:
            key1 = False
        key2 = bool(os.environ.get("AI_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip())
        st.write(f"Secrets has AI_API_KEY/OPENAI_API_KEY: {key1}")
        st.write(f"Env has AI_API_KEY/OPENAI_API_KEY: {key2}")
        st.write(f"Using key: {OPENAI_AVAILABLE}")
        if where:
            st.write(f"Found via: {where}")

    with st.sidebar.expander("🔐 Auth Debug Info", expanded=False):
        _auth_admins_section = False
        _auth_users_section = False
        try:
            _auth_admins_section = "auth" in st.secrets and "admins" in st.secrets["auth"]
            _auth_users_section = "auth" in st.secrets and "users" in st.secrets["auth"]
        except Exception:
            pass
        st.write(f"auth.admins section exists: {_auth_admins_section}")
        st.write(f"auth.users section exists: {_auth_users_section}")
        st.write(f"Admin usernames loaded: {len(ADMIN_USERS)}")
        st.write(f"Standard usernames loaded: {len(USER_USERS)}")
        st.write(f"bcrypt available: {BCRYPT_AVAILABLE}")
        if ADMIN_USERS:
            st.write(f"Admin keys: {', '.join(sorted(ADMIN_USERS.keys()))}")
        if USER_USERS:
            st.write(f"User keys: {', '.join(sorted(USER_USERS.keys()))}")
        for severity, msg in _validate_auth_config():
            if severity == "ok":
                st.success(msg)
            elif severity == "warn":
                st.warning(msg)
            else:
                st.error(msg)

# =========================
# STRAIN LOOKUP TOGGLE
# =========================
with st.sidebar.expander("🌿 Strain Lookup Settings", expanded=False):
    st.markdown("**Free Strain Database Lookup**")
    st.write("Uses a comprehensive database of cannabis strains to automatically classify products.")
    strain_enabled = st.checkbox(
        "Enable strain lookup for flower/pre-rolls",
        value=st.session_state.strain_lookup_enabled,
        help="When enabled, uses a free strain database to identify strain types for products that don't have explicit strain info in their names. Completely free, no API costs!"
    )
    if strain_enabled != st.session_state.strain_lookup_enabled:
        st.session_state.strain_lookup_enabled = strain_enabled
        # Clear the cache when toggling
        strain_lookup_cache.clear()
        st.success("Setting updated! Refresh your data to apply changes.")
    
    st.info(f"📊 Database contains {len(STRAIN_DATABASE)} strain entries")
    st.info(f"💾 Cache has {len(strain_lookup_cache)} lookups")

# =========================
# 🔐 THEME TOGGLE + ADMIN + TRIAL GATE
# =========================
st.sidebar.markdown("### 🎨 Theme")
theme_choice = st.sidebar.radio(
    "Mode",
    ["Dark", "Light"],
    index=0 if st.session_state.theme == "Dark" else 1,
)
if theme_choice != st.session_state.theme:
    st.session_state.theme = theme_choice
    _safe_rerun()

st.sidebar.markdown("### 👑 Admin Login")

if not st.session_state.is_admin:
    now = datetime.now()
    admin_locked = (
        st.session_state._admin_lockout_until is not None
        and now < st.session_state._admin_lockout_until
    )
    if admin_locked:
        remaining_s = int((st.session_state._admin_lockout_until - now).total_seconds())
        st.sidebar.error(
            f"⛔ Too many failed attempts. Try again in {remaining_s // 60}m {remaining_s % 60}s."
        )
    else:
        admin_user = st.sidebar.text_input("Username", key="admin_user_input")
        admin_pass = st.sidebar.text_input("Password", type="password", key="admin_pass_input")
        if st.sidebar.button("Login as Admin"):
            if admin_user in ADMIN_USERS and _check_password(admin_pass, ADMIN_USERS[admin_user]):
                st.session_state.is_admin = True
                st.session_state.admin_user = admin_user
                st.session_state._admin_fail_count = 0
                st.session_state._admin_lockout_until = None
                st.sidebar.success("✅ Admin mode enabled.")
            else:
                st.session_state._admin_fail_count += 1
                remaining_attempts = _LOCKOUT_MAX_ATTEMPTS - st.session_state._admin_fail_count
                if st.session_state._admin_fail_count >= _LOCKOUT_MAX_ATTEMPTS:
                    st.session_state._admin_lockout_until = datetime.now() + timedelta(minutes=_LOCKOUT_MINUTES)
                    st.sidebar.error(
                        f"⛔ Too many failed attempts. Login locked for {_LOCKOUT_MINUTES} minutes."
                    )
                else:
                    st.sidebar.error(
                        f"❌ Invalid admin credentials. {remaining_attempts} attempt(s) remaining."
                    )
else:
    st.sidebar.success(f"👑 Admin mode: {st.session_state.admin_user}")
    if st.sidebar.button("Logout Admin"):
        st.session_state.is_admin = False
        st.session_state.admin_user = None
        _safe_rerun()

# -------------------------
# 👤 STANDARD USER LOGIN (non-admin)
# -------------------------
st.sidebar.markdown("### 👤 User Login")

if (not st.session_state.is_admin) and (not st.session_state.user_authenticated):
    now = datetime.now()
    user_locked = (
        st.session_state._user_lockout_until is not None
        and now < st.session_state._user_lockout_until
    )
    if user_locked:
        remaining_s = int((st.session_state._user_lockout_until - now).total_seconds())
        st.sidebar.error(
            f"⛔ Too many failed attempts. Try again in {remaining_s // 60}m {remaining_s % 60}s."
        )
    else:
        u_user = st.sidebar.text_input("Username", key="user_user_input")
        u_pass = st.sidebar.text_input("Password", type="password", key="user_pass_input")
        if st.sidebar.button("Login", key="login_user_btn"):
            if u_user in USER_USERS and _check_password(u_pass, USER_USERS[u_user]):
                st.session_state.user_authenticated = True
                st.session_state.user_user = u_user
                st.session_state._user_fail_count = 0
                st.session_state._user_lockout_until = None
                st.sidebar.success("✅ User access enabled.")
            else:
                st.session_state._user_fail_count += 1
                remaining_attempts = _LOCKOUT_MAX_ATTEMPTS - st.session_state._user_fail_count
                if st.session_state._user_fail_count >= _LOCKOUT_MAX_ATTEMPTS:
                    st.session_state._user_lockout_until = datetime.now() + timedelta(minutes=_LOCKOUT_MINUTES)
                    st.sidebar.error(
                        f"⛔ Too many failed attempts. Login locked for {_LOCKOUT_MINUTES} minutes."
                    )
                else:
                    st.sidebar.error(
                        f"❌ Invalid user credentials. {remaining_attempts} attempt(s) remaining."
                    )
elif (not st.session_state.is_admin) and st.session_state.user_authenticated:
    st.sidebar.success(f"👤 User: {st.session_state.user_user}")
    if st.sidebar.button("Logout", key="logout_user_btn"):
        st.session_state.user_authenticated = False
        st.session_state.user_user = None
        _safe_rerun()

trial_now = datetime.now()

if (not st.session_state.is_admin) and (not st.session_state.user_authenticated):
    st.sidebar.markdown("### 🔐 Trial Access")

    if st.session_state.trial_start is None:
        trial_key_input = st.sidebar.text_input("Enter trial key", type="password", key="trial_key_input")
        if st.sidebar.button("Activate Trial", key="activate_trial"):
            if _check_trial_key(trial_key_input.strip()):
                st.session_state.trial_start = trial_now.isoformat()
                st.sidebar.success("✅ Trial activated. You have 24 hours of access.")
            else:
                st.sidebar.error("❌ Invalid trial key.")
        st.warning("This is a trial build. Enter a valid key to unlock the app.")
        st.stop()
    else:
        try:
            started_at = datetime.fromisoformat(st.session_state.trial_start)
        except Exception:
            st.session_state.trial_start = None
            _safe_rerun()

        elapsed = trial_now - started_at
        remaining = timedelta(hours=TRIAL_DURATION_HOURS) - elapsed

        if remaining.total_seconds() <= 0:
            st.sidebar.error("⛔ Trial expired. Please contact the vendor for full access.")
            st.error("The 24-hour trial has expired. Contact the vendor to purchase a full license.")
            st.stop()
        else:
            hours_left = int(remaining.total_seconds() // 3600)
            mins_left = int((remaining.total_seconds() % 3600) // 60)
            st.sidebar.info(f"⏰ Trial time remaining: {hours_left}h {mins_left}m")

# =========================
# RESTORE TODAY'S UPLOADS (cross-session persistence)
# Runs once per session, after authentication is confirmed.
# =========================
if not st.session_state._daily_restored:
    _restore_username = None
    if st.session_state.is_admin and st.session_state.admin_user:
        _restore_username = st.session_state.admin_user
    elif st.session_state.user_authenticated and st.session_state.user_user:
        _restore_username = st.session_state.user_user
    if _restore_username:
        _restored_any = _load_from_daily_store(_restore_username)
        st.session_state._daily_restored = True
        if _restored_any:
            st.session_state._daily_restore_msg = True

# =========================
# HEADER
# =========================
_display_user = (
    st.session_state.admin_user if st.session_state.get("is_admin")
    else st.session_state.get("user_user") or "Buyer"
)
render_topbar("Search SKUs, Vendors, Reports...", datetime.now().strftime("%b %d, %Y"))
render_section_header(
    "BUYER DASHBOARD",
    subtitle="Compliance and operations intelligence for buyer and extraction teams.",
)
if st.session_state.get("_daily_restore_msg"):
    st.info(
        "📂 Your uploads from earlier today have been restored automatically. "
        "You can re-upload files at any time to refresh them."
    )
    st.session_state._daily_restore_msg = False
if OPENAI_AVAILABLE:
    st.markdown("✅ AI buyer-assist is **ON** for this session.")
else:
    st.markdown("⚠️ AI buyer-assist is **OFF** (local Ollama not reachable).")
st.markdown("---")

with st.sidebar.expander("🔗 Local App Link", expanded=False):
    st.write(f"Local URL: {LOCAL_APP_URL}")
    st.markdown(f"[Open local app]({LOCAL_APP_URL})")

if not PLOTLY_AVAILABLE:
    st.warning(
        "⚠️ Plotly is not installed in this environment. Charts will be disabled.\n\n"
        "If using Streamlit Cloud, add `plotly` and `reportlab` to your `requirements.txt` file."
    )

# =========================
# GOD-ONLY: Upload viewer (requested)
# =========================
_UPLOAD_TTL_MINUTES = 60

if st.session_state.is_admin:
    # TTL purge: remove entries older than _UPLOAD_TTL_MINUTES on each run
    now_ts = datetime.now()
    expired_ids = []
    for uid, meta in list(st.session_state.uploaded_files_store.items()):
        try:
            entry_ts = datetime.strptime(meta["ts"], "%Y-%m-%d %H:%M:%S")
            if (now_ts - entry_ts).total_seconds() > _UPLOAD_TTL_MINUTES * 60:
                expired_ids.append(uid)
        except (KeyError, ValueError):
            pass
    for uid in expired_ids:
        st.session_state.uploaded_files_store.pop(uid, None)
    st.session_state.upload_log = [
        r for r in st.session_state.upload_log if r["upload_id"] not in expired_ids
    ]

    with st.sidebar.expander("🗂️ Upload Viewer (Admin)", expanded=False):
        st.warning(
            "⚠️ This panel displays sensitive user-uploaded data. "
            "Handle with care and do not share outside authorized personnel."
        )
        if st.button("🗑️ Clear all stored uploads", key="clear_upload_store"):
            st.session_state.upload_log = []
            st.session_state.uploaded_files_store = {}
            st.session_state._upload_sig_seen = set()
            st.success("All stored uploads cleared.")
        if len(st.session_state.upload_log) == 0:
            st.write("No uploads logged yet.")
        else:
            log_df = pd.DataFrame(st.session_state.upload_log)
            st.dataframe(log_df, use_container_width=True)
            st.markdown("#### Download an uploaded file")
            upload_ids = [r["upload_id"] for r in st.session_state.upload_log]
            selected = st.selectbox("Select upload", upload_ids)
            if selected and selected in st.session_state.uploaded_files_store:
                meta = st.session_state.uploaded_files_store[selected]
                st.write(f"Uploader: {meta['uploader']}")
                st.write(f"Role: {meta['role']}")
                st.write(f"File: {meta['name']}")
                st.download_button(
                    "⬇️ Download uploaded file",
                    data=meta["bytes"],
                    file_name=meta["name"],
                    mime="application/octet-stream",
                )



def kpi_card(label: str, value, help_text: str = ""):
    """Reusable compact KPI tile."""
    with st.container(border=True):
        st.caption(label)
        st.markdown(f"### {value}")
        if help_text:
            st.caption(help_text)

# ============================================================
# EXTRA MODULE – EXTRACTION COMMAND CENTER
# ============================================================
def _compute_extraction_alerts(run_df, job_df):
    """Compute operational extraction alerts for leadership and shift teams."""
    alerts = []
    if run_df is None or run_df.empty:
        return alerts

    if "yield_pct" in run_df.columns:
        low_yield = run_df[run_df["yield_pct"] < 12]
        if not low_yield.empty:
            alerts.append(f"Low yield runs: {len(low_yield)} below 12% yield.")

    if "qa_hold" in run_df.columns:
        qa_holds = int(run_df["qa_hold"].fillna(False).sum())
        if qa_holds > 0:
            alerts.append(f"QA holds active: {qa_holds} run(s).")

    if "coa_status" in run_df.columns:
        pending_or_failed = int(run_df["coa_status"].isin(["Pending", "Failed"]).sum())
        if pending_or_failed > 0:
            alerts.append(f"COA risk: {pending_or_failed} run(s) pending/failed.")

    if "margin_per_gram" in run_df.columns:
        negative_margin = int((pd.to_numeric(run_df["margin_per_gram"], errors="coerce").fillna(0) < 0).sum())
        if negative_margin > 0:
            alerts.append(f"Negative margin runs: {negative_margin}.")

    if "value_risk_flag" in run_df.columns:
        high_value_risk = int(run_df["value_risk_flag"].isin(["Critical", "Warning"]).sum())
        if high_value_risk > 0:
            alerts.append(f"Value risk flags: {high_value_risk} run(s) need review.")

    if job_df is not None and not job_df.empty and "sla_status" in job_df.columns:
        at_risk_jobs = int((job_df["sla_status"] == "At Risk").sum())
        if at_risk_jobs > 0:
            alerts.append(f"Toll jobs at SLA risk: {at_risk_jobs}.")

    return alerts


def _generate_extraction_ai_brief(
    run_df,
    job_df,
    alerts,
    inventory_context: dict[str, Any] | None = None,
    value_context: dict[str, Any] | None = None,
):
    if not OPENAI_AVAILABLE or ai_client is None:
        return "AI extraction brief unavailable. Configure provider in the Main AI Copilot panel."

    run_preview = run_df.head(50).to_dict(orient="records") if run_df is not None else []
    job_preview = job_df.head(50).to_dict(orient="records") if job_df is not None else []

    prompt = f"""
Create an extraction operations briefing for cannabis processing leadership.

Alerts: {json.dumps(alerts, indent=2)}
Runs sample: {json.dumps(run_preview, indent=2, default=str)}
Jobs sample: {json.dumps(job_preview, indent=2, default=str)}
Inventory context: {json.dumps(inventory_context or {}, indent=2, default=str)}
Value context: {json.dumps(value_context or {}, indent=2, default=str)}

Output sections:
1) Operational health summary
2) Highest-priority batch/job interventions
3) QA/COA actions
4) Throughput + margin recommendations for next 72 hours
"""

    try:
        resp = _generate_ai_with_quota_fallback(
            system_prompt=(
                "You are a cannabis extraction operations strategist. "
                "Provide practical, compliance-aware actions."
            ),
            user_prompt=prompt,
            max_tokens=750,
        )
        return resp.text
    except Exception as exc:
        return f"AI extraction brief failed: {exc}"


_ECC_INVENTORY_COLUMNS = [
    "received_date",
    "material_name",
    "material_type",
    "strain",
    "source_vendor",
    "batch_id_internal",
    "metrc_package_id",
    "input_category",
    "current_weight_g",
    "reserved_weight_g",
    "available_weight_g",
    "cost_per_g",
    "total_cost",
    "status",
    "storage_location",
    "intended_method",
    "notes",
]

_ECC_MATERIAL_TYPES = [
    "Fresh Frozen",
    "Cured Biomass",
    "Trim",
    "Hash",
    "Crude",
    "Distillate",
    "Ethanol",
    "Solvent",
    "Other",
]
_ECC_STATUS_VALUES = ["Available", "Reserved", "In Process", "Quarantine", "Depleted"]
_ECC_METHOD_VALUES = ["BHO", "CO2", "Rosin", "Ethanol", "Mixed / TBD"]
_ECC_METHOD_DEFAULT_YIELD = {"BHO": 15.0, "CO2": 12.0, "Rosin": 8.0, "Ethanol": 14.0}
# Centralized extraction output taxonomy used across run forms, process updates,
# valuation mapping, and chart grouping logic.
EXTRACTION_OUTPUT_OPTIONS: dict[str, list[str]] = {
    "solvent_based": [
        "BHO",
        "Live Resin",
        "Badder",
        "Budder",
        "Batter",
        "Shatter",
        "Crumble",
        "Sugar",
        "Sauce",
        "Terp Sauce",
        "Diamonds",
        "THCA Crystalline",
        "Diamonds in Sauce",
        "HTE",
        "HTFSE",
        "Distillate",
        "CO2 Oil",
        "RSO",
        "Bulk Oil",
    ],
    "solventless": [
        "Rosin",
        "Live Rosin",
        "Hash Rosin",
        "Bubble Hash",
        "Ice Water Hash",
        "Full Melt",
        "Dry Sift",
        "Pressed Hash",
        "Temple Ball",
        "Piatella",
    ],
    "filled_products": [
        "Vape Oil",
        "Vape Cart Fill",
        "Disposable Fill",
        "Infused Pre-Roll Input",
    ],
}
EXTRACTION_OUTPUT_FLAT_OPTIONS = [label for labels in EXTRACTION_OUTPUT_OPTIONS.values() for label in labels]
EXTRACTION_PRODUCT_TYPE_OPTIONS = EXTRACTION_OUTPUT_FLAT_OPTIONS + ["Other"]
EXTRACTION_DOWNSTREAM_OPTIONS = ["N/A"] + EXTRACTION_OUTPUT_FLAT_OPTIONS
EXTRACTION_OUTPUT_NORM_LOOKUP = {
    re.sub(r"[^a-z0-9]+", "_", v.strip().lower()).strip("_"): v
    for v in EXTRACTION_OUTPUT_FLAT_OPTIONS
}
EXTRACTION_OUTPUT_ALIAS_LOOKUP = {
    "diamonds_sauce": "Diamonds in Sauce",
    "diamonds_and_sauce": "Diamonds in Sauce",
    "ice_hash": "Ice Water Hash",
    "cart_fill": "Vape Cart Fill",
    "distillate_cart": "Vape Cart Fill",
    "distillate_disposable": "Disposable Fill",
    "disty_carts": "Vape Cart Fill",
    "disty_disposables": "Disposable Fill",
    "bulk_distillate": "Bulk Oil",
    "fresh_press": "Rosin",
    "rosin_jam": "Hash Rosin",
}
# Estimated default market assumptions (USD per finished gram) for internal KPI
# modeling only. These are not live market feeds.
# TODO: replace MARKET_PRICE_MAP with admin-configurable pricing or live pricing feed
MARKET_PRICE_MAP = {
    "BHO": 12,
    "Live Resin": 20,
    "Badder": 16,
    "Budder": 16,
    "Batter": 16,
    "Shatter": 11,
    "Crumble": 10,
    "Sugar": 14,
    "Sauce": 18,
    "Terp Sauce": 20,
    "Diamonds": 24,
    "THCA Crystalline": 22,
    "Diamonds in Sauce": 26,
    "HTE": 18,
    "HTFSE": 22,
    "Distillate": 9,
    "CO2 Oil": 10,
    "RSO": 8,
    "Bulk Oil": 10,
    "Rosin": 32,
    "Live Rosin": 38,
    "Hash Rosin": 42,
    "Bubble Hash": 18,
    "Ice Water Hash": 20,
    "Full Melt": 30,
    "Dry Sift": 14,
    "Pressed Hash": 12,
    "Temple Ball": 14,
    "Piatella": 36,
    "Vape Oil": 14,
    "Vape Cart Fill": 16,
    "Disposable Fill": 16,
    "Infused Pre-Roll Input": 7,
}
_ECC_METHOD_TO_OUTPUT_FALLBACK = {"BHO": "BHO", "CO2": "CO2 Oil", "Rosin": "Rosin", "Ethanol": "RSO"}
_ECC_FALLBACK_INPUT_COST_PER_G = 1.25
_ECC_FALLBACK_OPERATIONAL_COST_USD = 150.0
_ECC_LOW_MARGIN_PER_G_THRESHOLD = 2.0
_ECC_LOW_MARGIN_PCT_THRESHOLD = 10.0
_ECC_EXTREME_COST_TO_VALUE_WARNING_RATIO = 0.85
_ECC_SUSPICIOUS_MARGIN_PCT_THRESHOLD = 80.0
_ECC_DEFAULT_ALLOCATION_GRAMS = 50.0
_ECC_DRAFT_BATCH_PREFIX = "INV-DRAFT"

_ECC_TRACEABILITY_FIELDS: list[str] = [
    "source_inventory_batch_ids",
    "source_inventory_metrc_ids",
    "allocated_input_weight_g",
    "allocated_input_cost_total",
    "inventory_linked",
]
_ECC_VALUE_FIELDS: list[str] = [
    "input_cost_total",
    "operational_cost_total",
    "total_cost",
    "cost_per_gram",
    "market_price_per_gram",
    "estimated_value_usd",
    "margin_per_gram",
    "total_profit_usd",
    "margin_pct_est",
    "value_risk_flag",
    "unmapped_output_type",
    "output_mapping_warning",
    "normalized_output_type",
]
_ECC_MANUAL_VALUE_FIELDS: list[str] = [
    "manual_cost_per_gram",
    "manual_market_price_per_gram",
]


def _ecc_norm_price_key(value: Any) -> str:
    """Normalize label text into a lowercase key for MARKET_PRICE_MAP lookups."""
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def normalize_extraction_output_label(value: Any) -> str:
    """Normalize extraction output labels to a canonical centralized taxonomy label."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    key = _ecc_norm_price_key(raw)
    if key in {"n_a", "na", "none"}:
        return ""
    alias_match = EXTRACTION_OUTPUT_ALIAS_LOOKUP.get(key)
    if alias_match:
        return alias_match
    return EXTRACTION_OUTPUT_NORM_LOOKUP.get(key, raw)


def _ecc_parse_list_field(raw_value: Any) -> list[str]:
    """Parse list-like input from JSON/list/CSV-ish text into a deduplicated string list."""
    if raw_value is None or (isinstance(raw_value, float) and np.isnan(raw_value)):
        return []
    if isinstance(raw_value, (list, tuple, set)):
        values = [str(v).strip() for v in raw_value if str(v).strip()]
    else:
        text = str(raw_value).strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
            if isinstance(decoded, list):
                values = [str(v).strip() for v in decoded if str(v).strip()]
            else:
                values = [x.strip() for x in text.split(",") if x.strip()]
        except Exception:
            values = [x.strip() for x in text.replace("[", "").replace("]", "").split(",") if x.strip()]
    return list(dict.fromkeys(values))


def _ecc_serialize_list_field(values: list[str]) -> str:
    return json.dumps([str(v).strip() for v in values if str(v).strip()])


def _ecc_safe_div(numerator: Any, denominator: Any) -> float:
    """Safe division that returns 0.0 for invalid inputs or zero denominator."""
    try:
        num = float(numerator)
        den = float(denominator)
    except Exception:
        return 0.0
    return (num / den) if den else 0.0


def _ecc_get_market_price_per_gram(row: pd.Series) -> tuple[float, str, bool]:
    """Return market price by priority: downstream product → finished product type → product type → method."""
    candidates = [
        normalize_extraction_output_label(row.get("downstream_product", "")),
        normalize_extraction_output_label(row.get("finished_product_type", "")),
        normalize_extraction_output_label(row.get("product_type", "")),
    ]
    for label in candidates:
        if label in MARKET_PRICE_MAP:
            return float(MARKET_PRICE_MAP[label]), label, False

    method_norm = str(row.get("method", "")).strip()
    method_fallback = _ECC_METHOD_TO_OUTPUT_FALLBACK.get(method_norm, "")
    if method_fallback and method_fallback in MARKET_PRICE_MAP:
        return float(MARKET_PRICE_MAP[method_fallback]), method_fallback, True
    return 0.0, "unmapped_output_type", True


def _ecc_ensure_run_schema(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in _ECC_TRACEABILITY_FIELDS:
        if col not in out.columns:
            out[col] = False if col == "inventory_linked" else (0.0 if col.startswith("allocated_") else "[]")
    for col in _ECC_VALUE_FIELDS:
        if col not in out.columns:
            if col == "value_risk_flag":
                out[col] = "Neutral"
            elif col in ["output_mapping_warning", "normalized_output_type"]:
                out[col] = ""
            else:
                out[col] = False if col == "unmapped_output_type" else 0.0
    for col in _ECC_MANUAL_VALUE_FIELDS:
        if col not in out.columns:
            out[col] = 0.0
    out["inventory_linked"] = out["inventory_linked"].fillna(False).astype(bool)
    for numeric_col in [
        "allocated_input_weight_g",
        "allocated_input_cost_total",
        "input_cost_total",
        "operational_cost_total",
        "total_cost",
        "cost_per_gram",
        "market_price_per_gram",
        "estimated_value_usd",
        "margin_per_gram",
        "total_profit_usd",
        "margin_pct_est",
    ]:
        out[numeric_col] = pd.to_numeric(out[numeric_col], errors="coerce").fillna(0.0)
    for list_col in ["source_inventory_batch_ids", "source_inventory_metrc_ids"]:
        out[list_col] = out[list_col].fillna("[]").astype(str)
    out["value_risk_flag"] = out["value_risk_flag"].fillna("Neutral").astype(str)
    out["output_mapping_warning"] = out["output_mapping_warning"].fillna("").astype(str)
    out["normalized_output_type"] = out["normalized_output_type"].fillna("").astype(str)
    out["unmapped_output_type"] = out["unmapped_output_type"].fillna(False).astype(bool)
    for numeric_col in _ECC_MANUAL_VALUE_FIELDS:
        out[numeric_col] = pd.to_numeric(out[numeric_col], errors="coerce").fillna(0.0)
    if "finished_product_type" not in out.columns:
        out["finished_product_type"] = out.get("product_type", "Other")
    out["finished_product_type"] = out["finished_product_type"].fillna(out.get("product_type", "Other")).astype(str)
    return out


def _ecc_calculate_run_value_metrics(run_df: pd.DataFrame, inventory_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Compute run-level cost, market value, margin, and risk flags using inventory-linked cost basis when available."""
    if run_df is None:
        return pd.DataFrame()
    out = _ecc_ensure_run_schema(run_df.copy())
    for col in ["input_weight_g", "finished_output_g", "processing_fee_usd", "cogs_usd"]:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    inv = _ecc_finalize_inventory_frame(inventory_df.copy()) if inventory_df is not None else pd.DataFrame()
    inv_avg_cost_per_g = 0.0
    if not inv.empty:
        inv_cost_series = pd.to_numeric(inv.get("cost_per_g", 0), errors="coerce").replace(0, np.nan)
        inv_avg_cost_per_g = float(inv_cost_series.mean())
    fallback_input_cost_per_g = inv_avg_cost_per_g if inv_avg_cost_per_g > 0 else _ECC_FALLBACK_INPUT_COST_PER_G
    fallback_operational_cost = _ECC_FALLBACK_OPERATIONAL_COST_USD

    inv_batch_cost_map: dict[str, float] = {}
    inv_metrc_cost_map: dict[str, float] = {}
    if not inv.empty:
        for _, inv_row in inv.iterrows():
            _cost = float(pd.to_numeric(inv_row.get("cost_per_g", 0), errors="coerce") or 0.0)
            _batch = str(inv_row.get("batch_id_internal", "")).strip()
            _metrc = str(inv_row.get("metrc_package_id", "")).strip()
            if _batch and _cost > 0:
                inv_batch_cost_map[_batch] = _cost
            if _metrc and _cost > 0:
                inv_metrc_cost_map[_metrc] = _cost

    input_cost_vals: list[float] = []
    op_cost_vals: list[float] = []
    total_cost_vals: list[float] = []
    cost_per_g_vals: list[float] = []
    mkt_price_vals: list[float] = []
    est_val_vals: list[float] = []
    margin_per_g_vals: list[float] = []
    total_profit_vals: list[float] = []
    margin_pct_vals: list[float] = []
    value_risk_flags: list[str] = []
    unmapped_vals: list[bool] = []
    mapping_warning_vals: list[str] = []
    normalized_output_vals: list[str] = []

    for _, row in out.iterrows():
        finished_output_g = float(row.get("finished_output_g", 0.0) or 0.0)
        input_weight_g = float(row.get("allocated_input_weight_g", 0.0) or 0.0)
        if input_weight_g <= 0:
            input_weight_g = float(row.get("input_weight_g", 0.0) or 0.0)

        allocated_input_cost_total = float(row.get("allocated_input_cost_total", 0.0) or 0.0)
        if allocated_input_cost_total > 0:
            input_cost_total = allocated_input_cost_total
        else:
            linked_batch_ids = _ecc_parse_list_field(row.get("source_inventory_batch_ids", "[]"))
            linked_metrc_ids = _ecc_parse_list_field(row.get("source_inventory_metrc_ids", "[]"))
            matched_costs = [
                inv_batch_cost_map[x]
                for x in linked_batch_ids
                if x in inv_batch_cost_map
            ] + [
                inv_metrc_cost_map[x]
                for x in linked_metrc_ids
                if x in inv_metrc_cost_map
            ]
            run_cost_per_input_g = float(pd.to_numeric(row.get("cost_per_input_gram", np.nan), errors="coerce"))
            if matched_costs:
                cost_per_input_g = float(np.mean(matched_costs))
            elif pd.notna(run_cost_per_input_g) and run_cost_per_input_g > 0:
                cost_per_input_g = run_cost_per_input_g
            else:
                cost_per_input_g = fallback_input_cost_per_g
            input_cost_total = input_weight_g * cost_per_input_g

        processing_fee = float(row.get("processing_fee_usd", 0.0) or 0.0)
        labor_cost = float(pd.to_numeric(row.get("labor_cost_usd", 0.0), errors="coerce") or 0.0)
        overhead_cost = float(pd.to_numeric(row.get("overhead_cost_usd", 0.0), errors="coerce") or 0.0)
        operational_cost_total = processing_fee + labor_cost + overhead_cost
        if operational_cost_total <= 0:
            operational_cost_total = fallback_operational_cost

        total_cost = input_cost_total + operational_cost_total
        cost_per_gram = _ecc_safe_div(total_cost, finished_output_g)
        market_price_per_gram, normalized_output_type, is_unmapped_output = _ecc_get_market_price_per_gram(row)
        manual_cost_override = float(pd.to_numeric(row.get("manual_cost_per_gram", np.nan), errors="coerce") or 0.0)
        manual_market_price_override = float(pd.to_numeric(row.get("manual_market_price_per_gram", np.nan), errors="coerce") or 0.0)
        if manual_cost_override > 0:
            cost_per_gram = manual_cost_override
            total_cost = round(cost_per_gram * finished_output_g, 4)
        if manual_market_price_override > 0:
            market_price_per_gram = manual_market_price_override
        estimated_value_usd = finished_output_g * market_price_per_gram
        margin_per_gram = market_price_per_gram - cost_per_gram
        total_profit_usd = estimated_value_usd - total_cost
        margin_pct_est = _ecc_safe_div(total_profit_usd * 100.0, estimated_value_usd)

        # Value risk classification:
        # - Critical: negative margin/profit
        # - Warning: thin margin or high cost-to-value pressure
        # - Review: unusually high profitability, may indicate mapping/input anomaly
        flag = "Neutral"
        if margin_per_gram < 0 or total_profit_usd < 0:
            flag = "Critical"
        elif margin_per_gram < _ECC_LOW_MARGIN_PER_G_THRESHOLD or margin_pct_est < _ECC_LOW_MARGIN_PCT_THRESHOLD:
            flag = "Warning"
        elif cost_per_gram > market_price_per_gram * _ECC_EXTREME_COST_TO_VALUE_WARNING_RATIO:
            flag = "Warning"
        elif margin_pct_est > _ECC_SUSPICIOUS_MARGIN_PCT_THRESHOLD and finished_output_g > 0:
            flag = "Review"
        if is_unmapped_output and flag != "Critical":
            flag = "Warning"

        input_cost_vals.append(round(input_cost_total, 2))
        op_cost_vals.append(round(operational_cost_total, 2))
        total_cost_vals.append(round(total_cost, 2))
        cost_per_g_vals.append(round(cost_per_gram, 4))
        mkt_price_vals.append(round(market_price_per_gram, 4))
        est_val_vals.append(round(estimated_value_usd, 2))
        margin_per_g_vals.append(round(margin_per_gram, 4))
        total_profit_vals.append(round(total_profit_usd, 2))
        margin_pct_vals.append(round(margin_pct_est, 2))
        value_risk_flags.append(flag)
        unmapped_vals.append(bool(is_unmapped_output))
        mapping_warning_vals.append("⚠️ Unmapped Output Type" if is_unmapped_output else "")
        normalized_output_vals.append(normalized_output_type)

    out["input_cost_total"] = input_cost_vals
    out["operational_cost_total"] = op_cost_vals
    out["total_cost"] = total_cost_vals
    out["cost_per_gram"] = cost_per_g_vals
    out["market_price_per_gram"] = mkt_price_vals
    out["estimated_value_usd"] = est_val_vals
    out["margin_per_gram"] = margin_per_g_vals
    out["total_profit_usd"] = total_profit_vals
    out["margin_pct_est"] = margin_pct_vals
    out["value_risk_flag"] = value_risk_flags
    out["unmapped_output_type"] = unmapped_vals
    out["output_mapping_warning"] = mapping_warning_vals
    out["normalized_output_type"] = normalized_output_vals
    return out


def _ecc_load_uploaded_inventory_file(uploaded_file):
    raw = uploaded_file.getvalue()
    file_name = str(getattr(uploaded_file, "name", "")).lower()
    if file_name.endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(raw))
    return pd.read_csv(BytesIO(raw))


def _ecc_enforce_inventory_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    out = df.copy()
    for col in _ECC_INVENTORY_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan
    return out[_ECC_INVENTORY_COLUMNS]


def _ecc_normalize_extraction_inventory(raw_df: pd.DataFrame):
    alias_map = {
        "material_name": ["material_name", "product", "item", "material", "inventory item", "material name"],
        "material_type": ["material_type", "type", "material type", "category", "inventory category"],
        "current_weight_g": ["current_weight_g", "weight", "qty", "quantity", "grams", "g", "current weight", "on hand"],
        "reserved_weight_g": ["reserved_weight_g", "reserved", "allocated", "committed", "reserved grams"],
        "received_date": ["received_date", "received date", "intake date", "date in", "date received"],
        "source_vendor": ["source_vendor", "vendor", "supplier", "producer", "source"],
        "storage_location": ["storage_location", "room", "location", "storage", "vault"],
        "metrc_package_id": ["metrc_package_id", "package id", "metrc package", "metrc id"],
        "batch_id_internal": ["batch_id_internal", "batch id", "internal batch id", "batch"],
        "strain": ["strain"],
        "input_category": ["input_category", "input category"],
        "available_weight_g": ["available_weight_g", "available grams", "available weight", "available"],
        "cost_per_g": ["cost_per_g", "cost per g", "cost per gram"],
        "total_cost": ["total_cost", "total cost"],
        "status": ["status"],
        "intended_method": ["intended_method", "intended method", "method"],
        "notes": ["notes", "note"],
    }
    mapped = {}
    normalized = pd.DataFrame(index=raw_df.index)
    for target_col, aliases in alias_map.items():
        src_col = detect_column(raw_df.columns, [normalize_col(a) for a in aliases])
        if src_col:
            normalized[target_col] = raw_df[src_col]
            mapped[target_col] = src_col

    normalized = _ecc_enforce_inventory_schema(normalized)
    return normalized, len(mapped), mapped


def _ecc_finalize_inventory_frame(df: pd.DataFrame) -> pd.DataFrame:
    inv = _ecc_enforce_inventory_schema(df)
    for numeric_col in ["current_weight_g", "reserved_weight_g", "available_weight_g", "cost_per_g", "total_cost"]:
        inv[numeric_col] = pd.to_numeric(inv[numeric_col], errors="coerce")
    inv["current_weight_g"] = inv["current_weight_g"].fillna(0.0)
    inv["reserved_weight_g"] = inv["reserved_weight_g"].fillna(0.0)
    inv["available_weight_g"] = inv["available_weight_g"].fillna(inv["current_weight_g"] - inv["reserved_weight_g"])
    inv["cost_per_g"] = inv["cost_per_g"].fillna(0.0)
    inv["total_cost"] = inv["total_cost"].fillna(inv["current_weight_g"] * inv["cost_per_g"])

    inv["received_date"] = pd.to_datetime(inv["received_date"], errors="coerce").dt.normalize()
    for text_col in [
        "material_name",
        "material_type",
        "strain",
        "source_vendor",
        "batch_id_internal",
        "metrc_package_id",
        "input_category",
        "status",
        "storage_location",
        "intended_method",
        "notes",
    ]:
        inv[text_col] = inv[text_col].fillna("").astype(str).str.strip()

    material_lookup = {v.lower(): v for v in _ECC_MATERIAL_TYPES}
    status_lookup = {v.lower(): v for v in _ECC_STATUS_VALUES}
    method_lookup = {v.lower(): v for v in _ECC_METHOD_VALUES}
    inv["material_type"] = inv["material_type"].str.lower().map(material_lookup).fillna("Other")
    inv["status"] = inv["status"].str.lower().map(status_lookup).fillna("Available")
    inv["intended_method"] = inv["intended_method"].str.lower().map(method_lookup).fillna("Mixed / TBD")
    return inv


def _ecc_add_inventory_aging(inv_df: pd.DataFrame) -> pd.DataFrame:
    out = inv_df.copy()
    today = pd.Timestamp.today().normalize()
    age_days_raw = (today - pd.to_datetime(out["received_date"], errors="coerce")).dt.days
    out["future_received_date"] = age_days_raw < 0
    out["age_days"] = age_days_raw.fillna(0).clip(lower=0).astype(int)
    out["aging_flag"] = np.select(
        [
            out["age_days"] < 14,
            (out["age_days"] >= 14) & (out["age_days"] <= 29),
            (out["age_days"] >= 30) & (out["age_days"] <= 59),
            out["age_days"] >= 60,
        ],
        ["Fresh", "Aging", "Priority Run", "Stale"],
        default="Fresh",
    )
    return out


def _ecc_add_estimated_output(inv_df: pd.DataFrame, global_yield_pct: float = 12.0, use_method_defaults: bool = True):
    out = inv_df.copy()
    if use_method_defaults:
        out["yield_pct_assumed"] = out["intended_method"].map(_ECC_METHOD_DEFAULT_YIELD).fillna(global_yield_pct)
    else:
        out["yield_pct_assumed"] = float(global_yield_pct)
    out["estimated_output_g"] = out["available_weight_g"] * out["yield_pct_assumed"] / 100.0
    return out


def _ecc_append_inventory_rows(existing_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    merged = pd.concat([existing_df, new_df], ignore_index=True)
    # Treat rows as duplicates when they refer to the same lot identity/location tuple.
    dedupe_subset = ["received_date", "material_name", "batch_id_internal", "metrc_package_id", "storage_location"]
    dedupe_key_present = merged[dedupe_subset].fillna("").astype(str).apply(
        lambda row: any(v.strip() for v in row),
        axis=1,
    )
    deduped_with_keys = merged[dedupe_key_present].drop_duplicates(subset=dedupe_subset, keep="last")
    keep_without_keys = merged[~dedupe_key_present]
    return pd.concat([deduped_with_keys, keep_without_keys], ignore_index=True)


def _ecc_apply_default_if_empty(df: pd.DataFrame, column_name: str, default_value: str):
    df[column_name] = df[column_name].replace("", np.nan).fillna(default_value)
    return df


# ─── Mass-balance helpers ─────────────────────────────────────────────────────
_MB_EDITABLE_FIELDS: list[str] = [
    "extraction_output_g",
    "post_process_output_g",
    "distillation_output_g",
    "final_output_g",
]
_MB_COMPUTED_FIELDS: list[str] = [
    "extraction_loss_g",
    "post_process_loss_g",
    "distillation_loss_g",
    "final_loss_g",
    "extraction_yield_pct",
    "post_process_yield_pct",
    "distillation_yield_pct",
    "final_yield_pct",
    "post_process_stage_efficiency_pct",
    "distillation_efficiency_pct",
    "final_stage_efficiency_pct",
    "mass_balance_flag",
]
# Unusually high yield warning thresholds per method
_MB_HIGH_YIELD_THRESHOLDS: dict[str, float] = {
    "BHO": 40.0,
    "CO2": 35.0,
    "Rosin": 25.0,
    "Ethanol": 35.0,
}


def _ensure_mass_balance_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Add mass-balance columns with safe defaults when absent; back-fill from legacy fields."""
    df = df.copy()
    for col in _MB_EDITABLE_FIELDS:
        if col not in df.columns:
            df[col] = 0.0
    for col in _MB_COMPUTED_FIELDS:
        if col not in df.columns:
            df[col] = "OK" if col == "mass_balance_flag" else 0.0
    # Back-fill extraction_output_g from intermediate_output_g (only for rows still at zero)
    if "intermediate_output_g" in df.columns:
        mask = pd.to_numeric(df["extraction_output_g"], errors="coerce").fillna(0.0) == 0.0
        df.loc[mask, "extraction_output_g"] = pd.to_numeric(
            df.loc[mask, "intermediate_output_g"], errors="coerce"
        ).fillna(0.0)
    # Back-fill final_output_g from finished_output_g (only for rows still at zero)
    if "finished_output_g" in df.columns:
        mask = pd.to_numeric(df["final_output_g"], errors="coerce").fillna(0.0) == 0.0
        df.loc[mask, "final_output_g"] = pd.to_numeric(
            df.loc[mask, "finished_output_g"], errors="coerce"
        ).fillna(0.0)
    return df


def _compute_mass_balance(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute all derived mass-balance columns from editable stage weights."""
    df = _ensure_mass_balance_cols(df)
    for col in ["input_weight_g"] + _MB_EDITABLE_FIELDS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    inp = df["input_weight_g"].replace(0.0, float("nan"))
    ext = df["extraction_output_g"]
    pp = df["post_process_output_g"]
    dist = df["distillation_output_g"]
    final = df["final_output_g"]
    ext_nz = ext.replace(0.0, float("nan"))
    pp_nz = pp.replace(0.0, float("nan"))
    dist_nz = dist.replace(0.0, float("nan"))

    # Stage losses (zero when downstream stage is not used)
    df["extraction_loss_g"] = (inp - ext).clip(lower=0).fillna(0.0).round(3)
    df["post_process_loss_g"] = (ext - pp).where(pp > 0, other=0.0).clip(lower=0).fillna(0.0).round(3)
    df["distillation_loss_g"] = (pp - dist).where(dist > 0, other=0.0).clip(lower=0).fillna(0.0).round(3)
    # Final-stage loss: diff from last used upstream stage
    last_upstream = dist.where(dist > 0, pp.where(pp > 0, ext))
    df["final_loss_g"] = (last_upstream - final).clip(lower=0).fillna(0.0).round(3)

    # Yields vs raw input
    df["extraction_yield_pct"] = (ext / inp * 100).fillna(0.0).round(2)
    df["post_process_yield_pct"] = (pp / inp * 100).fillna(0.0).round(2)
    df["distillation_yield_pct"] = (dist / inp * 100).fillna(0.0).round(2)
    df["final_yield_pct"] = (final / inp * 100).fillna(0.0).round(2)

    # Stage-to-stage efficiencies
    df["post_process_stage_efficiency_pct"] = (pp / ext_nz * 100).fillna(0.0).round(2)
    df["distillation_efficiency_pct"] = (dist / pp_nz * 100).fillna(0.0).round(2)
    df["final_stage_efficiency_pct"] = (final / dist_nz * 100).fillna(0.0).round(2)

    # Backward-compat: overall extraction-to-finish efficiency (used by top-level KPIs)
    df["post_process_efficiency_pct"] = (final / ext_nz * 100).fillna(0.0).round(2)

    # Backward-compat: sync legacy fields so Executive Overview / Run Analytics still work
    existing_yield = df.get("yield_pct", pd.Series(0.0, index=df.index)).fillna(0.0)
    df["yield_pct"] = df["final_yield_pct"].where(df["final_yield_pct"] > 0, other=existing_yield)
    existing_finished = df.get("finished_output_g", pd.Series(0.0, index=df.index)).fillna(0.0)
    df["finished_output_g"] = final.where(final > 0, other=existing_finished)

    # Validation flags
    method_thresh = (
        df["method"].map(_MB_HIGH_YIELD_THRESHOLDS).fillna(40.0)
        if "method" in df.columns
        else pd.Series(40.0, index=df.index)
    )
    critical_mask = (
        ((ext > df["input_weight_g"]) & (df["input_weight_g"] > 0) & (ext > 0))
        | ((pp > ext) & (ext > 0) & (pp > 0))
        | ((dist > pp) & (pp > 0) & (dist > 0))
        | ((final > last_upstream) & (last_upstream > 0) & (final > 0))
    )
    warning_mask = (
        (df["final_yield_pct"] > method_thresh) & (df["input_weight_g"] > 0)
    ) & ~critical_mask

    df["mass_balance_flag"] = "OK"
    df.loc[warning_mask, "mass_balance_flag"] = "Warning"
    df.loc[critical_mask, "mass_balance_flag"] = "Critical"

    return df


# ──────────────────────────────────────────────────────────────────────────────


def render_extraction_command_center():

    if "ecc_run_log" not in st.session_state:
        st.session_state.ecc_run_log = pd.DataFrame(
            [
                {
                    "run_date": "2026-03-27",
                    "state": "MA",
                    "license_name": "Example Lab",
                    "client_name": "In House",
                    "batch_id_internal": "BHO-0001",
                    "metrc_package_id_input": "1A4060300000000000001111",
                    "metrc_package_id_output": "1A4060300000000000002222",
                    "metrc_manifest_or_transfer_id": "TR-001",
                    "method": "BHO",
                    "strain": "The 4th Kind",
                    "product_type": "Sugar",
                    "downstream_product": "N/A",
                    "process_stage": "Packaged",
                    "intake_complete": True,
                    "extraction_complete": True,
                    "post_process_complete": True,
                    "formulation_complete": True,
                    "filling_complete": True,
                    "packaging_complete": True,
                    "ready_for_transfer": True,
                    "input_material_type": "Fresh Frozen",
                    "input_weight_g": 2500.0,
                    "intermediate_output_g": 480.0,
                    "finished_output_g": 430.0,
                    "residual_loss_g": 50.0,
                    "yield_pct": 17.2,
                    "post_process_efficiency_pct": 89.6,
                    # Mass-balance stage fields (inline editable in Process Tracker)
                    "extraction_output_g": 480.0,
                    "extraction_loss_g": 2020.0,
                    "post_process_output_g": 430.0,
                    "post_process_loss_g": 50.0,
                    "distillation_output_g": 0.0,
                    "distillation_loss_g": 0.0,
                    "final_output_g": 430.0,
                    "final_loss_g": 0.0,
                    "extraction_yield_pct": 19.2,
                    "post_process_yield_pct": 17.2,
                    "distillation_yield_pct": 0.0,
                    "final_yield_pct": 17.2,
                    "post_process_stage_efficiency_pct": 89.58,
                    "distillation_efficiency_pct": 0.0,
                    "final_stage_efficiency_pct": 0.0,
                    "mass_balance_flag": "OK",
                    "operator": "Operator A",
                    "machine_line": "BHO-1",
                    "status": "Complete",
                    "toll_processing": False,
                    "processing_fee_usd": 0.0,
                    "est_revenue_usd": 3440.0,
                    "cogs_usd": 1200.0,
                    "source_inventory_batch_ids": "[]",
                    "source_inventory_metrc_ids": "[]",
                    "allocated_input_weight_g": 0.0,
                    "allocated_input_cost_total": 0.0,
                    "inventory_linked": False,
                    "input_cost_total": 0.0,
                    "operational_cost_total": 0.0,
                    "total_cost": 0.0,
                    "cost_per_gram": 0.0,
                    "market_price_per_gram": 0.0,
                    "estimated_value_usd": 0.0,
                    "margin_per_gram": 0.0,
                    "total_profit_usd": 0.0,
                    "margin_pct_est": 0.0,
                    "value_risk_flag": "Neutral",
                    "coa_status": "Passed",
                    "qa_hold": False,
                    "notes": "Sample seed record",
                }
            ]
        )

    if "ecc_client_jobs" not in st.session_state:
        st.session_state.ecc_client_jobs = pd.DataFrame(
            [
                {
                    "client_name": "North Shore Processing",
                    "state": "MA",
                    "license_or_registration": "LIC-001",
                    "metrc_transfer_id": "TR-001",
                    "material_received_date": "2026-03-25",
                    "promised_completion_date": "2026-03-30",
                    "method": "BHO",
                    "input_weight_g": 2500.0,
                    "expected_output_g": 450.0,
                    "actual_output_g": 430.0,
                    "sla_status": "On Track",
                    "invoice_status": "Draft",
                    "payment_status": "Pending",
                    "coa_status": "Passed",
                    "job_status": "Processing",
                }
            ]
        )
    if "ecc_inventory_log" not in st.session_state:
        st.session_state.ecc_inventory_log = pd.DataFrame(columns=_ECC_INVENTORY_COLUMNS)

    # Ensure mass-balance columns exist for older sessions that pre-date this feature
    st.session_state.ecc_run_log = _ensure_mass_balance_cols(st.session_state.ecc_run_log)
    st.session_state.ecc_run_log = _ecc_ensure_run_schema(st.session_state.ecc_run_log)

    render_section_header(
        "Extraction Command Center",
        subtitle="Built for BHO, CO2, Rosin, and Ethanol operations with toll processing and METRC-aware workflows.",
    )

    with st.sidebar:
        st.markdown("### 🧪 Extraction Controls")
        states = ["All", "MA", "ME", "NY", "NJ", "MI", "NV", "CA", "Other"]
        methods = ["All", "BHO", "CO2", "Rosin", "Ethanol"]

        selected_state = st.selectbox("State", states, index=0, key="ecc_selected_state")
        selected_method = st.selectbox("Extraction Method", methods, index=0, key="ecc_selected_method")
        toll_only = st.toggle("Show Toll Processing Only", value=False, key="ecc_toll_only")
        st.divider()

        st.markdown("#### METRC / Compliance")
        st.text_input(
            "Facility License Number",
            placeholder="Example: LIC123-OPERATIONS",
            key="ecc_facility_license_number",
        )
        st.text_input(
            "Primary METRC License Label",
            placeholder="Example: MA Processing License",
            key="ecc_metrc_license_label",
        )
        st.selectbox(
            "Seed-to-Sale Tracking",
            ["METRC", "BioTrack", "Other / Mixed"],
            key="ecc_seed_to_sale_tracking",
        )

    run_df = _compute_mass_balance(st.session_state.ecc_run_log.copy())
    job_df = st.session_state.ecc_client_jobs.copy()
    inventory_master_df = _ecc_add_inventory_aging(_ecc_finalize_inventory_frame(st.session_state.ecc_inventory_log.copy()))
    inventory_method_projection_df = _ecc_add_estimated_output(inventory_master_df, global_yield_pct=12.0, use_method_defaults=True)
    run_df = _ecc_calculate_run_value_metrics(run_df, inventory_master_df)

    if selected_state != "All":
        run_df = run_df[run_df["state"] == selected_state]
        job_df = job_df[job_df["state"] == selected_state]
    if selected_method != "All":
        run_df = run_df[run_df["method"] == selected_method]
        job_df = job_df[job_df["method"] == selected_method]
    if toll_only:
        run_df = run_df[run_df["toll_processing"]]

    total_runs = len(run_df)
    total_finished_output = float(run_df["finished_output_g"].sum()) if not run_df.empty else 0.0
    avg_yield = float(run_df["yield_pct"].mean()) if not run_df.empty else 0.0
    avg_post_eff = float(run_df["post_process_efficiency_pct"].mean()) if not run_df.empty else 0.0
    active_days = run_df["run_date"].nunique() if not run_df.empty else 0
    at_risk_batches = int(
        ((run_df["qa_hold"]) | (run_df["coa_status"].isin(["Failed", "Pending"]))).sum()
    ) if not run_df.empty else 0
    est_revenue = float(run_df["est_revenue_usd"].sum()) if not run_df.empty else 0.0
    cogs = float(run_df["cogs_usd"].sum()) if not run_df.empty else 0.0
    gross_margin_pct = ((est_revenue - cogs) / est_revenue * 100) if est_revenue else 0.0
    avg_cost_per_g = float(run_df["cost_per_gram"].replace(0, np.nan).mean(skipna=True) or 0.0) if not run_df.empty else 0.0
    avg_value_per_g = float(run_df["market_price_per_gram"].replace(0, np.nan).mean(skipna=True) or 0.0) if not run_df.empty else 0.0
    avg_margin_per_g = float(run_df["margin_per_gram"].mean(skipna=True) or 0.0) if not run_df.empty else 0.0
    total_est_profit = float(run_df["total_profit_usd"].sum()) if not run_df.empty else 0.0
    negative_margin_runs = int((run_df["margin_per_gram"] < 0).sum()) if not run_df.empty else 0
    low_margin_runs = int(
        ((run_df["margin_per_gram"] >= 0) & (run_df["margin_per_gram"] < _ECC_LOW_MARGIN_PER_G_THRESHOLD)).sum()
    ) if not run_df.empty else 0
    extreme_cost_runs = int(
        (run_df["cost_per_gram"] > run_df["market_price_per_gram"] * _ECC_EXTREME_COST_TO_VALUE_WARNING_RATIO).sum()
    ) if not run_df.empty else 0
    suspicious_profit_runs = int((run_df["margin_pct_est"] > _ECC_SUSPICIOUS_MARGIN_PCT_THRESHOLD).sum()) if not run_df.empty else 0

    render_extraction_kpi(
        [
            {"label": "Runs", "value": total_runs},
            {"label": "Output", "value": f"{total_finished_output:,.1f} g"},
            {"label": "Avg Yield", "value": f"{avg_yield:.1f}%"},
            {"label": "Efficiency", "value": f"{avg_post_eff:.1f}%"},
            {"label": "Risk", "value": "Low" if at_risk_batches == 0 else ("Medium" if at_risk_batches < 3 else "High")},
        ]
    )

    top = st.columns(8)
    with top[0]:
        kpi_card("Extraction Runs", total_runs)
    with top[1]:
        kpi_card("Finished Output (g)", f"{total_finished_output:,.1f}")
    with top[2]:
        kpi_card("Avg Yield %", f"{avg_yield:.1f}%")
    with top[3]:
        kpi_card("Post-Process Eff.", f"{avg_post_eff:.1f}%")
    with top[4]:
        kpi_card("Active Production Days", active_days)
    with top[5]:
        kpi_card("At-Risk Batches", at_risk_batches)
    with top[6]:
        kpi_card("Revenue", f"${est_revenue:,.0f}")
    with top[7]:
        kpi_card("Gross Margin", f"{gross_margin_pct:.1f}%")

    render_extraction_kpi(
        [
            {"label": "Avg Cost / g", "value": f"${avg_cost_per_g:,.2f}"},
            {"label": "Avg Value / g", "value": f"${avg_value_per_g:,.2f}"},
            {"label": "Avg Margin / g", "value": f"${avg_margin_per_g:,.2f}"},
            {"label": "Total Est. Profit", "value": f"${total_est_profit:,.0f}"},
        ]
    )

    overview_tab, runs_tab, process_tab, inv_tab, toll_tab, compliance_tab, inputs_tab, ai_ops_tab = st.tabs(
        [
            "Executive Overview",
            "Run Analytics",
            "Process Tracker",
            "Extraction Inventory",
            "Toll Processing",
            "Compliance / METRC",
            "Data Input",
            "AI Ops Brief",
        ]
    )

    with overview_tab:
        display_df = run_df.copy()
        display_df["run_date_parsed"] = pd.to_datetime(display_df.get("run_date"), errors="coerce")
        qa_hold_series = (
            display_df["qa_hold"].fillna(False).astype(bool)
            if "qa_hold" in display_df.columns
            else pd.Series(False, index=display_df.index)
        )
        coa_series = (
            display_df["coa_status"].fillna("Pending").astype(str)
            if "coa_status" in display_df.columns
            else pd.Series("Pending", index=display_df.index)
        )
        display_df["qa_risk_bucket"] = np.where(
            qa_hold_series,
            "QA Hold",
            coa_series,
        )
        downstream_series = (
            display_df["downstream_product"].fillna("").astype(str).map(normalize_extraction_output_label)
            if "downstream_product" in display_df.columns
            else pd.Series("", index=display_df.index)
        )
        finished_product_series = (
            display_df["finished_product_type"].fillna("").astype(str).map(normalize_extraction_output_label)
            if "finished_product_type" in display_df.columns
            else pd.Series("", index=display_df.index)
        )
        product_series = (
            display_df["product_type"].fillna("Other").astype(str).map(normalize_extraction_output_label)
            if "product_type" in display_df.columns
            else pd.Series("Other", index=display_df.index)
        )
        display_df["product_bucket"] = downstream_series
        display_df["product_bucket"] = np.where(
            display_df["product_bucket"].astype(str).str.strip().eq(""),
            finished_product_series,
            display_df["product_bucket"],
        )
        display_df["product_bucket"] = np.where(
            pd.Series(display_df["product_bucket"]).astype(str).str.strip().eq(""),
            product_series,
            display_df["product_bucket"],
        )

        row1_l, row1_r = st.columns(2)
        with row1_l:
            chart_card_start("Output by Method", "Finished extraction output grouped by method.")
            if display_df.empty:
                st.info("No run data available.")
            else:
                method_summary = (
                    display_df.groupby("method", as_index=False)["finished_output_g"]
                    .sum()
                    .sort_values("finished_output_g", ascending=False)
                )
                if PLOTLY_AVAILABLE:
                    fig = px.bar(
                        method_summary,
                        x="method",
                        y="finished_output_g",
                        color_discrete_sequence=["#f5a524"],
                    )
                    fig.update_layout(height=340, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.bar_chart(method_summary.set_index("method")["finished_output_g"])
            chart_card_end()
        with row1_r:
            chart_card_start("Yield Trend Over Time", "Run-level yield trend to spot process drift.")
            trend_df = display_df[display_df["run_date_parsed"].notna()].sort_values("run_date_parsed")
            if trend_df.empty:
                st.caption("No dated runs available for trend view.")
            elif PLOTLY_AVAILABLE:
                fig = px.line(
                    trend_df,
                    x="run_date_parsed",
                    y="yield_pct",
                    markers=True,
                    color_discrete_sequence=["#f5a524"],
                )
                fig.update_layout(height=340, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.line_chart(trend_df.set_index("run_date_parsed")["yield_pct"])
            chart_card_end()

        row2_l, row2_r = st.columns(2)
        with row2_l:
            chart_card_start("Revenue vs COGS Trend", "Financial trendline across run dates.")
            revenue_df = (
                display_df[display_df["run_date_parsed"].notna()]
                .assign(run_day=lambda d: d["run_date_parsed"].dt.date)
                .groupby("run_day", as_index=False)[["est_revenue_usd", "cogs_usd"]]
                .sum()
            )
            if revenue_df.empty:
                st.caption("No financial timeline data yet.")
            elif PLOTLY_AVAILABLE:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=revenue_df["run_day"], y=revenue_df["est_revenue_usd"], mode="lines+markers", name="Revenue", line=dict(color="#f5a524")))
                fig.add_trace(go.Scatter(x=revenue_df["run_day"], y=revenue_df["cogs_usd"], mode="lines+markers", name="COGS", line=dict(color="#ff6161")))
                fig.update_layout(height=340, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.line_chart(revenue_df.set_index("run_day")[["est_revenue_usd", "cogs_usd"]])
            chart_card_end()
        with row2_r:
            chart_card_start("Batch Status Breakdown", "Current run status distribution.")
            status_df = (
                display_df.groupby("status", as_index=False)["batch_id_internal"]
                .count()
                .rename(columns={"batch_id_internal": "count"})
                .sort_values("count", ascending=False)
            )
            if status_df.empty:
                st.caption("No status data.")
            elif PLOTLY_AVAILABLE:
                fig = px.pie(status_df, values="count", names="status")
                fig.update_layout(height=340, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.bar_chart(status_df.set_index("status")["count"])
            chart_card_end()

        row3_l, row3_r = st.columns(2)
        with row3_l:
            chart_card_start("COA / QA Risk Breakdown", "QA hold and COA outcome composition.")
            qa_df = (
                display_df.groupby("qa_risk_bucket", as_index=False)["batch_id_internal"]
                .count()
                .rename(columns={"batch_id_internal": "count"})
            )
            if qa_df.empty:
                st.caption("No QA/COA risk data.")
            elif PLOTLY_AVAILABLE:
                fig = px.bar(qa_df, x="qa_risk_bucket", y="count", color="qa_risk_bucket")
                fig.update_layout(height=340, template="plotly_dark", showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.bar_chart(qa_df.set_index("qa_risk_bucket")["count"])
            chart_card_end()
        with row3_r:
            chart_card_start("Output by Product Type", "Finished output grouped by product downstream path.")
            prod_df = (
                display_df.groupby("product_bucket", as_index=False)["finished_output_g"]
                .sum()
                .sort_values("finished_output_g", ascending=False)
            )
            if prod_df.empty:
                st.caption("No output product data.")
            elif PLOTLY_AVAILABLE:
                fig = px.bar(prod_df, x="product_bucket", y="finished_output_g", color_discrete_sequence=["#f5a524"])
                fig.update_layout(height=340, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.bar_chart(prod_df.set_index("product_bucket")["finished_output_g"])
            chart_card_end()

        row4_l, row4_r = st.columns(2)
        with row4_l:
            chart_card_start("Method Efficiency Comparison", "Average post-process efficiency by method.")
            eff_df = (
                display_df.groupby("method", as_index=False)["post_process_efficiency_pct"]
                .mean()
                .sort_values("post_process_efficiency_pct", ascending=False)
            )
            if eff_df.empty:
                st.caption("No efficiency data.")
            elif PLOTLY_AVAILABLE:
                fig = px.bar(eff_df, x="method", y="post_process_efficiency_pct", color_discrete_sequence=["#f5a524"])
                fig.update_layout(height=340, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.bar_chart(eff_df.set_index("method")["post_process_efficiency_pct"])
            chart_card_end()
        with row4_r:
            chart_card_start("Inventory Pressure Snapshot", "Available grams, aging pressure, and projected output by intended method.")
            if inventory_method_projection_df.empty:
                st.caption("No extraction inventory available.")
            else:
                inv_press = (
                    inventory_method_projection_df.groupby("intended_method", as_index=False)[["available_weight_g", "estimated_output_g"]]
                    .sum()
                    .sort_values("available_weight_g", ascending=False)
                )
                if PLOTLY_AVAILABLE:
                    fig = go.Figure()
                    fig.add_trace(go.Bar(x=inv_press["intended_method"], y=inv_press["available_weight_g"], name="Available g", marker_color="#5aa8ff"))
                    fig.add_trace(go.Bar(x=inv_press["intended_method"], y=inv_press["estimated_output_g"], name="Projected Output g", marker_color="#f5a524"))
                    fig.update_layout(
                        barmode="group",
                        height=300,
                        template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.bar_chart(inv_press.set_index("intended_method")[["available_weight_g", "estimated_output_g"]])
                st.caption(
                    f"Aging lots (30+ days): {int((inventory_method_projection_df['age_days'] >= 30).sum())} • "
                    f"Projected output: {float(inventory_method_projection_df['estimated_output_g'].sum()):,.1f} g"
                )
            chart_card_end()

        row5_l, row5_r = st.columns(2)
        with row5_l:
            chart_card_start("Top At-Risk Batches", "Operational, QA, and value-risk prioritized runs.")
            at_risk_df = display_df.copy()
            qa_hold_flag = at_risk_df.get("qa_hold", pd.Series(False, index=at_risk_df.index)).fillna(False).astype(bool).astype(int)
            coa_status_flag = at_risk_df.get("coa_status", pd.Series("", index=at_risk_df.index)).fillna("").isin(["Failed", "Pending"]).astype(int)
            negative_margin_flag = at_risk_df.get("margin_per_gram", pd.Series(0.0, index=at_risk_df.index)).fillna(0.0).lt(0).astype(int)
            low_yield_flag = at_risk_df.get("yield_pct", pd.Series(0.0, index=at_risk_df.index)).fillna(0.0).lt(10).astype(int)
            at_risk_df["risk_score"] = (
                qa_hold_flag * 3
                + coa_status_flag * 2
                + negative_margin_flag * 2
                + low_yield_flag
            )
            at_risk_df = at_risk_df.sort_values(["risk_score", "yield_pct"], ascending=[False, True]).head(12)
            cols = ["batch_id_internal", "method", "yield_pct", "coa_status", "qa_hold", "status", "margin_per_gram", "output_mapping_warning"]
            st.dataframe(at_risk_df[[c for c in cols if c in at_risk_df.columns]], use_container_width=True, hide_index=True)
            chart_card_end()
        with row5_r:
            chart_card_start("Top Aging Material Lots", "Oldest lots requiring run allocation priority.")
            aging_cols = ["material_name", "batch_id_internal", "age_days", "available_weight_g", "aging_flag", "intended_method"]
            if inventory_master_df.empty:
                st.caption("No inventory lots available.")
            else:
                aging_df = inventory_master_df.sort_values(["age_days", "available_weight_g"], ascending=[False, False]).head(12)
                st.dataframe(aging_df[[c for c in aging_cols if c in aging_df.columns]], use_container_width=True, hide_index=True)
            chart_card_end()

        row6_l, row6_r = st.columns(2)
        with row6_l:
            chart_card_start("Executive Risk Summary", "Critical, warning, and neutral observations from workflow, inventory, and value layers.")
            critical: list[str] = []
            warning: list[str] = []
            neutral: list[str] = []
            if negative_margin_runs > 0:
                critical.append(f"{negative_margin_runs} run(s) are currently negative-margin.")
            if at_risk_batches > 0:
                critical.append(f"{at_risk_batches} batch(es) are QA hold or COA pending/failed.")
            if avg_yield < 10 and total_runs > 0:
                warning.append("Average yield is below 10%.")
            if low_margin_runs > 0:
                warning.append(f"{low_margin_runs} run(s) have low margin (< $2/g).")
            if extreme_cost_runs > 0:
                warning.append(f"{extreme_cost_runs} run(s) show extreme cost-per-gram pressure.")
            if not inventory_master_df.empty and int((inventory_master_df["age_days"] >= 30).sum()) > 0:
                warning.append("Inventory contains aging lots (30+ days).")
            if suspicious_profit_runs > 0:
                neutral.append(f"{suspicious_profit_runs} run(s) have unusually high estimated profitability and should be reviewed.")
            unmapped_output_runs = int(display_df.get("unmapped_output_type", pd.Series(False, index=display_df.index)).fillna(False).astype(bool).sum()) if not display_df.empty else 0
            if unmapped_output_runs > 0:
                warning.append(f"{unmapped_output_runs} run(s) use unmapped output taxonomy and are on fallback valuation.")
            if total_runs > 0 and not critical and not warning:
                neutral.append("No critical workflow or value risks detected in current filters.")

            if critical:
                st.error("Critical")
                for msg in critical:
                    st.markdown(f"- {msg}")
            if warning:
                st.warning("Warning")
                for msg in warning:
                    st.markdown(f"- {msg}")
            if neutral:
                st.info("Neutral / Review")
                for msg in neutral:
                    st.markdown(f"- {msg}")
            chart_card_end()
        with row6_r:
            chart_card_start("AI Ops Context Preview", "Snapshot of context passed into AI Ops Brief.")
            st.write(
                {
                    "negative_margin_runs": negative_margin_runs,
                    "low_margin_runs": low_margin_runs,
                    "extreme_cost_runs": extreme_cost_runs,
                    "inventory_aging_lots_30_plus": int((inventory_master_df["age_days"] >= 30).sum()) if not inventory_master_df.empty else 0,
                    "inventory_linked_runs": int(display_df["inventory_linked"].fillna(False).sum()) if not display_df.empty else 0,
                }
            )
            chart_card_end()

        st.markdown("### Value & Profitability Analysis")
        v1, v2 = st.columns(2)
        with v1:
            chart_card_start("Profit by Method", "Total estimated profit by extraction method.")
            profit_method_df = (
                display_df.groupby("method", as_index=False)["total_profit_usd"]
                .sum()
                .sort_values("total_profit_usd", ascending=False)
            )
            if profit_method_df.empty:
                st.caption("No profitability data yet.")
            elif PLOTLY_AVAILABLE:
                fig = px.bar(profit_method_df, x="method", y="total_profit_usd", color="total_profit_usd", color_continuous_scale=["#ff6161", "#f5a524", "#4cd388"])
                fig.update_layout(height=320, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.bar_chart(profit_method_df.set_index("method")["total_profit_usd"])
            chart_card_end()
        with v2:
            chart_card_start("Cost vs Value per Method", "Average cost per gram versus market value per gram.")
            method_cost_val_df = (
                display_df.groupby("method", as_index=False)[["cost_per_gram", "market_price_per_gram"]]
                .mean()
                .sort_values("market_price_per_gram", ascending=False)
            )
            if method_cost_val_df.empty:
                st.caption("No cost/value comparison data.")
            elif PLOTLY_AVAILABLE:
                fig = go.Figure()
                fig.add_trace(go.Bar(x=method_cost_val_df["method"], y=method_cost_val_df["cost_per_gram"], name="Avg Cost/g", marker_color="#ff6161"))
                fig.add_trace(go.Bar(x=method_cost_val_df["method"], y=method_cost_val_df["market_price_per_gram"], name="Avg Value/g", marker_color="#4cd388"))
                fig.update_layout(barmode="group", height=320, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.bar_chart(method_cost_val_df.set_index("method")[["cost_per_gram", "market_price_per_gram"]])
            chart_card_end()

        v3, v4 = st.columns(2)
        with v3:
            chart_card_start("Margin by Product Type", "Average margin per gram by product output.")
            margin_product_df = (
                display_df.groupby("product_bucket", as_index=False)["margin_per_gram"]
                .mean()
                .sort_values("margin_per_gram", ascending=False)
            )
            if margin_product_df.empty:
                st.caption("No margin-by-product data.")
            elif PLOTLY_AVAILABLE:
                fig = px.bar(
                    margin_product_df,
                    x="product_bucket",
                    y="margin_per_gram",
                    color="margin_per_gram",
                    color_continuous_scale=["#ff6161", "#f5a524", "#4cd388"],
                )
                fig.update_layout(height=320, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.bar_chart(margin_product_df.set_index("product_bucket")["margin_per_gram"])
            chart_card_end()
        with v4:
            chart_card_start("Top Profitable / Worst Performing Runs", "Best and worst total profit outcomes.")
            top_cols = ["run_date", "batch_id_internal", "method", "product_bucket", "finished_output_g", "total_profit_usd", "margin_per_gram", "margin_pct_est", "output_mapping_warning"]
            top_runs = display_df.sort_values("total_profit_usd", ascending=False).head(8)
            worst_runs = display_df.sort_values("total_profit_usd", ascending=True).head(8)
            st.markdown("**Top Profitable Runs**")
            st.dataframe(top_runs[[c for c in top_cols if c in top_runs.columns]], use_container_width=True, hide_index=True)
            st.markdown("**Worst Performing Runs**")
            st.dataframe(worst_runs[[c for c in top_cols if c in worst_runs.columns]], use_container_width=True, hide_index=True)
            chart_card_end()

    with runs_tab:
        st.subheader("Run Explorer")
        run_explorer_df = run_df.copy()
        if "output_mapping_warning" in run_explorer_df.columns:
            run_explorer_df["output_mapping_warning"] = run_explorer_df["output_mapping_warning"].fillna("")
        st.dataframe(run_explorer_df, use_container_width=True, hide_index=True)
        with st.expander("Add Run Record", expanded=False):
            r1, r2, r3 = st.columns(3)
            with r1:
                run_date = st.date_input("Run Date", value=datetime.today(), key="ecc_run_date")
                state = st.selectbox(
                    "State / Jurisdiction",
                    ["MA", "ME", "NY", "NJ", "MI", "NV", "CA", "Other"],
                    key="ecc_run_state",
                )
                license_name = st.text_input("Facility / License Name", key="ecc_license_name")
                client_name = st.text_input("Client Name", value="In House", key="ecc_client_name")
                batch_id_internal = st.text_input("Internal Batch ID", key="ecc_batch_id")
                method = st.selectbox("Method", ["BHO", "CO2", "Rosin", "Ethanol"], key="ecc_method")
                product_type = st.selectbox(
                    "Product Type",
                    EXTRACTION_PRODUCT_TYPE_OPTIONS,
                    key="ecc_product_type",
                )
                downstream_product = st.selectbox(
                    "Downstream Product Path",
                    EXTRACTION_DOWNSTREAM_OPTIONS,
                    key="ecc_downstream_product",
                    help="Track whether extracted oil is converted into finished vape products.",
                )
                process_stage = st.selectbox(
                    "Current Process Stage",
                    ["Intake", "Extraction", "Post-Process", "Formulation", "Filling", "Packaged", "Transferred"],
                    index=0,
                    key="ecc_process_stage",
                )
            with r2:
                input_material_type = st.selectbox(
                    "Input Material Type",
                    ["Fresh Frozen", "Cured Biomass", "Hash", "Flower", "Trim", "Other"],
                    key="ecc_input_material_type",
                )
                input_weight_g = st.number_input("Input Weight (g)", min_value=0.0, step=1.0, key="ecc_input_weight")
                cost_per_input_gram = st.number_input(
                    "Input Cost Basis ($/g)",
                    min_value=0.0,
                    step=0.1,
                    key="ecc_cost_per_input_gram",
                    help="Used when the run is not linked to inventory lot allocations.",
                )
                intermediate_output_g = st.number_input(
                    "Intermediate Output (g)", min_value=0.0, step=0.1, key="ecc_intermediate_output"
                )
                finished_output_g = st.number_input(
                    "Finished Output (g)", min_value=0.0, step=0.1, key="ecc_finished_output"
                )
                residual_loss_g = st.number_input(
                    "Residual Loss (g)", min_value=0.0, step=0.1, key="ecc_residual_loss"
                )
                operator = st.text_input("Operator", key="ecc_operator")
                machine_line = st.text_input("Machine / Line", key="ecc_machine_line")
            with r3:
                metrc_package_id_input = st.text_input("METRC Package ID - Input", key="ecc_pkg_input")
                metrc_package_id_output = st.text_input("METRC Package ID - Output", key="ecc_pkg_output")
                metrc_manifest_or_transfer_id = st.text_input(
                    "METRC Manifest / Transfer ID",
                    key="ecc_manifest_id",
                )
                coa_status = st.selectbox(
                    "COA Status",
                    ["Pending", "Passed", "Failed", "Not Submitted"],
                    key="ecc_coa_status",
                )
                qa_hold = st.checkbox("QA Hold", key="ecc_qa_hold")
                toll_processing_flag = st.checkbox("Toll Processing Job", key="ecc_toll_flag")
                processing_fee_usd = st.number_input(
                    "Processing Fee (USD)", min_value=0.0, step=10.0, key="ecc_processing_fee"
                )
                est_revenue_usd = st.number_input(
                    "Estimated Revenue (USD)", min_value=0.0, step=10.0, key="ecc_est_revenue"
                )
                cogs_usd = st.number_input("COGS (USD)", min_value=0.0, step=10.0, key="ecc_cogs")
                notes = st.text_area("Run Notes", key="ecc_notes")

            if st.button("Add Run", type="primary", key="ecc_add_run"):
                yield_pct = (finished_output_g / input_weight_g * 100) if input_weight_g else 0.0
                post_eff = (finished_output_g / intermediate_output_g * 100) if intermediate_output_g else 0.0
                new_row = pd.DataFrame(
                    [
                        {
                            "run_date": str(run_date),
                            "state": state,
                            "license_name": license_name,
                            "client_name": client_name,
                            "batch_id_internal": batch_id_internal,
                            "metrc_package_id_input": metrc_package_id_input,
                            "metrc_package_id_output": metrc_package_id_output,
                            "metrc_manifest_or_transfer_id": metrc_manifest_or_transfer_id,
                            "method": method,
                            "product_type": normalize_extraction_output_label(product_type) or product_type,
                            "finished_product_type": normalize_extraction_output_label(product_type) or product_type,
                            "downstream_product": normalize_extraction_output_label(downstream_product) or downstream_product,
                            "process_stage": process_stage,
                            "intake_complete": process_stage in ["Extraction", "Post-Process", "Formulation", "Filling", "Packaged", "Transferred"],
                            "extraction_complete": process_stage in ["Post-Process", "Formulation", "Filling", "Packaged", "Transferred"],
                            "post_process_complete": process_stage in ["Formulation", "Filling", "Packaged", "Transferred"],
                            "formulation_complete": process_stage in ["Filling", "Packaged", "Transferred"],
                            "filling_complete": process_stage in ["Packaged", "Transferred"],
                            "packaging_complete": process_stage in ["Packaged", "Transferred"],
                            "ready_for_transfer": process_stage == "Transferred",
                            "input_material_type": input_material_type,
                            "input_weight_g": input_weight_g,
                            "cost_per_input_gram": cost_per_input_gram,
                            "intermediate_output_g": intermediate_output_g,
                            "finished_output_g": finished_output_g,
                            "residual_loss_g": residual_loss_g,
                            "yield_pct": yield_pct,
                            "post_process_efficiency_pct": post_eff,
                            "operator": operator,
                            "machine_line": machine_line,
                            "status": "Complete",
                            "toll_processing": toll_processing_flag,
                            "processing_fee_usd": processing_fee_usd,
                            "est_revenue_usd": est_revenue_usd,
                            "cogs_usd": cogs_usd,
                            "source_inventory_batch_ids": "[]",
                            "source_inventory_metrc_ids": "[]",
                            "allocated_input_weight_g": 0.0,
                            "allocated_input_cost_total": 0.0,
                            "inventory_linked": False,
                            "coa_status": coa_status,
                            "qa_hold": qa_hold,
                            "notes": notes,
                        }
                    ]
                )
                st.session_state.ecc_run_log = pd.concat(
                    [st.session_state.ecc_run_log, new_row],
                    ignore_index=True,
                )
                st.success("Run added. Rerun to view updated KPIs.")

    with process_tab:
        st.subheader("Start-to-Finish Process Tracker")
        st.caption(
            "Track stage-by-stage mass balance. Edit stage weights inline — losses and yields update automatically."
        )

        if st.session_state.ecc_run_log.empty:
            st.info("No runs available yet. Add a run to begin tracking the extraction process.")
        else:
            # ── KPI tiles ────────────────────────────────────────────────────
            _mb_all = _compute_mass_balance(st.session_state.ecc_run_log.copy())
            _total_input_pt = float(_mb_all["input_weight_g"].fillna(0).sum())
            _final_col = _mb_all["final_output_g"].where(
                _mb_all["final_output_g"] > 0,
                _mb_all.get("finished_output_g", pd.Series(0.0, index=_mb_all.index)).fillna(0),
            )
            _total_final_pt = float(_final_col.sum())
            _avg_final_yield_pt = float(
                _mb_all["final_yield_pct"].replace(0, float("nan")).mean(skipna=True) or 0.0
            )
            _total_loss_pt = float(
                (
                    _mb_all["extraction_loss_g"]
                    + _mb_all["post_process_loss_g"]
                    + _mb_all["distillation_loss_g"]
                    + _mb_all["final_loss_g"]
                ).fillna(0).sum()
            )
            _runs_with_warnings_pt = int(
                _mb_all["mass_balance_flag"].isin(["Warning", "Critical"]).sum()
            )
            k1, k2, k3, k4, k5 = st.columns(5)
            with k1:
                kpi_card("Total Input Weight", f"{_total_input_pt:,.1f} g")
            with k2:
                kpi_card("Total Final Output", f"{_total_final_pt:,.1f} g")
            with k3:
                kpi_card("Avg Final Yield %", f"{_avg_final_yield_pt:.1f}%")
            with k4:
                kpi_card("Total Process Loss", f"{_total_loss_pt:,.1f} g")
            with k5:
                kpi_card("Runs w/ Warnings", _runs_with_warnings_pt)

            st.divider()

            # ── Run selector ─────────────────────────────────────────────────
            process_df = _mb_all.reset_index(drop=True)
            process_df = _ecc_calculate_run_value_metrics(process_df, inventory_master_df)
            if "process_stage" not in process_df.columns:
                process_df["process_stage"] = "Intake"
            for _col in [
                "intake_complete",
                "extraction_complete",
                "post_process_complete",
                "formulation_complete",
                "filling_complete",
                "packaging_complete",
                "ready_for_transfer",
            ]:
                if _col not in process_df.columns:
                    process_df[_col] = False

            process_df["run_label"] = (
                process_df["run_date"].astype(str)
                + " • "
                + process_df["batch_id_internal"].astype(str).replace("", "No Batch ID")
                + " • "
                + process_df["method"].astype(str)
            )
            selected_run = st.selectbox(
                "Select Run to Update",
                process_df["run_label"].tolist(),
                key="ecc_process_selected_run",
            )
            selected_idx = process_df.index[process_df["run_label"] == selected_run][0]
            selected_row = process_df.loc[selected_idx]

            # Mass-balance status badge
            _flag_val = str(selected_row.get("mass_balance_flag", "OK"))
            _flag_icon = {"OK": "🟢", "Warning": "🟡", "Critical": "🔴"}.get(_flag_val, "⚪")
            _flag_color = {
                "OK": "#4cd388",
                "Warning": "#f3c74c",
                "Critical": "#ff6161",
            }.get(_flag_val, "#5aa8ff")
            st.markdown(
                f"<span class='pill-badge' style='background:{_flag_color};'>{_flag_icon} Mass Balance: {_flag_val}</span>",
                unsafe_allow_html=True,
            )

            st.markdown("#### Linked Inventory & Value Context")
            source_batches = _ecc_parse_list_field(selected_row.get("source_inventory_batch_ids", "[]"))
            source_metrc = _ecc_parse_list_field(selected_row.get("source_inventory_metrc_ids", "[]"))
            src1, src2, src3 = st.columns(3)
            with src1:
                st.metric("Inventory Linked", "Yes" if bool(selected_row.get("inventory_linked", False)) else "No")
                st.metric("Allocated Input (g)", f"{float(selected_row.get('allocated_input_weight_g', 0.0)):.1f}")
            with src2:
                st.metric("Allocated Input Cost", f"${float(selected_row.get('allocated_input_cost_total', 0.0)):,.2f}")
                st.metric("Cost / g", f"${float(selected_row.get('cost_per_gram', 0.0)):,.2f}")
            with src3:
                st.metric("Value / g", f"${float(selected_row.get('market_price_per_gram', 0.0)):,.2f}")
                st.metric("Margin / g", f"${float(selected_row.get('margin_per_gram', 0.0)):,.2f}")
            if source_batches or source_metrc:
                st.caption(
                    f"Source batches: {', '.join(source_batches) if source_batches else 'n/a'} | "
                    f"Source METRC IDs: {', '.join(source_metrc) if source_metrc else 'n/a'}"
                )
            linked_source_batch = str(selected_row.get("source_inventory_batch_id", "")).strip()
            linked_source_material = str(selected_row.get("source_material_name", "")).strip()
            if linked_source_batch or linked_source_material:
                st.caption(
                    f"Linked source lot: {linked_source_batch or 'n/a'} | "
                    f"Source material: {linked_source_material or 'n/a'}"
                )

            st.markdown("#### Value Model Overrides")
            ov1, ov2 = st.columns(2)
            with ov1:
                manual_cost_per_g = st.number_input(
                    "Override Cost / g ($)",
                    min_value=0.0,
                    step=0.1,
                    value=float(selected_row.get("manual_cost_per_gram", 0.0) or 0.0),
                    help="Optional manual override. Set to 0 to use calculated cost-per-gram.",
                    key=f"ecc_manual_cost_per_g_update_{int(selected_idx)}",
                )
            with ov2:
                manual_value_per_g = st.number_input(
                    "Override Value / g ($)",
                    min_value=0.0,
                    step=0.1,
                    value=float(selected_row.get("manual_market_price_per_gram", 0.0) or 0.0),
                    help="Optional manual override. Set to 0 to use taxonomy/method market value mapping.",
                    key=f"ecc_manual_value_per_g_update_{int(selected_idx)}",
                )

            # ── Process status controls (preserved from original) ─────────
            st.markdown("#### Process Status")
            p1, p2, p3 = st.columns(3)
            with p1:
                updated_stage = st.selectbox(
                    "Process Stage",
                    ["Intake", "Extraction", "Post-Process", "Formulation", "Filling", "Packaged", "Transferred"],
                    index=["Intake", "Extraction", "Post-Process", "Formulation", "Filling", "Packaged", "Transferred"].index(
                        selected_row.get("process_stage", "Intake")
                    ) if selected_row.get("process_stage", "Intake") in ["Intake", "Extraction", "Post-Process", "Formulation", "Filling", "Packaged", "Transferred"] else 0,
                    key="ecc_process_stage_update",
                )
                updated_status = st.selectbox(
                    "Operational Status",
                    ["Queued", "Processing", "Packaging", "Complete", "Hold"],
                    index=(
                        ["Queued", "Processing", "Packaging", "Complete", "Hold"].index(selected_row.get("status", "Processing"))
                        if selected_row.get("status", "Processing") in ["Queued", "Processing", "Packaging", "Complete", "Hold"]
                        else 1
                    ),
                    key="ecc_process_status_update",
                )
                updated_product_type = st.selectbox(
                    "Finished Product Type",
                    EXTRACTION_PRODUCT_TYPE_OPTIONS,
                    index=(
                        EXTRACTION_PRODUCT_TYPE_OPTIONS.index(
                            normalize_extraction_output_label(
                                selected_row.get("finished_product_type", selected_row.get("product_type", "Other"))
                            ) or "Other"
                        )
                        if (normalize_extraction_output_label(selected_row.get("finished_product_type", selected_row.get("product_type", "Other"))) or "Other")
                        in EXTRACTION_PRODUCT_TYPE_OPTIONS
                        else EXTRACTION_PRODUCT_TYPE_OPTIONS.index("Other")
                    ),
                    key="ecc_process_product_type_update",
                )
            with p2:
                updated_downstream = st.selectbox(
                    "Downstream Output",
                    EXTRACTION_DOWNSTREAM_OPTIONS,
                    index=(
                        EXTRACTION_DOWNSTREAM_OPTIONS.index(
                            normalize_extraction_output_label(selected_row.get("downstream_product", "N/A"))
                            or selected_row.get("downstream_product", "N/A")
                        )
                        if (normalize_extraction_output_label(selected_row.get("downstream_product", "N/A")) or selected_row.get("downstream_product", "N/A"))
                        in EXTRACTION_DOWNSTREAM_OPTIONS
                        else 0
                    ),
                    key="ecc_process_downstream_update",
                )
                updated_coa = st.selectbox(
                    "COA Status",
                    ["Pending", "Passed", "Failed", "Not Submitted"],
                    index=(
                        ["Pending", "Passed", "Failed", "Not Submitted"].index(selected_row.get("coa_status", "Pending"))
                        if selected_row.get("coa_status", "Pending") in ["Pending", "Passed", "Failed", "Not Submitted"]
                        else 0
                    ),
                    key="ecc_process_coa_update",
                )
                updated_qa_hold = st.checkbox(
                    "QA Hold",
                    value=bool(selected_row.get("qa_hold", False)),
                    key="ecc_process_qa_hold_update",
                )
            with p3:
                intake_complete = st.checkbox("Intake Complete", value=bool(selected_row.get("intake_complete", False)), key="ecc_intake_complete_update")
                extraction_complete = st.checkbox("Extraction Complete", value=bool(selected_row.get("extraction_complete", False)), key="ecc_extraction_complete_update")
                post_process_complete = st.checkbox("Post-Process Complete", value=bool(selected_row.get("post_process_complete", False)), key="ecc_post_process_complete_update")
                formulation_complete = st.checkbox("Formulation Complete", value=bool(selected_row.get("formulation_complete", False)), key="ecc_formulation_complete_update")
                filling_complete = st.checkbox("Filling Complete", value=bool(selected_row.get("filling_complete", False)), key="ecc_filling_complete_update")
                packaging_complete = st.checkbox("Packaging Complete", value=bool(selected_row.get("packaging_complete", False)), key="ecc_packaging_complete_update")
                ready_for_transfer = st.checkbox("Ready for Transfer", value=bool(selected_row.get("ready_for_transfer", False)), key="ecc_ready_for_transfer_update")

            updated_notes = st.text_area(
                "Process Notes / Handoff Notes",
                value=str(selected_row.get("notes", "")),
                key="ecc_process_notes_update",
            )

            # ── Mass Balance — Stage Weights (inline editor) ──────────────
            st.markdown("#### Mass Balance — Stage Weights")
            st.caption(
                "Enter the measured output at each stage. "
                "Leave a stage at 0 if it is not used in this run. "
                "Losses and yields recalculate automatically."
            )
            mb1, mb2, mb3, mb4, mb5 = st.columns(5)
            with mb1:
                upd_input_weight = st.number_input(
                    "Input Weight (g)",
                    min_value=0.0,
                    step=1.0,
                    value=float(selected_row.get("input_weight_g", 0.0)),
                    key="ecc_mb_input_weight",
                )
            with mb2:
                upd_extraction_output = st.number_input(
                    "Extraction Output (g)",
                    min_value=0.0,
                    step=0.1,
                    value=float(selected_row.get("extraction_output_g", 0.0)),
                    key="ecc_mb_extraction_output",
                )
            with mb3:
                upd_post_process_output = st.number_input(
                    "Post-Process Output (g)",
                    min_value=0.0,
                    step=0.1,
                    value=float(selected_row.get("post_process_output_g", 0.0)),
                    key="ecc_mb_post_process_output",
                    help="Leave 0 if post-process stage is not used for this run.",
                )
            with mb4:
                upd_distillation_output = st.number_input(
                    "Distillation Output (g)",
                    min_value=0.0,
                    step=0.1,
                    value=float(selected_row.get("distillation_output_g", 0.0)),
                    key="ecc_mb_distillation_output",
                    help="Leave 0 if distillation stage is not used for this run.",
                )
            with mb5:
                upd_final_output = st.number_input(
                    "Final Output (g)",
                    min_value=0.0,
                    step=0.1,
                    value=float(
                        selected_row.get(
                            "final_output_g",
                            float(selected_row.get("finished_output_g", 0.0)),
                        )
                    ),
                    key="ecc_mb_final_output",
                )

            # Live loss/yield preview (computed client-side without modifying session state)
            _inp_v = float(upd_input_weight)
            _ext_v = float(upd_extraction_output)
            _pp_v = float(upd_post_process_output)
            _dist_v = float(upd_distillation_output)
            _final_v = float(upd_final_output)
            _inp_safe = _inp_v if _inp_v > 0 else float("nan")
            _last_up_v = _dist_v if _dist_v > 0 else (_pp_v if _pp_v > 0 else _ext_v)
            _ext_loss_v = max(0.0, _inp_v - _ext_v) if _inp_v > 0 else 0.0
            _pp_loss_v = max(0.0, _ext_v - _pp_v) if _pp_v > 0 and _ext_v > 0 else 0.0
            _dist_loss_v = max(0.0, _pp_v - _dist_v) if _dist_v > 0 and _pp_v > 0 else 0.0
            _final_loss_v = max(0.0, _last_up_v - _final_v) if _last_up_v > 0 else 0.0
            _ext_yield_v = _ext_v / _inp_safe * 100 if not np.isnan(_inp_safe) else 0.0
            _final_yield_v = _final_v / _inp_safe * 100 if not np.isnan(_inp_safe) else 0.0

            st.markdown("**Computed Losses & Yields — live preview:**")
            pr1, pr2, pr3, pr4, pr5, pr6 = st.columns(6)
            with pr1:
                st.metric("Extraction Loss (g)", f"{_ext_loss_v:.1f}")
            with pr2:
                st.metric("Post-Process Loss (g)", f"{_pp_loss_v:.1f}")
            with pr3:
                st.metric("Distillation Loss (g)", f"{_dist_loss_v:.1f}")
            with pr4:
                st.metric("Final Stage Loss (g)", f"{_final_loss_v:.1f}")
            with pr5:
                st.metric("Extraction Yield %", f"{_ext_yield_v:.1f}%")
            with pr6:
                st.metric("Final Yield %", f"{_final_yield_v:.1f}%")

            # Inline validation messages
            _method_thresh = _MB_HIGH_YIELD_THRESHOLDS.get(str(selected_row.get("method", "BHO")), 40.0)
            if _inp_v > 0 and _ext_v > _inp_v:
                st.error("🔴 Critical: Extraction output exceeds input weight — verify your values.")
            elif _pp_v > 0 and _ext_v > 0 and _pp_v > _ext_v:
                st.error("🔴 Critical: Post-process output exceeds extraction output.")
            elif _dist_v > 0 and _pp_v > 0 and _dist_v > _pp_v:
                st.error("🔴 Critical: Distillation output exceeds post-process output.")
            elif _final_v > 0 and _last_up_v > 0 and _final_v > _last_up_v:
                st.error("🔴 Critical: Final output exceeds last upstream stage output.")
            elif _final_yield_v > _method_thresh and _inp_v > 0:
                st.warning(
                    f"🟡 Warning: Final yield {_final_yield_v:.1f}% is unusually high for "
                    f"{selected_row.get('method', 'this method')} (threshold: {_method_thresh}%). "
                    "Verify your values."
                )

            # ── Save button ───────────────────────────────────────────────
            if st.button("Update Extraction Process", type="primary", key="ecc_update_process"):
                # Write back status/workflow fields
                st.session_state.ecc_run_log.loc[selected_idx, "process_stage"] = updated_stage
                st.session_state.ecc_run_log.loc[selected_idx, "status"] = updated_status
                normalized_product_type = normalize_extraction_output_label(updated_product_type) or updated_product_type
                normalized_downstream = normalize_extraction_output_label(updated_downstream) or updated_downstream
                st.session_state.ecc_run_log.loc[selected_idx, "product_type"] = normalized_product_type
                st.session_state.ecc_run_log.loc[selected_idx, "finished_product_type"] = normalized_product_type
                st.session_state.ecc_run_log.loc[selected_idx, "downstream_product"] = normalized_downstream
                st.session_state.ecc_run_log.loc[selected_idx, "manual_cost_per_gram"] = float(manual_cost_per_g or 0.0)
                st.session_state.ecc_run_log.loc[selected_idx, "manual_market_price_per_gram"] = float(manual_value_per_g or 0.0)
                st.session_state.ecc_run_log.loc[selected_idx, "coa_status"] = updated_coa
                st.session_state.ecc_run_log.loc[selected_idx, "qa_hold"] = updated_qa_hold
                st.session_state.ecc_run_log.loc[selected_idx, "intake_complete"] = intake_complete
                st.session_state.ecc_run_log.loc[selected_idx, "extraction_complete"] = extraction_complete
                st.session_state.ecc_run_log.loc[selected_idx, "post_process_complete"] = post_process_complete
                st.session_state.ecc_run_log.loc[selected_idx, "formulation_complete"] = formulation_complete
                st.session_state.ecc_run_log.loc[selected_idx, "filling_complete"] = filling_complete
                st.session_state.ecc_run_log.loc[selected_idx, "packaging_complete"] = packaging_complete
                st.session_state.ecc_run_log.loc[selected_idx, "ready_for_transfer"] = ready_for_transfer
                st.session_state.ecc_run_log.loc[selected_idx, "notes"] = updated_notes
                # Write back editable mass-balance stage weights
                st.session_state.ecc_run_log.loc[selected_idx, "input_weight_g"] = upd_input_weight
                st.session_state.ecc_run_log.loc[selected_idx, "extraction_output_g"] = upd_extraction_output
                st.session_state.ecc_run_log.loc[selected_idx, "post_process_output_g"] = upd_post_process_output
                st.session_state.ecc_run_log.loc[selected_idx, "distillation_output_g"] = upd_distillation_output
                st.session_state.ecc_run_log.loc[selected_idx, "final_output_g"] = upd_final_output
                # Keep legacy fields in sync so upstream views (Executive Overview, Run Analytics) reflect edits
                st.session_state.ecc_run_log.loc[selected_idx, "intermediate_output_g"] = upd_extraction_output
                # Use the last non-zero downstream stage as the legacy finished_output_g fallback
                _legacy_finished = next(
                    (v for v in [upd_final_output, upd_distillation_output, upd_post_process_output, upd_extraction_output] if v > 0),
                    0.0,
                )
                st.session_state.ecc_run_log.loc[selected_idx, "finished_output_g"] = _legacy_finished
                # Recompute all derived mass-balance columns and write back for all rows
                _mb_updated = _compute_mass_balance(st.session_state.ecc_run_log.copy())
                _derived_write_back = (
                    _MB_COMPUTED_FIELDS
                    + ["yield_pct", "finished_output_g", "post_process_efficiency_pct"]
                )
                for _dc in _derived_write_back:
                    if _dc in _mb_updated.columns:
                        st.session_state.ecc_run_log[_dc] = _mb_updated[_dc]
                st.success("Extraction process and mass balance updated successfully.")

            # ── Process Snapshot ─────────────────────────────────────────
            _process_view_cols = [
                "run_date",
                "batch_id_internal",
                "method",
                "process_stage",
                "status",
                "input_weight_g",
                "extraction_output_g",
                "extraction_loss_g",
                "extraction_yield_pct",
                "post_process_output_g",
                "post_process_loss_g",
                "distillation_output_g",
                "distillation_loss_g",
                "final_output_g",
                "final_loss_g",
                "final_yield_pct",
                "mass_balance_flag",
                "coa_status",
                "qa_hold",
                "ready_for_transfer",
            ]
            st.markdown("#### Process Snapshot")
            _snapshot_df = _compute_mass_balance(st.session_state.ecc_run_log.copy())
            st.dataframe(
                _snapshot_df[[c for c in _process_view_cols if c in _snapshot_df.columns]],
                use_container_width=True,
                hide_index=True,
            )

            # ── Stage loss + yield charts ─────────────────────────────────
            st.markdown("#### Stage Loss & Yield Analysis")
            _chart_df = _snapshot_df
            if not _chart_df.empty:
                ch_left, ch_right = st.columns(2)
                with ch_left:
                    st.markdown("**Total Loss by Stage (g)**")
                    _stage_loss_df = pd.DataFrame(
                        {
                            "Stage": ["Extraction", "Post-Process", "Distillation", "Final Stage"],
                            "Total Loss (g)": [
                                float(_chart_df["extraction_loss_g"].fillna(0).sum()),
                                float(_chart_df["post_process_loss_g"].fillna(0).sum()),
                                float(_chart_df["distillation_loss_g"].fillna(0).sum()),
                                float(_chart_df["final_loss_g"].fillna(0).sum()),
                            ],
                        }
                    )
                    st.bar_chart(_stage_loss_df.set_index("Stage")["Total Loss (g)"])
                with ch_right:
                    st.markdown("**Final Yield % by Run**")
                    _yield_chart = _chart_df[["batch_id_internal", "final_yield_pct"]].copy()
                    _yield_chart = _yield_chart[_yield_chart["final_yield_pct"] > 0].set_index(
                        "batch_id_internal"
                    )
                    if not _yield_chart.empty:
                        st.bar_chart(_yield_chart["final_yield_pct"])
                    else:
                        st.caption("No final yield data to display yet.")

    with inv_tab:
        st.subheader("Extraction Input Inventory")
        st.caption("Track extraction input lots (fresh frozen, biomass, trim, hash, crude, distillate, solvents) separately from run records.")

        age_threshold = st.slider("Aging threshold (days)", min_value=7, max_value=120, value=30, key="ecc_inventory_aging_threshold")
        low_stock_threshold = st.number_input(
            "Low available stock threshold (g)",
            min_value=0.0,
            value=250.0,
            step=25.0,
            key="ecc_inventory_low_stock_threshold",
        )
        yield_model = st.radio(
            "Projected yield model",
            ["Method defaults", "Single global yield %"],
            horizontal=True,
            key="ecc_inventory_yield_model",
        )
        global_yield_pct = st.slider(
            "Global projected yield %",
            min_value=1.0,
            max_value=40.0,
            value=12.0,
            step=0.5,
            key="ecc_inventory_global_yield_pct",
        )
        use_method_defaults = yield_model == "Method defaults"
        chart_card_start("Projected Output Calculator", "Tune the projected output model before appending inventory.")
        st.caption("Method defaults use method-specific assumptions. Global mode applies one yield % to all lots.")
        st.caption(f"Current active model: {'Method defaults' if use_method_defaults else f'Global {global_yield_pct:.1f}%'}")
        chart_card_end()

        uploaded_inventory_file = st.file_uploader(
            "Upload extraction inventory (CSV, XLSX, XLS)",
            type=["csv", "xlsx", "xls"],
            key="ecc_inventory_upload",
        )

        if uploaded_inventory_file is not None:
            try:
                uploaded_inv_df = _ecc_load_uploaded_inventory_file(uploaded_inventory_file)
                st.caption(f"Detected {len(uploaded_inv_df.columns)} source columns.")
                auto_normalized, auto_matches, auto_map = _ecc_normalize_extraction_inventory(uploaded_inv_df)
                st.caption(f"Auto-mapped fields: {auto_matches}")
                if auto_map:
                    st.write({k: v for k, v in auto_map.items()})

                if auto_matches >= 3:
                    auto_preview = _ecc_finalize_inventory_frame(auto_normalized)
                    st.dataframe(auto_preview.head(100), use_container_width=True, hide_index=True)
                    if st.button("Append Auto-Mapped Inventory", key="ecc_inventory_append_auto", type="primary"):
                        st.session_state.ecc_inventory_log = _ecc_append_inventory_rows(st.session_state.ecc_inventory_log, auto_preview)
                        st.success(f"Added {len(auto_preview)} row(s) into extraction inventory log.")
                else:
                    st.warning("Auto-mapping detected fewer than 3 fields. Use manual mapping below.")
                    map_options = _ECC_INVENTORY_COLUMNS + ["IGNORE"]
                    st.markdown("##### Manual Column Mapping")
                    manual_rows = []
                    for col_idx, col in enumerate(uploaded_inv_df.columns):
                        col_key = f"{col_idx}_{normalize_col(col)}"
                        sample = uploaded_inv_df[col].dropna().astype(str).head(1)
                        sample_value = sample.iloc[0] if not sample.empty else ""
                        c1, c2, c3 = st.columns([1.2, 1.6, 1.2])
                        with c1:
                            st.code(str(col))
                        with c2:
                            st.write(sample_value)
                        with c3:
                            target_field = st.selectbox(
                                f"Map {col}",
                                options=map_options,
                                index=map_options.index("IGNORE"),
                                key=f"ecc_inv_map_{col_key}",
                                label_visibility="collapsed",
                            )
                        manual_rows.append((col, target_field))

                    m1, m2, m3 = st.columns(3)
                    with m1:
                        default_material_type = st.selectbox(
                            "Default material_type",
                            options=["(none)"] + _ECC_MATERIAL_TYPES,
                            index=0,
                            key="ecc_inv_default_material_type",
                        )
                    with m2:
                        default_status = st.selectbox(
                            "Default status",
                            options=["(none)"] + _ECC_STATUS_VALUES,
                            index=1,
                            key="ecc_inv_default_status",
                        )
                    with m3:
                        default_method = st.selectbox(
                            "Default intended_method",
                            options=["(none)"] + _ECC_METHOD_VALUES,
                            index=0,
                            key="ecc_inv_default_method",
                        )

                    if st.button("Convert to Extraction Inventory", key="ecc_inventory_convert_manual", type="primary"):
                        mapped_df = pd.DataFrame(index=uploaded_inv_df.index)
                        for source_col, target_col in manual_rows:
                            if target_col != "IGNORE":
                                mapped_df[target_col] = uploaded_inv_df[source_col]

                        mapped_df = _ecc_enforce_inventory_schema(mapped_df)
                        if default_material_type != "(none)":
                            mapped_df = _ecc_apply_default_if_empty(mapped_df, "material_type", default_material_type)
                        if default_status != "(none)":
                            mapped_df = _ecc_apply_default_if_empty(mapped_df, "status", default_status)
                        if default_method != "(none)":
                            mapped_df = _ecc_apply_default_if_empty(mapped_df, "intended_method", default_method)

                        mapped_df = _ecc_finalize_inventory_frame(mapped_df)
                        st.session_state.ecc_inventory_log = _ecc_append_inventory_rows(st.session_state.ecc_inventory_log, mapped_df)
                        st.success(f"Converted and appended {len(mapped_df)} row(s).")
                        st.dataframe(mapped_df.head(100), use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(f"Could not load extraction inventory file: {exc}")

        inventory_df = _ecc_add_inventory_aging(_ecc_finalize_inventory_frame(st.session_state.ecc_inventory_log.copy()))
        inventory_df = _ecc_add_estimated_output(
            inventory_df,
            global_yield_pct=global_yield_pct,
            use_method_defaults=use_method_defaults,
        )

        total_input = float(inventory_df["current_weight_g"].sum()) if not inventory_df.empty else 0.0
        total_available = float(inventory_df["available_weight_g"].sum()) if not inventory_df.empty else 0.0
        total_reserved = float(inventory_df["reserved_weight_g"].sum()) if not inventory_df.empty else 0.0
        total_lots = int(len(inventory_df))
        aging_lots = int((inventory_df["age_days"] >= age_threshold).sum()) if not inventory_df.empty else 0
        projected_total = float(inventory_df["estimated_output_g"].sum()) if not inventory_df.empty else 0.0

        render_extraction_kpi(
            [
                {"label": "Total Input Weight", "value": f"{total_input:,.1f} g"},
                {"label": "Available Weight", "value": f"{total_available:,.1f} g"},
                {"label": "Reserved Weight", "value": f"{total_reserved:,.1f} g"},
                {"label": "Aging Lots", "value": aging_lots},
                {"label": "Estimated Output", "value": f"{projected_total:,.1f} g"},
            ]
        )

        k1, k2, k3, k4, k5, k6 = st.columns(6)
        with k1:
            kpi_card("Total Input Weight (g)", f"{total_input:,.1f}")
        with k2:
            kpi_card("Available Weight (g)", f"{total_available:,.1f}")
        with k3:
            kpi_card("Reserved Weight (g)", f"{total_reserved:,.1f}")
        with k4:
            kpi_card("Lots in Inventory", total_lots)
        with k5:
            kpi_card("Aging Lots", aging_lots)
        with k6:
            kpi_card("Est. Output Potential (g)", f"{projected_total:,.1f}")

        if inventory_df.empty:
            st.info("No extraction inventory rows in session yet. Upload a file to begin.")
        else:
            future_date_count = int(inventory_df["future_received_date"].sum()) if "future_received_date" in inventory_df.columns else 0
            if future_date_count > 0:
                st.warning(f"{future_date_count} lot(s) have a received date in the future. Aging days were floored at 0.")

            p1, p2 = st.columns(2)
            with p1:
                chart_card_start("Inventory by Material Type", "Estimated output grouped by material type.")
                by_type = (
                    inventory_df.groupby("material_type", as_index=False)["estimated_output_g"]
                    .sum()
                    .sort_values("estimated_output_g", ascending=False)
                )
                st.bar_chart(by_type.set_index("material_type")["estimated_output_g"])
                chart_card_end()
            with p2:
                chart_card_start("Output by Intended Method", "Estimated output grouped by intended extraction method.")
                by_method = (
                    inventory_df.groupby("intended_method", as_index=False)["estimated_output_g"]
                    .sum()
                    .sort_values("estimated_output_g", ascending=False)
                )
                st.bar_chart(by_method.set_index("intended_method")["estimated_output_g"])
                chart_card_end()

            chart_card_start("Aging Distribution", "Lot aging distribution for planning priority runs.")
            _aging_bins = pd.cut(
                pd.to_numeric(inventory_df["age_days"], errors="coerce").fillna(0),
                bins=[-1, 7, 30, 60, 10_000],
                labels=["Fresh (0-7)", "Aging (8-30)", "Priority Run (31-60)", "Stale (60+)"],
            )
            _aging_chart = _aging_bins.value_counts().reindex(["Fresh (0-7)", "Aging (8-30)", "Priority Run (31-60)", "Stale (60+)"], fill_value=0)
            st.bar_chart(_aging_chart)
            chart_card_end()

            st.markdown("#### Inventory Filters")
            f1, f2, f3 = st.columns(3)
            with f1:
                mat_filter = st.multiselect(
                    "Material Type",
                    options=sorted([x for x in inventory_df["material_type"].dropna().unique() if str(x).strip()]),
                    default=[],
                    key="ecc_inv_filter_material_type",
                )
                status_filter = st.multiselect(
                    "Status",
                    options=sorted([x for x in inventory_df["status"].dropna().unique() if str(x).strip()]),
                    default=[],
                    key="ecc_inv_filter_status",
                )
            with f2:
                method_filter = st.multiselect(
                    "Intended Method",
                    options=sorted([x for x in inventory_df["intended_method"].dropna().unique() if str(x).strip()]),
                    default=[],
                    key="ecc_inv_filter_method",
                )
                aging_filter = st.multiselect(
                    "Aging Flag",
                    options=["Fresh", "Aging", "Priority Run", "Stale"],
                    default=[],
                    key="ecc_inv_filter_aging",
                )
            with f3:
                location_filter = st.multiselect(
                    "Storage Location",
                    options=sorted([x for x in inventory_df["storage_location"].dropna().unique() if str(x).strip()]),
                    default=[],
                    key="ecc_inv_filter_location",
                )
                text_filter = st.text_input(
                    "Search material / batch / vendor",
                    key="ecc_inv_filter_text",
                ).strip().lower()

            filtered_inv = inventory_df.copy()
            if mat_filter:
                filtered_inv = filtered_inv[filtered_inv["material_type"].isin(mat_filter)]
            if status_filter:
                filtered_inv = filtered_inv[filtered_inv["status"].isin(status_filter)]
            if method_filter:
                filtered_inv = filtered_inv[filtered_inv["intended_method"].isin(method_filter)]
            if aging_filter:
                filtered_inv = filtered_inv[filtered_inv["aging_flag"].isin(aging_filter)]
            if location_filter:
                filtered_inv = filtered_inv[filtered_inv["storage_location"].isin(location_filter)]
            if text_filter:
                text_cols = (
                    filtered_inv["material_name"].fillna("").astype(str)
                    + " "
                    + filtered_inv["batch_id_internal"].fillna("").astype(str)
                    + " "
                    + filtered_inv["source_vendor"].fillna("").astype(str)
                ).str.lower()
                filtered_inv = filtered_inv[text_cols.str.contains(text_filter, na=False)]

            filtered_inv["priority"] = filtered_inv["aging_flag"].fillna("Fresh")

            table_cols = [
                "material_name",
                "material_type",
                "batch_id_internal",
                "available_weight_g",
                "age_days",
                "priority",
                "intended_method",
            ]
            chart_card_start("Extraction Inventory Table", "Material Name, Type, Batch, Available, Age, Priority, Method.")
            st.dataframe(filtered_inv[[c for c in table_cols if c in filtered_inv.columns]], use_container_width=True, hide_index=True)
            chart_card_end()

            st.markdown("### Inventory → Workflow Allocation")
            st.caption("Select one or more lots, allocate grams, and create a queued run draft or attach to an existing run.")
            selectable_inv = filtered_inv[filtered_inv["available_weight_g"] > 0].copy()
            if selectable_inv.empty:
                st.info("No available inventory lots match current filters.")
            else:
                selectable_inv["batch_id_internal"] = selectable_inv["batch_id_internal"].fillna("").astype(str)
                lot_idx_options = selectable_inv.index.tolist()

                multi_mode = st.checkbox("Select multiple lots", key="ecc_allocate_multi_mode")

                if not multi_mode:
                    # ── Single-lot path (unchanged) ───────────────────────────────────
                    selected_lot_idx = st.selectbox(
                        "Inventory Lot (batch_id_internal)",
                        options=lot_idx_options,
                        format_func=lambda idx: str(selectable_inv.loc[idx, "batch_id_internal"]).strip() or f"Lot {idx}",
                        key="ecc_allocate_selected_lot",
                    )
                    selected_lot = selectable_inv.loc[selected_lot_idx]
                    selected_batch_id = str(selected_lot.get("batch_id_internal", "")).strip()
                    selected_metrc_id = str(selected_lot.get("metrc_package_id", "")).strip()
                    selected_material_name = str(selected_lot.get("material_name", "")).strip()
                    selected_available_weight = float(pd.to_numeric(selected_lot.get("available_weight_g", 0), errors="coerce") or 0.0)
                    selected_cost_per_g = float(pd.to_numeric(selected_lot.get("cost_per_g", 0), errors="coerce") or 0.0)
                    selected_intended_method = str(selected_lot.get("intended_method", "")).strip()

                    alloc_a, alloc_b = st.columns(2)
                    with alloc_a:
                        allocation_weight_g = st.number_input(
                            "allocation_weight_g",
                            min_value=0.0,
                            value=min(_ECC_DEFAULT_ALLOCATION_GRAMS, selected_available_weight),
                            step=1.0,
                            key="ecc_allocation_weight_g",
                        )
                        allocation_client = st.text_input(
                            "client_name",
                            value="In House",
                            key="ecc_allocation_client_name",
                        )
                    with alloc_b:
                        method_options = _ECC_METHOD_VALUES.copy()
                        if selected_intended_method and selected_intended_method not in method_options:
                            method_options = [selected_intended_method] + method_options
                        default_method_idx = method_options.index(selected_intended_method) if selected_intended_method in method_options else 0
                        allocation_method = st.selectbox(
                            "method",
                            options=method_options,
                            index=default_method_idx,
                            key="ecc_allocation_method_single",
                        )
                        st.caption(
                            f"METRC: {selected_metrc_id or 'n/a'} | Material: {selected_material_name or 'n/a'} | "
                            f"Available: {selected_available_weight:,.1f} g"
                        )

                    allocation_target = st.radio(
                        "Allocation Target",
                        options=["Create new run draft", "Attach to existing run"],
                        key="ecc_allocation_target",
                        horizontal=True,
                    )

                    selected_existing_run_label = None
                    _attach_run_log_ready = (
                        allocation_target == "Attach to existing run"
                        and "ecc_run_log" in st.session_state
                        and isinstance(st.session_state.ecc_run_log, pd.DataFrame)
                        and not st.session_state.ecc_run_log.empty
                    )
                    if _attach_run_log_ready:
                        _attach_df = _ecc_ensure_run_schema(st.session_state.ecc_run_log.copy()).reset_index()
                        _attach_df["_run_label"] = (
                            _attach_df["run_date"].astype(str)
                            + " • "
                            + _attach_df["batch_id_internal"].astype(str).replace("", "No Batch ID")
                            + " • "
                            + _attach_df["method"].astype(str)
                        )
                        selected_existing_run_label = st.selectbox(
                            "Run to attach inventory to",
                            options=_attach_df["_run_label"].tolist(),
                            key="ecc_allocate_attach_run",
                        )
                    elif allocation_target == "Attach to existing run":
                        st.info("No existing runs in the log. Use 'Create new run draft' first.")

                    if st.button("Allocate Inventory", key="ecc_allocate_inventory", type="primary"):
                        if allocation_weight_g <= 0:
                            st.error("Allocation weight must be greater than 0 g.")
                        elif allocation_weight_g > selected_available_weight:
                            st.error(
                                f"Allocation weight cannot exceed available weight ({selected_available_weight:,.1f} g)."
                            )
                        elif allocation_target == "Attach to existing run" and not _attach_run_log_ready:
                            st.error("No existing runs available to attach to.")
                        else:
                            inv_working = _ecc_finalize_inventory_frame(st.session_state.ecc_inventory_log.copy())
                            if selected_lot_idx not in inv_working.index:
                                st.error("Selected lot was not found in inventory. Please refresh selection.")
                            else:
                                available_before = float(pd.to_numeric(inv_working.loc[selected_lot_idx, "available_weight_g"], errors="coerce") or 0.0)
                                if allocation_weight_g > available_before:
                                    st.error(
                                        f"Allocation weight cannot exceed available weight ({available_before:,.1f} g)."
                                    )
                                else:
                                    # ── Shared: update inventory lot ──────────────────────────────
                                    inv_working.loc[selected_lot_idx, "available_weight_g"] = max(
                                        available_before - float(allocation_weight_g),
                                        0.0,
                                    )
                                    if "reserved_weight_g" in inv_working.columns:
                                        reserved_before = float(pd.to_numeric(inv_working.loc[selected_lot_idx, "reserved_weight_g"], errors="coerce") or 0.0)
                                        inv_working.loc[selected_lot_idx, "reserved_weight_g"] = max(
                                            reserved_before + float(allocation_weight_g),
                                            0.0,
                                        )
                                    if inv_working.loc[selected_lot_idx, "available_weight_g"] <= 0:
                                        inv_working.loc[selected_lot_idx, "status"] = "Depleted"
                                    elif str(inv_working.loc[selected_lot_idx, "status"]).strip().lower() == "available":
                                        inv_working.loc[selected_lot_idx, "status"] = "Reserved"
                                    st.session_state.ecc_inventory_log = inv_working[_ECC_INVENTORY_COLUMNS].copy()

                                    # ── Ensure run log is a DataFrame ────────────────────────────
                                    if "ecc_run_log" not in st.session_state:
                                        st.session_state.ecc_run_log = pd.DataFrame()
                                    existing_run_log = st.session_state.ecc_run_log
                                    if isinstance(existing_run_log, list):
                                        run_log = pd.DataFrame(existing_run_log)
                                        st.session_state.ecc_run_log = run_log.copy()
                                    else:
                                        run_log = existing_run_log.copy()
                                    run_log = _ecc_ensure_run_schema(_ensure_mass_balance_cols(run_log))
                                    allocation_cost_total = float(allocation_weight_g) * selected_cost_per_g

                                    if allocation_target == "Create new run draft":
                                        run_id_values = (
                                            run_log.get("batch_id_internal", pd.Series(dtype="object"))
                                            .fillna("")
                                            .astype(str)
                                            .str.extract(r"^RUN-(\d{4})$")[0]
                                        )
                                        parsed_run_nums = pd.to_numeric(run_id_values, errors="coerce").dropna()
                                        current_max_run_num = int(parsed_run_nums.max()) if not parsed_run_nums.empty else 0
                                        next_run_num = current_max_run_num + 1
                                        run_batch_id = f"RUN-{next_run_num:04d}"

                                        draft_row = pd.DataFrame(
                                            [
                                                {
                                                    "run_date": str(datetime.today().date()),
                                                    "batch_id_internal": run_batch_id,
                                                    "client_name": allocation_client or "In House",
                                                    "method": allocation_method,
                                                    "process_stage": "Queued",
                                                    "status": "Queued",
                                                    "input_weight_g": float(allocation_weight_g),
                                                    "source_inventory_batch_id": selected_batch_id,
                                                    "source_inventory_metrc_id": selected_metrc_id,
                                                    "source_material_name": selected_material_name,
                                                    "source_inventory_batch_ids": _ecc_serialize_list_field([selected_batch_id] if selected_batch_id else []),
                                                    "source_inventory_metrc_ids": _ecc_serialize_list_field([selected_metrc_id] if selected_metrc_id else []),
                                                    "inventory_linked": True,
                                                    "allocated_input_weight_g": float(allocation_weight_g),
                                                    "allocated_input_cost_total": allocation_cost_total,
                                                    "input_cost_total": allocation_cost_total,
                                                }
                                            ]
                                        )
                                        run_log = pd.concat([run_log, draft_row], ignore_index=True)
                                        st.session_state.ecc_run_log = _ecc_ensure_run_schema(_ensure_mass_balance_cols(run_log))
                                        st.success(
                                            f"Created run {run_batch_id} with {float(allocation_weight_g):,.1f} g from lot {selected_batch_id or 'n/a'}."
                                        )
                                    else:
                                        # ── Attach to existing run ────────────────────────────────
                                        if not selected_existing_run_label:
                                            st.error("Select a run to attach inventory to.")
                                        else:
                                            _attach_df2 = run_log.reset_index()
                                            _attach_df2["_run_label"] = (
                                                _attach_df2["run_date"].astype(str)
                                                + " • "
                                                + _attach_df2["batch_id_internal"].astype(str).replace("", "No Batch ID")
                                                + " • "
                                                + _attach_df2["method"].astype(str)
                                            )
                                            _match = _attach_df2[_attach_df2["_run_label"] == selected_existing_run_label]
                                            if _match.empty:
                                                st.error("Selected run could not be matched. Please refresh selection.")
                                            else:
                                                target_idx = int(_match["index"].iloc[0])
                                                existing_batches = _ecc_parse_list_field(run_log.loc[target_idx, "source_inventory_batch_ids"])
                                                existing_metrc = _ecc_parse_list_field(run_log.loc[target_idx, "source_inventory_metrc_ids"])
                                                merged_batches = list(dict.fromkeys(existing_batches + ([selected_batch_id] if selected_batch_id else [])))
                                                merged_metrc = list(dict.fromkeys(existing_metrc + ([selected_metrc_id] if selected_metrc_id else [])))
                                                run_log.loc[target_idx, "source_inventory_batch_ids"] = _ecc_serialize_list_field(merged_batches)
                                                run_log.loc[target_idx, "source_inventory_metrc_ids"] = _ecc_serialize_list_field(merged_metrc)
                                                _existing_bid = str(run_log.loc[target_idx, "source_inventory_batch_id"]).strip()
                                                if not _existing_bid or _existing_bid in {"nan", "None"}:
                                                    run_log.loc[target_idx, "source_inventory_batch_id"] = selected_batch_id
                                                _existing_mid = str(run_log.loc[target_idx, "source_inventory_metrc_id"]).strip()
                                                if not _existing_mid or _existing_mid in {"nan", "None"}:
                                                    run_log.loc[target_idx, "source_inventory_metrc_id"] = selected_metrc_id
                                                _existing_mat = str(run_log.loc[target_idx, "source_material_name"]).strip()
                                                if not _existing_mat or _existing_mat in {"nan", "None"}:
                                                    run_log.loc[target_idx, "source_material_name"] = selected_material_name
                                                run_log.loc[target_idx, "allocated_input_weight_g"] = float(run_log.loc[target_idx, "allocated_input_weight_g"]) + float(allocation_weight_g)
                                                run_log.loc[target_idx, "allocated_input_cost_total"] = float(run_log.loc[target_idx, "allocated_input_cost_total"]) + allocation_cost_total
                                                run_log.loc[target_idx, "input_cost_total"] = float(run_log.loc[target_idx, "input_cost_total"]) + allocation_cost_total
                                                run_log.loc[target_idx, "inventory_linked"] = True
                                                if float(run_log.loc[target_idx, "input_weight_g"]) <= 0:
                                                    run_log.loc[target_idx, "input_weight_g"] = float(run_log.loc[target_idx, "allocated_input_weight_g"])
                                                if str(run_log.loc[target_idx, "method"]).strip() in {"", "Mixed / TBD"}:
                                                    run_log.loc[target_idx, "method"] = allocation_method
                                                st.session_state.ecc_run_log = _ecc_ensure_run_schema(_ensure_mass_balance_cols(run_log))
                                                st.success(
                                                    f"Attached {float(allocation_weight_g):,.1f} g from lot {selected_batch_id or 'n/a'} to run {selected_existing_run_label}."
                                                )

                else:
                    # ── Multi-lot path ────────────────────────────────────────────────
                    selected_lot_indices = st.multiselect(
                        "Inventory Lots (batch_id_internal)",
                        options=lot_idx_options,
                        format_func=lambda idx: str(selectable_inv.loc[idx, "batch_id_internal"]).strip() or f"Lot {idx}",
                        key="ecc_allocate_multi_lots",
                    )

                    if not selected_lot_indices:
                        st.info("Select at least one inventory lot above.")
                    else:
                        # Per-lot weight inputs
                        lot_alloc_weights: dict = {}
                        for _ml_idx in selected_lot_indices:
                            _ml_lot = selectable_inv.loc[_ml_idx]
                            _ml_label = str(_ml_lot.get("batch_id_internal", "")).strip() or f"Lot {_ml_idx}"
                            _ml_avail = float(pd.to_numeric(_ml_lot.get("available_weight_g", 0), errors="coerce") or 0.0)
                            _ml_metrc = str(_ml_lot.get("metrc_package_id", "")).strip()
                            _ml_mat = str(_ml_lot.get("material_name", "")).strip()
                            _ml_w = st.number_input(
                                f"Grams from {_ml_label} (available: {_ml_avail:,.1f} g)",
                                min_value=0.0,
                                value=min(_ECC_DEFAULT_ALLOCATION_GRAMS, _ml_avail),
                                step=1.0,
                                key=f"ecc_alloc_wt_{_ml_idx}",
                            )
                            st.caption(f"  METRC: {_ml_metrc or 'n/a'} | Material: {_ml_mat or 'n/a'}")
                            lot_alloc_weights[_ml_idx] = _ml_w

                        _multi_total_alloc = sum(lot_alloc_weights.values())
                        st.metric("Total Allocated (g)", f"{_multi_total_alloc:,.1f}")

                        _first_lot_multi = selectable_inv.loc[selected_lot_indices[0]]
                        _first_intended_method_multi = str(_first_lot_multi.get("intended_method", "")).strip()

                        multi_alloc_a, multi_alloc_b = st.columns(2)
                        with multi_alloc_a:
                            allocation_client_multi = st.text_input(
                                "client_name",
                                value="In House",
                                key="ecc_allocation_client_name_multi",
                            )
                        with multi_alloc_b:
                            _method_opts_multi = _ECC_METHOD_VALUES.copy()
                            if _first_intended_method_multi and _first_intended_method_multi not in _method_opts_multi:
                                _method_opts_multi = [_first_intended_method_multi] + _method_opts_multi
                            _default_method_idx_multi = _method_opts_multi.index(_first_intended_method_multi) if _first_intended_method_multi in _method_opts_multi else 0
                            allocation_method_multi = st.selectbox(
                                "method",
                                options=_method_opts_multi,
                                index=_default_method_idx_multi,
                                key="ecc_allocation_method_multi",
                            )

                        allocation_target_multi = st.radio(
                            "Allocation Target",
                            options=["Create new run draft", "Attach to existing run"],
                            key="ecc_allocation_target_multi",
                            horizontal=True,
                        )

                        selected_existing_run_label_multi = None
                        _attach_run_log_ready_multi = (
                            allocation_target_multi == "Attach to existing run"
                            and "ecc_run_log" in st.session_state
                            and isinstance(st.session_state.ecc_run_log, pd.DataFrame)
                            and not st.session_state.ecc_run_log.empty
                        )
                        if _attach_run_log_ready_multi:
                            _attach_df_multi = _ecc_ensure_run_schema(st.session_state.ecc_run_log.copy()).reset_index()
                            _attach_df_multi["_run_label"] = (
                                _attach_df_multi["run_date"].astype(str)
                                + " • "
                                + _attach_df_multi["batch_id_internal"].astype(str).replace("", "No Batch ID")
                                + " • "
                                + _attach_df_multi["method"].astype(str)
                            )
                            selected_existing_run_label_multi = st.selectbox(
                                "Run to attach inventory to",
                                options=_attach_df_multi["_run_label"].tolist(),
                                key="ecc_allocate_attach_run_multi",
                            )
                        elif allocation_target_multi == "Attach to existing run":
                            st.info("No existing runs in the log. Use 'Create new run draft' first.")

                        if st.button("Allocate Inventory (Multi-Lot)", key="ecc_allocate_inventory_multi", type="primary"):
                            _multi_errors = []
                            for _ml_idx, _ml_w in lot_alloc_weights.items():
                                _ml_avail_check = float(pd.to_numeric(selectable_inv.loc[_ml_idx, "available_weight_g"], errors="coerce") or 0.0)
                                _ml_label_check = str(selectable_inv.loc[_ml_idx, "batch_id_internal"]).strip() or f"Lot {_ml_idx}"
                                if _ml_w <= 0:
                                    _multi_errors.append(f"Lot {_ml_label_check}: allocation weight must be > 0 g.")
                                elif _ml_w > _ml_avail_check:
                                    _multi_errors.append(f"Lot {_ml_label_check}: {_ml_w:,.1f} g exceeds available {_ml_avail_check:,.1f} g.")
                            if allocation_target_multi == "Attach to existing run" and not _attach_run_log_ready_multi:
                                _multi_errors.append("No existing runs available to attach to.")
                            if _multi_errors:
                                for _me in _multi_errors:
                                    st.error(_me)
                            else:
                                inv_working = _ecc_finalize_inventory_frame(st.session_state.ecc_inventory_log.copy())
                                _lot_inv_errors = []
                                for _ml_idx, _ml_w in lot_alloc_weights.items():
                                    if _ml_idx not in inv_working.index:
                                        _ml_label_check = str(selectable_inv.loc[_ml_idx, "batch_id_internal"]).strip() or f"Lot {_ml_idx}"
                                        _lot_inv_errors.append(f"Lot {_ml_label_check} not found in inventory. Refresh selection.")
                                        continue
                                    _ml_avail_now = float(pd.to_numeric(inv_working.loc[_ml_idx, "available_weight_g"], errors="coerce") or 0.0)
                                    if _ml_w > _ml_avail_now:
                                        _ml_label_check = str(selectable_inv.loc[_ml_idx, "batch_id_internal"]).strip() or f"Lot {_ml_idx}"
                                        _lot_inv_errors.append(f"Lot {_ml_label_check}: {_ml_w:,.1f} g exceeds current available {_ml_avail_now:,.1f} g.")
                                if _lot_inv_errors:
                                    for _lie in _lot_inv_errors:
                                        st.error(_lie)
                                else:
                                    # Mutate each lot and collect aggregated fields
                                    _all_batch_ids: list = []
                                    _all_metrc_ids: list = []
                                    _multi_total_cost = 0.0
                                    _multi_total_weight = 0.0
                                    _multi_first_batch_id = ""
                                    _multi_first_metrc_id = ""
                                    _multi_first_material_name = ""
                                    for _ml_idx, _ml_w in lot_alloc_weights.items():
                                        _ml_lot2 = selectable_inv.loc[_ml_idx]
                                        _ml_bid = str(_ml_lot2.get("batch_id_internal", "")).strip()
                                        _ml_mid = str(_ml_lot2.get("metrc_package_id", "")).strip()
                                        _ml_mat2 = str(_ml_lot2.get("material_name", "")).strip()
                                        _ml_cpg = float(pd.to_numeric(_ml_lot2.get("cost_per_g", 0), errors="coerce") or 0.0)
                                        _ml_avail_before = float(pd.to_numeric(inv_working.loc[_ml_idx, "available_weight_g"], errors="coerce") or 0.0)
                                        inv_working.loc[_ml_idx, "available_weight_g"] = max(_ml_avail_before - float(_ml_w), 0.0)
                                        if "reserved_weight_g" in inv_working.columns:
                                            _ml_res_before = float(pd.to_numeric(inv_working.loc[_ml_idx, "reserved_weight_g"], errors="coerce") or 0.0)
                                            inv_working.loc[_ml_idx, "reserved_weight_g"] = max(_ml_res_before + float(_ml_w), 0.0)
                                        if inv_working.loc[_ml_idx, "available_weight_g"] <= 0:
                                            inv_working.loc[_ml_idx, "status"] = "Depleted"
                                        elif str(inv_working.loc[_ml_idx, "status"]).strip().lower() == "available":
                                            inv_working.loc[_ml_idx, "status"] = "Reserved"
                                        if _ml_bid:
                                            _all_batch_ids.append(_ml_bid)
                                        if _ml_mid:
                                            _all_metrc_ids.append(_ml_mid)
                                        _multi_total_cost += float(_ml_w) * _ml_cpg
                                        _multi_total_weight += float(_ml_w)
                                        if not _multi_first_batch_id:
                                            _multi_first_batch_id = _ml_bid
                                        if not _multi_first_metrc_id:
                                            _multi_first_metrc_id = _ml_mid
                                        if not _multi_first_material_name:
                                            _multi_first_material_name = _ml_mat2
                                    st.session_state.ecc_inventory_log = inv_working[_ECC_INVENTORY_COLUMNS].copy()

                                    # Ensure run log is a DataFrame
                                    if "ecc_run_log" not in st.session_state:
                                        st.session_state.ecc_run_log = pd.DataFrame()
                                    _existing_run_log_multi = st.session_state.ecc_run_log
                                    if isinstance(_existing_run_log_multi, list):
                                        run_log = pd.DataFrame(_existing_run_log_multi)
                                        st.session_state.ecc_run_log = run_log.copy()
                                    else:
                                        run_log = _existing_run_log_multi.copy()
                                    run_log = _ecc_ensure_run_schema(_ensure_mass_balance_cols(run_log))
                                    _all_batch_ids_deduped = list(dict.fromkeys(_all_batch_ids))
                                    _all_metrc_ids_deduped = list(dict.fromkeys(_all_metrc_ids))

                                    if allocation_target_multi == "Create new run draft":
                                        _run_id_values_multi = (
                                            run_log.get("batch_id_internal", pd.Series(dtype="object"))
                                            .fillna("")
                                            .astype(str)
                                            .str.extract(r"^RUN-(\d{4})$")[0]
                                        )
                                        _parsed_nums_multi = pd.to_numeric(_run_id_values_multi, errors="coerce").dropna()
                                        _max_run_num_multi = int(_parsed_nums_multi.max()) if not _parsed_nums_multi.empty else 0
                                        run_batch_id_multi = f"RUN-{_max_run_num_multi + 1:04d}"
                                        draft_row_multi = pd.DataFrame(
                                            [
                                                {
                                                    "run_date": str(datetime.today().date()),
                                                    "batch_id_internal": run_batch_id_multi,
                                                    "client_name": allocation_client_multi or "In House",
                                                    "method": allocation_method_multi,
                                                    "process_stage": "Queued",
                                                    "status": "Queued",
                                                    "input_weight_g": _multi_total_weight,
                                                    "source_inventory_batch_id": _multi_first_batch_id,
                                                    "source_inventory_metrc_id": _multi_first_metrc_id,
                                                    "source_material_name": _multi_first_material_name,
                                                    "source_inventory_batch_ids": _ecc_serialize_list_field(_all_batch_ids_deduped),
                                                    "source_inventory_metrc_ids": _ecc_serialize_list_field(_all_metrc_ids_deduped),
                                                    "inventory_linked": True,
                                                    "allocated_input_weight_g": _multi_total_weight,
                                                    "allocated_input_cost_total": _multi_total_cost,
                                                    "input_cost_total": _multi_total_cost,
                                                }
                                            ]
                                        )
                                        run_log = pd.concat([run_log, draft_row_multi], ignore_index=True)
                                        st.session_state.ecc_run_log = _ecc_ensure_run_schema(_ensure_mass_balance_cols(run_log))
                                        st.success(
                                            f"Created run {run_batch_id_multi} with {_multi_total_weight:,.1f} g from {len(lot_alloc_weights)} lot(s)."
                                        )
                                    else:
                                        # Attach to existing run (multi-lot)
                                        if not selected_existing_run_label_multi:
                                            st.error("Select a run to attach inventory to.")
                                        else:
                                            _attach_df2m = run_log.reset_index()
                                            _attach_df2m["_run_label"] = (
                                                _attach_df2m["run_date"].astype(str)
                                                + " • "
                                                + _attach_df2m["batch_id_internal"].astype(str).replace("", "No Batch ID")
                                                + " • "
                                                + _attach_df2m["method"].astype(str)
                                            )
                                            _match_m = _attach_df2m[_attach_df2m["_run_label"] == selected_existing_run_label_multi]
                                            if _match_m.empty:
                                                st.error("Selected run could not be matched. Please refresh selection.")
                                            else:
                                                target_idx_m = int(_match_m["index"].iloc[0])
                                                _ex_batches_m = _ecc_parse_list_field(run_log.loc[target_idx_m, "source_inventory_batch_ids"])
                                                _ex_metrc_m = _ecc_parse_list_field(run_log.loc[target_idx_m, "source_inventory_metrc_ids"])
                                                run_log.loc[target_idx_m, "source_inventory_batch_ids"] = _ecc_serialize_list_field(list(dict.fromkeys(_ex_batches_m + _all_batch_ids_deduped)))
                                                run_log.loc[target_idx_m, "source_inventory_metrc_ids"] = _ecc_serialize_list_field(list(dict.fromkeys(_ex_metrc_m + _all_metrc_ids_deduped)))
                                                _ex_bid_m = str(run_log.loc[target_idx_m, "source_inventory_batch_id"]).strip()
                                                if not _ex_bid_m or _ex_bid_m in {"nan", "None"}:
                                                    run_log.loc[target_idx_m, "source_inventory_batch_id"] = _multi_first_batch_id
                                                _ex_mid_m = str(run_log.loc[target_idx_m, "source_inventory_metrc_id"]).strip()
                                                if not _ex_mid_m or _ex_mid_m in {"nan", "None"}:
                                                    run_log.loc[target_idx_m, "source_inventory_metrc_id"] = _multi_first_metrc_id
                                                _ex_mat_m = str(run_log.loc[target_idx_m, "source_material_name"]).strip()
                                                if not _ex_mat_m or _ex_mat_m in {"nan", "None"}:
                                                    run_log.loc[target_idx_m, "source_material_name"] = _multi_first_material_name
                                                run_log.loc[target_idx_m, "allocated_input_weight_g"] = float(run_log.loc[target_idx_m, "allocated_input_weight_g"]) + _multi_total_weight
                                                run_log.loc[target_idx_m, "allocated_input_cost_total"] = float(run_log.loc[target_idx_m, "allocated_input_cost_total"]) + _multi_total_cost
                                                run_log.loc[target_idx_m, "input_cost_total"] = float(run_log.loc[target_idx_m, "input_cost_total"]) + _multi_total_cost
                                                run_log.loc[target_idx_m, "inventory_linked"] = True
                                                if float(run_log.loc[target_idx_m, "input_weight_g"]) <= 0:
                                                    run_log.loc[target_idx_m, "input_weight_g"] = float(run_log.loc[target_idx_m, "allocated_input_weight_g"])
                                                if str(run_log.loc[target_idx_m, "method"]).strip() in {"", "Mixed / TBD"}:
                                                    run_log.loc[target_idx_m, "method"] = allocation_method_multi
                                                st.session_state.ecc_run_log = _ecc_ensure_run_schema(_ensure_mass_balance_cols(run_log))
                                                st.success(
                                                    f"Attached {_multi_total_weight:,.1f} g from {len(lot_alloc_weights)} lot(s) to run {selected_existing_run_label_multi}."
                                                )

    with toll_tab:
        st.subheader("Toll Processing Command View")
        st.dataframe(job_df, use_container_width=True, hide_index=True)
        with st.expander("Add Toll Processing Job", expanded=False):
            t1, t2, t3 = st.columns(3)
            with t1:
                client_name = st.text_input("Client Name", key="ecc_job_client_name")
                state = st.selectbox("State", ["MA", "ME", "NY", "NJ", "MI", "NV", "CA", "Other"], key="ecc_job_state")
                license_or_registration = st.text_input("Client License / Registration", key="ecc_job_license")
                method = st.selectbox("Method", ["BHO", "CO2", "Rosin", "Ethanol"], key="ecc_job_method")
            with t2:
                metrc_transfer_id = st.text_input("METRC Transfer ID", key="ecc_job_metrc")
                material_received_date = st.date_input("Material Received Date", key="ecc_job_received")
                promised_completion_date = st.date_input("Promised Completion Date", key="ecc_job_promised")
                input_weight_g = st.number_input("Input Weight (g)", min_value=0.0, step=1.0, key="ecc_job_input")
            with t3:
                expected_output_g = st.number_input(
                    "Expected Output (g)", min_value=0.0, step=0.1, key="ecc_job_expected"
                )
                actual_output_g = st.number_input("Actual Output (g)", min_value=0.0, step=0.1, key="ecc_job_actual")
                invoice_status = st.selectbox(
                    "Invoice Status", ["Draft", "Sent", "Paid", "Overdue"], key="ecc_job_invoice"
                )
                payment_status = st.selectbox("Payment Status", ["Pending", "Partial", "Paid"], key="ecc_job_payment")
                coa_status = st.selectbox("COA Status", ["Pending", "Passed", "Failed"], key="ecc_job_coa")
                job_status = st.selectbox(
                    "Job Status",
                    ["Queued", "Processing", "Packaging", "Complete", "Hold"],
                    key="ecc_job_status",
                )

            if st.button("Add Toll Job", key="ecc_add_job"):
                today = pd.Timestamp.today().normalize()
                promised = pd.Timestamp(promised_completion_date)
                sla_status = "At Risk" if promised < today else "On Track"
                new_job = pd.DataFrame(
                    [
                        {
                            "client_name": client_name,
                            "state": state,
                            "license_or_registration": license_or_registration,
                            "metrc_transfer_id": metrc_transfer_id,
                            "material_received_date": str(material_received_date),
                            "promised_completion_date": str(promised_completion_date),
                            "method": method,
                            "input_weight_g": input_weight_g,
                            "expected_output_g": expected_output_g,
                            "actual_output_g": actual_output_g,
                            "sla_status": sla_status,
                            "invoice_status": invoice_status,
                            "payment_status": payment_status,
                            "coa_status": coa_status,
                            "job_status": job_status,
                        }
                    ]
                )
                st.session_state.ecc_client_jobs = pd.concat(
                    [st.session_state.ecc_client_jobs, new_job],
                    ignore_index=True,
                )
                st.success("Toll job added.")

    with compliance_tab:
        st.subheader("Compliance / METRC Traceability")
        required_fields = pd.DataFrame(
            [
                ["State", "Jurisdiction for reporting and workflow rules"],
                ["Facility / License Name", "Required internal mapping for multi-site operations"],
                ["Internal Batch ID", "Your own batch identifier"],
                ["METRC Package ID - Input", "Starting package used in the run"],
                ["METRC Package ID - Output", "Finished package created from the run"],
                ["METRC Manifest / Transfer ID", "Movement and custody tracking"],
                ["Client License / Registration", "Critical for toll processing"],
                ["COA Status", "Pending, passed, failed, or not submitted"],
                ["QA Hold", "Operational hold flag"],
                ["Run Notes", "Exception log, deviations, and event context"],
            ],
            columns=["Field", "Purpose"],
        )
        st.dataframe(required_fields, use_container_width=True, hide_index=True)

    with inputs_tab:
        chart_card_start("Data Input + Mapping", "Upload extraction data, preview parsed rows, map fields, and convert to run log.")
        render_extraction_partner_upload_ui()
        chart_card_end()

    with ai_ops_tab:
        st.subheader("AI Operations Brief")
        run_value_df = _ecc_calculate_run_value_metrics(run_df.copy(), inventory_master_df)
        alerts = _compute_extraction_alerts(run_value_df, job_df)
        inventory_context = {}
        value_context = {}
        inventory_for_ai = _ecc_add_estimated_output(
            _ecc_add_inventory_aging(_ecc_finalize_inventory_frame(st.session_state.ecc_inventory_log.copy())),
            global_yield_pct=12.0,
            use_method_defaults=True,
        )
        if not inventory_for_ai.empty:
            ai_age_threshold = int(st.session_state.get("ecc_inventory_aging_threshold", 30))
            ai_low_stock_threshold = float(st.session_state.get("ecc_inventory_low_stock_threshold", 250.0))
            inventory_context = {
                "inventory_lots": int(len(inventory_for_ai)),
                "aging_material_count": int((inventory_for_ai["age_days"] >= ai_age_threshold).sum()),
                "low_available_stock_count": int((inventory_for_ai["available_weight_g"] <= ai_low_stock_threshold).sum()),
                "projected_output_g": float(inventory_for_ai["estimated_output_g"].sum()),
            }
            st.markdown("#### Inventory Context")
            st.write(inventory_context)

        if not run_value_df.empty:
            value_context = {
                "negative_margin_runs": int((run_value_df["margin_per_gram"] < 0).sum()),
                "low_margin_runs": int(
                    (
                        (run_value_df["margin_per_gram"] >= 0)
                        & (run_value_df["margin_per_gram"] < _ECC_LOW_MARGIN_PER_G_THRESHOLD)
                    ).sum()
                ),
                "total_estimated_profit_usd": float(run_value_df["total_profit_usd"].sum()),
                "avg_cost_per_gram": float(run_value_df["cost_per_gram"].replace(0, np.nan).mean(skipna=True) or 0.0),
                "avg_value_per_gram": float(run_value_df["market_price_per_gram"].replace(0, np.nan).mean(skipna=True) or 0.0),
                "inventory_linked_runs": int(run_value_df["inventory_linked"].fillna(False).sum()),
                "value_risk_runs": int(run_value_df["value_risk_flag"].isin(["Critical", "Warning"]).sum()),
            }
            st.markdown("#### Value & Profitability Context")
            st.write(value_context)

        if alerts:
            st.markdown("#### Current Alerts")
            for alert in alerts:
                st.warning(alert)
        else:
            st.success("No high-priority extraction alerts detected from current dataset.")

        st.markdown("#### Recommended Actions")
        st.caption("Generate a shift-ready brief grounded in current run and toll job data.")

        if st.button("Generate AI Extraction Brief", key="ecc_ai_ops_brief"):
            with st.spinner("Analyzing extraction operations..."):
                brief = _generate_extraction_ai_brief(
                    run_value_df,
                    job_df,
                    alerts,
                    inventory_context=inventory_context,
                    value_context=value_context,
                )
            st.markdown(brief)

# =========================
# TOP-LEVEL APP MODE SWITCH
# =========================
app_mode = st.radio(
    "Workspace",
    ["🛒 Buyer Operations", "🧪 Extraction Command Center"],
    index=0,
    horizontal=True,
    help="Switch between the purchasing dashboard and the extraction workspace.",
)

_render_sidebar_nav_mockup(app_mode, None)

if app_mode == "🧪 Extraction Command Center":
    render_hero(
        "Good Morning, Extraction Team",
        "Command center KPIs, process signals, and inventory risk in one view.",
        _display_user,
        "Operations",
    )
    render_main_ai_copilot(app_mode, "🧪 Extraction Command Center")
    render_extraction_command_center()
    st.stop()

# =========================
# GLOBAL DATA MODE SELECTOR (BUYER OPERATIONS ONLY)
# =========================
st.sidebar.markdown("---")
data_mode = st.sidebar.radio(
    "🔌 Data Input Mode",
    ["📁 Uploads", "🔴 Dutchie Live"],
    key="data_mode",
    help=(
        "Uploads: use manual CSV/XLSX exports from your POS system (current behaviour). "
        "Dutchie Live: pull data directly from the Dutchie API — requires API credentials. "
        "See docs/dutchie.md for setup instructions."
    ),
)
st.sidebar.markdown("---")

# =========================
# PAGE SWITCH (BUYER OPERATIONS)
# =========================
section = st.sidebar.radio(
    "App Section",
    [
        "📊 Inventory Dashboard",
        "📈 Trends",
        "🚚 Delivery Impact",
        "🐢 Slow Movers",
        "🧾 PO Builder",
        "🧭 Compliance Q&A",
        "🧠 Buyer Intelligence",
        "🛠️ Admin Tools",
    ],
    index=0,
)

_render_sidebar_nav_mockup(app_mode, section)

render_main_ai_copilot(app_mode, section)

# ============================================================
# PAGE 1 – INVENTORY DASHBOARD
# ============================================================
if section == "📊 Inventory Dashboard":
    render_hero(
        f"Good Morning, {_display_user}",
        "Here's what's happening with your portfolio today.",
        str(_display_user),
        "Buyer • Operations",
    )

    st.sidebar.markdown("### 🧩 Data Source")
    data_source = st.sidebar.selectbox(
        "Select POS / Data Source",
        ["Dutchie", "BLAZE"],
        index=0,
        help="Changes how column names are interpreted. Files are still CSV/XLSX exports.",
    )

    # ------------------------------------------------------------
    # DATA SOURCE: UPLOADS vs DUTCHIE LIVE
    # ------------------------------------------------------------
    if data_mode == "📁 Uploads":
        st.sidebar.header("📂 Upload Core Reports")
        inv_file = st.sidebar.file_uploader(
            "Inventory File (CSV or Excel)", type=["csv", "xlsx", "xls"], key="inv_upload"
        )
        product_sales_file = st.sidebar.file_uploader(
            "Product Sales Report (qty-based Excel)", type=["xlsx", "xls"], key="sales_upload"
        )
        extra_sales_file = st.sidebar.file_uploader(
            "Optional Extra Sales Detail (revenue)",
            type=["xlsx", "xls"],
            help="Optional: revenue detail. Can be used for pricing trends.",
            key="extra_sales_upload",
        )
        quarantine_file = st.sidebar.file_uploader(
            "Quarantine List (CSV or Excel)",
            type=["csv", "xlsx", "xls"],
            help="Optional: list of items in quarantine to exclude from slow movers analysis.",
            key="quarantine_upload",
        )

        # ------------------------------------------------------------
        # UPLOAD CACHE (prevents uploads from wiping when switching tabs)
        # ------------------------------------------------------------
        class _UploadedFileLike(BytesIO):
            def __init__(self, b: bytes, name: str):
                super().__init__(b)
                self.name = name

        def _cache_upload(file_obj, cache_key: str):
            if file_obj is None:
                return
            try:
                file_obj.seek(0)
                b = file_obj.read()
                file_obj.seek(0)
            except Exception:
                return
            if len(b) > MAX_UPLOAD_BYTES:
                st.error(
                    f"❌ File '{getattr(file_obj, 'name', 'upload')}' exceeds the "
                    f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB size limit and was not processed."
                )
                return
            st.session_state[cache_key] = {"name": getattr(file_obj, "name", "upload"), "bytes": b}

        def _load_cached(cache_key: str):
            obj = st.session_state.get(cache_key)
            if isinstance(obj, dict) and obj.get("bytes"):
                return _UploadedFileLike(obj["bytes"], obj.get("name", "cached_upload"))
            return None

        _cache_upload(inv_file, "_cache_inv")
        _cache_upload(product_sales_file, "_cache_sales")
        _cache_upload(extra_sales_file, "_cache_extra_sales")
        _cache_upload(quarantine_file, "_cache_quarantine")

        # Persist file caches to the daily store so they survive session timeouts
        _ds_user = (
            st.session_state.admin_user if st.session_state.is_admin
            else st.session_state.get("user_user")
        )
        if _ds_user:
            _save_to_daily_store(_ds_user)

        if inv_file is None:
            inv_file = _load_cached("_cache_inv")
            if inv_file is not None:
                st.sidebar.caption(f"Using cached Inventory file: {inv_file.name}")
        if product_sales_file is None:
            product_sales_file = _load_cached("_cache_sales")
            if product_sales_file is not None:
                st.sidebar.caption(f"Using cached Product Sales file: {product_sales_file.name}")
        if extra_sales_file is None:
            extra_sales_file = _load_cached("_cache_extra_sales")
            if extra_sales_file is not None:
                st.sidebar.caption(f"Using cached Extra Sales file: {extra_sales_file.name}")
        if quarantine_file is None:
            quarantine_file = _load_cached("_cache_quarantine")
            if quarantine_file is not None:
                st.sidebar.caption(f"Using cached Quarantine file: {quarantine_file.name}")

        if st.sidebar.button("🧹 Clear uploads (today & session)"):
            _ds_user_clear = (
                st.session_state.admin_user if st.session_state.is_admin
                else st.session_state.get("user_user")
            )
            _clear_daily_store(_ds_user_clear)
            st.session_state._daily_restored = False
            _safe_rerun()

        # Track uploads for God viewer (de-duped)
        current_user = (
            st.session_state.admin_user
            if st.session_state.is_admin
            else (st.session_state.user_user if st.session_state.user_authenticated else "trial_user")
        )
        if inv_file is not None:
            track_upload(inv_file, current_user, "inventory")
        if product_sales_file is not None:
            track_upload(product_sales_file, current_user, "product_sales")
        if extra_sales_file is not None:
            track_upload(extra_sales_file, current_user, "extra_sales")
        if quarantine_file is not None:
            track_upload(quarantine_file, current_user, "quarantine")

    else:
        # ── Dutchie Live mode ────────────────────────────────────────────────
        # File upload widgets are not shown; data comes from the Dutchie API.
        inv_file = None
        product_sales_file = None
        extra_sales_file = None
        quarantine_file = None

        if _DUTCHIE_CLIENT_AVAILABLE:
            _dc = DutchieConfig.from_env_and_secrets()
            _bundle, _dutchie_err = fetch_dutchie_data(_dc)
            if _dutchie_err:
                st.sidebar.warning(f"⚠️ Dutchie Live: {_dutchie_err}")
            else:
                _inv_live, _sales_live, _extra_live, _del_live, _dsales_live = _bundle
                if _inv_live is not None:
                    st.session_state.inv_raw_df = _inv_live
                if _sales_live is not None:
                    st.session_state.sales_raw_df = _sales_live
                if _extra_live is not None:
                    st.session_state.extra_sales_df = _extra_live
                if _del_live is not None:
                    st.session_state.delivery_raw_df = _del_live
                if _dsales_live is not None:
                    st.session_state.daily_sales_raw_df = _dsales_live
        else:
            st.sidebar.error("❌ dutchie_client module is not available.")

    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Forecast Settings")
    doh_threshold = int(st.sidebar.number_input("Target Days on Hand", 1, 60, 21))
    st.session_state.doh_threshold_cache = int(doh_threshold)
    velocity_adjustment = float(st.sidebar.number_input("Velocity Adjustment", 0.01, 5.0, 0.5))
    date_diff = int(st.sidebar.slider("Days in Sales Period", 7, 120, 60))

    # Cache raw dataframes
    if inv_file is not None:
        try:
            inv_df_raw = read_inventory_file(inv_file)
            try:
                inv_df_raw, vault_included, vault_excluded = filter_vault_inventory(inv_df_raw)
                st.sidebar.info(
                    f"🏦 Vault filter applied: **{vault_included}** batch rows included, "
                    f"**{vault_excluded}** excluded (non-Vault rooms)."
                )
            except ValueError as ve:
                st.error(str(ve))
                st.stop()
            st.session_state.inv_raw_df = inv_df_raw
        except Exception as e:
            st.error(f"Error reading inventory file: {e}")
            st.stop()

    if product_sales_file is not None:
        try:
            sales_raw_raw = read_sales_file(product_sales_file)
            st.session_state.sales_raw_df = sales_raw_raw
        except Exception as e:
            st.error(f"Error reading Product Sales report: {e}")
            st.stop()

    if extra_sales_file is not None:
        try:
            extra_sales_raw = read_sales_file(extra_sales_file)
            st.session_state.extra_sales_df = extra_sales_raw
        except Exception:
            st.session_state.extra_sales_df = None

    # Process quarantine file and extract product names
    if quarantine_file is not None:
        try:
            quarantine_df = read_inventory_file(quarantine_file)
            # Normalize column names
            quarantine_df.columns = quarantine_df.columns.astype(str).str.strip().str.lower()
            # Detect product name column
            quarantine_name_col = detect_column(
                quarantine_df.columns, 
                [normalize_col(a) for a in INV_NAME_ALIASES]
            )
            if quarantine_name_col:
                # Extract and normalize product names, filtering out NaN/null/empty values
                quarantined_items = set(
                    item for item in 
                    quarantine_df[quarantine_name_col]
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .tolist()
                    if item  # Filter out empty strings
                )
                st.session_state.quarantined_items = quarantined_items
            else:
                st.warning("Could not detect product name column in quarantine file. Quarantine filter not applied.")
                st.session_state.quarantined_items = set()
        except Exception as e:
            st.error(f"Error reading quarantine file: {e}")
            st.session_state.quarantined_items = set()
    else:
        # No quarantine file uploaded
        st.session_state.quarantined_items = set()

    if st.session_state.inv_raw_df is None or st.session_state.sales_raw_df is None:
        if data_mode == "📁 Uploads":
            st.info("📂 Upload inventory + product sales files to continue.")
        else:
            if _DUTCHIE_CLIENT_AVAILABLE:
                _dc_check = DutchieConfig.from_env_and_secrets()
                if not _dc_check.is_configured():
                    st.warning(
                        "🔴 **Dutchie Live** mode is active but API credentials are not configured.  "
                        f"Missing: `{'`, `'.join(_dc_check.missing_keys())}`.  "
                        "See *docs/dutchie.md* for setup instructions, or switch to "
                        "**📁 Uploads** mode in the sidebar."
                    )
                else:
                    st.warning(
                        "🔴 **Dutchie Live** mode is active but no data was returned.  "
                        "Credentials are configured — add the real API calls in "
                        "`dutchie_client.py → fetch_dutchie_data` to enable live data."
                    )
            else:
                st.error("❌ dutchie_client module is not available.")
        st.stop()

    try:
        inv_df = st.session_state.inv_raw_df.copy()
        sales_raw = st.session_state.sales_raw_df.copy()

        # -------- INVENTORY --------
        inv_df.columns = inv_df.columns.astype(str).str.strip().str.lower()

        name_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_NAME_ALIASES])
        cat_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_CAT_ALIASES])
        qty_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_QTY_ALIASES])
        sku_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_SKU_ALIASES])
        batch_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_BATCH_ALIASES])
        cost_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_COST_ALIASES])
        retail_price_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_RETAIL_PRICE_ALIASES])
        strain_type_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_STRAIN_TYPE_ALIASES])

        if not (name_col and cat_col and qty_col):
            st.error(
                "Could not auto-detect inventory columns (product / category / on-hand). "
                "Check your Inventory export headers."
            )
            st.stop()

        inv_df = inv_df.rename(columns={name_col: "itemname", cat_col: "subcategory", qty_col: "onhandunits"})
        if sku_col:
            inv_df = inv_df.rename(columns={sku_col: "sku"})
        if batch_col:
            inv_df = inv_df.rename(columns={batch_col: "batch"})
        if strain_type_col:
            inv_df = inv_df.rename(columns={strain_type_col: "_explicit_strain_type"})
        if retail_price_col:
            inv_df = inv_df.rename(columns={retail_price_col: "retail_price"})
            inv_df["retail_price"] = parse_currency_to_float(inv_df["retail_price"])
        # Always derive unit_cost as INV_COST_RETAIL_RATIO of retail_price (overrides any explicit cost column)
        if "retail_price" in inv_df.columns:
            inv_df["unit_cost"] = inv_df["retail_price"].fillna(0) * INV_COST_RETAIL_RATIO
        elif cost_col:
            inv_df = inv_df.rename(columns={cost_col: "unit_cost"})
            inv_df["unit_cost"] = parse_currency_to_float(inv_df["unit_cost"]).fillna(0)

        # Normalize itemname for better matching
        inv_df["itemname"] = inv_df["itemname"].astype(str).str.strip()
        
        inv_df["onhandunits"] = pd.to_numeric(inv_df["onhandunits"], errors="coerce").fillna(0)

        # -------- Inventory Deduplication (Product Name + Batch ID) --------
        inv_df, num_dupes_removed, dedupe_log = deduplicate_inventory(inv_df)
        
        # Display deduplication results to user
        if num_dupes_removed > 0:
            st.sidebar.success(dedupe_log)
        elif "No batch" not in dedupe_log and "No inventory" not in dedupe_log:
            st.sidebar.info(dedupe_log)

        inv_df["subcategory"] = inv_df["subcategory"].apply(normalize_rebelle_category)
        # Derive strain_type from name/category, then prefer explicit column if present
        inv_df["strain_type"] = inv_df.apply(lambda x: extract_strain_type(x.get("itemname", ""), x.get("subcategory", "")), axis=1)
        if "_explicit_strain_type" in inv_df.columns:
            explicit = inv_df["_explicit_strain_type"].astype(str).str.strip().str.lower()
            valid = explicit.isin(VALID_STRAIN_TYPES)
            inv_df.loc[valid, "strain_type"] = explicit[valid]
            inv_df = inv_df.drop(columns=["_explicit_strain_type"])
        inv_df["packagesize"] = inv_df.apply(lambda x: extract_size(x.get("itemname", ""), x.get("subcategory", "")), axis=1)
        inv_df["product_name"] = inv_df["itemname"]  # alias for product-level groupings; itemname retained for existing merges

        inv_summary = (
            inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["onhandunits"]
            .sum()
            .reset_index()
        )
        if "unit_cost" in inv_df.columns:
            _cost_summary = (
                inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["unit_cost"]
                .median()
                .reset_index()
            )
            inv_summary = inv_summary.merge(_cost_summary, on=["subcategory", "strain_type", "packagesize"], how="left")
        if "retail_price" in inv_df.columns:
            _retail_summary = (
                inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["retail_price"]
                .median()
                .reset_index()
            )
            inv_summary = inv_summary.merge(_retail_summary, on=["subcategory", "strain_type", "packagesize"], how="left")

        # -------- PRODUCT-LEVEL INVENTORY GROUPING --------
        inv_product = (
            inv_df.groupby(["subcategory", "product_name", "strain_type", "packagesize"], dropna=False)["onhandunits"]
            .sum()
            .reset_index()
        )

        # -------- SALES (qty-based ONLY) --------
        # Normalize column names: trim whitespace and lowercase
        sales_raw.columns = sales_raw.columns.astype(str).str.strip().str.lower()

        name_col_sales = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_NAME_ALIASES])
        qty_col_sales = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_QTY_ALIASES])
        mc_col = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_CAT_ALIASES])
        sales_sku_col = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_SKU_ALIASES])

        if not (name_col_sales and qty_col_sales and mc_col):
            missing_cols = []
            if not name_col_sales:
                missing_cols.append("product name")
            if not qty_col_sales:
                missing_cols.append("units/quantity sold")
            if not mc_col:
                missing_cols.append("category")
            
            st.error(
                f"Product Sales file detected but could not find required columns: {', '.join(missing_cols)}.\n\n"
                "Tip: Use Dutchie 'Product Sales Report' (qty) without editing headers.\n\n"
                f"Available columns: {', '.join(sales_raw.columns[:10])}..."
            )
            st.stop()

        sales_raw = sales_raw.rename(columns={name_col_sales: "product_name", qty_col_sales: "unitssold", mc_col: "mastercategory"})
        if sales_sku_col:
            sales_raw = sales_raw.rename(columns={sales_sku_col: "sku"})

        # Detect and rename optional new-format columns
        sales_batch_col = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_BATCH_ALIASES])
        sales_package_col = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_PACKAGE_ALIASES])
        sales_net_sales_col = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_REV_ALIASES])
        sales_order_id_col = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_ORDER_ID_ALIASES])
        sales_order_time_col = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_ORDER_TIME_ALIASES])
        if sales_batch_col and sales_batch_col != "batch_id":
            sales_raw = sales_raw.rename(columns={sales_batch_col: "batch_id"})
        if sales_package_col and sales_package_col != "package_id":
            sales_raw = sales_raw.rename(columns={sales_package_col: "package_id"})
        if sales_net_sales_col and sales_net_sales_col != "net_sales":
            sales_raw = sales_raw.rename(columns={sales_net_sales_col: "net_sales"})
        if sales_order_id_col and sales_order_id_col != "order_id":
            sales_raw = sales_raw.rename(columns={sales_order_id_col: "order_id"})
        if sales_order_time_col and sales_order_time_col != "order_time":
            sales_raw = sales_raw.rename(columns={sales_order_time_col: "order_time"})

        # Normalize product names for better matching
        sales_raw["product_name"] = sales_raw["product_name"].astype(str).str.strip()
        
        sales_raw["unitssold"] = pd.to_numeric(sales_raw["unitssold"], errors="coerce").fillna(0)
        sales_raw["mastercategory"] = sales_raw["mastercategory"].astype(str).str.strip()
        sales_raw["mastercategory"] = sales_raw["mastercategory"].apply(normalize_rebelle_category)

        sales_df = sales_raw[
            ~sales_raw["mastercategory"].astype(str).str.contains("accessor", na=False)
            & (sales_raw["mastercategory"] != "all")
        ].copy()

        sales_df["packagesize"] = sales_df.apply(lambda row: extract_size(row.get("product_name", ""), row.get("mastercategory", "")), axis=1)
        sales_df["strain_type"] = sales_df.apply(lambda row: extract_strain_type(row.get("product_name", ""), row.get("mastercategory", "")), axis=1)

        # -------- SALES DETAIL (per-row, deduplicated, for SKU drilldown) --------
        sales_detail_df = sales_df.copy()
        sales_detail_df["product"] = sales_detail_df["product_name"].astype(str).str.strip()
        if "net_sales" in sales_detail_df.columns:
            sales_detail_df["net_sales"] = pd.to_numeric(sales_detail_df["net_sales"], errors="coerce").fillna(0)
        # Deduplicate exact duplicate exported rows to prevent double counting
        sales_detail_df = sales_detail_df.drop_duplicates()

        sales_summary = (
            sales_df.groupby(["mastercategory", "packagesize"], dropna=False)["unitssold"]
            .sum()
            .reset_index()
        )
        sales_summary["avgunitsperday"] = (sales_summary["unitssold"] / max(int(date_diff), 1)) * float(velocity_adjustment)

        # -------- PRODUCT-LEVEL SALES GROUPING --------
        sales_product = (
            sales_df.groupby(["mastercategory", "product_name", "strain_type", "packagesize"], dropna=False)["unitssold"]
            .sum()
            .reset_index()
        )
        sales_product["avgunitsperday"] = (sales_product["unitssold"] / max(int(date_diff), 1)) * float(velocity_adjustment)

        detail_product = pd.merge(
            inv_product,
            sales_product,
            how="left",
            left_on=["subcategory", "product_name", "strain_type", "packagesize"],
            right_on=["mastercategory", "product_name", "strain_type", "packagesize"],
        ).fillna(0)

        detail = pd.merge(
            inv_summary,
            sales_summary,
            how="left",
            left_on=["subcategory", "packagesize"],
            right_on=["mastercategory", "packagesize"],
        ).fillna(0)

        # ---- FLOWER 28g educated guess ----
        flower_mask = detail["subcategory"].astype(str).str.contains("flower", na=False)
        flower_cats = detail.loc[flower_mask, "subcategory"].unique().tolist()

        def estimate_28g_from_flower_sales(cat_name: str):
            direct = sales_df[(sales_df["mastercategory"] == cat_name) & (sales_df["packagesize"] == "28g")]
            if not direct.empty:
                units_28 = float(direct["unitssold"].sum())
                avg_28 = (units_28 / max(int(date_diff), 1)) * float(velocity_adjustment)
                return units_28, avg_28

            cat_sales = sales_df[sales_df["mastercategory"] == cat_name].copy()
            if cat_sales.empty:
                return 0.0, 0.0

            total_grams = 0.0
            for _, r in cat_sales.iterrows():
                grams = _parse_grams_from_size(r.get("packagesize", "unspecified"))
                if grams is None:
                    continue
                total_grams += float(r.get("unitssold", 0)) * grams

            if total_grams <= 0:
                return 0.0, 0.0

            est_oz_units = total_grams / 28.0
            avg_oz = (est_oz_units / max(int(date_diff), 1)) * float(velocity_adjustment)
            return float(est_oz_units), float(avg_oz)

        missing_rows = []
        for cat in flower_cats:
            has_28 = ((detail["subcategory"] == cat) & (detail["packagesize"] == "28g")).any()
            if not has_28:
                units_28, avg_28 = estimate_28g_from_flower_sales(cat)
                missing_rows.append({
                    "subcategory": cat,
                    "strain_type": "unspecified",
                    "packagesize": "28g",
                    "onhandunits": 0,
                    "mastercategory": cat,
                    "unitssold": units_28,
                    "avgunitsperday": avg_28,
                })
            else:
                row_mask = (detail["subcategory"] == cat) & (detail["packagesize"] == "28g")
                if row_mask.any():
                    cur_avg = float(detail.loc[row_mask, "avgunitsperday"].iloc[0])
                    if cur_avg == 0:
                        units_28, avg_28 = estimate_28g_from_flower_sales(cat)
                        if avg_28 > 0:
                            detail.loc[row_mask, "unitssold"] = units_28
                            detail.loc[row_mask, "avgunitsperday"] = avg_28

        if missing_rows:
            detail = pd.concat([detail, pd.DataFrame(missing_rows)], ignore_index=True)

        # ---- EDIBLES 500mg educated guess ----
        edibles_mask = detail["subcategory"].astype(str).str.contains("edible", na=False)
        edibles_cats = detail.loc[edibles_mask, "subcategory"].unique().tolist()

        def estimate_500mg_from_edible_sales(cat_name: str):
            direct = sales_df[(sales_df["mastercategory"] == cat_name) & (sales_df["packagesize"] == "500mg")]
            if not direct.empty:
                units_500 = float(direct["unitssold"].sum())
                avg_500 = (units_500 / max(int(date_diff), 1)) * float(velocity_adjustment)
                return units_500, avg_500

            cat_sales = sales_df[sales_df["mastercategory"] == cat_name].copy()
            if cat_sales.empty:
                return 0.0, 0.0

            total_mg = 0.0
            for _, r in cat_sales.iterrows():
                mg = _parse_mg_from_size(r.get("packagesize", "unspecified"))
                if mg is None:
                    continue
                total_mg += float(r.get("unitssold", 0)) * mg

            if total_mg <= 0:
                return 0.0, 0.0

            est_500_units = total_mg / 500.0
            avg_500 = (est_500_units / max(int(date_diff), 1)) * float(velocity_adjustment)
            return float(est_500_units), float(avg_500)

        edibles_missing = []
        for cat in edibles_cats:
            has_500 = ((detail["subcategory"] == cat) & (detail["packagesize"] == "500mg")).any()
            if not has_500:
                units_500, avg_500 = estimate_500mg_from_edible_sales(cat)
                edibles_missing.append({
                    "subcategory": cat,
                    "strain_type": "unspecified",
                    "packagesize": "500mg",
                    "onhandunits": 0,
                    "mastercategory": cat,
                    "unitssold": units_500,
                    "avgunitsperday": avg_500,
                })
            else:
                row_mask = (detail["subcategory"] == cat) & (detail["packagesize"] == "500mg")
                if row_mask.any():
                    cur_avg = float(detail.loc[row_mask, "avgunitsperday"].iloc[0])
                    if cur_avg == 0:
                        units_500, avg_500 = estimate_500mg_from_edible_sales(cat)
                        if avg_500 > 0:
                            detail.loc[row_mask, "unitssold"] = units_500
                            detail.loc[row_mask, "avgunitsperday"] = avg_500

        if edibles_missing:
            detail = pd.concat([detail, pd.DataFrame(edibles_missing)], ignore_index=True)

        # ============================================================
        # DOH + Reorder
        # ============================================================
        detail["daysonhand"] = np.where(
            detail["avgunitsperday"] > 0,
            detail["onhandunits"] / detail["avgunitsperday"],
            0,
        )
        detail["daysonhand"] = detail["daysonhand"].replace([np.inf, -np.inf], 0).fillna(0).astype(int)

        detail["reorderqty"] = np.where(
            detail["daysonhand"] < doh_threshold,
            np.ceil((doh_threshold - detail["daysonhand"]) * detail["avgunitsperday"]),
            0,
        ).astype(int)

        def tag(row):
            if row["daysonhand"] <= 7 and row["avgunitsperday"] > 0:
                return "1 – Reorder ASAP"
            if row["daysonhand"] <= 21 and row["avgunitsperday"] > 0:
                return "2 – Watch Closely"
            if row["avgunitsperday"] == 0:
                return "4 – Dead Item"
            return "3 – Comfortable Cover"

        detail["reorderpriority"] = detail.apply(tag, axis=1)

        # Product-level DOH
        detail_product["avgunitsperday"] = pd.to_numeric(detail_product["avgunitsperday"], errors="coerce").fillna(0)
        detail_product["onhandunits"] = pd.to_numeric(detail_product["onhandunits"], errors="coerce").fillna(0)
        detail_product["daysonhand"] = np.where(
            detail_product["avgunitsperday"] > 0,
            detail_product["onhandunits"] / detail_product["avgunitsperday"],
            0,
        )
        detail_product["daysonhand"] = detail_product["daysonhand"].replace([np.inf, -np.inf], 0).fillna(0).astype(int)

        # Cache for cross-reference in PO Builder
        st.session_state.detail_cached_df = detail.copy()
        st.session_state.detail_product_cached_df = detail_product.copy()
        st.session_state.doh_threshold_cache = int(doh_threshold)

        # =======================
        # POLISHED BUYER OVERVIEW
        # =======================
        _revenue_series = pd.to_numeric(sales_df["net_sales"], errors="coerce").fillna(0) if "net_sales" in sales_df.columns else pd.Series(dtype=float)
        _total_revenue = float(_revenue_series.sum()) if not _revenue_series.empty else 0.0
        _avg_doh = float(pd.to_numeric(detail["daysonhand"], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0).mean()) if not detail.empty else 0.0
        _active_skus = int((pd.to_numeric(detail["onhandunits"], errors="coerce").fillna(0) > 0).sum()) if "onhandunits" in detail.columns else 0
        _low_stock = int(((detail["daysonhand"] > 0) & (detail["daysonhand"] <= doh_threshold)).sum()) if "daysonhand" in detail.columns else 0
        _oos = int((pd.to_numeric(detail["onhandunits"], errors="coerce").fillna(0) <= 0).sum()) if "onhandunits" in detail.columns else 0
        _health_score = max(0, min(100, int(100 - ((_low_stock * 2) + (_oos * 3)))))

        render_metric_tiles(
            [
                {"label": "Total Revenue", "value": f"${_total_revenue:,.0f}", "help": "Current sales window", "color": "green"},
                {"label": "Avg DOH", "value": f"{_avg_doh:,.1f}", "help": "Days on hand across lines", "color": "orange"},
                {"label": "Active SKUs", "value": f"{_active_skus:,}", "help": "On-hand inventory > 0", "color": "blue"},
                {"label": "Low Stock", "value": f"{_low_stock:,}", "help": f"DOH ≤ {doh_threshold}", "color": "yellow"},
                {"label": "Out of Stock", "value": f"{_oos:,}", "help": "Requires replenishment", "color": "red"},
            ]
        )

        _ov1, _ov2 = st.columns([1.7, 1])
        with _ov1:
            chart_card_start("Sales Trend", "Net sales trend over available order/report dates.")
            _sales_date_col = next((c for c in sales_raw.columns if "date" in str(c).lower() or "time" in str(c).lower()), None)
            if _sales_date_col is None:
                st.info("No date column detected for trend chart.")
            else:
                _trend = sales_raw.copy()
                _trend["_date"] = pd.to_datetime(_trend[_sales_date_col], errors="coerce").dt.date
                _trend = _trend[_trend["_date"].notna()]
                if _trend.empty:
                    st.info("No valid date rows for trend chart.")
                else:
                    if "net_sales" in _trend.columns:
                        _trend["_metric"] = pd.to_numeric(_trend["net_sales"], errors="coerce").fillna(0)
                    else:
                        _trend["_metric"] = pd.to_numeric(_trend.get("unitssold", 0), errors="coerce").fillna(0)
                    _trend_plot = _trend.groupby("_date", as_index=False)["_metric"].sum().sort_values("_date")
                    if PLOTLY_AVAILABLE:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=_trend_plot["_date"], y=_trend_plot["_metric"], mode="lines+markers", line={"color": "#ff9a3c", "width": 3}))
                        fig.update_layout(
                            margin={"l": 10, "r": 10, "t": 10, "b": 10},
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            height=280,
                            font={"color": "rgba(255,255,255,0.88)"},
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.line_chart(_trend_plot.set_index("_date")["_metric"])
            chart_card_end()
        with _ov2:
            chart_card_start("Revenue by Category", "Revenue mix by category (or units fallback).")
            _cat_metric = "net_sales" if "net_sales" in sales_df.columns else "unitssold"
            _cat_df = (
                sales_df.groupby("mastercategory", as_index=False)[_cat_metric].sum().sort_values(_cat_metric, ascending=False)
                if "mastercategory" in sales_df.columns and not sales_df.empty
                else pd.DataFrame()
            )
            if _cat_df.empty:
                st.info("No category distribution available.")
            elif PLOTLY_AVAILABLE:
                fig = go.Figure(
                    go.Pie(
                        labels=_cat_df["mastercategory"].astype(str),
                        values=_cat_df[_cat_metric],
                        hole=0.48,
                        marker={"colors": ["#ff9a3c", "#5aa8ff", "#4cd388", "#f3c74c", "#ff6161"]},
                    )
                )
                fig.update_layout(
                    margin={"l": 10, "r": 10, "t": 10, "b": 10},
                    paper_bgcolor="rgba(0,0,0,0)",
                    font={"color": "rgba(255,255,255,0.88)"},
                    height=280,
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.bar_chart(_cat_df.set_index("mastercategory")[_cat_metric])
            chart_card_end()

        _tbl_col, _health_col = st.columns([1.7, 1])
        with _tbl_col:
            chart_card_start("Top Slow Movers", "Highest days-on-hand with low movement.")
            _slow_cols = [c for c in ["subcategory", "product_name", "packagesize", "daysonhand", "reorderpriority"] if c in detail_product.columns]
            _slow = detail_product.copy() if not detail_product.empty else pd.DataFrame()
            if _slow.empty or "daysonhand" not in _slow.columns:
                st.info("No slow mover rows available yet.")
            else:
                _slow = _slow.sort_values("daysonhand", ascending=False).head(12)
                st.dataframe(_slow[_slow_cols], use_container_width=True, hide_index=True)
            chart_card_end()
        with _health_col:
            chart_card_start("Inventory Health", "Composite score from low-stock and OOS pressure.")
            if PLOTLY_AVAILABLE:
                fig = go.Figure(go.Indicator(mode="gauge+number", value=_health_score, gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#ff9a3c"}}))
                fig.update_layout(height=260, margin={"l": 10, "r": 10, "t": 20, "b": 0}, paper_bgcolor="rgba(0,0,0,0)", font={"color": "rgba(255,255,255,0.88)"})
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.progress(max(0, min(100, _health_score)) / 100.0, text=f"Health score: {_health_score}/100")
            chart_card_end()

        _insights = [
            f"{_low_stock} lines are in low-stock range (DOH <= {doh_threshold}).",
            f"{_oos} lines are out of stock and need immediate attention.",
            f"Average DOH is {_avg_doh:,.1f} days across filtered rows.",
        ]
        _actions = ["Prioritize Reorders", "Review Aging Lots", "Open Ask Doobie"]
        render_ai_brief(_insights, _actions)
        render_action_button("Open Ask Doobie")
        st.caption("Use the Main AI Copilot in the sidebar to ask buyer questions.")

        # =======================
        # SUMMARY + CLICK FILTERS
        # =======================
        st.markdown("### Inventory Summary")
        total_units = int(detail["unitssold"].sum())
        reorder_asap = int((detail["reorderpriority"] == "1 – Reorder ASAP").sum())

        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"Units Sold (Granular Size-Level): {total_units}", key="btn_total_units"):
                st.session_state.metric_filter = "All"
        with col2:
            if st.button(f"Reorder ASAP (Lines): {reorder_asap}", key="btn_reorder_asap"):
                st.session_state.metric_filter = "Reorder ASAP"

        if st.session_state.metric_filter == "Reorder ASAP":
            detail_view = detail[detail["reorderpriority"] == "1 – Reorder ASAP"].copy()
        else:
            detail_view = detail.copy()

        # Enrich summary rows with product context (product_count, top_products)
        try:
            _dp = detail_product[["subcategory", "product_name", "strain_type", "packagesize", "unitssold"]].copy()
            _dp["unitssold"] = pd.to_numeric(_dp["unitssold"], errors="coerce").fillna(0)
            _dp_sorted = _dp.sort_values("unitssold", ascending=False)
            _top_products = (
                _dp_sorted.groupby(["subcategory", "strain_type", "packagesize"], dropna=False, sort=False)["product_name"]
                .apply(lambda x: ", ".join(x.astype(str).head(5).tolist()))
                .reset_index()
                .rename(columns={"product_name": "top_products"})
            )
            _product_counts = (
                _dp.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["product_name"]
                .nunique()
                .reset_index()
                .rename(columns={"product_name": "product_count"})
            )
            _prod_ctx_df = _top_products.merge(_product_counts, on=["subcategory", "strain_type", "packagesize"], how="left")
            detail_view = detail_view.merge(_prod_ctx_df, on=["subcategory", "strain_type", "packagesize"], how="left")
            detail_view["product_count"] = detail_view["product_count"].fillna(0).astype(int)
            detail_view["top_products"] = detail_view["top_products"].fillna("")
        except Exception:
            pass

        st.markdown(f"*Current filter:* **{st.session_state.metric_filter}**")
        st.markdown("### Forecast Table")

        # Quick view: Category DOS at a glance
        try:
            cat_quick = (
                detail_view.groupby("subcategory", dropna=False)
                .agg(
                    onhandunits=("onhandunits", "sum"),
                    avgunitsperday=("avgunitsperday", "sum"),
                    reorder_lines=("reorderpriority", lambda x: int((x == "1 – Reorder ASAP").sum())),
                )
                .reset_index()
            )
            cat_quick["category_dos"] = np.where(
                cat_quick["avgunitsperday"] > 0,
                cat_quick["onhandunits"] / cat_quick["avgunitsperday"],
                0,
            )
            cat_quick["category_dos"] = cat_quick["category_dos"].replace([np.inf, -np.inf], 0).fillna(0).astype(int)
            # Enrich category DOS with product context
            try:
                _dp_cat = detail_product[["subcategory", "product_name", "unitssold"]].copy()
                _dp_cat["unitssold"] = pd.to_numeric(_dp_cat["unitssold"], errors="coerce").fillna(0)
                _dp_cat_sorted = _dp_cat.sort_values("unitssold", ascending=False)
                _cat_top = (
                    _dp_cat_sorted.groupby("subcategory", dropna=False, sort=False)["product_name"]
                    .apply(lambda x: ", ".join(x.astype(str).head(5).tolist()))
                    .reset_index()
                    .rename(columns={"product_name": "top_products"})
                )
                _cat_count = (
                    _dp_cat.groupby("subcategory", dropna=False)["product_name"]
                    .nunique()
                    .reset_index()
                    .rename(columns={"product_name": "product_count"})
                )
                _cat_ctx_df = _cat_top.merge(_cat_count, on="subcategory", how="left")
                cat_quick = cat_quick.merge(_cat_ctx_df, on="subcategory", how="left")
                cat_quick["product_count"] = cat_quick["product_count"].fillna(0).astype(int)
                cat_quick["top_products"] = cat_quick["top_products"].fillna("")
            except Exception:
                pass
            st.markdown("#### Category DOS (at a glance)")
            _cat_q_cols = ["subcategory", "category_dos", "reorder_lines"]
            if "product_count" in cat_quick.columns:
                _cat_q_cols += ["product_count", "top_products"]
            st.dataframe(
                cat_quick[_cat_q_cols].sort_values(
                    ["reorder_lines", "category_dos"], ascending=[False, True]
                ),
                use_container_width=True,
            )
        except Exception:
            pass

        def red_low(val):
            try:
                v = int(val)
                return "color:#FF3131" if v < doh_threshold else ""
            except Exception:
                return ""

        all_cats = sorted(detail_view["subcategory"].unique())

        def cat_sort_key(c):
            c_low = str(c).lower()
            if c_low in REB_CATEGORIES:
                return (REB_CATEGORIES.index(c_low), c_low)
            return (len(REB_CATEGORIES), c_low)

        all_cats_sorted = sorted(all_cats, key=cat_sort_key)

        selected_cats = st.sidebar.multiselect(
            "Visible Categories",
            all_cats_sorted,
            default=all_cats_sorted,
        )
        detail_view = detail_view[detail_view["subcategory"].isin(selected_cats)]

        show_product_rows = st.sidebar.checkbox(
            "Show product-level rows",
            value=False,
            help="When ON, shows a product-level table with explicit product_name column below the summary.",
            key="show_product_rows",
        )

        display_cols = [
            "top_products",
            "mastercategory",
            "subcategory",
            "strain_type",
            "packagesize",
            "onhandunits",
            "unitssold",
            "avgunitsperday",
            "daysonhand",
            "reorderqty",
            "reorderpriority",
            "product_count",
        ]
        display_cols = [c for c in display_cols if c in detail_view.columns]

        # ========= Export Forecast Table (Excel) — requested =========
        def build_forecast_export_bytes(df: pd.DataFrame) -> bytes:
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Forecast")
            buf.seek(0)
            return buf.read()

        export_df = detail_view[display_cols].copy()
        st.download_button(
            "📥 Export Forecast Table (Excel)",
            data=build_forecast_export_bytes(export_df),
            file_name="forecast_table.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # ========= SKU drilldown for flagged reorder products (weighted) =========
        def sku_drilldown_table(cat, size, strain_type):
            """
            Returns two tables:
            1) SKU-level view aggregated by product+batch (deduplicated) for this row slice
            2) Batch rollup (if inventory batch data exists)

            IMPORTANT: Always returns (sku_df, batch_df) so callers can safely unpack.
            """
            empty = (pd.DataFrame(), pd.DataFrame())

            # --- SALES DETAIL SLICE (deduplicated, aggregated) ---
            sd = sales_detail_df[
                (sales_detail_df["mastercategory"] == cat) & (sales_detail_df["packagesize"] == size)
            ].copy()

            if str(strain_type).lower() != "unspecified":
                sd = sd[sd["strain_type"].astype(str).str.lower() == str(strain_type).lower()]

            if sd.empty:
                return empty

            # Aggregate by product + batch_id (and package_id if present) to prevent duplicate listing
            has_batch = "batch_id" in sd.columns
            has_package = "package_id" in sd.columns
            has_net_sales = "net_sales" in sd.columns
            has_sku = "sku" in sd.columns

            group_cols = ["product"]
            if has_batch:
                group_cols.append("batch_id")
            if has_package:
                group_cols.append("package_id")

            agg_dict = {"unitssold": "sum"}
            if has_net_sales:
                agg_dict["net_sales"] = "sum"
            if has_sku:
                # SKU is expected to uniquely correspond to a product; take first within the group
                agg_dict["sku"] = "first"

            sku_df = sd.groupby(group_cols, dropna=False).agg(agg_dict).reset_index()
            sku_df["est_units_per_day"] = (sku_df["unitssold"] / max(int(date_diff), 1)) * float(velocity_adjustment)

            # Build ordered output columns
            out_cols = ["product"]
            if has_batch:
                out_cols.append("batch_id")
            if has_package:
                out_cols.append("package_id")
            out_cols.append("unitssold")
            if has_net_sales:
                out_cols.append("net_sales")
            out_cols.append("est_units_per_day")
            if has_sku:
                out_cols.append("sku")

            sku_df = sku_df[out_cols].sort_values("est_units_per_day", ascending=False).head(50)
            sku_df = sku_df.rename(columns={"product": "product_name"})

            # --- INVENTORY SLICE ---
            idf = inv_df[(inv_df["subcategory"] == cat) & (inv_df["packagesize"] == size)].copy()
            if str(strain_type).lower() != "unspecified":
                idf = idf[idf["strain_type"].astype(str).str.lower() == str(strain_type).lower()]

            batch_df = pd.DataFrame()
            if not idf.empty and "batch" in idf.columns:
                batch_df = (
                    idf.groupby("batch", dropna=False)["onhandunits"]
                    .sum()
                    .reset_index()
                    .rename(columns={"onhandunits": "batch_onhandunits"})
                    .sort_values("batch_onhandunits", ascending=False)
                )

            return sku_df, batch_df

        # Expanders by category
        for cat in sorted(detail_view["subcategory"].unique(), key=cat_sort_key):
            group = detail_view[detail_view["subcategory"] == cat].copy()

            with st.expander(cat.title()):
                try:
                    denom = float(group["avgunitsperday"].sum())
                    cat_dos = (float(group["onhandunits"].sum()) / denom) if denom > 0 else 0.0
                except Exception:
                    cat_dos = 0.0
                st.markdown(f"**Category DOS:** {int(cat_dos)} days")

                g = group[display_cols].copy()
                st.dataframe(
                    g.style.map(red_low, subset=["daysonhand"]),
                    use_container_width=True,
                )

                flagged = group[group["reorderpriority"] == "1 – Reorder ASAP"].copy()
                if not flagged.empty:
                    st.markdown("#### 🔎 Flagged Reorder Lines — View SKUs (Weighted by Velocity)")
                    for _, r in flagged.iterrows():
                        row_label = f"{r.get('strain_type','unspecified')} • {r.get('packagesize','unspecified')} • Reorder Qty: {int(r.get('reorderqty',0))}"
                        with st.expander(f"View SKUs — {row_label}", expanded=False):
                            sku_df_out, batch_df_out = sku_drilldown_table(
                                cat=r.get("subcategory"),
                                size=r.get("packagesize"),
                                strain_type=r.get("strain_type"),
                            )
                            if sku_df_out.empty:
                                st.info("No matching SKU-level sales rows found for this slice.")
                            else:
                                st.dataframe(sku_df_out, use_container_width=True)
                            if not batch_df_out.empty:
                                st.markdown("##### 🧬 Batch / Lot Breakdown (On-Hand)")
                                st.dataframe(batch_df_out, use_container_width=True)

        # ========= Product-Level Detail Table (toggle) =========
        if show_product_rows and not detail_product.empty:
            st.markdown("---")
            st.markdown("### 📦 Product-Level Rows")
            dpv = detail_product[detail_product["subcategory"].isin(selected_cats)].copy()
            dpv["unitssold"] = pd.to_numeric(dpv["unitssold"], errors="coerce").fillna(0)
            dpv["onhandunits"] = pd.to_numeric(dpv["onhandunits"], errors="coerce").fillna(0)
            _PROD_ROW_LIMIT = PRODUCT_TABLE_DISPLAY_LIMIT
            if len(dpv) > _PROD_ROW_LIMIT:
                st.caption(f"⚠️ Showing top {_PROD_ROW_LIMIT} rows by units sold. Download below for full data.")
                dpv = dpv.sort_values("unitssold", ascending=False).head(_PROD_ROW_LIMIT)
            prod_display_cols = [
                "product_name", "subcategory", "strain_type", "packagesize",
                "onhandunits", "unitssold", "avgunitsperday", "daysonhand",
            ]
            prod_display_cols = [c for c in prod_display_cols if c in dpv.columns]
            st.dataframe(dpv[prod_display_cols], use_container_width=True)
            st.download_button(
                "📥 Download Product-Level Table (Excel)",
                data=build_forecast_export_bytes(dpv[prod_display_cols]),
                file_name="product_level_forecast.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_product_level",
            )

        # ============================================================
        # SKU INVENTORY BUYER VIEW
        # ============================================================
        st.markdown("---")
        st.markdown("### 📋 SKU Inventory Buyer View")
        st.write(
            "Filter, sort, and analyze your inventory at the SKU level. "
            "Use tabs for focused views: Reorder, Overstock, or Expiring."
        )

        try:
            # -- Rebuild SKU-level inventory from raw data (self-contained) --
            _b_inv = st.session_state.inv_raw_df.copy()
            _b_inv.columns = _b_inv.columns.astype(str).str.strip().str.lower()

            _b_name_col = detect_column(_b_inv.columns, [normalize_col(a) for a in INV_NAME_ALIASES])
            _b_qty_col = detect_column(_b_inv.columns, [normalize_col(a) for a in INV_QTY_ALIASES])
            _b_cat_col = detect_column(_b_inv.columns, [normalize_col(a) for a in INV_CAT_ALIASES])
            _b_sku_col = detect_column(_b_inv.columns, [normalize_col(a) for a in INV_SKU_ALIASES])
            _b_cost_col = detect_column(_b_inv.columns, [normalize_col(a) for a in INV_COST_ALIASES])
            _b_retail_col = detect_column(_b_inv.columns, [normalize_col(a) for a in INV_RETAIL_PRICE_ALIASES])
            _b_brand_col = detect_column(_b_inv.columns, [normalize_col(a) for a in INV_BRAND_ALIASES])
            _b_expiry_col = detect_column(_b_inv.columns, [normalize_col(a) for a in INV_EXPIRY_ALIASES])

            if not (_b_name_col and _b_qty_col):
                st.warning("Could not detect required inventory columns (product name / on-hand) for Buyer View.")
            else:
                _b_rename = {_b_name_col: "itemname", _b_qty_col: "onhandunits"}
                if _b_cat_col:
                    _b_rename[_b_cat_col] = "category"
                if _b_sku_col:
                    _b_rename[_b_sku_col] = "sku"
                if _b_cost_col:
                    _b_rename[_b_cost_col] = "unit_cost"
                if _b_retail_col:
                    _b_rename[_b_retail_col] = "retail_price"
                if _b_brand_col:
                    _b_rename[_b_brand_col] = "brand_vendor"
                if _b_expiry_col:
                    _b_rename[_b_expiry_col] = "expiration_date"

                _b_inv = _b_inv.rename(columns=_b_rename)
                _b_inv["itemname"] = _b_inv["itemname"].astype(str).str.strip()
                _b_inv["onhandunits"] = pd.to_numeric(_b_inv["onhandunits"], errors="coerce").fillna(0)
                if "unit_cost" in _b_inv.columns:
                    _b_inv["unit_cost"] = parse_currency_to_float(_b_inv["unit_cost"])
                if "retail_price" in _b_inv.columns:
                    _b_inv["retail_price"] = parse_currency_to_float(_b_inv["retail_price"])
                if "expiration_date" in _b_inv.columns:
                    _b_inv["expiration_date"] = pd.to_datetime(_b_inv["expiration_date"], errors="coerce")

                # Aggregate to one row per SKU (sum on-hand, min expiry, first for others)
                _b_agg = {"onhandunits": "sum"}
                for _bc in ["unit_cost", "retail_price", "brand_vendor", "category", "sku"]:
                    if _bc in _b_inv.columns:
                        _b_agg[_bc] = "first"
                if "expiration_date" in _b_inv.columns:
                    _b_agg["expiration_date"] = "min"  # earliest expiry per SKU
                _b_sku_df = _b_inv.groupby("itemname", dropna=False).agg(_b_agg).reset_index()

                # Friendly notice for missing optional columns
                _b_missing = []
                if "unit_cost" not in _b_sku_df.columns:
                    _b_missing.append("wholesale unit cost (for $ on hand – cost)")
                if "retail_price" not in _b_sku_df.columns:
                    _b_missing.append("retail price / med price (for $ on hand – retail)")
                if "brand_vendor" not in _b_sku_df.columns:
                    _b_missing.append("vendor/brand")
                if "expiration_date" not in _b_sku_df.columns:
                    _b_missing.append("expiration date")
                if _b_missing:
                    st.info(
                        f"ℹ️ Optional columns not found in inventory file: "
                        f"{', '.join(_b_missing)}. "
                        "Add these columns to unlock full buyer view features."
                    )

                # ---- FILTER BAR (reuses sm-filter-bar CSS) ----
                st.markdown('<div class="sm-filter-bar">', unsafe_allow_html=True)
                st.markdown("##### 🔍 Buyer Filters & Settings")

                _bfr1, _bfr2, _bfr3, _bfr4 = st.columns([3, 2, 2, 2])
                with _bfr1:
                    _b_search = st.text_input(
                        "Search (SKU / Product / Brand)",
                        key="inv_b_search",
                        placeholder="Type to filter…",
                        help="Filters by product name, SKU, or brand/vendor (case-insensitive).",
                    )
                with _bfr2:
                    _b_vel_win = st.selectbox(
                        "Velocity window",
                        options=SLOW_MOVER_VELOCITY_WINDOWS,
                        index=1,
                        format_func=lambda d: f"Last {d} days",
                        key="inv_b_vel_win",
                        help=(
                            "Days used for avg weekly sales and DOH calculations. "
                            "Shorter = more recent; longer = smoother."
                        ),
                    )
                with _bfr3:
                    _b_top_n_lbl = {25: "Top 25", 50: "Top 50", 100: "Top 100", 0: "All"}
                    _b_top_n = st.selectbox(
                        "Show top N",
                        options=list(_b_top_n_lbl.keys()),
                        index=3,
                        format_func=lambda k: _b_top_n_lbl[k],
                        key="inv_b_top_n",
                    )
                with _bfr4:
                    _b_sort_by = st.selectbox(
                        "Sort by",
                        options=INVENTORY_SORT_OPTIONS,
                        key="inv_b_sort_by",
                    )

                _bfr5, _bfr6, _bfr7, _bfr8 = st.columns([3, 2, 2, 2])
                with _bfr5:
                    _b_cat_opts = ["All"]
                    if "category" in _b_sku_df.columns:
                        _b_cat_opts += sorted(
                            _b_sku_df["category"].dropna().astype(str).unique().tolist()
                        )
                    _b_cat = st.selectbox(
                        "Category / Subcategory", options=_b_cat_opts, key="inv_b_cat"
                    )
                with _bfr6:
                    _b_brand_opts = ["All"]
                    if "brand_vendor" in _b_sku_df.columns:
                        _b_brand_opts += sorted(
                            _b_sku_df["brand_vendor"].dropna().astype(str).unique().tolist()
                        )
                    _b_brand = st.selectbox(
                        "Vendor / Brand", options=_b_brand_opts, key="inv_b_brand"
                    )
                with _bfr7:
                    _b_exp_window = st.selectbox(
                        "Expiration window",
                        options=["Any", "<30 days", "<60 days", "<90 days"],
                        key="inv_b_exp_window",
                        help="Filter by days until earliest expiration date.",
                    )
                with _bfr8:
                    _b_onhand_only = st.toggle(
                        "On-hand > 0",
                        value=True,
                        key="inv_b_onhand_only",
                        help="Hide SKUs with zero units on hand.",
                    )

                _bfr9, _bfr10 = st.columns([2, 2])
                with _bfr9:
                    _b_doh_min = st.number_input(
                        "DOH min (days)",
                        min_value=0,
                        max_value=9998,
                        value=0,
                        step=1,
                        key="inv_b_doh_min",
                        help="Only show SKUs with DOH ≥ this value.",
                    )
                with _bfr10:
                    _b_doh_max = st.number_input(
                        "DOH max (days)",
                        min_value=0,
                        max_value=9999,
                        value=9999,
                        step=1,
                        key="inv_b_doh_max",
                        help="Only show SKUs with DOH ≤ this value (9999 = no upper limit).",
                    )

                st.markdown('</div>', unsafe_allow_html=True)

                # ---- COMPUTE VELOCITY ----
                _b_sales_raw = st.session_state.sales_raw_df.copy()
                _b_sales_raw.columns = _b_sales_raw.columns.astype(str).str.strip().str.lower()
                _b_sname_col = detect_column(
                    _b_sales_raw.columns, [normalize_col(a) for a in SALES_NAME_ALIASES]
                )
                _b_sqty_col = detect_column(
                    _b_sales_raw.columns, [normalize_col(a) for a in SALES_QTY_ALIASES]
                )
                _b_sdate_cols = [c for c in _b_sales_raw.columns if "date" in c]
                _b_sdate_col = _b_sdate_cols[0] if _b_sdate_cols else None

                if _b_sname_col and _b_sqty_col:
                    _b_sales_raw[_b_sqty_col] = pd.to_numeric(
                        _b_sales_raw[_b_sqty_col], errors="coerce"
                    ).fillna(0)
                    if _b_sdate_col:
                        _b_sales_raw[_b_sdate_col] = pd.to_datetime(
                            _b_sales_raw[_b_sdate_col], errors="coerce"
                        )
                        _b_cutoff = _b_sales_raw[_b_sdate_col].max() - pd.Timedelta(
                            days=_b_vel_win
                        )
                        _b_sw = _b_sales_raw[
                            _b_sales_raw[_b_sdate_col] >= _b_cutoff
                        ].copy()
                    else:
                        _b_sw = _b_sales_raw.copy()

                    _b_vel = (
                        _b_sw.groupby(_b_sname_col)[_b_sqty_col]
                        .sum()
                        .reset_index()
                        .rename(
                            columns={_b_sname_col: "itemname", _b_sqty_col: "total_sold"}
                        )
                    )
                    _b_vel["daily_run_rate"] = _b_vel["total_sold"] / max(_b_vel_win, 1)
                    _b_vel["avg_weekly_sales"] = _b_vel["daily_run_rate"] * 7
                else:
                    _b_vel = pd.DataFrame(
                        columns=["itemname", "total_sold", "daily_run_rate", "avg_weekly_sales"]
                    )

                # ---- MERGE INVENTORY + VELOCITY ----
                _b_merged = _b_sku_df.merge(_b_vel, on="itemname", how="left")
                _b_merged["daily_run_rate"] = _b_merged["daily_run_rate"].fillna(0)
                _b_merged["avg_weekly_sales"] = _b_merged["avg_weekly_sales"].fillna(0)
                _b_merged["total_sold"] = _b_merged["total_sold"].fillna(0)
                _b_merged["days_of_supply"] = np.where(
                    _b_merged["daily_run_rate"] > 0,
                    _b_merged["onhandunits"] / _b_merged["daily_run_rate"],
                    UNKNOWN_DAYS_OF_SUPPLY,
                )

                if "unit_cost" in _b_merged.columns:
                    _b_merged["dollars_on_hand"] = (
                        _b_merged["onhandunits"] * _b_merged["unit_cost"]
                    )
                if "retail_price" in _b_merged.columns:
                    _b_merged["retail_dollars_on_hand"] = (
                        _b_merged["onhandunits"] * _b_merged["retail_price"]
                    )

                _b_today = pd.Timestamp.today().normalize()
                if "expiration_date" in _b_merged.columns:
                    _b_merged["days_to_expire"] = (
                        _b_merged["expiration_date"] - _b_today
                    ).dt.days

                # Status badge: Reorder / Healthy / Overstock / Expiring / No Stock
                def _inv_status_badge(row) -> str:
                    on_hand = row["onhandunits"]
                    doh = row["days_of_supply"]
                    if on_hand <= 0:
                        return "⬛ No Stock"
                    if "days_to_expire" in row.index:
                        days_exp = row["days_to_expire"]
                        if pd.notna(days_exp) and days_exp < INVENTORY_EXPIRING_SOON_DAYS:
                            return "⚠️ Expiring"
                    if 0 < doh <= INVENTORY_REORDER_DOH_THRESHOLD:
                        return "🔴 Reorder"
                    if doh >= INVENTORY_OVERSTOCK_DOH_THRESHOLD:
                        return "🟠 Overstock"
                    return "✅ Healthy"

                _b_merged["status"] = _b_merged.apply(_inv_status_badge, axis=1)

                # ---- FILTER + SORT helper ----
                _b_exp_days_map = {"<30 days": 30, "<60 days": 60, "<90 days": 90}

                def _apply_inv_filters(df, tab_filter=None):
                    _wdf = df.copy()
                    if _b_onhand_only:
                        _wdf = _wdf[_wdf["onhandunits"] > 0]
                    if _b_cat != "All" and "category" in _wdf.columns:
                        _wdf = _wdf[_wdf["category"].astype(str) == _b_cat]
                    if _b_brand != "All" and "brand_vendor" in _wdf.columns:
                        _wdf = _wdf[_wdf["brand_vendor"].astype(str) == _b_brand]
                    if _b_exp_window != "Any" and "days_to_expire" in _wdf.columns:
                        _elim = _b_exp_days_map[_b_exp_window]
                        _wdf = _wdf[
                            _wdf["days_to_expire"].notna()
                            & (_wdf["days_to_expire"] < _elim)
                        ]
                    if _b_search.strip():
                        _q = _b_search.strip().lower()
                        _msk = _wdf["itemname"].str.lower().str.contains(_q, na=False)
                        if "sku" in _wdf.columns:
                            _msk |= (
                                _wdf["sku"].astype(str).str.lower().str.contains(_q, na=False)
                            )
                        if "brand_vendor" in _wdf.columns:
                            _msk |= (
                                _wdf["brand_vendor"]
                                .astype(str)
                                .str.lower()
                                .str.contains(_q, na=False)
                            )
                        _wdf = _wdf[_msk]
                    # DOH range filter
                    _wdf = _wdf[
                        (_wdf["days_of_supply"] >= _b_doh_min)
                        & (_wdf["days_of_supply"] <= _b_doh_max)
                    ]
                    if tab_filter is not None:
                        _wdf = tab_filter(_wdf)
                    _inv_sort_map = {
                        "$ on hand ↓": ("dollars_on_hand", False),
                        "DOH (high→low) ↓": ("days_of_supply", False),
                        "DOH (low→high) ↑": ("days_of_supply", True),
                        "Expiring soonest": ("days_to_expire", True),
                        "Avg weekly sales ↓": ("avg_weekly_sales", False),
                    }
                    _sc, _sasc = _inv_sort_map.get(_b_sort_by, ("days_of_supply", False))
                    if _sc in _wdf.columns:
                        _wdf = _wdf.sort_values(_sc, ascending=_sasc, na_position="last")
                    elif _b_sort_by == "Expiring soonest" and "days_to_expire" not in _wdf.columns:
                        # Fall back to DOH ascending when expiry column is unavailable
                        _wdf = _wdf.sort_values("days_of_supply", ascending=True, na_position="last")
                    elif _b_sort_by == "$ on hand ↓" and "dollars_on_hand" not in _wdf.columns:
                        # Fall back to DOH descending when cost column is unavailable
                        _wdf = _wdf.sort_values("days_of_supply", ascending=False, na_position="last")
                    if _b_top_n and _b_top_n > 0:
                        _wdf = _wdf.head(_b_top_n)
                    return _wdf

                # ---- KPI strip + decision-first table helper ----
                def _render_inv_table(df):
                    if df.empty:
                        st.success("✅ No SKUs match the current filters.")
                        return
                    # KPI strip
                    _skus_in_stock = int((df["onhandunits"] > 0).sum())
                    _total_dol = (
                        df["dollars_on_hand"].sum()
                        if "dollars_on_hand" in df.columns
                        else None
                    )
                    _total_retail_dol = (
                        df["retail_dollars_on_hand"].sum()
                        if "retail_dollars_on_hand" in df.columns
                        else None
                    )
                    _reorder_n = int((df["status"] == "🔴 Reorder").sum())
                    _overstock_n = int((df["status"] == "🟠 Overstock").sum())
                    _exp_mask = df["status"] == "⚠️ Expiring"
                    _exp_n = int(_exp_mask.sum())
                    _exp_dol = (
                        df.loc[_exp_mask, "dollars_on_hand"].sum()
                        if "dollars_on_hand" in df.columns
                        else None
                    )
                    # Determine how many KPI columns to show
                    _has_both_valuations = _total_dol is not None and _total_retail_dol is not None
                    if _has_both_valuations:
                        _kc1, _kc2, _kc3, _kc4, _kc5, _kc_exp = st.columns(6)
                    else:
                        _kc1, _kc2, _kc3, _kc4, _kc_exp = st.columns(5)
                    _kc1.metric(
                        "📦 SKUs in stock",
                        _skus_in_stock,
                        help="SKUs with on-hand > 0 in current view.",
                    )
                    if _has_both_valuations:
                        _kc2.metric(
                            "💰 Total $ on hand (Cost)",
                            f"${_total_dol:,.0f}",
                            help="Wholesale cost basis: on-hand units × unit cost.",
                        )
                        _kc3.metric(
                            "🏷️ Total $ on hand (Retail)",
                            f"${_total_retail_dol:,.0f}",
                            help="Retail price basis: on-hand units × retail price.",
                        )
                        _kc4.metric("🔴 Reorder SKUs", _reorder_n,
                                    help=f"DOH ≤ {INVENTORY_REORDER_DOH_THRESHOLD} days.")
                        _kc5.metric("🟠 Overstock SKUs", _overstock_n,
                                    help=f"DOH ≥ {INVENTORY_OVERSTOCK_DOH_THRESHOLD} days.")
                    else:
                        if _total_dol is not None:
                            _single_val_label = f"${_total_dol:,.0f}"
                        elif _total_retail_dol is not None:
                            _single_val_label = f"${_total_retail_dol:,.0f}"
                        else:
                            _single_val_label = "N/A"
                        _kc2.metric(
                            "💰 Total $ on hand",
                            _single_val_label,
                            help="Requires cost or retail price column in inventory file.",
                        )
                        _kc3.metric("🔴 Reorder SKUs", _reorder_n,
                                    help=f"DOH ≤ {INVENTORY_REORDER_DOH_THRESHOLD} days.")
                        _kc4.metric("🟠 Overstock SKUs", _overstock_n,
                                    help=f"DOH ≥ {INVENTORY_OVERSTOCK_DOH_THRESHOLD} days.")
                    _exp_label = f"{_exp_n}"
                    if _exp_dol is not None:
                        _exp_label += f" (${_exp_dol:,.0f})"
                    _kc_exp.metric(
                        f"⚠️ Expiring <{INVENTORY_EXPIRING_SOON_DAYS}d",
                        _exp_label,
                        help=f"SKUs with earliest expiry < {INVENTORY_EXPIRING_SOON_DAYS} days.",
                    )
                    st.markdown("---")
                    # Decision-first table (8–10 default columns)
                    _avg_wkly_lbl = f"Avg Wkly ({_b_vel_win}d)"
                    _dcmap = {}
                    if "sku" in df.columns:
                        _dcmap["SKU"] = "sku"
                    _dcmap["Item"] = "itemname"
                    if "category" in df.columns:
                        _dcmap["Category"] = "category"
                    if "brand_vendor" in df.columns:
                        _dcmap["Brand/Vendor"] = "brand_vendor"
                    _dcmap["On Hand"] = "onhandunits"
                    _dcmap[_avg_wkly_lbl] = "avg_weekly_sales"
                    _dcmap["DOH"] = "days_of_supply"
                    if "unit_cost" in df.columns:
                        _dcmap["Unit Cost"] = "unit_cost"
                    if "retail_price" in df.columns:
                        _dcmap["Retail Price"] = "retail_price"
                    if "dollars_on_hand" in df.columns:
                        _dcmap["$ On Hand (Cost)"] = "dollars_on_hand"
                    if "retail_dollars_on_hand" in df.columns:
                        _dcmap["$ On Hand (Retail)"] = "retail_dollars_on_hand"
                    if "expiration_date" in df.columns:
                        _dcmap["Earliest Exp"] = "expiration_date"
                    if "days_to_expire" in df.columns:
                        _dcmap["Days to Exp"] = "days_to_expire"
                    _dcmap["Status"] = "status"

                    _src_c = [v for v in _dcmap.values() if v in df.columns]
                    _lbl_c = [k for k, v in _dcmap.items() if v in df.columns]
                    _disp = df[_src_c].copy()
                    _disp.columns = _lbl_c

                    # Round / format
                    for _lbl in [_avg_wkly_lbl, "DOH"]:
                        if _lbl in _disp.columns:
                            _disp[_lbl] = (
                                _disp[_lbl].replace(UNKNOWN_DAYS_OF_SUPPLY, np.nan).round(1)
                            )
                    if "On Hand" in _disp.columns:
                        _disp["On Hand"] = _disp["On Hand"].round(0).astype(int)
                    # Format all $ on-hand columns (derived from _dcmap to avoid duplication)
                    _dollar_col_labels = [
                        lbl for lbl, src in _dcmap.items()
                        if src in ("dollars_on_hand", "retail_dollars_on_hand")
                    ]
                    for _dollar_lbl in _dollar_col_labels:
                        if _dollar_lbl in _disp.columns:
                            _disp[_dollar_lbl] = pd.to_numeric(
                                _disp[_dollar_lbl], errors="coerce"
                            ).round(2)
                    if "Days to Exp" in _disp.columns:
                        _disp["Days to Exp"] = pd.to_numeric(
                            _disp["Days to Exp"], errors="coerce"
                        ).astype("Int64")

                    st.markdown(
                        f"**{len(_disp)} SKU(s)** "
                        f"(velocity window: {_b_vel_win} days)"
                    )
                    st.markdown('<div class="sm-table-wrap">', unsafe_allow_html=True)
                    st.dataframe(_disp, use_container_width=True, hide_index=True)
                    st.markdown('</div>', unsafe_allow_html=True)

                    with st.expander("🔎 Show all columns"):
                        st.dataframe(
                            df.replace(UNKNOWN_DAYS_OF_SUPPLY, np.nan),
                            use_container_width=True,
                            hide_index=True,
                        )

                # ---- TABS ----
                _b_tab_all, _b_tab_reorder, _b_tab_overstock, _b_tab_expiring = st.tabs(
                    ["📦 All Inventory", "🔴 Reorder", "🟠 Overstock", "⚠️ Expiring"]
                )

                with _b_tab_all:
                    _render_inv_table(_apply_inv_filters(_b_merged))

                with _b_tab_reorder:
                    st.caption(
                        f"Default: DOH ≤ {INVENTORY_REORDER_DOH_THRESHOLD} days, "
                        "sorted DOH ascending (most urgent first)."
                    )
                    _reo_df = _apply_inv_filters(
                        _b_merged,
                        tab_filter=lambda df: df[
                            df["days_of_supply"] <= INVENTORY_REORDER_DOH_THRESHOLD
                        ],
                    )
                    if not _reo_df.empty:
                        _reo_df = _reo_df.sort_values(
                            "days_of_supply", ascending=True, na_position="last"
                        )
                    _render_inv_table(_reo_df)

                with _b_tab_overstock:
                    st.caption(
                        f"Default: DOH ≥ {INVENTORY_OVERSTOCK_DOH_THRESHOLD} days, "
                        "sorted $ on hand descending."
                    )
                    _ov_df = _apply_inv_filters(
                        _b_merged,
                        tab_filter=lambda df: df[
                            df["days_of_supply"] >= INVENTORY_OVERSTOCK_DOH_THRESHOLD
                        ],
                    )
                    if not _ov_df.empty:
                        if "dollars_on_hand" in _ov_df.columns:
                            _ov_df = _ov_df.sort_values(
                                "dollars_on_hand", ascending=False, na_position="last"
                            )
                        else:
                            _ov_df = _ov_df.sort_values(
                                "days_of_supply", ascending=False, na_position="last"
                            )
                    _render_inv_table(_ov_df)

                with _b_tab_expiring:
                    st.caption(
                        f"Default: Earliest expiry < {INVENTORY_EXPIRING_SOON_DAYS} days, "
                        "sorted soonest first."
                    )
                    if "expiration_date" in _b_merged.columns:
                        _exp_df = _apply_inv_filters(
                            _b_merged,
                            tab_filter=lambda df: df[
                                df["days_to_expire"].notna()
                                & (df["days_to_expire"] < INVENTORY_EXPIRING_SOON_DAYS)
                            ],
                        )
                        if not _exp_df.empty:
                            _exp_df = _exp_df.sort_values(
                                "days_to_expire", ascending=True, na_position="last"
                            )
                        _render_inv_table(_exp_df)
                    else:
                        st.info(
                            "ℹ️ No expiration date column detected in the inventory file. "
                            "Add an 'expiration date' or 'expiry date' column to use this tab."
                        )

        except Exception as _b_err:
            st.error(f"Error building Buyer View: {_b_err}")

        # =======================
        # AI INVENTORY CHECK
        # =======================
        st.markdown("---")
        st.markdown("### 🤖 AI Inventory Check (Optional)")

        if OPENAI_AVAILABLE:
            if st.button("Run AI check on current view"):
                with st.spinner("Having the AI look over this slice like a buyer..."):
                    ai_summary = ai_inventory_check(detail_view, doh_threshold, data_source)
                st.markdown(ai_summary)
        else:
            st.info(
                "AI buyer-assist is disabled because no `AI_API_KEY` (or `OPENAI_API_KEY`) was found in "
                "Streamlit secrets or environment."
            )

    except Exception as e:
        st.error(f"Error: {e}")


# ============================================================
# PAGE 2A – COMPLIANCE Q&A
# ============================================================
elif section == "🧭 Compliance Q&A":
    st.subheader("🧭 Compliance Q&A")
    st.caption(
        "Grounded compliance answers from structured sources only. "
        "Upload reviewed source rows and query by state/scope/topic."
    )

    template_df = pd.DataFrame(
        [
            {
                "state": "CA",
                "scope": "adult-use",
                "topic": "packaging",
                "answer": "Child-resistant packaging is required before retail sale.",
                "source_citation": "16 CCR § 17407",
                "source_url": "https://cannabis.ca.gov/",
                "last_updated": "2026-01-15",
                "review_status": "reviewed",
            }
        ]
    )

    st.markdown("**Required source columns**: state, scope, topic, answer, source_citation, source_url, last_updated, review_status")

    buf = BytesIO()
    template_df.to_csv(buf, index=False)
    st.download_button(
        "Download compliance source template (CSV)",
        data=buf.getvalue(),
        file_name="compliance_sources_template.csv",
        mime="text/csv",
    )

    source_file = st.file_uploader(
        "Upload structured compliance sources (CSV)",
        type=["csv"],
        key="compliance_source_upload",
    )

    repo = None
    if source_file is not None:
        try:
            source_df = pd.read_csv(source_file)
            repo = _load_compliance_sources_from_df(source_df)
            st.success(f"Loaded {len(source_df)} compliance source row(s).")
            st.dataframe(source_df.head(100), use_container_width=True)
        except Exception as exc:
            st.error(f"Could not load compliance sources: {exc}")

    c1, c2, c3 = st.columns(3)
    with c1:
        state = st.text_input("State", value="CA", key="compliance_state")
    with c2:
        scope = st.selectbox("Scope", ["adult-use", "medical"], key="compliance_scope")
    with c3:
        topic = st.text_input("Topic", value="packaging", key="compliance_topic")

    question = st.text_area(
        "Compliance question",
        value="What are the packaging requirements for adult-use products?",
        key="compliance_question",
    )

    if st.button("Answer from structured sources", key="compliance_ask"):
        if repo is None:
            st.warning("Upload structured compliance source rows first.")
        else:
            result = _generate_grounded_compliance_response(repo, state, scope, topic, question)
            st.markdown(result)

# ============================================================
# PAGE 2B – BUYER INTELLIGENCE
# ============================================================
elif section == "🧠 Buyer Intelligence":
    st.subheader("🧠 Buyer Intelligence")
    st.caption("Demand, risk, and AI buyer brief generated from your uploaded sales/inventory data.")
    with st.expander("🌐 Optional live market references", expanded=False):
        st.caption(
            "Use these external sources as directional market context. "
            "Prioritize your store-level sales, margin, and inventory data for buy decisions."
        )
        for source in BUYER_MARKET_REFERENCES:
            st.markdown(f"- [{source['name']}]({source['url']}) — {source['notes']}")

    sales_raw_df = st.session_state.sales_raw_df
    inv_raw_df = st.session_state.inv_raw_df

    if sales_raw_df is None:
        st.info("Upload Product Sales data on Inventory Dashboard to use Buyer Intelligence.")
        st.stop()

    lookback_days = int(
        st.sidebar.slider(
            "Buyer intelligence lookback (days)",
            min_value=14,
            max_value=120,
            value=60,
            key="buyer_intel_lookback",
        )
    )

    try:
        summary, by_category, by_product = _compute_buyer_intelligence(
            inv_df_raw=inv_raw_df,
            sales_df_raw=sales_raw_df,
            lookback_days=lookback_days,
        )

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            kpi_card("Tracked SKUs", f"{summary['tracked_skus']:,}")
        with k2:
            kpi_card("Units Sold", f"{summary['total_units_sold']:,.0f}")
        with k3:
            kpi_card("Revenue", f"${summary['total_revenue']:,.0f}")
        with k4:
            kpi_card("Reorder Risk SKUs", f"{summary['at_risk_skus']:,}")

        c1, c2 = st.columns([1, 1.4])
        with c1:
            st.markdown("#### Top Categories")
            st.dataframe(by_category.head(20), use_container_width=True, hide_index=True)
        with c2:
            st.markdown("#### SKU Risk Table")
            st.dataframe(
                by_product.head(200),
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("---")
        st.markdown("### 🤖 AI Buyer Brief")
        if st.button("Generate AI Buyer Brief", key="buyer_intel_ai_brief"):
            with st.spinner("Generating buyer brief..."):
                brief = _generate_buyer_brief_ai(summary, by_category, by_product, lookback_days)
            st.markdown(brief)

    except Exception as exc:
        st.error(f"Could not build buyer intelligence view: {exc}")

# ============================================================
# PAGE 2C – ADMIN TOOLS
# ============================================================
elif section == "🛠️ Admin Tools":
    st.subheader("🛠️ Admin Tools")

    if not st.session_state.get("is_admin", False):
        st.warning("Admin access is required for this section.")
        st.stop()

    st.caption("Provider diagnostics, compliance source QA, and operational admin utilities.")

    a1, a2 = st.columns(2)
    with a1:
        st.markdown("### AI Provider Diagnostics")
        key, where = _find_openai_key()
        st.write(f"Configured key found: {'Yes' if bool(key) else 'No'}")
        if where:
            st.write(f"Key source: {where}")
        st.write(f"Provider connected: {'Yes' if OPENAI_AVAILABLE else 'No'}")
        if ai_provider is not None:
            st.write(f"Provider name: {getattr(ai_provider, 'provider_name', 'unknown')}")

        if st.button("Run AI Health Check", key="admin_ai_health_check"):
            try:
                result = _generate_ai_with_quota_fallback(
                    system_prompt="You are a diagnostic assistant.",
                    user_prompt="Respond with: AI health check OK.",
                    max_tokens=30,
                )
                st.success(f"AI check response: {result.text}")
            except Exception as exc:
                st.error(f"AI health check failed: {exc}")

    with a2:
        st.markdown("### Session Data Overview")
        inv_rows = len(st.session_state.inv_raw_df) if isinstance(st.session_state.get("inv_raw_df"), pd.DataFrame) else 0
        sales_rows = len(st.session_state.sales_raw_df) if isinstance(st.session_state.get("sales_raw_df"), pd.DataFrame) else 0
        st.write(f"Inventory rows in session: {inv_rows}")
        st.write(f"Sales rows in session: {sales_rows}")
        st.write(f"Upload cache entries: {len(st.session_state.get('uploaded_files_by_user_day', {}))}")

        if st.button("Clear session dataframes", key="admin_clear_session_frames"):
            st.session_state.inv_raw_df = None
            st.session_state.sales_raw_df = None
            st.success("Session dataframes cleared.")

    st.markdown("---")
    st.markdown("### Compliance Source QA")
    st.caption("Upload a compliance source CSV to validate schema completeness and row quality.")

    qa_upload = st.file_uploader(
        "Upload compliance source CSV for QA",
        type=["csv"],
        key="admin_compliance_qa_upload",
    )

    if qa_upload is not None:
        try:
            qa_df = pd.read_csv(qa_upload)
            report = _audit_compliance_source_df(qa_df)
            st.dataframe(qa_df.head(100), use_container_width=True)

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                kpi_card("Rows", report["row_count"])
            with c2:
                kpi_card("Missing Columns", len(report["missing_columns"]))
            with c3:
                kpi_card("Duplicate Rows", report["duplicate_rows"])
            with c4:
                kpi_card("Blank Critical Rows", report["blank_critical_rows"])

            if report["missing_columns"]:
                st.error(f"Missing required columns: {', '.join(report['missing_columns'])}")
            else:
                st.success("Required columns are present.")
        except Exception as exc:
            st.error(f"Could not audit file: {exc}")

# ============================================================
# PAGE 2 – TRENDS
# ============================================================
elif section == "📈 Trends":
    st.subheader("📈 Trends")

    st.markdown(
        "This page reads the same uploaded Dutchie/BLAZE exports (if present) and surfaces "
        "quick signals: category mix, package-size mix, and velocity movers.\n\n"
        "**Note:** If you haven’t uploaded files yet, go to **Inventory Dashboard** first."
    )

    inv_df_raw = st.session_state.inv_raw_df
    sales_raw_df = st.session_state.sales_raw_df

    if sales_raw_df is None:
        st.info("Upload at least the Product Sales report on the Inventory Dashboard page to see Trends.")
        st.stop()

    st.sidebar.markdown("### 📈 Trend Settings")
    trend_days = int(st.sidebar.slider("Trend window (days)", 7, 120, 30, key="trend_days"))
    compare_days = int(st.sidebar.slider("Comparison window (prior days)", 7, 120, 30, key="compare_days"))
    run_rate_multiplier = float(st.sidebar.number_input("Run-rate multiplier", 0.1, 3.0, 1.0, 0.1, key="run_rate_mult"))

    sales = sales_raw_df.copy()
    sales.columns = sales.columns.astype(str).str.lower()

    name_col_sales = detect_column(sales.columns, [normalize_col(a) for a in SALES_NAME_ALIASES])
    qty_col_sales = detect_column(sales.columns, [normalize_col(a) for a in SALES_QTY_ALIASES])
    mc_col = detect_column(sales.columns, [normalize_col(a) for a in SALES_CAT_ALIASES])
    rev_col = detect_column(sales.columns, [normalize_col(a) for a in SALES_REV_ALIASES])

    if not (name_col_sales and qty_col_sales and mc_col):
        st.error("Could not detect required columns in Product Sales report for Trends.\n\nNeed: product name + units sold + category.")
        st.stop()

    sales = sales.rename(columns={name_col_sales: "product_name", qty_col_sales: "unitssold", mc_col: "mastercategory"})
    if rev_col:
        sales = sales.rename(columns={rev_col: "revenue"})

    sales["unitssold"] = pd.to_numeric(sales["unitssold"], errors="coerce").fillna(0)
    if "revenue" in sales.columns:
        sales["revenue"] = pd.to_numeric(sales["revenue"], errors="coerce").fillna(0)

    sales["mastercategory"] = sales["mastercategory"].apply(normalize_rebelle_category)
    sales = sales[
        ~sales["mastercategory"].astype(str).str.contains("accessor", na=False)
        & (sales["mastercategory"] != "all")
    ].copy()

    sales["packagesize"] = sales.apply(lambda r: extract_size(r.get("product_name", ""), r.get("mastercategory", "")), axis=1)
    sales["strain_type"] = sales.apply(lambda r: extract_strain_type(r.get("product_name", ""), r.get("mastercategory", "")), axis=1)

    cat_units = sales.groupby("mastercategory", dropna=False)["unitssold"].sum().reset_index()
    cat_units["units_per_day"] = (cat_units["unitssold"] / max(int(trend_days), 1)) * float(run_rate_multiplier)

    total_units = float(cat_units["unitssold"].sum()) if not cat_units.empty else 0.0
    cat_units["unit_share"] = np.where(total_units > 0, cat_units["unitssold"] / total_units, 0.0)

    st.markdown("### Category Mix (Units)")
    st.dataframe(cat_units.sort_values("unitssold", ascending=False), use_container_width=True)

    size_units = sales.groupby("packagesize", dropna=False)["unitssold"].sum().reset_index()
    size_units["units_per_day"] = (size_units["unitssold"] / max(int(trend_days), 1)) * float(run_rate_multiplier)
    st.markdown("### Package Size Mix (Units)")
    st.dataframe(size_units.sort_values("unitssold", ascending=False), use_container_width=True)

    st.markdown("### Top Movers (SKU-level)")
    sku_cols = ["product_name", "mastercategory", "strain_type", "packagesize", "unitssold"]
    if "revenue" in sales.columns:
        sku_cols.append("revenue")
    sku_view = sales[sku_cols].copy()
    sku_view["units_per_day"] = (sku_view["unitssold"] / max(int(trend_days), 1)) * float(run_rate_multiplier)

    if "revenue" in sku_view.columns:
        sku_view["avg_price"] = np.where(sku_view["unitssold"] > 0, sku_view["revenue"] / sku_view["unitssold"], 0.0)

    st.dataframe(sku_view.sort_values("units_per_day", ascending=False).head(50), use_container_width=True)

    st.markdown("### Best Sellers by Category")
    top_n = int(st.number_input("Top N per category", 1, 50, 10, key="trend_top_n"))
    cat_list = sorted([c for c in sales["mastercategory"].dropna().unique().tolist()])
    if len(cat_list) == 0:
        st.info("No categories found in sales data.")
    else:
        for cat in cat_list:
            with st.expander(f"{str(cat).title()} — Top {int(top_n)}", expanded=False):
                cat_df = sku_view[sku_view["mastercategory"] == cat].copy()
                st.dataframe(cat_df.sort_values("units_per_day", ascending=False).head(int(top_n)), use_container_width=True)

    # If inventory is available, show "fast movers low stock"
    if inv_df_raw is not None:
        inv_df = inv_df_raw.copy()
        inv_df.columns = inv_df.columns.astype(str).str.strip().str.lower()

        name_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_NAME_ALIASES])
        cat_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_CAT_ALIASES])
        qty_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_QTY_ALIASES])

        if name_col and cat_col and qty_col:
            inv_df = inv_df.rename(columns={name_col: "itemname", cat_col: "subcategory", qty_col: "onhandunits"})
            inv_df["subcategory"] = inv_df["subcategory"].apply(normalize_rebelle_category)
            inv_df["packagesize"] = inv_df.apply(lambda r: extract_size(r.get("itemname", ""), r.get("subcategory", "")), axis=1)
            inv_df["strain_type"] = inv_df.apply(lambda r: extract_strain_type(r.get("itemname", ""), r.get("subcategory", "")), axis=1)
            inv_df["onhandunits"] = pd.to_numeric(inv_df["onhandunits"], errors="coerce").fillna(0)

            inv_small = inv_df[["itemname", "subcategory", "packagesize", "strain_type", "onhandunits"]].copy()
            sku_tmp = sku_view.rename(columns={"product_name": "itemname", "mastercategory": "subcategory"}).copy()
            merged = pd.merge(sku_tmp, inv_small, how="left", on=["itemname", "subcategory", "packagesize", "strain_type"])
            merged["onhandunits"] = pd.to_numeric(merged.get("onhandunits", 0), errors="coerce").fillna(0)

            merged["risk_score"] = merged["units_per_day"] / np.maximum(merged["onhandunits"], 1)
            st.markdown("### Fast Movers + Low Stock (SKU-level)")
            st.dataframe(merged.sort_values("risk_score", ascending=False).head(50), use_container_width=True)

# ============================================================
# PAGE – DELIVERY IMPACT
# ============================================================
elif section == "🚚 Delivery Impact":
    st.subheader("🚚 Delivery Impact Analysis")

    if not _DELIVERY_IMPACT_AVAILABLE:
        st.error(
            "❌ The `delivery_impact` module could not be imported. "
            "Make sure `delivery_impact.py` is present in the project root."
        )
        st.stop()

    if data_mode == "🔴 Dutchie Live":
        # ── Dutchie Live mode ────────────────────────────────────────────────
        st.info(
            "🔴 **Dutchie Live** mode is active.  "
            "Delivery and daily sales data will be fetched from the Dutchie API once "
            "credentials are configured."
        )
        if _DUTCHIE_CLIENT_AVAILABLE:
            _dc_del = DutchieConfig.from_env_and_secrets()
            if not _dc_del.is_configured():
                st.warning(
                    "⚠️ Dutchie API credentials are not yet configured.  "
                    f"Missing: `{'`, `'.join(_dc_del.missing_keys())}`.  "
                    "See *docs/dutchie.md* for setup instructions, or switch to "
                    "**📁 Uploads** mode in the sidebar."
                )
            else:
                _bundle_del, _err_del = fetch_dutchie_data(_dc_del)
                if _err_del:
                    st.warning(f"⚠️ Dutchie Live: {_err_del}")
                else:
                    st.success("✅ Dutchie Live: delivery data fetched successfully.")
        else:
            st.error("❌ dutchie_client module is not available.")
    else:
        # ── Uploads mode ─────────────────────────────────────────────────────
        st.markdown(
            """
            Upload one or more **delivery manifests** (CSV or XLSX preferred, PDF also supported)
            and a **sales report** (CSV or XLSX).
            The app will parse each manifest for its received date/time and delivered items, then
            compute a **14-day before vs 14-day after** comparison to show how each delivery
            correlates with spikes in **Net Sales** and **order count (traffic proxy)**.
            """
        )

        # ── File uploaders ───────────────────────────────────────────────────
        _di_col1, _di_col2 = st.columns(2)

        with _di_col1:
            st.markdown("#### 📦 Manifest Files")
            _manifest_files = st.file_uploader(
                "Upload delivery manifest (CSV, XLSX, or PDF)",
                type=["csv", "xlsx", "xls", "pdf"],
                accept_multiple_files=True,
                key="di_manifest_upload",
                help=(
                    "CSV or XLSX receiving exports are recommended. "
                    "Each file should contain product names and received quantities. "
                    "PDF is also supported as a fallback."
                ),
            )

        with _di_col2:
            st.markdown("#### 📊 Sales Report")
            _sales_file = st.file_uploader(
                "Upload sales report (CSV or XLSX)",
                type=["csv", "xlsx"],
                key="di_sales_upload",
                help=(
                    "Expected columns: Order ID, Order Time, Product Name, "
                    "Total Inventory Sold, Net Sales. "
                    "Metadata preamble rows (e.g. Export Date:) are skipped automatically."
                ),
            )

        if _manifest_files and _sales_file:
            try:
                # ── Enforce upload limits ────────────────────────────────────
                _sales_file.seek(0)
                _sales_bytes = _sales_file.read()
                _sales_file.seek(0)
                if len(_sales_bytes) > MAX_UPLOAD_BYTES:
                    st.error(
                        f"❌ Sales file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."
                    )
                    st.stop()

                # ── Parse sales report ───────────────────────────────────────
                with st.spinner("Parsing sales report…"):
                    _sales_df = _parse_sales_report_bytes(_sales_bytes, _sales_file.name)

                if _sales_df.empty:
                    st.error(
                        "❌ No usable sales rows found. "
                        "Ensure the file has Order Time and Net Sales columns."
                    )
                    st.stop()

                _sales_products = sorted(_sales_df["product_name"].dropna().unique().tolist())
                st.success(
                    f"✅ Sales report parsed: **{len(_sales_df):,}** line items · "
                    f"**{_sales_df['order_time'].dt.date.nunique()}** unique days · "
                    f"**{len(_sales_products):,}** unique products"
                )

                # ── Parse manifests ──────────────────────────────────────────
                _manifests: list = []
                _all_debug_texts: dict = {}

                with st.spinner("Parsing manifest files…"):
                    for _mf in _manifest_files:
                        if len(_mf.getvalue()) > MAX_UPLOAD_BYTES:
                            st.warning(
                                f"⚠️ Manifest **{_mf.name}** exceeds the size limit – skipped."
                            )
                            continue
                        _mf.seek(0)
                        _mf_bytes = _mf.read()
                        _mf_name_lower = _mf.name.lower()

                        if _mf_name_lower.endswith((".csv", ".xlsx", ".xls")):
                            _recv_dt, _items_df, _debug_text = parse_manifest_csv_xlsx_bytes(
                                _mf_bytes, filename=_mf.name
                            )
                        else:
                            _recv_dt, _items_df, _debug_text = parse_manifest_pdf_bytes(
                                _mf_bytes, filename=_mf.name
                            )

                        _all_debug_texts[_mf.name] = _debug_text
                        if _recv_dt is None and _items_df.empty:
                            st.warning(
                                f"⚠️ Could not extract data from **{_mf.name}**. "
                                "Check the debug dump below."
                            )
                        # Guarantee received_dt is a pd.Timestamp (or None/NaT→None).
                        _recv_dt_coerced = pd.to_datetime(_recv_dt, errors="coerce")
                        _recv_dt_final = (
                            None if pd.isna(_recv_dt_coerced)
                            else _recv_dt_coerced
                        )
                        if _recv_dt is not None and _recv_dt_final is None:
                            st.warning(
                                f"⚠️ Manifest **{_mf.name}** has an unparseable received date "
                                f"({_recv_dt!r}) and will be excluded from analysis."
                            )
                        _manifests.append({
                            "filename": _mf.name,
                            "received_dt": _recv_dt_final,
                            "items_df": _items_df,
                            "debug_text": _debug_text,
                        })

                if not _manifests:
                    st.error("❌ No manifests could be parsed.")
                    st.stop()

                # ── Sidebar controls ─────────────────────────────────────────
                st.sidebar.markdown("---")
                st.sidebar.markdown("### 🚚 Delivery Impact Settings")

                _comparison_mode = st.sidebar.selectbox(
                    "Analysis Mode",
                    ["📅 Before/After (±N days)", "📆 Same weekday last week (WoW)"],
                    index=0,
                    key="di_comparison_mode",
                    help=(
                        "**Before/After (±N days)**: compare N days before vs N days after delivery.\n\n"
                        "**Same weekday last week (WoW)**: compare the delivery calendar day "
                        "to the same weekday 7 days prior (e.g. Thu 03-19 vs Thu 03-12)."
                    ),
                )
                _wow_mode = _comparison_mode == "📆 Same weekday last week (WoW)"

                # Window-days selector is only relevant in Before/After mode
                if not _wow_mode:
                    _window_days = st.sidebar.selectbox(
                        "Comparison window (days before/after)",
                        options=[7, 14, 21, 28],
                        index=1,
                        key="di_window",
                    )
                else:
                    _window_days = st.session_state.get("di_window", 14)

                _granularity = st.sidebar.radio(
                    "Chart granularity",
                    ["daily", "hourly"],
                    index=0,
                    key="di_granularity",
                )

                _fuzzy_threshold = st.sidebar.slider(
                    "Fuzzy match threshold",
                    min_value=0.60,
                    max_value=1.00,
                    value=0.82,
                    step=0.01,
                    key="di_fuzzy",
                    help=(
                        "Minimum similarity (0–1) to accept a fuzzy product-name match. "
                        "Higher = stricter."
                    ),
                )

                _show_total = st.sidebar.checkbox("Total Net Sales", value=True, key="di_ov_total")
                _show_del = st.sidebar.checkbox("Delivered-items Net Sales", value=True, key="di_ov_del")
                _show_nondel = st.sidebar.checkbox("Non-delivered Net Sales", value=False, key="di_ov_nondel")
                _show_orders = st.sidebar.checkbox("Order Count (traffic)", value=True, key="di_ov_orders")

                # ── Per-manifest matching & manifest selector ────────────────
                _valid_manifests = [m for m in _manifests if m["received_dt"] is not None]
                _invalid_manifests = [m for m in _manifests if m["received_dt"] is None]

                if _invalid_manifests:
                    st.warning(
                        "⚠️ The following manifests had no detectable received date and will be "
                        "excluded from analysis: "
                        + ", ".join(f"**{m['filename']}**" for m in _invalid_manifests)
                    )

                if not _valid_manifests:
                    st.error(
                        "❌ None of the uploaded manifests contained a detectable received date/time."
                    )
                    st.stop()

                # Build manifest options for selector
                _manifest_options = ["📦 Combined (all manifests)"] + [
                    f"📄 {m['filename']} ({m['received_dt'].strftime('%Y-%m-%d %H:%M')})"
                    for m in _valid_manifests
                ]
                _selected_manifest_label = st.selectbox(
                    "View manifest",
                    _manifest_options,
                    key="di_manifest_sel",
                )

                # Resolve which manifests to show
                if _selected_manifest_label == "📦 Combined (all manifests)":
                    _active_manifests = _valid_manifests
                else:
                    _active_manifests = [
                        m for m in _valid_manifests
                        if f"📄 {m['filename']} ({m['received_dt'].strftime('%Y-%m-%d %H:%M')})"
                        == _selected_manifest_label
                    ]

                # ── Match delivered items for active manifests ───────────────
                _all_matched: dict = {}
                _all_unmatched: list = []
                _all_delivered_sales_names: list = []

                for _m in _active_manifests:
                    if _m["items_df"].empty:
                        continue
                    _manifest_item_names = _m["items_df"]["item_name"].dropna().tolist()
                    _matched, _unmatched = match_manifest_to_sales(
                        _manifest_item_names,
                        _sales_products,
                        fuzzy_threshold=_fuzzy_threshold,
                    )
                    _all_matched.update(_matched)
                    for _u in _unmatched:
                        if _u not in _all_unmatched:
                            _all_unmatched.append(_u)
                    for _sn in _matched.values():
                        if _sn not in _all_delivered_sales_names:
                            _all_delivered_sales_names.append(_sn)

                # ── KPI computation ──────────────────────────────────────────
                st.markdown("---")
                if _wow_mode:
                    st.markdown("### 📊 KPI Summary – Same Weekday Last Week (WoW)")
                else:
                    st.markdown("### 📊 KPI Summary")

                _kpi_rows: list = []
                _combined_kpi_keys = [
                    "net_sales_before", "net_sales_after", "net_sales_lift_abs", "net_sales_lift_pct",
                    "orders_before", "orders_after",
                    "delivered_sales_before", "delivered_sales_after",
                    "delivered_sales_lift_abs", "delivered_sales_lift_pct",
                    "delivered_units_before", "delivered_units_after",
                ]

                def _safe_numeric(v):
                    """Return float(v) if v is numeric or numeric-looking string, else None."""
                    if v is None:
                        return None
                    v_num = pd.to_numeric(v, errors="coerce")
                    if pd.isna(v_num):
                        return None
                    return float(v_num)

                for _m in _active_manifests:
                    if _wow_mode:
                        _kpis = compute_weekday_wow_kpis(
                            _sales_df,
                            _m["received_dt"],
                            delivered_names=_all_delivered_sales_names or None,
                        )
                        _prior_label = _kpis["prior_day_start"].strftime("%Y-%m-%d (%a)")
                        _deliv_label = _kpis["delivery_day_start"].strftime("%Y-%m-%d (%a)")
                        _before_col = f"Net Sales {_prior_label} ($)"
                        _after_col = f"Net Sales {_deliv_label} ($)"
                    else:
                        _kpis = compute_delivery_kpis(
                            _sales_df,
                            _m["received_dt"],
                            window_days=_window_days,
                            delivered_names=_all_delivered_sales_names or None,
                        )
                        _before_col = "Net Sales Before ($)"
                        _after_col = "Net Sales After ($)"
                    _kpi_rows.append({
                        "Manifest": _m["filename"],
                        "Received": _m["received_dt"].strftime("%Y-%m-%d %H:%M"),
                        _before_col: f"{_kpis['net_sales_before']:,.2f}",
                        _after_col: f"{_kpis['net_sales_after']:,.2f}",
                        "$ Lift": f"{_kpis['net_sales_lift_abs']:,.2f}",
                        "% Lift": (
                            f"{_kpis['net_sales_lift_pct']:.1f}%"
                            if not pd.isna(_kpis["net_sales_lift_pct"])
                            else "N/A"
                        ),
                        "Orders Before": _kpis["orders_before"],
                        "Orders After": _kpis["orders_after"],
                    })

                if _kpi_rows:
                    _kpi_df = pd.DataFrame(_kpi_rows)
                    st.dataframe(_kpi_df, use_container_width=True)

                # ── Summary metrics ──────────────────────────────────────────
                # Compute combined KPIs from all active manifests (hardened numeric aggregation)
                _combined_kpis: dict = {}
                for _m in _active_manifests:
                    if _wow_mode:
                        _kpis = compute_weekday_wow_kpis(
                            _sales_df,
                            _m["received_dt"],
                            delivered_names=_all_delivered_sales_names or None,
                        )
                    else:
                        _kpis = compute_delivery_kpis(
                            _sales_df,
                            _m["received_dt"],
                            window_days=_window_days,
                            delivered_names=_all_delivered_sales_names or None,
                        )
                    for _k in _combined_kpi_keys:
                        v_num = _safe_numeric(_kpis.get(_k))
                        if v_num is not None:
                            _combined_kpis[_k] = _combined_kpis.get(_k, 0.0) + v_num

                if _combined_kpis:
                    _mk1, _mk2, _mk3, _mk4 = st.columns(4)
                    _ns_b = _combined_kpis.get("net_sales_before", 0.0)
                    _ns_a = _combined_kpis.get("net_sales_after", 0.0)
                    _ns_lift = _ns_a - _ns_b
                    _ns_pct = (_ns_lift / _ns_b * 100) if _ns_b else 0.0
                    if _wow_mode:
                        _mk1.metric("Net Sales (prior week same day)", f"${_ns_b:,.0f}", delta=None)
                        _mk2.metric(
                            "Net Sales (delivery day)",
                            f"${_ns_a:,.0f}",
                            delta=f"{_ns_lift:+,.0f} ({_ns_pct:+.1f}%)",
                        )
                    else:
                        _mk1.metric("Net Sales (before)", f"${_ns_b:,.0f}", delta=None)
                        _mk2.metric(
                            "Net Sales (after)",
                            f"${_ns_a:,.0f}",
                            delta=f"{_ns_lift:+,.0f} ({_ns_pct:+.1f}%)",
                        )
                    _del_b = _combined_kpis.get("delivered_sales_before")
                    _del_a = _combined_kpis.get("delivered_sales_after")
                    if _del_b is not None and _del_a is not None:
                        _del_lift = _del_a - _del_b
                        _del_pct = (_del_lift / _del_b * 100) if _del_b else 0.0
                        _del_label = "Delivered-items Sales (delivery day)" if _wow_mode else "Delivered-items Sales (after)"
                        _mk3.metric(
                            _del_label,
                            f"${_del_a:,.0f}",
                            delta=f"{_del_lift:+,.0f} ({_del_pct:+.1f}%)",
                        )
                    else:
                        _mk3.metric("Delivered-items Sales", "N/A")
                    _o_b = _combined_kpis.get("orders_before", 0.0)
                    _o_a = _combined_kpis.get("orders_after", 0.0)
                    _o_lift = _o_a - _o_b
                    _o_label = "Orders (delivery day)" if _wow_mode else "Orders (after)"
                    _mk4.metric(_o_label, f"{int(_o_a):,}", delta=f"{int(_o_lift):+,}")

                # ── Line chart ───────────────────────────────────────────────
                st.markdown("---")
                if _wow_mode:
                    st.markdown("### 📈 Time-Series Chart – Delivery Day vs Prior Week Same Day")
                else:
                    st.markdown("### 📈 Time-Series Chart")

                # Build time series for each active manifest and combine
                _ts_frames: list = []
                _wow_delivery_frames: list = []
                _wow_prior_frames: list = []

                for _m in _active_manifests:
                    if _wow_mode:
                        _ts_deliv, _ts_prior = build_wow_time_series(
                            _sales_df,
                            _m["received_dt"],
                            granularity=_granularity,
                            delivered_names=_all_delivered_sales_names or None,
                        )
                        if not _ts_deliv.empty:
                            _wow_delivery_frames.append(_ts_deliv)
                        if not _ts_prior.empty:
                            _wow_prior_frames.append(_ts_prior)
                    else:
                        _ts = build_time_series(
                            _sales_df,
                            _m["received_dt"],
                            window_days=_window_days,
                            granularity=_granularity,
                            delivered_names=_all_delivered_sales_names or None,
                        )
                        if not _ts.empty:
                            _ts["_manifest"] = _m["filename"]
                            _ts["_recv_dt"] = _m["received_dt"]
                            _ts_frames.append(_ts)

                _chart_data_available = (
                    (_wow_mode and (_wow_delivery_frames or _wow_prior_frames))
                    or (not _wow_mode and _ts_frames)
                )

                def _coerce_ts_frame_for_plot(df: pd.DataFrame) -> pd.DataFrame:
                    """Guarantee safe dtypes in a time-series frame before passing to Plotly.

                    * ``period``               → datetime (drop NaT rows)
                    * numeric sales/count cols → float  (coerce; fill NaN with 0)
                    """
                    if df.empty:
                        return df
                    df = df.copy()
                    df["period"] = pd.to_datetime(df["period"], errors="coerce")
                    df = df.dropna(subset=["period"])
                    for _col in ("total_net_sales", "delivered_net_sales",
                                 "non_delivered_net_sales", "order_count"):
                        if _col in df.columns:
                            df[_col] = pd.to_numeric(df[_col], errors="coerce").fillna(0)
                    return df

                if _chart_data_available:
                    if PLOTLY_AVAILABLE:
                        _fig = go.Figure()

                        if _wow_mode:
                            # ── WoW overlay chart ────────────────────────────
                            def _merge_wow_frames(frames):
                                if not frames:
                                    return pd.DataFrame()
                                if len(frames) == 1:
                                    return frames[0].copy()
                                return (
                                    pd.concat(frames)
                                    .groupby("period")
                                    [["total_net_sales", "delivered_net_sales",
                                      "non_delivered_net_sales", "order_count"]]
                                    .sum()
                                    .reset_index()
                                )

                            _ts_deliv_combined = _coerce_ts_frame_for_plot(
                                _merge_wow_frames(_wow_delivery_frames)
                            )
                            _ts_prior_combined = _coerce_ts_frame_for_plot(
                                _merge_wow_frames(_wow_prior_frames)
                            )

                            if _show_total and not _ts_deliv_combined.empty:
                                _fig.add_trace(go.Scatter(
                                    x=_ts_deliv_combined["period"],
                                    y=_ts_deliv_combined["total_net_sales"],
                                    name="Total Net Sales – Delivery Day",
                                    mode="lines+markers",
                                    line={"width": 2},
                                ))
                            if _show_total and not _ts_prior_combined.empty:
                                _fig.add_trace(go.Scatter(
                                    x=_ts_prior_combined["period"],
                                    y=_ts_prior_combined["total_net_sales"],
                                    name="Total Net Sales – Prior Week Same Day",
                                    mode="lines+markers",
                                    line={"width": 2, "dash": "dash"},
                                ))

                            if _show_del:
                                if not _ts_deliv_combined.empty and "delivered_net_sales" in _ts_deliv_combined.columns:
                                    _fig.add_trace(go.Scatter(
                                        x=_ts_deliv_combined["period"],
                                        y=_ts_deliv_combined["delivered_net_sales"],
                                        name="Delivered-items Sales – Delivery Day",
                                        mode="lines+markers",
                                        line={"dash": "dot", "width": 2},
                                    ))
                                if not _ts_prior_combined.empty and "delivered_net_sales" in _ts_prior_combined.columns:
                                    _fig.add_trace(go.Scatter(
                                        x=_ts_prior_combined["period"],
                                        y=_ts_prior_combined["delivered_net_sales"],
                                        name="Delivered-items Sales – Prior Week",
                                        mode="lines+markers",
                                        line={"dash": "dot", "width": 2},
                                    ))

                            if _show_orders:
                                if not _ts_deliv_combined.empty and "order_count" in _ts_deliv_combined.columns:
                                    _fig.add_trace(go.Bar(
                                        x=_ts_deliv_combined["period"],
                                        y=_ts_deliv_combined["order_count"],
                                        name="Order Count – Delivery Day",
                                        yaxis="y2",
                                        opacity=0.50,
                                    ))
                                if not _ts_prior_combined.empty and "order_count" in _ts_prior_combined.columns:
                                    _fig.add_trace(go.Bar(
                                        x=_ts_prior_combined["period"],
                                        y=_ts_prior_combined["order_count"],
                                        name="Order Count – Prior Week",
                                        yaxis="y2",
                                        opacity=0.25,
                                    ))

                            # Delivery day marker
                            for _m in _active_manifests:
                                _deliv_day = pd.to_datetime(_m.get("received_dt"), errors="coerce")
                                if pd.notna(_deliv_day):
                                    # Plotly requires a numeric x (ms since epoch) for
                                    # add_vline when annotation_position is used on a
                                    # datetime axis.  Passing pd.Timestamp or a string
                                    # causes "unsupported operand type(s) for +: 'int'
                                    # and 'str'" in plotly.shapeannotation._mean.
                                    _vline_x = int(
                                        _deliv_day.normalize().value // 1_000_000
                                    )
                                    _fig.add_vline(
                                        x=_vline_x,
                                        line_dash="dash",
                                        line_color="red",
                                        annotation_text=f"Delivery Day: {_m.get('filename', '')}",
                                        annotation_position="top left",
                                        annotation_font_size=10,
                                    )
                                else:
                                    st.warning(
                                        f"⚠️ Delivery marker skipped – could not parse received_dt"
                                        f"{' for ' + _m['filename'] if _m.get('filename') else ''}."
                                    )
                        else:
                            # ── Before/After window chart ────────────────────
                            # Merge time series (sum across manifests for combined view)
                            if len(_ts_frames) > 1:
                                _ts_merged = (
                                    pd.concat(_ts_frames)
                                    .groupby("period")
                                    [["total_net_sales", "delivered_net_sales",
                                      "non_delivered_net_sales", "order_count"]]
                                    .sum()
                                    .reset_index()
                                )
                                _ts_combined = _coerce_ts_frame_for_plot(_ts_merged)
                            else:
                                _ts_combined = _coerce_ts_frame_for_plot(_ts_frames[0].copy())

                            if _show_total:
                                _fig.add_trace(go.Scatter(
                                    x=_ts_combined["period"],
                                    y=_ts_combined["total_net_sales"],
                                    name="Total Net Sales ($)",
                                    mode="lines",
                                    line={"width": 2},
                                ))

                            if _show_del and "delivered_net_sales" in _ts_combined.columns:
                                _fig.add_trace(go.Scatter(
                                    x=_ts_combined["period"],
                                    y=_ts_combined["delivered_net_sales"],
                                    name="Delivered-items Net Sales ($)",
                                    mode="lines",
                                    line={"dash": "dot", "width": 2},
                                ))

                            if _show_nondel and "non_delivered_net_sales" in _ts_combined.columns:
                                _fig.add_trace(go.Scatter(
                                    x=_ts_combined["period"],
                                    y=_ts_combined["non_delivered_net_sales"],
                                    name="Non-delivered Net Sales ($)",
                                    mode="lines",
                                    line={"dash": "dash", "width": 2},
                                ))

                            if _show_orders and "order_count" in _ts_combined.columns:
                                _fig.add_trace(go.Bar(
                                    x=_ts_combined["period"],
                                    y=_ts_combined["order_count"],
                                    name="Order Count",
                                    yaxis="y2",
                                    opacity=0.35,
                                ))

                            # Add vertical lines for each delivery date
                            for _m in _active_manifests:
                                _x = pd.to_datetime(_m.get("received_dt"), errors="coerce")
                                if pd.notna(_x):
                                    # Convert to integer ms-since-epoch so Plotly's
                                    # annotation positioning arithmetic doesn't fail with
                                    # "unsupported operand type(s) for +: 'int' and 'str'"
                                    _vline_x = int(_x.value // 1_000_000)
                                    _fig.add_vline(
                                        x=_vline_x,
                                        line_dash="dash",
                                        line_color="red",
                                        annotation_text=f"Delivery: {_m.get('filename', '')}",
                                        annotation_position="top left",
                                        annotation_font_size=10,
                                    )
                                else:
                                    st.warning(
                                        f"⚠️ Delivery marker skipped – could not parse received_dt"
                                        f"{' for ' + _m['filename'] if _m.get('filename') else ''}."
                                    )

                        _fig.update_layout(
                            xaxis_title="Date" if _granularity == "daily" else "Date/Hour",
                            xaxis_type="date",
                            yaxis_title="Net Sales ($)",
                            yaxis2={
                                "title": "Order Count",
                                "overlaying": "y",
                                "side": "right",
                                "showgrid": False,
                            },
                            legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
                            hovermode="x unified",
                            height=480,
                            margin={"t": 40, "b": 40},
                        )

                        st.plotly_chart(_fig, use_container_width=True)
                    else:
                        st.warning("⚠️ Plotly is not installed – chart unavailable. Install `plotly` to enable charts.")
                        if not _wow_mode and _ts_frames:
                            st.dataframe(_ts_frames[0], use_container_width=True)
                else:
                    st.info(
                        "ℹ️ No sales data found in the analysis windows. "
                        "Check that your sales report covers dates around the delivery dates."
                    )

                # ── Top items by lift ────────────────────────────────────────
                if _all_delivered_sales_names:
                    st.markdown("---")
                    st.markdown("### 🏆 Top Delivered Items by Lift")

                    _top_rows_all: list = []
                    for _m in _active_manifests:
                        if _wow_mode:
                            _kpis = compute_weekday_wow_kpis(
                                _sales_df,
                                _m["received_dt"],
                                delivered_names=_all_delivered_sales_names,
                            )
                        else:
                            _kpis = compute_delivery_kpis(
                                _sales_df,
                                _m["received_dt"],
                                window_days=_window_days,
                                delivered_names=_all_delivered_sales_names,
                            )
                        _top = _kpis.get("top_items")
                        if _top is not None and not _top.empty:
                            _top["manifest"] = _m["filename"]
                            _top_rows_all.append(_top)

                    if _top_rows_all:
                        _top_combined = pd.concat(_top_rows_all).reset_index(drop=True)
                        _top_combined = (
                            _top_combined
                            .groupby("item_name")
                            .agg(
                                sales_lift=("sales_lift", "sum"),
                                units_lift=("units_lift", "sum"),
                                net_sales_before=("net_sales_before", "sum"),
                                net_sales_after=("net_sales_after", "sum"),
                            )
                            .reset_index()
                            .sort_values("sales_lift", ascending=False)
                        )
                        st.dataframe(
                            _top_combined.rename(columns={
                                "item_name": "Product",
                                "sales_lift": "Sales Lift ($)",
                                "units_lift": "Units Lift",
                                "net_sales_before": "Net Sales Before ($)",
                                "net_sales_after": "Net Sales After ($)",
                            }),
                            use_container_width=True,
                        )

                # ── Unmatched items ──────────────────────────────────────────
                if _all_unmatched:
                    st.markdown("---")
                    st.markdown("### ⚠️ Unmatched Manifest Items")
                    st.caption(
                        "These items from the manifests could not be matched to any product "
                        "in the sales report. Their sales are not included in the delivered-items metrics."
                    )
                    _unmatched_df = pd.DataFrame({"Manifest Item (unmatched)": _all_unmatched})
                    st.dataframe(_unmatched_df, use_container_width=True)

                if _all_matched:
                    with st.expander("🔍 View item matching results", expanded=False):
                        _match_rows = [
                            {"Manifest Item": k, "Matched Sales Product": v}
                            for k, v in _all_matched.items()
                        ]
                        st.dataframe(pd.DataFrame(_match_rows), use_container_width=True)

                # ── Debug PDF text dumps ─────────────────────────────────────
                for _fname, _dtext in _all_debug_texts.items():
                    if _dtext:
                        with st.expander(f"🐛 PDF debug text: {_fname}", expanded=False):
                            st.text(_dtext[:4000] + ("…" if len(_dtext) > 4000 else ""))
                            st.download_button(
                                f"⬇️ Download full text for {_fname}",
                                data=_dtext.encode("utf-8"),
                                file_name=f"{_fname}_debug.txt",
                                mime="text/plain",
                                key=f"di_debug_{_fname}",
                            )

            except Exception as _di_exc:
                import traceback as _tb
                st.error(f"❌ Error processing files: {_di_exc}")
                st.write("Please check that your files match the expected format and try again.")
                with st.expander("🐛 Full traceback (for debugging)", expanded=False):
                    st.code(_tb.format_exc(), language="python")
                    # Dtype diagnostic summary to help identify type-coercion issues
                    try:
                        if "_sales_df" in dir() and isinstance(_sales_df, pd.DataFrame):
                            st.markdown("**Sales DF dtypes:**")
                            st.text(str(_sales_df.dtypes))
                        for _name, _frame in [
                            ("_ts_deliv_combined", locals().get("_ts_deliv_combined")),
                            ("_ts_prior_combined", locals().get("_ts_prior_combined")),
                            ("_ts_combined", locals().get("_ts_combined")),
                        ]:
                            if isinstance(_frame, pd.DataFrame) and not _frame.empty:
                                st.markdown(f"**{_name} dtypes:**")
                                st.text(str(_frame.dtypes))
                    except Exception:
                        pass
        else:
            _missing = []
            if not _manifest_files:
                _missing.append("one or more manifest PDFs")
            if not _sales_file:
                _missing.append("a sales report (CSV or XLSX)")
            st.info(f"👆 Upload {' and '.join(_missing)} to see the analysis.")


# ============================================================
# PAGE – SLOW MOVERS & TRENDS
# ============================================================
elif section == "🐢 Slow Movers":
    st.subheader("🐢 Slow Movers & Trends")
    st.write(
        "Identify products sitting on the shelf, understand velocity, and take action. "
        "Use the filters below to focus on what matters most."
    )

    if st.session_state.inv_raw_df is None or st.session_state.sales_raw_df is None:
        st.warning("⚠️ Please upload inventory and sales files in the Inventory Dashboard section first.")
        st.stop()

    # ----------------------------------------------------------
    # Helper: compute the suggested action badge for a product
    # ----------------------------------------------------------
    def _sm_action_badge(days_of_supply: float, weekly_sales: float, on_hand: float) -> str:
        """Return a short action label based on DOH, velocity and stock."""
        if on_hand <= 0:
            return "⬛ No Stock"
        if weekly_sales <= 0 or days_of_supply >= UNKNOWN_DAYS_OF_SUPPLY:
            return "🔴 Investigate"
        if days_of_supply > 180:
            return "🔴 Promo / Stop Reorder"
        if days_of_supply > 120:
            return "🟠 Markdown"
        if days_of_supply > 90:
            return "🟡 Watch"
        if days_of_supply > 60:
            return "🟢 Monitor"
        return "✅ Healthy"

    # ----------------------------------------------------------
    # Helper: compute slow-mover score (0–100, higher = worse)
    # ----------------------------------------------------------
    def _sm_score(days_of_supply: float, weekly_sales: float) -> float:
        """Composite slow-mover score: higher means slower / more problematic."""
        if weekly_sales <= 0:
            return 100.0
        # Normalise DOH against a 180-day ceiling
        doh_component = min(days_of_supply / 180.0, 1.0) * 100.0
        return round(doh_component, 1)

    try:
        # -------------------------------------------------------
        # RAW DATA PREP (column detection, dedup, quarantine)
        # -------------------------------------------------------
        inv_df = st.session_state.inv_raw_df.copy()
        sales_df = st.session_state.sales_raw_df.copy()

        inv_df.columns = inv_df.columns.astype(str).str.strip().str.lower()
        sales_df.columns = sales_df.columns.astype(str).str.strip().str.lower()

        # Detect required sales columns
        sales_name_col = detect_column(sales_df.columns, [normalize_col(a) for a in SALES_NAME_ALIASES])
        sales_qty_col = detect_column(sales_df.columns, [normalize_col(a) for a in SALES_QTY_ALIASES])

        if not (sales_name_col and sales_qty_col):
            st.error(
                f"Sales data does not have required columns.\n\n"
                f"Looking for: product name (tried: {', '.join(SALES_NAME_ALIASES[:5])}...) "
                f"and quantity sold (tried: {', '.join(SALES_QTY_ALIASES[:5])}...)\n\n"
                f"Available columns: {', '.join(sales_df.columns[:10])}..."
            )
            st.stop()

        # Detect required inventory columns
        inv_name_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_NAME_ALIASES])
        inv_qty_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_QTY_ALIASES])
        inv_batch_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_BATCH_ALIASES])

        if not (inv_name_col and inv_qty_col):
            st.error(
                f"Inventory data does not have required columns.\n\n"
                f"Looking for: product name (tried: {', '.join(INV_NAME_ALIASES[:5])}...) "
                f"and quantity (tried: {', '.join(INV_QTY_ALIASES[:5])}...)\n\n"
                f"Available columns: {', '.join(inv_df.columns[:10])}..."
            )
            st.stop()

        # Detect optional inventory columns
        inv_cost_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_COST_ALIASES])
        inv_retail_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_RETAIL_PRICE_ALIASES])
        inv_brand_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_BRAND_ALIASES])
        inv_sku_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_SKU_COL_ALIASES])
        inv_cat_col_raw = detect_column(inv_df.columns, [normalize_col(a) for a in INV_CAT_ALIASES])

        # Rename required columns
        inv_df = inv_df.rename(columns={inv_name_col: "itemname", inv_qty_col: "onhandunits"})
        if inv_batch_col:
            inv_df = inv_df.rename(columns={inv_batch_col: "batch"})

        inv_df["itemname"] = inv_df["itemname"].astype(str).str.strip()
        inv_df["onhandunits"] = pd.to_numeric(inv_df["onhandunits"], errors="coerce").fillna(0)

        if inv_cost_col:
            inv_df[inv_cost_col] = parse_currency_to_float(inv_df[inv_cost_col])
        if inv_retail_col:
            inv_df = inv_df.rename(columns={inv_retail_col: "retail_price"})
            inv_df["retail_price"] = parse_currency_to_float(inv_df["retail_price"])

        # Dedup and quarantine
        inv_df, num_dupes, dedupe_msg = deduplicate_inventory(inv_df)
        if num_dupes > 0:
            st.info(dedupe_msg)

        quarantined_items = st.session_state.get('quarantined_items', set())
        if quarantined_items:
            original_count = len(inv_df)
            inv_df = inv_df[~inv_df["itemname"].isin(quarantined_items)].copy()
            filtered_count = original_count - len(inv_df)
            if filtered_count > 0:
                st.info(f"🚫 Filtered out {filtered_count} quarantined item(s) from slow movers analysis.")

        # -------------------------------------------------------
        # DATE COLUMN DETECTION (for velocity window & last-sale)
        # -------------------------------------------------------
        date_cols_sales = [col for col in sales_df.columns if 'date' in col]
        _last_sale_by_product: dict = {}
        _sales_date_col = date_cols_sales[0] if date_cols_sales else None
        _data_date_range = DEFAULT_SALES_PERIOD_DAYS  # fallback

        if _sales_date_col:
            sales_df[_sales_date_col] = pd.to_datetime(sales_df[_sales_date_col], errors='coerce')
            _dr = (sales_df[_sales_date_col].max() - sales_df[_sales_date_col].min()).days
            if _dr > 0:
                _data_date_range = _dr
            # Last-sale date per product
            _last_sale_by_product = (
                sales_df.groupby(sales_name_col)[_sales_date_col].max()
                .dropna().to_dict()
            )

        # -------------------------------------------------------
        # ---- FILTER BAR ----------------------------------------
        # -------------------------------------------------------
        st.markdown('<div class="sm-filter-bar">', unsafe_allow_html=True)
        st.markdown("##### 🔍 Filters & Settings")

        _fb_r1c1, _fb_r1c2, _fb_r1c3, _fb_r1c4 = st.columns([3, 2, 2, 2])
        with _fb_r1c1:
            sm_search = st.text_input(
                "Search (SKU / Product / Brand)",
                value="",
                placeholder="Type to filter…",
                key="sm_search",
                help="Filters by product name, SKU, or brand/vendor (case-insensitive).",
            )
        with _fb_r1c2:
            sm_velocity_window = st.selectbox(
                "Velocity window",
                options=SLOW_MOVER_VELOCITY_WINDOWS,
                index=1,
                format_func=lambda d: f"Last {d} days",
                key="sm_velocity_window",
                help=(
                    "The number of days used to compute average weekly sales. "
                    "Shorter windows reflect recent demand; longer windows smooth out spikes."
                ),
            )
        with _fb_r1c3:
            sm_doh_threshold = st.number_input(
                "Slow mover DOH >",
                min_value=1,
                max_value=999,
                value=SLOW_MOVER_DEFAULT_DOH_THRESHOLD,
                step=5,
                key="sm_doh_threshold",
                help=(
                    "Days-on-Hand (DOH) threshold: products with more than this many days "
                    "of supply are flagged as slow movers. Default is 60 days."
                ),
            )
        with _fb_r1c4:
            _top_n_labels = {25: "Top 25", 50: "Top 50", 100: "Top 100", 0: "All"}
            sm_top_n = st.selectbox(
                "Show top N",
                options=list(_top_n_labels.keys()),
                index=3,
                format_func=lambda k: _top_n_labels[k],
                key="sm_top_n",
                help="Limit results to the N worst slow movers.",
            )

        _fb_r2c1, _fb_r2c2, _fb_r2c3, _fb_r2c4 = st.columns([3, 2, 2, 2])
        with _fb_r2c1:
            # Category dropdown (populated from data)
            _cat_options_raw = []
            if inv_cat_col_raw and inv_cat_col_raw in inv_df.columns:
                _cat_options_raw = sorted(inv_df[inv_cat_col_raw].dropna().astype(str).unique().tolist())
            sm_category = st.selectbox(
                "Category / Subcategory",
                options=["All"] + _cat_options_raw,
                index=0,
                key="sm_category",
            )
        with _fb_r2c2:
            # Brand/Vendor dropdown
            _brand_options_raw = []
            if inv_brand_col and inv_brand_col in inv_df.columns:
                _brand_options_raw = sorted(inv_df[inv_brand_col].dropna().astype(str).unique().tolist())
            sm_brand = st.selectbox(
                "Vendor / Brand",
                options=["All"] + _brand_options_raw,
                index=0,
                key="sm_brand",
            )
        with _fb_r2c3:
            sm_sort_by = st.selectbox(
                "Sort by",
                options=SLOW_MOVER_SORT_OPTIONS,
                index=0,
                key="sm_sort_by",
            )
        with _fb_r2c4:
            sm_only_slow = st.toggle(
                "Only slow movers",
                value=True,
                key="sm_only_slow",
                help="When ON shows only products exceeding the DOH threshold; OFF shows all products.",
            )
            sm_exclude_zero = st.toggle(
                "Exclude on-hand = 0",
                value=False,
                key="sm_exclude_zero",
                help="Hide products with zero units on hand.",
            )

        st.markdown('</div>', unsafe_allow_html=True)

        # -------------------------------------------------------
        # COMPUTE VELOCITY USING SELECTED WINDOW
        # -------------------------------------------------------
        # Re-aggregate sales capped to selected velocity window
        if _sales_date_col:
            _cutoff = sales_df[_sales_date_col].max() - pd.Timedelta(days=sm_velocity_window)
            sales_window = sales_df[sales_df[_sales_date_col] >= _cutoff].copy()
            _effective_days = min(sm_velocity_window, _data_date_range) or sm_velocity_window
        else:
            sales_window = sales_df.copy()
            _effective_days = sm_velocity_window

        sales_velocity = (
            sales_window.groupby(sales_name_col)[sales_qty_col]
            .sum()
            .reset_index()
            .rename(columns={sales_name_col: "product", sales_qty_col: "total_sold"})
        )
        sales_velocity["daily_run_rate"] = sales_velocity["total_sold"] / max(_effective_days, 1)
        sales_velocity["avg_weekly_sales"] = sales_velocity["daily_run_rate"] * 7

        # -------------------------------------------------------
        # MERGE INVENTORY + SALES
        # -------------------------------------------------------
        slow_movers = inv_df.merge(
            sales_velocity,
            left_on="itemname",
            right_on="product",
            how="left",
        )

        slow_movers["daily_run_rate"] = slow_movers["daily_run_rate"].fillna(0)
        slow_movers["avg_weekly_sales"] = slow_movers["avg_weekly_sales"].fillna(0)
        slow_movers["total_sold"] = slow_movers["total_sold"].fillna(0)

        slow_movers["days_of_supply"] = np.where(
            slow_movers["daily_run_rate"] > 0,
            slow_movers["onhandunits"] / slow_movers["daily_run_rate"],
            UNKNOWN_DAYS_OF_SUPPLY,
        )
        slow_movers["weeks_of_supply"] = (slow_movers["days_of_supply"] / 7).round(1)

        # Days since last sale
        _today = pd.Timestamp.today().normalize()
        if _last_sale_by_product:
            def _days_since_last_sale(name):
                if name in _last_sale_by_product:
                    return int((_today - _last_sale_by_product[name]).days)
                return None
            slow_movers["days_since_last_sale"] = slow_movers["itemname"].map(_days_since_last_sale)
        else:
            slow_movers["days_since_last_sale"] = None

        # $ on-hand (if cost or retail price column available)
        if inv_cost_col and inv_cost_col in slow_movers.columns:
            slow_movers["dollars_on_hand"] = (
                slow_movers["onhandunits"] * slow_movers[inv_cost_col]
            )
        else:
            slow_movers["dollars_on_hand"] = None
        if "retail_price" in slow_movers.columns:
            slow_movers["retail_dollars_on_hand"] = (
                slow_movers["onhandunits"] * slow_movers["retail_price"]
            )

        # Slow-mover score and action badge
        slow_movers["sm_score"] = slow_movers.apply(
            lambda r: _sm_score(r["days_of_supply"], r["avg_weekly_sales"]), axis=1
        )
        slow_movers["action"] = slow_movers.apply(
            lambda r: _sm_action_badge(r["days_of_supply"], r["avg_weekly_sales"], r["onhandunits"]),
            axis=1,
        )

        # Legacy discount suggestion (preserved for export)
        def _suggest_discount(days):
            if days > 180:
                return "30-50% (Urgent)"
            elif days > 120:
                return "20-30% (High Priority)"
            elif days > 90:
                return "15-20% (Medium Priority)"
            elif days > 60:
                return "10-15% (Low Priority)"
            else:
                return "No discount needed"

        slow_movers["suggested_discount"] = slow_movers["days_of_supply"].apply(_suggest_discount)

        # -------------------------------------------------------
        # SERVER-SIDE FILTERING
        # -------------------------------------------------------
        working_df = slow_movers.copy()

        # Toggle: only slow movers
        if sm_only_slow:
            working_df = working_df[working_df["days_of_supply"] > sm_doh_threshold]

        # Toggle: exclude on-hand = 0
        if sm_exclude_zero:
            working_df = working_df[working_df["onhandunits"] > 0]

        # Category filter
        if sm_category != "All" and inv_cat_col_raw and inv_cat_col_raw in working_df.columns:
            working_df = working_df[working_df[inv_cat_col_raw].astype(str) == sm_category]

        # Brand filter
        if sm_brand != "All" and inv_brand_col and inv_brand_col in working_df.columns:
            working_df = working_df[working_df[inv_brand_col].astype(str) == sm_brand]

        # Search filter (SKU / product name / brand)
        if sm_search.strip():
            _q = sm_search.strip().lower()
            _mask = working_df["itemname"].str.lower().str.contains(_q, na=False)
            if inv_sku_col and inv_sku_col in working_df.columns:
                _mask |= working_df[inv_sku_col].astype(str).str.lower().str.contains(_q, na=False)
            if inv_brand_col and inv_brand_col in working_df.columns:
                _mask |= working_df[inv_brand_col].astype(str).str.lower().str.contains(_q, na=False)
            working_df = working_df[_mask]

        # Sort
        _sort_map = {
            "Days of Supply ↓": ("days_of_supply", False),
            "Weeks of Supply ↓": ("weeks_of_supply", False),
            "$ On-Hand ↓": ("dollars_on_hand", False),
            "Days Since Last Sale ↓": ("days_since_last_sale", False),
        }
        _sort_col, _sort_asc = _sort_map.get(sm_sort_by, ("days_of_supply", False))
        if _sort_col in working_df.columns:
            working_df = working_df.sort_values(_sort_col, ascending=_sort_asc, na_position="last")

        # Top-N
        if sm_top_n and sm_top_n > 0:
            working_df = working_df.head(sm_top_n)

        # -------------------------------------------------------
        # KPI SUMMARY STRIP
        # -------------------------------------------------------
        _slow_count = len(working_df[working_df["days_of_supply"] > sm_doh_threshold])
        _units_tied = int(working_df["onhandunits"].sum())
        _median_doh = working_df["days_of_supply"].replace(UNKNOWN_DAYS_OF_SUPPLY, np.nan).median()
        _median_doh_str = f"{_median_doh:.0f} days" if not pd.isna(_median_doh) else "N/A"

        # Worst category by $ tied up or by units
        _worst_cat_str = "N/A"
        if inv_cat_col_raw and inv_cat_col_raw in working_df.columns and not working_df.empty:
            try:
                if "dollars_on_hand" in working_df.columns and working_df["dollars_on_hand"].notna().any():
                    _worst_cat_str = (
                        working_df.groupby(inv_cat_col_raw)["dollars_on_hand"].sum()
                        .idxmax()
                    )
                else:
                    _worst_cat_str = (
                        working_df.groupby(inv_cat_col_raw)["onhandunits"].sum()
                        .idxmax()
                    )
            except ValueError:
                _worst_cat_str = "N/A"

        _dollars_tied_str = "N/A"
        if "dollars_on_hand" in working_df.columns and working_df["dollars_on_hand"].notna().any():
            _dollars_tied = working_df["dollars_on_hand"].sum()
            _dollars_tied_str = f"${_dollars_tied:,.0f}"

        st.markdown("#### 📌 Snapshot — Filtered Data")
        _kc1, _kc2, _kc3, _kc4, _kc5 = st.columns(5)
        _kc1.metric("🐢 Slow-moving SKUs", _slow_count,
                    help=f"Products with DOH > {sm_doh_threshold} days in current view.")
        _kc2.metric("📦 Units tied up", f"{_units_tied:,}",
                    help="Total units on hand across filtered products.")
        _kc3.metric("📊 Median DOH", _median_doh_str,
                    help="Days-on-Hand: units on hand ÷ daily run rate.")
        _kc4.metric("💰 $ Tied Up", _dollars_tied_str,
                    help="Estimated inventory value tied up (requires cost column).")
        _kc5.metric("🏷️ Worst Category", str(_worst_cat_str),
                    help="Category with most units (or $ if cost available) tied up in slow movers.")

        st.markdown("---")

        # -------------------------------------------------------
        # DECISION-FIRST TABLE (default columns: 7–9)
        # -------------------------------------------------------
        if working_df.empty:
            st.success("✅ No products match current filters. Try adjusting thresholds or filters.")
        else:
            # Build display columns
            _display_cols_map: dict = {}  # label -> source col
            _avg_weekly_label = f"Avg Wkly Sales ({sm_velocity_window}d)"

            if inv_sku_col and inv_sku_col in working_df.columns:
                _display_cols_map["SKU"] = inv_sku_col
            _display_cols_map["Product"] = "itemname"
            if inv_brand_col and inv_brand_col in working_df.columns:
                _display_cols_map["Brand/Vendor"] = inv_brand_col
            if inv_cat_col_raw and inv_cat_col_raw in working_df.columns:
                _display_cols_map["Category"] = inv_cat_col_raw
            _display_cols_map["On Hand"] = "onhandunits"
            _display_cols_map[_avg_weekly_label] = "avg_weekly_sales"
            _display_cols_map["DOH"] = "days_of_supply"
            _display_cols_map["Wks Supply"] = "weeks_of_supply"
            if "dollars_on_hand" in working_df.columns and working_df["dollars_on_hand"].notna().any():
                _display_cols_map["$ On-Hand"] = "dollars_on_hand"
            if "days_since_last_sale" in working_df.columns and working_df["days_since_last_sale"].notna().any():
                _display_cols_map["Days Since Sale"] = "days_since_last_sale"
            _display_cols_map["Action"] = "action"

            _src_cols = list(_display_cols_map.values())
            _lbl_cols = list(_display_cols_map.keys())

            display_df = working_df[[c for c in _src_cols if c in working_df.columns]].copy()
            display_df.columns = [_lbl_cols[i] for i, c in enumerate(_src_cols) if c in working_df.columns]

            # Round numeric columns
            for _lbl in [_avg_weekly_label, "DOH", "Wks Supply"]:
                if _lbl in display_df.columns:
                    display_df[_lbl] = display_df[_lbl].replace(
                        UNKNOWN_DAYS_OF_SUPPLY, np.nan
                    ).round(1)
            if "On Hand" in display_df.columns:
                display_df["On Hand"] = display_df["On Hand"].round(0).astype(int)
            if "$ On-Hand" in display_df.columns:
                display_df["$ On-Hand"] = pd.to_numeric(
                    display_df["$ On-Hand"], errors="coerce"
                ).round(2)
            if "Days Since Sale" in display_df.columns:
                display_df["Days Since Sale"] = pd.to_numeric(
                    display_df["Days Since Sale"], errors="coerce"
                ).astype("Int64")

            st.markdown(
                f"**Showing {len(display_df)} product(s)** "
                f"(velocity window: {sm_velocity_window} days | DOH threshold: {sm_doh_threshold})"
            )

            st.markdown('<div class="sm-table-wrap">', unsafe_allow_html=True)
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)

            # -------------------------------------------------------
            # EXPANDABLE: Show more columns (all original data)
            # -------------------------------------------------------
            with st.expander("🔎 Show full detail / all columns"):
                st.dataframe(
                    working_df.replace(UNKNOWN_DAYS_OF_SUPPLY, np.nan),
                    use_container_width=True,
                    hide_index=True,
                )

            # -------------------------------------------------------
            # DISCOUNT TIER SUMMARY (preserved from original)
            # -------------------------------------------------------
            st.markdown("### 📉 Discount Tier Summary")
            tier_summary = (
                working_df.groupby("suggested_discount")
                .agg(product_count=("itemname", "count"), total_units=("onhandunits", "sum"))
                .reset_index()
                .rename(columns={
                    "suggested_discount": "Discount Tier",
                    "product_count": "Product Count",
                    "total_units": "Total Units",
                })
            )
            st.dataframe(tier_summary, use_container_width=True, hide_index=True)

            # -------------------------------------------------------
            # EXPORT (preserves existing functionality + adds detail sheet)
            # -------------------------------------------------------
            st.markdown("### 📥 Export")
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                display_df.to_excel(writer, sheet_name='Slow Movers', index=False)
                tier_summary.to_excel(writer, sheet_name='Summary', index=False)
                working_df.replace(UNKNOWN_DAYS_OF_SUPPLY, np.nan).to_excel(
                    writer, sheet_name='Full Detail', index=False
                )
            output.seek(0)

            st.download_button(
                label="📥 Download Slow Movers Report (Excel)",
                data=output,
                file_name=f"slow_movers_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    except Exception as e:
        st.error(f"Error analyzing slow movers: {str(e)}")
        import traceback
        st.write("Debug info:", traceback.format_exc())

# ============================================================
# PAGE – PO BUILDER
# ============================================================
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
                st.dataframe(reorder_rows[_xref_cols].reset_index(drop=True), use_container_width=True)

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

        st.dataframe(items_df, use_container_width=True)
        
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
