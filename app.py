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
        st.experimental_rerun()


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
    """Map similar names to canonical categories."""
    s = str(raw).lower().strip()

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
    """
    s = str(text).lower()

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
    """
    s = str(name).lower()
    cat = str(subcat).lower()

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


def read_sales_file(uploaded_file):
    """
    Read Excel sales report with smart header detection.
    Looks for a row that contains something like 'category' and 'product'
    (Dutchie 'Product Sales Report' style).
    """
    uploaded_file.seek(0)
    tmp = pd.read_excel(uploaded_file, header=None)
    header_row = 0
    max_scan = min(20, len(tmp))
    for i in range(max_scan):
        row_text = " ".join(str(v) for v in tmp.iloc[i].tolist()).lower()
        if "category" in row_text and ("product" in row_text or "name" in row_text):
            header_row = i
            break
    uploaded_file.seek(0)
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
        # stable signature without heavy hashing libs
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

    if st.sidebar.button("🧹 Clear cached uploads"):
        for k in ["_cache_inv", "_cache_sales", "_cache_extra_sales"]:
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

        inv_df["onhandunits"] = pd.to_numeric(inv_df["onhandunits"], errors="coerce").fillna(0)

        # -------- Optional batch de-duplication (prevents accidental double-counting) --------
        if "batch" in inv_df.columns:
            inv_df["batch"] = inv_df["batch"].astype(str).str.strip()
            inv_df["batch"] = inv_df["batch"].replace({"": np.nan, "nan": np.nan, "none": np.nan})

            has_batch = inv_df["batch"].notna()
            if has_batch.any():
                dedupe_keys = ["sku", "batch"] if "sku" in inv_df.columns else ["itemname", "batch"]

                inv_with = inv_df[has_batch].copy()
                inv_without = inv_df[~has_batch].copy()

                agg_map = {"onhandunits": "max"}
                for c in ["itemname", "subcategory"]:
                    if c in inv_with.columns and c not in dedupe_keys:
                        agg_map[c] = "first"
                if "sku" in inv_with.columns and "sku" not in dedupe_keys:
                    agg_map["sku"] = "first"
                if "batch" in inv_with.columns and "batch" not in dedupe_keys:
                    agg_map["batch"] = "first"

                inv_with = (
                    inv_with.sort_values("onhandunits", ascending=False)
                    .groupby(dedupe_keys, dropna=False, as_index=False)
                    .agg(agg_map)
                )
                inv_df = pd.concat([inv_with, inv_without], ignore_index=True)

        inv_df["subcategory"] = inv_df["subcategory"].apply(normalize_rebelle_category)
        inv_df["strain_type"] = inv_df.apply(lambda x: extract_strain_type(x.get("itemname", ""), x.get("subcategory", "")), axis=1)
        inv_df["packagesize"] = inv_df.apply(lambda x: extract_size(x.get("itemname", ""), x.get("subcategory", "")), axis=1)

        inv_summary = (
            inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["onhandunits"]
            .sum()
            .reset_index()
        )

        # -------- SALES (qty-based ONLY) --------
        sales_raw.columns = sales_raw.columns.astype(str).str.lower()

        name_col_sales = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_NAME_ALIASES])
        qty_col_sales = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_QTY_ALIASES])
        mc_col = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_CAT_ALIASES])
        sales_sku_col = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_SKU_ALIASES])

        if not (name_col_sales and qty_col_sales and mc_col):
            st.error(
                "Product Sales file detected but could not find required columns.\n\n"
                "Looked for: product name, units/quantity sold, and category.\n\n"
                "Tip: Use Dutchie 'Product Sales Report' (qty) without editing headers."
            )
            st.stop()

        sales_raw = sales_raw.rename(columns={name_col_sales: "product_name", qty_col_sales: "unitssold", mc_col: "mastercategory"})
        if sales_sku_col:
            sales_raw = sales_raw.rename(columns={sales_sku_col: "sku"})

        sales_raw["unitssold"] = pd.to_numeric(sales_raw["unitssold"], errors="coerce").fillna(0)
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

        # ============================================================
        # EDUCATED GUESS ROWS (DO NOT REMOVE)
        # - Flower: ensure 28g row exists and has estimated velocity if possible
        # - Edibles: ensure 500mg row exists and has estimated velocity if possible
        # ============================================================

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

    st.sidebar.header("📂 Upload Delivery + Daily Sales Reports")
    delivery_file = st.sidebar.file_uploader(
        "Delivery / Receiving Report (CSV/XLSX preferred, PDF accepted best-effort)",
        type=["csv", "xlsx", "xls", "pdf"],
        key="delivery_file_uploader",
    )
    daily_sales_file = st.sidebar.file_uploader(
        "Daily Sales Report (CSV/XLSX with Date + Units/Revenue)",
        type=["csv", "xlsx", "xls"],
        key="daily_sales_file_uploader",
    )

    current_user = st.session_state.admin_user if st.session_state.is_admin else (st.session_state.user_user if st.session_state.user_authenticated else "trial_user")
    if delivery_file is not None:
        track_upload(delivery_file, current_user, "delivery_report")
    if daily_sales_file is not None:
        track_upload(daily_sales_file, current_user, "daily_sales_report")

    if delivery_file is not None:
        try:
            st.session_state.delivery_raw_df = read_delivery_file(delivery_file)
        except Exception as e:
            st.error(f"Error reading delivery report: {e}")
            st.stop()

    if daily_sales_file is not None:
        try:
            st.session_state.daily_sales_raw_df = read_daily_sales_file(daily_sales_file)
        except Exception as e:
            st.error(f"Error reading daily sales report: {e}")
            st.stop()

    if st.session_state.delivery_raw_df is None or st.session_state.daily_sales_raw_df is None:
        st.info("Upload both a delivery report and a daily sales report to run the analysis.")
        st.stop()

    delivery_raw = st.session_state.delivery_raw_df.copy()
    daily_raw = st.session_state.daily_sales_raw_df.copy()

    if list(delivery_raw.columns) == ["raw"] or delivery_raw.shape[1] <= 1:
        st.warning(
            "The delivery PDF could not be reliably parsed into columns. "
            "If possible, export the receiving report as CSV/XLSX from your source system and upload that instead."
        )
        st.dataframe(delivery_raw.head(50), use_container_width=True)
        st.stop()

    # ---------- Normalize Delivery columns ----------
    delivery_raw.columns = delivery_raw.columns.astype(str).str.strip().str.lower()

    del_date_aliases = [
        "receiveddate", "received date", "deliverydate", "delivery date", "date received",
        "date", "received", "posteddate", "posted date"
    ]
    del_name_aliases = ["product", "productname", "item", "itemname", "name", "description", "sku name", "product name"]
    del_qty_aliases = [
        "qty", "quantity", "quantityreceived", "quantity received", "receivedqty", "received qty",
        "units", "unitsreceived", "units received", "receivedunits", "received units"
    ]
    del_cat_aliases = ["category", "subcategory", "department", "product category", "productcategory"]
    del_batch_aliases = ["batch", "batchnumber", "batch number", "lot", "lotnumber", "lot number"]

    del_date_col = detect_column(delivery_raw.columns, [normalize_col(a) for a in del_date_aliases])
    del_name_col = detect_column(delivery_raw.columns, [normalize_col(a) for a in del_name_aliases])
    del_qty_col = detect_column(delivery_raw.columns, [normalize_col(a) for a in del_qty_aliases])
    del_cat_col = detect_column(delivery_raw.columns, [normalize_col(a) for a in del_cat_aliases])
    del_batch_col = detect_column(delivery_raw.columns, [normalize_col(a) for a in del_batch_aliases])

    if not (del_date_col and del_name_col and del_qty_col):
        st.error(
            "Could not detect required delivery columns. Your delivery report must include: "
            "a received/delivery date, a product name, and a quantity received."
        )
        st.write("Detected columns:", list(delivery_raw.columns))
        st.stop()

    delivery = delivery_raw.rename(columns={del_date_col: "received_date", del_name_col: "product_name", del_qty_col: "qty_received"}).copy()

    if del_cat_col:
        delivery = delivery.rename(columns={del_cat_col: "category"})
        delivery["category"] = delivery["category"].apply(normalize_rebelle_category)
    else:
        delivery["category"] = "unspecified"

    if del_batch_col:
        delivery = delivery.rename(columns={del_batch_col: "batch"})
    else:
        delivery["batch"] = ""

    delivery["qty_received"] = pd.to_numeric(delivery["qty_received"], errors="coerce").fillna(0)
    delivery["received_date"] = pd.to_datetime(delivery["received_date"], errors="coerce")
    delivery = delivery.dropna(subset=["received_date"])
    if delivery.empty:
        st.error("No valid received/delivery dates found after parsing.")
        st.stop()

    # ---------- Normalize Daily Sales columns ----------
    daily_raw.columns = daily_raw.columns.astype(str).str.strip().str.lower()

    ds_date_aliases = ["date", "sale date", "salesdate", "business date", "day", "orderdate", "order date"]
    ds_cat_aliases = ["category", "subcategory", "department", "product category", "mastercategory"]
    ds_name_aliases = ["product", "productname", "product name", "item", "itemname", "name", "sku name", "description"]
    ds_units_aliases = ["units", "unitssold", "units sold", "quantity", "quantitysold", "qty", "qtysold", "items sold", "itemsold"]
    ds_rev_aliases = ["revenue", "sales", "net sales", "gross sales", "total sales", "total"]

    ds_date_col = detect_column(daily_raw.columns, [normalize_col(a) for a in ds_date_aliases])
    ds_units_col = detect_column(daily_raw.columns, [normalize_col(a) for a in ds_units_aliases])
    ds_cat_col = detect_column(daily_raw.columns, [normalize_col(a) for a in ds_cat_aliases])
    ds_name_col = detect_column(daily_raw.columns, [normalize_col(a) for a in ds_name_aliases])
    ds_rev_col = detect_column(daily_raw.columns, [normalize_col(a) for a in ds_rev_aliases])

    if not (ds_date_col and ds_units_col):
        st.error(
            "Could not detect required daily sales columns. Your daily sales report must include: "
            "a date column and units/quantity sold."
        )
        st.write("Detected columns:", list(daily_raw.columns))
        st.stop()

    daily = daily_raw.rename(columns={ds_date_col: "sale_date", ds_units_col: "units_sold"}).copy()
    daily["sale_date"] = pd.to_datetime(daily["sale_date"], errors="coerce")
    daily = daily.dropna(subset=["sale_date"])

    if ds_cat_col:
        daily = daily.rename(columns={ds_cat_col: "category"})
        daily["category"] = daily["category"].apply(normalize_rebelle_category)
    else:
        daily["category"] = "unspecified"

    if ds_name_col:
        daily = daily.rename(columns={ds_name_col: "product_name"})
    else:
        daily["product_name"] = ""

    if ds_rev_col:
        daily = daily.rename(columns={ds_rev_col: "revenue"})
        daily["revenue"] = pd.to_numeric(daily["revenue"], errors="coerce").fillna(0)
    else:
        daily["revenue"] = 0.0

    daily["units_sold"] = pd.to_numeric(daily["units_sold"], errors="coerce").fillna(0)

    # ---------- Controls ----------
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Impact Settings")
    lookback_days = int(st.sidebar.slider("Days before delivery (baseline window)", 1, 30, 7))
    lookforward_days = int(st.sidebar.slider("Days after delivery (impact window)", 1, 30, 7))
    date_floor = st.sidebar.date_input("Limit analysis from date", daily["sale_date"].min().date())
    date_ceiling = st.sidebar.date_input("Limit analysis to date", daily["sale_date"].max().date())

    daily = daily[(daily["sale_date"].dt.date >= date_floor) & (daily["sale_date"].dt.date <= date_ceiling)].copy()
    if daily.empty:
        st.error("No daily sales rows in the selected date range.")
        st.stop()

    delivery_dates = sorted(delivery["received_date"].dt.date.unique().tolist())
    selected_date = st.selectbox("Pick a delivery date to analyze", ["All delivery dates"] + [str(d) for d in delivery_dates])

    if selected_date != "All delivery dates":
        target_dates = [datetime.fromisoformat(selected_date).date()]
    else:
        target_dates = delivery_dates

    def _window_mask(dts, center_date, days_before, days_after, direction):
        c = pd.to_datetime(center_date)
        if direction == "before":
            start = c - pd.Timedelta(days=days_before)
            end = c - pd.Timedelta(days=1)
        else:
            start = c
            end = c + pd.Timedelta(days=days_after)
        return (dts >= start) & (dts <= end)

    impact_rows = []
    for d in target_dates:
        before_mask = _window_mask(daily["sale_date"], d, lookback_days, lookforward_days, "before")
        after_mask = _window_mask(daily["sale_date"], d, lookback_days, lookforward_days, "after")

        before = daily[before_mask]
        after = daily[after_mask]

        if before.empty or after.empty:
            continue

        b_cat = before.groupby("category", dropna=False)[["units_sold", "revenue"]].mean().reset_index()
        a_cat = after.groupby("category", dropna=False)[["units_sold", "revenue"]].mean().reset_index()

        merged = pd.merge(b_cat, a_cat, on="category", how="outer", suffixes=("_before", "_after")).fillna(0)
        merged["delivery_date"] = str(d)

        merged["units_delta"] = merged["units_sold_after"] - merged["units_sold_before"]
        merged["rev_delta"] = merged["revenue_after"] - merged["revenue_before"]

        merged["units_pct"] = np.where(
            merged["units_sold_before"] > 0,
            (merged["units_delta"] / merged["units_sold_before"]) * 100.0,
            0.0,
        )
        merged["rev_pct"] = np.where(
            merged["revenue_before"] > 0,
            (merged["rev_delta"] / merged["revenue_before"]) * 100.0,
            0.0,
        )

        impact_rows.append(merged)

    if not impact_rows:
        st.warning("Not enough overlapping days around the selected delivery date(s) to compute an impact window.")
        st.stop()

    impact = pd.concat(impact_rows, ignore_index=True)

    st.markdown("### Delivery impact by category")
    view = impact.sort_values(["delivery_date", "rev_delta"], ascending=[True, False]).copy()

    show_cols = [
        "delivery_date",
        "category",
        "units_sold_before",
        "units_sold_after",
        "units_delta",
        "units_pct",
        "revenue_before",
        "revenue_after",
        "rev_delta",
        "rev_pct",
    ]
    for c in show_cols:
        if c not in view.columns:
            view[c] = 0

    st.dataframe(view[show_cols], use_container_width=True)

    st.markdown("### Biggest winners (revenue delta)")
    winners = (
        view.groupby("category", dropna=False)[["rev_delta", "units_delta"]]
        .sum()
        .reset_index()
        .sort_values("rev_delta", ascending=False)
        .head(10)
    )
    st.dataframe(winners, use_container_width=True)

    st.markdown("### Delivery detail (what came in)")
    if selected_date != "All delivery dates":
        del_view = delivery[delivery["received_date"].dt.date == target_dates[0]].copy()
    else:
        del_view = delivery.copy()

    del_view = del_view.sort_values(["received_date", "category", "qty_received"], ascending=[True, True, False])
    st.dataframe(del_view[["received_date", "category", "product_name", "qty_received", "batch"]].head(500), use_container_width=True)


