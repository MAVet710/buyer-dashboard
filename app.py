import streamlit as st
import pandas as pd
import numpy as np
import re
import json
import os
from datetime import datetime, timedelta
from io import BytesIO

# For PDF generation
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

# ------------------------------------------------------------
# OPTIONAL / SAFE IMPORT FOR PLOTLY
# ------------------------------------------------------------
try:
    import plotly.express as px  # noqa: F401
    PLOTLY_AVAILABLE = True
except Exception:
    PLOTLY_AVAILABLE = False

# ------------------------------------------------------------
# OPTIONAL / SAFE IMPORT FOR OPENAI (AI INVENTORY CHECK)
# ------------------------------------------------------------
OPENAI_AVAILABLE = False
ai_client = None


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


# Common alias sets (used repeatedly)
INV_NAME_ALIASES = [
    "product", "productname", "item", "itemname", "name", "skuname",
    "skuid", "product name", "product_name", "product title", "title"
]
INV_CAT_ALIASES = [
    "category", "subcategory", "productcategory", "department",
    "mastercategory", "product category", "cannabis", "product_category"
]
INV_QTY_ALIASES = [
    "available", "onhand", "onhandunits", "quantity", "qty",
    "quantityonhand", "instock", "currentquantity", "current quantity",
    "inventoryavailable", "inventory available", "available quantity"
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

# Constants for slow movers analysis
UNKNOWN_DAYS_OF_SUPPLY = 999
DEFAULT_SALES_PERIOD_DAYS = 30  # Default assumption when date range cannot be determined

# Constants for PDF generation
MAX_SKU_LENGTH_PDF = 10
MAX_DESCRIPTION_LENGTH_PDF = 20
MAX_STRAIN_LENGTH_PDF = 10
MAX_SIZE_LENGTH_PDF = 8


def _find_openai_key():
    """
    Robust key lookup:
    1) st.secrets["OPENAI_API_KEY"] at top-level
    2) Any nested table that contains OPENAI_API_KEY
    3) os.environ["OPENAI_API_KEY"]
    Returns (key or None, where_found_str)
    """
    # 1) top-level
    try:
        if "OPENAI_API_KEY" in st.secrets:
            k = str(st.secrets["OPENAI_API_KEY"]).strip()
            if k:
                return k, "secrets:top"
    except Exception:
        pass

    # 2) nested
    try:
        for k0 in list(st.secrets.keys()):
            try:
                v = st.secrets.get(k0)
                if isinstance(v, dict) and "OPENAI_API_KEY" in v:
                    k = str(v["OPENAI_API_KEY"]).strip()
                    if k:
                        return k, f"secrets:{k0}"
            except Exception:
                continue
    except Exception:
        pass

    # 3) env
    envk = os.environ.get("OPENAI_API_KEY", "").strip()
    if envk:
        return envk, "env"

    return None, None


def init_openai_client():
    global OPENAI_AVAILABLE, ai_client
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        OPENAI_AVAILABLE = False
        ai_client = None
        return

    key, _where = _find_openai_key()
    if key:
        try:
            ai_client = OpenAI(api_key=key)
            OPENAI_AVAILABLE = True
        except Exception:
            OPENAI_AVAILABLE = False
            ai_client = None
    else:
        OPENAI_AVAILABLE = False
        ai_client = None


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
APP_TITLE = f"{CLIENT_NAME} Purchasing Dashboard"
APP_TAGLINE = "Streamlined purchasing visibility powered by Dutchie / BLAZE data."
LICENSE_FOOTER = "Semper Paratus • Powered by Good Weed and Data"

# 🔐 TRIAL SETTINGS
TRIAL_KEY = "mavet24"
TRIAL_DURATION_HOURS = 24

# 👑 ADMIN CREDS (multiple admins)
ADMIN_USERS = {
    "God": "Major420",
    "JVas": "UPG2025",
}

# 👤 STANDARD USER CREDS (non-admin)
USER_USERS = {
    "KHuston": "ChangeMe!",
    "ERoots": "Test420",
    "AFreed": "Test710",
}

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
if "theme" not in st.session_state:
    st.session_state.theme = "Dark"  # Dark by default
if "strain_lookup_enabled" not in st.session_state:
    st.session_state.strain_lookup_enabled = True  # Enable free strain database lookup by default

# Upload tracking (God-only viewer)
if "upload_log" not in st.session_state:
    st.session_state.upload_log = []  # list of dicts
if "uploaded_files_store" not in st.session_state:
    # key: upload_id -> {"name":..., "bytes":..., "uploader":..., "ts":...}
    st.session_state.uploaded_files_store = {}

# Upload de-dupe signature store (prevents repeated logging on reruns)
if "_upload_sig_seen" not in st.session_state:
    st.session_state._upload_sig_seen = set()

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
    </style>
    """,
    unsafe_allow_html=True,
)

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

    if name.endswith((".csv",)):
        return pd.read_csv(uploaded_file)

    if name.endswith((".xlsx", ".xls")):
        tmp = pd.read_excel(uploaded_file, header=None)
        header_row = 0
        max_scan = min(25, len(tmp))
        for i in range(max_scan):
            row_text = " ".join(str(v) for v in tmp.iloc[i].tolist()).lower()
            if any(tok in row_text for tok in ["date", "received", "delivery"]) and any(tok in row_text for tok in ["product", "item", "sku", "name"]):
                header_row = i
                break
        uploaded_file.seek(0)
        return pd.read_excel(uploaded_file, header=header_row)

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


# =========================
# SIMPLE AI INVENTORY CHECK
# =========================
def ai_inventory_check(detail_view, doh_threshold, data_source):
    """
    Send a small slice of the current table to the AI so it can
    comment on obvious issues: zero on-hand, crazy DOH, etc.
    """
    if not OPENAI_AVAILABLE or ai_client is None:
        return (
            "AI is not enabled. Add OPENAI_API_KEY to Streamlit secrets "
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
        resp = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a sharp, no-BS cannabis retail buyer coach."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=600,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"AI check failed: {e}"


# =========================
# INIT OPENAI + SHOW DEBUG (kept)
# =========================
init_openai_client()

# Always show debug panel (requested to keep) — does NOT reveal the key.
with st.sidebar.expander("🔍 AI Debug Info", expanded=False):
    key1 = False
    key2 = False
    where = None
    try:
        key, where = _find_openai_key()
        key1 = bool(key)
    except Exception:
        key1 = False
    key2 = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    st.write(f"Secrets has OPENAI_API_KEY: {key1}")
    st.write(f"Env has OPENAI_API_KEY: {key2}")
    st.write(f"Using key: {OPENAI_AVAILABLE}")
    if where:
        st.write(f"Found via: {where}")

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
    admin_user = st.sidebar.text_input("Username", key="admin_user_input")
    admin_pass = st.sidebar.text_input("Password", type="password", key="admin_pass_input")
    if st.sidebar.button("Login as Admin"):
        if admin_user in ADMIN_USERS and admin_pass == ADMIN_USERS[admin_user]:
            st.session_state.is_admin = True
            st.session_state.admin_user = admin_user
            st.sidebar.success("✅ Admin mode enabled.")
        else:
            st.sidebar.error("❌ Invalid admin credentials.")
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
    u_user = st.sidebar.text_input("Username", key="user_user_input")
    u_pass = st.sidebar.text_input("Password", type="password", key="user_pass_input")
    if st.sidebar.button("Login", key="login_user_btn"):
        if u_user in USER_USERS and u_pass == USER_USERS[u_user]:
            st.session_state.user_authenticated = True
            st.session_state.user_user = u_user
            st.sidebar.success("✅ User access enabled.")
        else:
            st.sidebar.error("❌ Invalid user credentials.")
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
            if trial_key_input.strip() == TRIAL_KEY:
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
# HEADER
# =========================
st.title(f"🌿 {APP_TITLE}")
st.markdown(f"**Brand:** {CLIENT_NAME}")
st.markdown(APP_TAGLINE)
if OPENAI_AVAILABLE:
    st.markdown("✅ AI buyer-assist is **ON** for this session.")
else:
    st.markdown("⚠️ AI buyer-assist is **OFF** (no API key detected).")
st.markdown("---")

if not PLOTLY_AVAILABLE:
    st.warning(
        "⚠️ Plotly is not installed in this environment. Charts will be disabled.\n\n"
        "If using Streamlit Cloud, add `plotly` and `reportlab` to your `requirements.txt` file."
    )

# =========================
# GOD-ONLY: Upload viewer (requested)
# =========================
if st.session_state.is_admin and st.session_state.admin_user == "God":
    with st.sidebar.expander("🗂️ Upload Viewer (God)", expanded=False):
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

# =========================
# PAGE SWITCH
# =========================
section = st.sidebar.radio(
    "App Section",
    ["📊 Inventory Dashboard", "📈 Trends", "🚚 Delivery Impact", "🐢 Slow Movers", "🧾 PO Builder"],
    index=0,
)

# ============================================================
# PAGE 1 – INVENTORY DASHBOARD
# ============================================================
if section == "📊 Inventory Dashboard":

    st.sidebar.markdown("### 🧩 Data Source")
    data_source = st.sidebar.selectbox(
        "Select POS / Data Source",
        ["Dutchie", "BLAZE"],
        index=0,
        help="Changes how column names are interpreted. Files are still CSV/XLSX exports.",
    )

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
            st.session_state[cache_key] = {"name": getattr(file_obj, "name", "upload"), "bytes": b}
        except Exception:
            return

    def _load_cached(cache_key: str):
        obj = st.session_state.get(cache_key)
        if isinstance(obj, dict) and obj.get("bytes"):
            return _UploadedFileLike(obj["bytes"], obj.get("name", "cached_upload"))
        return None

    _cache_upload(inv_file, "_cache_inv")
    _cache_upload(product_sales_file, "_cache_sales")
    _cache_upload(extra_sales_file, "_cache_extra_sales")
    _cache_upload(quarantine_file, "_cache_quarantine")

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

    if st.sidebar.button("🧹 Clear cached uploads"):
        for k in ["_cache_inv", "_cache_sales", "_cache_extra_sales", "_cache_quarantine"]:
            if k in st.session_state:
                del st.session_state[k]
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
                # Extract and normalize product names
                quarantined_items = set(
                    quarantine_df[quarantine_name_col].astype(str).str.strip().tolist()
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
        st.info("Upload inventory + product sales files to continue.")
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
        inv_df["strain_type"] = inv_df.apply(lambda x: extract_strain_type(x.get("itemname", ""), x.get("subcategory", "")), axis=1)
        inv_df["packagesize"] = inv_df.apply(lambda x: extract_size(x.get("itemname", ""), x.get("subcategory", "")), axis=1)

        inv_summary = (
            inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["onhandunits"]
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

        sales_summary = (
            sales_df.groupby(["mastercategory", "packagesize"], dropna=False)["unitssold"]
            .sum()
            .reset_index()
        )
        sales_summary["avgunitsperday"] = (sales_summary["unitssold"] / max(int(date_diff), 1)) * float(velocity_adjustment)

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
            st.markdown("#### Category DOS (at a glance)")
            st.dataframe(
                cat_quick[["subcategory", "category_dos", "reorder_lines"]].sort_values(
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

        display_cols = [
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
            1) SKU-level view (sales-weighted) for this row slice
            2) Batch rollup (if inventory batch data exists)

            IMPORTANT: Always returns (sku_df, batch_df) so callers can safely unpack.
            """
            empty = (pd.DataFrame(), pd.DataFrame())

            # --- SALES SLICE ---
            sd = sales_df[(sales_df["mastercategory"] == cat) & (sales_df["packagesize"] == size)].copy()

            if str(strain_type).lower() != "unspecified":
                sd = sd[sd["strain_type"].astype(str).str.lower() == str(strain_type).lower()]

            if sd.empty:
                return empty

            sd["est_units_per_day"] = (sd["unitssold"] / max(int(date_diff), 1)) * float(velocity_adjustment)

            # --- INVENTORY SLICE ---
            idf = inv_df[(inv_df["subcategory"] == cat) & (inv_df["packagesize"] == size)].copy()
            if str(strain_type).lower() != "unspecified":
                idf = idf[idf["strain_type"].astype(str).str.lower() == str(strain_type).lower()]

            cols = []
            if "sku" in sd.columns:
                cols.append("sku")
            cols += ["product_name", "unitssold", "est_units_per_day"]
            sku_df = sd[cols].copy()

            if not idf.empty:
                inv_cols = ["itemname", "onhandunits"]
                if "batch" in idf.columns:
                    inv_cols.append("batch")
                inv_small = idf[inv_cols].copy().rename(columns={"itemname": "product_name"})
                sku_df = pd.merge(sku_df, inv_small, how="left", on="product_name")

            if "onhandunits" not in sku_df.columns:
                sku_df["onhandunits"] = 0
            sku_df["onhandunits"] = pd.to_numeric(sku_df["onhandunits"], errors="coerce").fillna(0)

            sku_df = sku_df.sort_values("est_units_per_day", ascending=False).head(50)

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
                    g.style.applymap(red_low, subset=["daysonhand"]),
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
                "AI buyer-assist is disabled because no `OPENAI_API_KEY` was found in "
                "Streamlit secrets or environment."
            )

    except Exception as e:
        st.error(f"Error: {e}")


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
    st.subheader("Delivery Impact Analysis")
    st.write(
        "Use this page to measure whether deliveries correlate with an uptick in sales. "
        "For best results, upload (1) a delivery/receiving report with a received date and quantities, "
        "and (2) a daily sales report that includes a date column."
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📦 Delivery File")
        delivery_file = st.file_uploader(
            "Upload delivery/receiving report (CSV or XLSX)",
            type=["csv", "xlsx"],
            key="delivery_upload"
        )
    
    with col2:
        st.markdown("#### 📈 Daily Sales File")
        daily_sales_file = st.file_uploader(
            "Upload daily sales report (CSV or XLSX)",
            type=["csv", "xlsx"],
            key="daily_sales_upload"
        )
    
    if delivery_file and daily_sales_file:
        try:
            # Parse delivery file
            if delivery_file.name.endswith('.csv'):
                delivery_df = pd.read_csv(delivery_file)
            else:
                delivery_df = pd.read_excel(delivery_file)
            
            # Parse daily sales file
            if daily_sales_file.name.endswith('.csv'):
                daily_sales_df = pd.read_csv(daily_sales_file)
            else:
                daily_sales_df = pd.read_excel(daily_sales_file)
            
            # Normalize column names
            delivery_df.columns = delivery_df.columns.str.lower().str.strip()
            daily_sales_df.columns = daily_sales_df.columns.str.lower().str.strip()
            
            # Find date columns
            delivery_date_cols = [col for col in delivery_df.columns if 'date' in col or 'received' in col]
            sales_date_cols = [col for col in daily_sales_df.columns if 'date' in col]
            
            if delivery_date_cols and sales_date_cols:
                delivery_df['delivery_date'] = pd.to_datetime(delivery_df[delivery_date_cols[0]], errors='coerce')
                daily_sales_df['sale_date'] = pd.to_datetime(daily_sales_df[sales_date_cols[0]], errors='coerce')
                
                # Find category columns
                delivery_cat_cols = [col for col in delivery_df.columns if 'category' in col or 'product' in col]
                sales_cat_cols = [col for col in daily_sales_df.columns if 'category' in col or 'product' in col]
                
                if delivery_cat_cols:
                    delivery_df['category'] = delivery_df[delivery_cat_cols[0]]
                else:
                    delivery_df['category'] = 'All Products'
                
                if sales_cat_cols:
                    daily_sales_df['category'] = daily_sales_df[sales_cat_cols[0]]
                else:
                    daily_sales_df['category'] = 'All Products'
                
                # Group by date and category
                delivery_by_date = delivery_df.groupby(['delivery_date', 'category']).size().reset_index(name='delivery_count')
                sales_by_date = daily_sales_df.groupby(['sale_date', 'category']).size().reset_index(name='sales_count')
                
                st.markdown("### 📊 Analysis Results")
                
                # Show delivery dates
                st.markdown("#### Delivery Dates")
                st.dataframe(delivery_by_date.sort_values('delivery_date', ascending=False), use_container_width=True)
                
                # Analyze impact for each delivery
                st.markdown("#### Impact Analysis")
                impact_results = []
                
                for _, delivery in delivery_by_date.iterrows():
                    del_date = delivery['delivery_date']
                    category = delivery['category']
                    
                    # Get sales 7 days before and after delivery
                    pre_sales = sales_by_date[
                        (sales_by_date['category'] == category) &
                        (sales_by_date['sale_date'] >= del_date - timedelta(days=7)) &
                        (sales_by_date['sale_date'] < del_date)
                    ]['sales_count'].mean()
                    
                    post_sales = sales_by_date[
                        (sales_by_date['category'] == category) &
                        (sales_by_date['sale_date'] > del_date) &
                        (sales_by_date['sale_date'] <= del_date + timedelta(days=7))
                    ]['sales_count'].mean()
                    
                    if pd.notna(pre_sales) and pd.notna(post_sales) and pre_sales > 0:
                        impact_pct = ((post_sales - pre_sales) / pre_sales) * 100
                    else:
                        impact_pct = 0
                    
                    impact_results.append({
                        'Delivery Date': del_date,
                        'Category': category,
                        'Avg Daily Sales (7d Before)': round(pre_sales, 2) if pd.notna(pre_sales) else 0,
                        'Avg Daily Sales (7d After)': round(post_sales, 2) if pd.notna(post_sales) else 0,
                        'Impact %': round(impact_pct, 2)
                    })
                
                if impact_results:
                    impact_df = pd.DataFrame(impact_results)
                    st.dataframe(impact_df.sort_values('Impact %', ascending=False), use_container_width=True)
                    
                    # Summary metrics
                    st.markdown("#### Category-Level Metrics")
                    category_summary = impact_df.groupby('Category').agg({
                        'Impact %': 'mean'
                    }).reset_index()
                    category_summary.columns = ['Category', 'Avg Impact %']
                    category_summary['Avg Impact %'] = category_summary['Avg Impact %'].round(2)
                    st.dataframe(category_summary, use_container_width=True)
                else:
                    st.warning("No impact data could be calculated. Ensure your files have overlapping date ranges.")
            else:
                st.error("Could not find date columns in the uploaded files.")
        
        except Exception as e:
            st.error(f"Error processing files: {str(e)}")
            st.write("Please ensure your files have date columns and are properly formatted.")
    else:
        st.info("👆 Upload both files to see the analysis")

# ============================================================
# PAGE – SLOW MOVERS
# ============================================================
elif section == "🐢 Slow Movers":
    st.subheader("Slow Movers Analysis")
    st.write(
        "Identify products that are sitting on the shelf with long gaps between sales. "
        "Get discount recommendations to move slow inventory faster."
    )
    
    if st.session_state.inv_raw_df is None or st.session_state.sales_raw_df is None:
        st.warning("⚠️ Please upload inventory and sales files in the Inventory Dashboard section first.")
        st.stop()
    
    try:
        # Get data from session state
        inv_df = st.session_state.inv_raw_df.copy()
        sales_df = st.session_state.sales_raw_df.copy()
        
        # Normalize column names consistently
        inv_df.columns = inv_df.columns.astype(str).str.strip().str.lower()
        sales_df.columns = sales_df.columns.astype(str).str.strip().str.lower()
        
        # Calculate sales velocity
        st.markdown("### 📊 Slow Movers Identification")
        
        # Use detect_column helper for consistent column detection
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
        
        # Aggregate sales by product
        sales_velocity = sales_df.groupby(sales_name_col).agg({
            sales_qty_col: 'sum'
        }).reset_index()
        sales_velocity.columns = ['product', 'total_sold']
        
        # Calculate daily run rate - find date column
        date_cols = [col for col in sales_df.columns if 'date' in col]
        if date_cols:
            sales_df[date_cols[0]] = pd.to_datetime(sales_df[date_cols[0]], errors='coerce')
            date_range = (sales_df[date_cols[0]].max() - sales_df[date_cols[0]].min()).days
            if date_range > 0:
                sales_velocity['days_of_data'] = date_range
                sales_velocity['daily_run_rate'] = sales_velocity['total_sold'] / date_range
            else:
                sales_velocity['daily_run_rate'] = sales_velocity['total_sold'] / DEFAULT_SALES_PERIOD_DAYS
        else:
            sales_velocity['daily_run_rate'] = sales_velocity['total_sold'] / DEFAULT_SALES_PERIOD_DAYS
        
        # Find inventory columns using detect_column helper
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
        
        # Rename columns for consistency
        inv_df = inv_df.rename(columns={inv_name_col: "itemname", inv_qty_col: "onhandunits"})
        if inv_batch_col:
            inv_df = inv_df.rename(columns={inv_batch_col: "batch"})
        
        # Normalize product names for better matching
        inv_df["itemname"] = inv_df["itemname"].astype(str).str.strip()
        inv_df["onhandunits"] = pd.to_numeric(inv_df["onhandunits"], errors="coerce").fillna(0)
        
        # Apply deduplication to inventory before analysis
        inv_df, num_dupes, dedupe_msg = deduplicate_inventory(inv_df)
        if num_dupes > 0:
            st.info(dedupe_msg)
        
        # Filter out quarantined items
        quarantined_items = st.session_state.get('quarantined_items', set())
        if quarantined_items:
            original_count = len(inv_df)
            inv_df = inv_df[~inv_df["itemname"].isin(quarantined_items)].copy()
            filtered_count = original_count - len(inv_df)
            if filtered_count > 0:
                st.info(f"🚫 Filtered out {filtered_count} quarantined item(s) from slow movers analysis.")
        else:
            st.info("ℹ️ No quarantine list uploaded. All items included in analysis.")
        
        # Merge with inventory
        slow_movers = inv_df.merge(
            sales_velocity,
            left_on="itemname",
            right_on='product',
            how='left'
        )
        
        # Calculate days of supply
        slow_movers['daily_run_rate'] = slow_movers['daily_run_rate'].fillna(0)
        slow_movers['days_of_supply'] = np.where(
            slow_movers['daily_run_rate'] > 0,
            slow_movers["onhandunits"] / slow_movers['daily_run_rate'],
            UNKNOWN_DAYS_OF_SUPPLY
        )
        
        # Identify slow movers (more than 60 days of supply)
        slow_movers_filtered = slow_movers[slow_movers['days_of_supply'] > 60].copy()
        
        if not slow_movers_filtered.empty:
            # Add discount tier suggestions
            def suggest_discount(days):
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
            
            slow_movers_filtered['suggested_discount'] = slow_movers_filtered['days_of_supply'].apply(suggest_discount)
            
            # Find category column using detect_column
            cat_col = detect_column(slow_movers_filtered.columns, [normalize_col(a) for a in INV_CAT_ALIASES])
            
            # Display results
            display_cols = ["itemname", "onhandunits", 'daily_run_rate', 'days_of_supply', 'suggested_discount']
            col_names = ['Product', 'On Hand', 'Daily Run Rate', 'Days of Supply', 'Suggested Discount']
            
            if cat_col:
                display_cols.insert(1, cat_col)
                col_names.insert(1, 'Category')
            
            display_df = slow_movers_filtered[display_cols].copy()
            display_df.columns = col_names
            display_df['Days of Supply'] = display_df['Days of Supply'].round(1)
            display_df['Daily Run Rate'] = display_df['Daily Run Rate'].round(2)
            display_df = display_df.sort_values('Days of Supply', ascending=False)
            
            st.markdown(f"**Found {len(display_df)} slow moving products**")
            st.dataframe(display_df, use_container_width=True)
            
            # Summary by discount tier
            st.markdown("### 📉 Discount Tier Summary")
            tier_summary = display_df.groupby('Suggested Discount').agg({
                'Product': 'count',
                'On Hand': 'sum'
            }).reset_index()
            tier_summary.columns = ['Discount Tier', 'Product Count', 'Total Units']
            st.dataframe(tier_summary, use_container_width=True)
            
            # Export to Excel
            st.markdown("### 📥 Export")
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                display_df.to_excel(writer, sheet_name='Slow Movers', index=False)
                tier_summary.to_excel(writer, sheet_name='Summary', index=False)
            output.seek(0)
            
            st.download_button(
                label="📥 Download Slow Movers Report (Excel)",
                data=output,
                file_name=f"slow_movers_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.success("✅ No slow movers found! All products are moving well.")
    
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