# ============================================================
# PAGE – SLOW MOVERS
# ============================================================
elif section == "🐢 Slow Movers":
    st.subheader("🐢 Slow Movers + Discount Ideas")
    st.markdown(
        "This tab looks for products sitting on the shelf with long gaps between sales, "
        "then suggests *light* discount tiers to get them moving."
    )

    st.sidebar.markdown("### 📂 Upload Sales Detail (for gap analysis)")
    st.sidebar.caption(
        "Best export: a **daily** or **transaction** product sales breakdown that includes a date column. "
        "If you only upload a summary Product Sales report (no dates), this tab will still work, "
        "but it can’t calculate gaps between sale days."
    )

    slow_sales_file = st.sidebar.file_uploader(
        "Detailed Sales Breakdown (daily or transaction-level)",
        type=["xlsx", "xls", "csv"],
        key="slow_sales_file",
    )

    current_user = (
        st.session_state.admin_user
        if st.session_state.is_admin
        else (st.session_state.user_user if st.session_state.user_authenticated else "trial_user")
    )
    if slow_sales_file is not None:
        track_upload(slow_sales_file, current_user, "slow_sales_detail")

    if st.session_state.inv_raw_df is None:
        st.info("Upload an Inventory file in the Inventory Dashboard tab first.")
        st.stop()
    if st.session_state.sales_raw_df is None:
        st.info("Upload a Product Sales report in the Inventory Dashboard tab first.")
        st.stop()

    inv_df = st.session_state.inv_raw_df.copy()
    sales_raw = st.session_state.sales_raw_df.copy()

    # Inventory normalize
    inv_df.columns = inv_df.columns.astype(str).str.strip().str.lower()
    name_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_NAME_ALIASES])
    cat_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_CAT_ALIASES])
    qty_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_QTY_ALIASES])
    sku_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_SKU_ALIASES])

    if not (name_col and cat_col and qty_col):
        st.error("Could not detect required inventory columns (name/category/available).")
        st.stop()

    inv_df = inv_df.rename(columns={name_col: "itemname", cat_col: "subcategory", qty_col: "onhandunits"})
    if sku_col:
        inv_df = inv_df.rename(columns={sku_col: "sku"})
    inv_df["onhandunits"] = pd.to_numeric(inv_df["onhandunits"], errors="coerce").fillna(0)
    inv_df["subcategory"] = inv_df["subcategory"].apply(normalize_rebelle_category)
    inv_df["strain_type"] = inv_df.apply(lambda x: extract_strain_type(x.get("itemname", ""), x.get("subcategory", "")), axis=1)
    inv_df["packagesize"] = inv_df.apply(lambda x: extract_size(x.get("itemname", ""), x.get("subcategory", "")), axis=1)

    # Sales summary normalize
    sales_raw.columns = sales_raw.columns.astype(str).str.lower()
    name_col_sales = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_NAME_ALIASES])
    qty_col_sales = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_QTY_ALIASES])
    mc_col = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_CAT_ALIASES])
    sales_sku_col = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_SKU_ALIASES])

    if not (name_col_sales and qty_col_sales and mc_col):
        st.error("Could not detect required Product Sales columns (product/category/units sold).")
        st.stop()

    sales_raw = sales_raw.rename(columns={name_col_sales: "product_name", qty_col_sales: "unitssold", mc_col: "mastercategory"})
    if sales_sku_col:
        sales_raw = sales_raw.rename(columns={sales_sku_col: "sku"})
    sales_raw["unitssold"] = pd.to_numeric(sales_raw["unitssold"], errors="coerce").fillna(0)
    sales_raw["mastercategory"] = sales_raw["mastercategory"].apply(normalize_rebelle_category)

    sales_df = sales_raw[
        ~sales_raw["mastercategory"].astype(str).str.contains("accessor", na=False)
        & (sales_raw["mastercategory"] != "all")
    ].copy()
    sales_df["packagesize"] = sales_df.apply(lambda r: extract_size(r.get("product_name", ""), r.get("mastercategory", "")), axis=1)
    sales_df["strain_type"] = sales_df.apply(lambda r: extract_strain_type(r.get("product_name", ""), r.get("mastercategory", "")), axis=1)

    detail_sales = None
    if slow_sales_file is not None:
        try:
            nm = slow_sales_file.name.lower()
            slow_sales_file.seek(0)
            if nm.endswith(".csv"):
                detail_sales = pd.read_csv(slow_sales_file)
            else:
                detail_sales = read_sales_file(slow_sales_file)
        except Exception as e:
            st.warning(f"Could not read the detailed sales file: {e}")
            detail_sales = None

    def _norm_name(x):
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(x).lower())).strip()

    inv_lookup = inv_df.copy()
    inv_lookup["name_key"] = inv_lookup["itemname"].apply(_norm_name)
    today = datetime.now().date()

    gap_table = None
    if detail_sales is not None and not detail_sales.empty:
        detail_sales.columns = [str(c).lower() for c in detail_sales.columns]

        d_name = detect_column(detail_sales.columns, [normalize_col(a) for a in SALES_NAME_ALIASES])
        d_qty = detect_column(detail_sales.columns, [normalize_col(a) for a in SALES_QTY_ALIASES])
        d_cat = detect_column(detail_sales.columns, [normalize_col(a) for a in SALES_CAT_ALIASES])

        date_aliases = ["date", "soldon", "sold on", "orderdate", "order date", "completeddate", "completed date", "day", "businessdate", "business date"]
        d_date = detect_column(detail_sales.columns, [normalize_col(a) for a in date_aliases])

        rev_aliases = ["netsales", "net sales", "grosssales", "gross sales", "revenue", "sales", "totalsales", "total sales", "subtotal"]
        d_rev = detect_column(detail_sales.columns, [normalize_col(a) for a in rev_aliases])

        if d_name and d_qty and d_cat and d_date:
            ds = detail_sales.rename(columns={d_name: "product_name", d_qty: "unitssold", d_cat: "mastercategory", d_date: "saledate"})
            if d_rev:
                ds = ds.rename(columns={d_rev: "revenue"})

            ds["unitssold"] = pd.to_numeric(ds["unitssold"], errors="coerce").fillna(0)
            ds["mastercategory"] = ds["mastercategory"].apply(normalize_rebelle_category)
            ds["saledate"] = pd.to_datetime(ds["saledate"], errors="coerce").dt.date
            ds = ds.dropna(subset=["saledate"])
            ds["name_key"] = ds["product_name"].apply(_norm_name)

            ds_pos = ds[ds["unitssold"] > 0].copy()

            if not ds_pos.empty:
                rows = []
                for key, g in ds_pos.groupby("name_key"):
                    dts = sorted(g["saledate"].unique())
                    last_dt = dts[-1]
                    first_dt = dts[0]
                    days_since_last = (today - last_dt).days if last_dt else None

                    gaps = []
                    for i in range(1, len(dts)):
                        gaps.append((dts[i] - dts[i - 1]).days)

                    avg_gap = float(np.mean(gaps)) if gaps else 0.0
                    med_gap = float(np.median(gaps)) if gaps else 0.0
                    sale_days = len(dts)
                    units = float(g["unitssold"].sum())
                    rev = float(g["revenue"].sum()) if "revenue" in g.columns else 0.0
                    avg_price = (rev / units) if (units > 0 and rev > 0) else np.nan

                    rows.append({
                        "name_key": key,
                        "product_name": str(g["product_name"].iloc[0]),
                        "mastercategory": str(g["mastercategory"].iloc[0]),
                        "units_sold": units,
                        "sale_days": sale_days,
                        "first_sale": first_dt,
                        "last_sale": last_dt,
                        "days_since_last_sale": days_since_last,
                        "avg_gap_days": round(avg_gap, 2),
                        "median_gap_days": round(med_gap, 2),
                        "avg_unit_price": avg_price,
                    })
                gap_table = pd.DataFrame(rows)

    if gap_table is None:
        gap_table = sales_df.groupby(["mastercategory", "product_name"], dropna=False)["unitssold"].sum().reset_index()
        gap_table = gap_table.rename(columns={"unitssold": "units_sold"})
        gap_table["sale_days"] = np.nan
        gap_table["first_sale"] = np.nan
        gap_table["last_sale"] = np.nan
        gap_table["days_since_last_sale"] = np.nan
        gap_table["avg_gap_days"] = np.nan
        gap_table["median_gap_days"] = np.nan
        gap_table["avg_unit_price"] = np.nan
        gap_table["name_key"] = gap_table["product_name"].apply(_norm_name)

    inv_onhand = inv_lookup.groupby(["name_key"], dropna=False)["onhandunits"].sum().reset_index()
    inv_onhand = inv_onhand.rename(columns={"onhandunits": "onhand_units"})

    out = pd.merge(gap_table, inv_onhand, how="left", on="name_key")
    out["onhand_units"] = pd.to_numeric(out["onhand_units"], errors="coerce").fillna(0)

    out["packagesize"] = out["product_name"].apply(lambda x: extract_size(x, None))
    out["strain_type"] = out.apply(lambda r: extract_strain_type(r.get("product_name", ""), r.get("mastercategory", "")), axis=1)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🏃 Adjustable Run Rates")
    rr_days = int(st.sidebar.slider("Run-rate window (days)", 7, 120, 30, key="rr_days"))
    min_onhand = int(st.sidebar.number_input("Minimum On-Hand to flag", 1, 999999, 5, key="min_onhand_flag"))

    out["est_units_per_day"] = out["units_sold"] / max(int(rr_days), 1)

    if "doh_threshold_cache" not in st.session_state:
        st.session_state.doh_threshold_cache = 21

    def _discount_tier(row):
        onhand = float(row.get("onhand_units", 0))
        vel = float(row.get("est_units_per_day", 0))
        dsl = row.get("days_since_last_sale", np.nan)
        gap = row.get("avg_gap_days", np.nan)

        if onhand <= 0:
            return 0

        tier = 0
        if (vel == 0) and (not pd.isna(dsl)) and (dsl >= 30):
            tier = 30
        elif (not pd.isna(dsl)) and (dsl >= 21):
            tier = 20
        elif (not pd.isna(dsl)) and (dsl >= 14):
            tier = 15
        elif (not pd.isna(gap)) and (gap >= 7):
            tier = 10
        elif vel == 0:
            tier = 15

        target_doh = int(st.session_state.get("doh_threshold_cache", 21))
        target_units = vel * target_doh
        if target_units > 0 and onhand > (2.0 * target_units):
            tier = min(40, tier + 5)

        return int(tier)

    out["suggested_discount_pct"] = out.apply(_discount_tier, axis=1)

    out["slow_mover_flag"] = (
        (out["onhand_units"] >= float(min_onhand))
        & (
            (out["est_units_per_day"] <= 0.05)
            | (out["suggested_discount_pct"] >= 10)
            | (out["avg_gap_days"].fillna(0) >= 7)
            | (out["days_since_last_sale"].fillna(0) >= 14)
        )
    )

    flagged = out[out["slow_mover_flag"]].copy()
    flagged = flagged.sort_values(["suggested_discount_pct", "onhand_units"], ascending=[False, False])

    st.markdown("### What this is looking for")
    st.markdown(
        "- **On-hand** sitting heavy\n"
        "- **Low run rate** (units/day)\n"
        "- **Long gaps** between sale days (when date-level data is provided)\n"
        "- A simple discount tier to move it before it turns into shelf art"
    )

    st.markdown("### Slow Movers (by Category)")
    if flagged.empty:
        st.success("Nothing is screaming 'slow mover' from the files you gave me.")
    else:
        def build_slow_export_bytes(df: pd.DataFrame) -> bytes:
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="SlowMovers")
            buf.seek(0)
            return buf.read()

        export_cols = [
            "mastercategory",
            "product_name",
            "packagesize",
            "strain_type",
            "onhand_units",
            "units_sold",
            "est_units_per_day",
            "days_since_last_sale",
            "avg_gap_days",
            "suggested_discount_pct",
            "avg_unit_price",
        ]
        export_cols = [c for c in export_cols if c in flagged.columns]

        st.download_button(
            "📥 Export Slow Movers (Excel)",
            data=build_slow_export_bytes(flagged[export_cols].copy()),
            file_name="slow_movers.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        def _cat_sort_key_local(c):
            c_low = str(c).lower()
            if c_low in REB_CATEGORIES:
                return (REB_CATEGORIES.index(c_low), c_low)
            return (len(REB_CATEGORIES), c_low)

        cats = sorted(flagged["mastercategory"].dropna().unique().tolist(), key=_cat_sort_key_local)
        for cat in cats:
            sub = flagged[flagged["mastercategory"] == cat].copy()
            with st.expander(cat.title(), expanded=False):
                show_cols = [
                    "product_name",
                    "packagesize",
                    "strain_type",
                    "onhand_units",
                    "units_sold",
                    "est_units_per_day",
                    "days_since_last_sale",
                    "avg_gap_days",
                    "suggested_discount_pct",
                    "avg_unit_price",
                ]
                show_cols = [c for c in show_cols if c in sub.columns]
                st.dataframe(sub[show_cols], use_container_width=True)

        st.markdown("---")
        st.markdown("### Discount notes (buyer common sense)")
        st.caption(
            "These are suggestions, not gospel. Use brand rules, MAP policies, and margin reality. "
            "If something is close to expiry or dead-dead, a bigger move may be justified."
        )


# ============================================================
# PAGE – PO BUILDER
# ============================================================
elif section == "🧾 PO Builder":
    st.subheader("🧾 Purchase Order Builder")

    st.markdown("The words above each PO field are white on the dark background for clarity.")
    st.markdown("### PO Header")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="po-label">Store / Ship-To Name</div>', unsafe_allow_html=True)
        store_name = st.text_input("", value="MAVet710", key="store_name")

        st.markdown('<div class="po-label">Store #</div>', unsafe_allow_html=True)
        store_number = st.text_input("", key="store_number")

        st.markdown('<div class="po-label">Store Address</div>', unsafe_allow_html=True)
        store_address = st.text_input("", key="store_address")

        st.markdown('<div class="po-label">Store Phone</div>', unsafe_allow_html=True)
        store_phone = st.text_input("", key="store_phone")

        st.markdown('<div class="po-label">Buyer / Contact Name</div>', unsafe_allow_html=True)
        store_contact = st.text_input("", key="store_contact")

    with col2:
        st.markdown('<div class="po-label">Vendor Name</div>', unsafe_allow_html=True)
        vendor_name = st.text_input("", key="vendor_name")

        st.markdown('<div class="po-label">Vendor License Number</div>', unsafe_allow_html=True)
        vendor_license = st.text_input("", key="vendor_license")

        st.markdown('<div class="po-label">Vendor Address</div>', unsafe_allow_html=True)
        vendor_address = st.text_input("", key="vendor_address")

        st.markdown('<div class="po-label">Vendor Contact / Email</div>', unsafe_allow_html=True)
        vendor_contact = st.text_input("", key="vendor_contact")

        st.markdown('<div class="po-label">PO Number</div>', unsafe_allow_html=True)
        po_number = st.text_input("", key="po_number")

        st.markdown('<div class="po-label">PO Date</div>', unsafe_allow_html=True)
        po_date = st.date_input("", datetime.today(), key="po_date")

        st.markdown('<div class="po-label">Payment Terms</div>', unsafe_allow_html=True)
        terms = st.text_input("", value="Net 30", key="terms")

    st.markdown('<div class="po-label">PO Notes / Special Instructions</div>', unsafe_allow_html=True)
    notes = st.text_area("", "", height=70, key="notes")

    st.markdown("---")
    st.markdown("### Line Items")

    num_lines = int(st.number_input("Number of Line Items", 1, 50, 5))

    items = []
    for i in range(int(num_lines)):
        with st.expander(f"Line {i + 1}", expanded=(i < 3)):
            c1, c2, c3, c4, c5, c6 = st.columns([1.2, 2.5, 1.4, 1.2, 1.2, 1.3])

            with c1:
                st.markdown('<div class="po-label">SKU ID</div>', unsafe_allow_html=True)
                sku = st.text_input("", key=f"sku_{i}")

            with c2:
                st.markdown('<div class="po-label">SKU Name / Description</div>', unsafe_allow_html=True)
                desc = st.text_input("", key=f"desc_{i}")

            with c3:
                st.markdown('<div class="po-label">Strain / Type</div>', unsafe_allow_html=True)
                strain = st.text_input("", key=f"strain_{i}")

            with c4:
                st.markdown('<div class="po-label">Size (e.g. 3.5g)</div>', unsafe_allow_html=True)
                size = st.text_input("", key=f"size_{i}")

            with c5:
                st.markdown('<div class="po-label">Qty</div>', unsafe_allow_html=True)
                qty = st.number_input("", min_value=0, step=1, key=f"qty_{i}")

            with c6:
                st.markdown('<div class="po-label">Unit Price ($)</div>', unsafe_allow_html=True)
                price = st.number_input("", min_value=0.0, step=0.01, key=f"price_{i}")

            line_total = qty * price
            st.markdown(f"**Line Total:** ${line_total:,.2f}")

            items.append(
                {
                    "SKU": sku,
                    "Description": desc,
                    "Strain": strain,
                    "Size": size,
                    "Qty": qty,
                    "Unit Price": price,
                    "Line Total": line_total,
                }
            )

    po_df = pd.DataFrame(items)
    po_df = po_df[
        (po_df["SKU"].astype(str).str.strip() != "")
        | (po_df["Description"].astype(str).str.strip() != "")
        | (po_df["Qty"] > 0)
    ]

    st.markdown("---")

    if not po_df.empty:
        subtotal = float(po_df["Line Total"].sum())

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown('<div class="po-label">Tax Rate (%)</div>', unsafe_allow_html=True)
            tax_rate = st.number_input("", 0.0, 30.0, 0.0, key="tax_rate")
        with c2:
            st.markdown('<div class="po-label">Discount ($)</div>', unsafe_allow_html=True)
            discount = st.number_input("", 0.0, step=0.01, key="discount")
        with c3:
            st.markdown('<div class="po-label">Shipping / Fees ($)</div>', unsafe_allow_html=True)
            shipping = st.number_input("", 0.0, step=0.01, key="shipping")

        tax_amount = subtotal * (tax_rate / 100.0)
        total = subtotal + tax_amount + shipping - discount

        st.markdown("### Totals")
        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("SUBTOTAL", f"${subtotal:,.2f}")
        s2.metric("DISCOUNT", f"-${discount:,.2f}")
        s3.metric("TAX", f"${tax_amount:,.2f}")
        s4.metric("SHIPPING", f"${shipping:,.2f}")
        s5.metric("TOTAL", f"${total:,.2f}")

        st.markdown("### PO Review")
        st.dataframe(po_df, use_container_width=True)

        pdf_bytes = generate_po_pdf(
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
        )

        st.markdown("### Download")
        st.download_button(
            "📥 Download PO (PDF)",
            data=pdf_bytes,
            file_name=f"PO_{po_number or 'mavet'}.pdf",
            mime="application/pdf",
        )
    else:
        st.info("Add at least one line item to generate totals and PDF.")


else:
    st.error("Unknown section selection. Please choose a page from the sidebar.")

# FOOTER
st.markdown("---")
year = datetime.now().year
st.markdown(f'<div class="footer">{LICENSE_FOOTER} • © {year}</div>', unsafe_allow_html=True)
