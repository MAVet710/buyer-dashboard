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

    key, where = _find_openai_key()
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
LICENSE_FOOTER = "MAVet710 Buyer Tools • Powered by MAVet710 Analytics"

# 🔐 TRIAL SETTINGS
TRIAL_KEY = "mavet24"
TRIAL_DURATION_HOURS = 24

# 👑 ADMIN CREDS (multiple admins)
ADMIN_USERS = {
    "God": "Major420",
    "JVas": "UPG2025",
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
page_icon_url = (
    "https://raw.githubusercontent.com/MAVet710/buyer-dashboard/main/IMG_7158.PNG"
)

st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
    page_icon=page_icon_url,
)

# Background image – MAVet image
background_url = (
    "https://raw.githubusercontent.com/MAVet710/buyer-dashboard/main/IMG_7158.PNG"
)

# =========================
# SESSION STATE DEFAULTS
# =========================
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "admin_user" not in st.session_state:
    st.session_state.admin_user = None
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
if "theme" not in st.session_state:
    st.session_state.theme = "Dark"  # Dark by default

# Upload tracking (God-only viewer)
if "upload_log" not in st.session_state:
    st.session_state.upload_log = []  # list of dicts
if "uploaded_files_store" not in st.session_state:
    # key: upload_id -> {"name":..., "bytes":..., "uploader":..., "ts":...}
    st.session_state.uploaded_files_store = {}

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


def track_upload(uploaded_file, uploader_username: str, file_role: str):
    """
    Store uploaded file bytes in session_state so 'God' can view/download later.
    """
    if uploaded_file is None:
        return

    try:
        uploaded_file.seek(0)
        b = uploaded_file.read()
        uploaded_file.seek(0)
    except Exception:
        return

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
    st.experimental_rerun()

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
        st.experimental_rerun()

trial_now = datetime.now()

if not st.session_state.is_admin:
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
            st.experimental_rerun()

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
    ["📊 Inventory Dashboard", "📈 Trends", "🧾 PO Builder"],
    index=0,
)

# ============================================================
# PAGE 1 – INVENTORY DASHBOARD
# ============================================================
if section == "📊 Inventory Dashboard":

    # Data source selector
    st.sidebar.markdown("### 🧩 Data Source")
    data_source = st.sidebar.selectbox(
        "Select POS / Data Source",
        ["Dutchie", "BLAZE"],
        index=0,
        help="Changes how column names are interpreted. Files are still CSV/XLSX exports.",
    )

    st.sidebar.header("📂 Upload Core Reports")

    inv_file = st.sidebar.file_uploader("Inventory File (CSV or Excel)", type=["csv", "xlsx", "xls"])
    product_sales_file = st.sidebar.file_uploader("Product Sales Report (qty-based Excel)", type=["xlsx", "xls"])
    extra_sales_file = st.sidebar.file_uploader(
        "Optional Extra Sales Detail (revenue)",
        type=["xlsx", "xls"],
        help="Optional: revenue detail. Can be used for pricing trends.",
    )

    # Track uploads for God viewer
    current_user = st.session_state.admin_user if st.session_state.is_admin else "trial_user"
    if inv_file is not None:
        track_upload(inv_file, current_user, "inventory")
    if product_sales_file is not None:
        track_upload(product_sales_file, current_user, "product_sales")
    if extra_sales_file is not None:
        track_upload(extra_sales_file, current_user, "extra_sales")

    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Forecast Settings")
    doh_threshold = st.sidebar.number_input("Target Days on Hand", 1, 60, 21)
    velocity_adjustment = st.sidebar.number_input("Velocity Adjustment", 0.01, 5.0, 0.5)
    date_diff = st.sidebar.slider("Days in Sales Period", 7, 120, 60)

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

    if st.session_state.inv_raw_df is not None and st.session_state.sales_raw_df is not None:
        try:
            inv_df = st.session_state.inv_raw_df.copy()
            sales_raw = st.session_state.sales_raw_df.copy()

            # -------- INVENTORY --------
            inv_df.columns = inv_df.columns.astype(str).str.strip().str.lower()

            inv_name_aliases = [
                "product", "productname", "item", "itemname", "name", "skuname",
                "skuid", "product name", "product_name", "product title", "title"
            ]
            inv_cat_aliases = [
                "category", "subcategory", "productcategory", "department",
                "mastercategory", "product category", "cannabis", "product_category"
            ]
            # Dutchie inventory uses "available" as on-hand
            inv_qty_aliases = [
                "available", "onhand", "onhandunits", "quantity", "qty",
                "quantityonhand", "instock", "currentquantity", "current quantity",
                "inventoryavailable", "inventory available", "available quantity"
            ]

            name_col = detect_column(inv_df.columns, [normalize_col(a) for a in inv_name_aliases])
            cat_col = detect_column(inv_df.columns, [normalize_col(a) for a in inv_cat_aliases])
            qty_col = detect_column(inv_df.columns, [normalize_col(a) for a in inv_qty_aliases])

            # SKU column (optional but used for drilldowns)
            inv_sku_aliases = ["sku", "skuid", "productid", "product_id", "itemid", "item_id"]
            sku_col = detect_column(inv_df.columns, [normalize_col(a) for a in inv_sku_aliases])

            if not (name_col and cat_col and qty_col):
                st.error(
                    "Could not auto-detect inventory columns (product / category / on-hand). "
                    "Check your Inventory export headers."
                )
                st.stop()

            inv_df = inv_df.rename(
                columns={
                    name_col: "itemname",
                    cat_col: "subcategory",
                    qty_col: "onhandunits",
                }
            )
            if sku_col:
                inv_df = inv_df.rename(columns={sku_col: "sku"})

            inv_df["onhandunits"] = pd.to_numeric(inv_df["onhandunits"], errors="coerce").fillna(0)

            inv_df["subcategory"] = inv_df["subcategory"].apply(normalize_rebelle_category)

            inv_df["strain_type"] = inv_df.apply(
                lambda x: extract_strain_type(x.get("itemname", ""), x.get("subcategory", "")),
                axis=1,
            )
            inv_df["packagesize"] = inv_df.apply(
                lambda x: extract_size(x.get("itemname", ""), x.get("subcategory", "")),
                axis=1,
            )

            inv_summary = (
                inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["onhandunits"]
                .sum()
                .reset_index()
            )

            # -------- SALES (qty-based ONLY) --------
            sales_raw.columns = sales_raw.columns.astype(str).str.lower()

            sales_name_aliases = [
                "product", "productname", "product title", "producttitle",
                "productid", "name", "item", "itemname", "skuname",
                "sku", "description", "product name", "product_name"
            ]
            name_col_sales = detect_column(sales_raw.columns, [normalize_col(a) for a in sales_name_aliases])

            qty_aliases = [
                "quantitysold", "quantity sold",
                "qtysold", "qty sold",
                "itemsold", "item sold", "items sold",
                "unitssold", "units sold", "unit sold", "unitsold", "units",
                "totalunits", "total units",
                "quantity", "qty",
            ]
            qty_col_sales = detect_column(sales_raw.columns, [normalize_col(a) for a in qty_aliases])

            mc_aliases = [
                "mastercategory", "category", "master_category",
                "productcategory", "product category",
                "department", "dept", "subcategory", "productcategoryname",
                "product category name"
            ]
            mc_col = detect_column(sales_raw.columns, [normalize_col(a) for a in mc_aliases])

            # SKU (optional for drilldowns)
            sales_sku_aliases = ["sku", "skuid", "productid", "product_id"]
            sales_sku_col = detect_column(sales_raw.columns, [normalize_col(a) for a in sales_sku_aliases])

            if not (name_col_sales and qty_col_sales and mc_col):
                st.error(
                    "Product Sales file detected but could not find required columns.\n\n"
                    "Looked for: product name, units/quantity sold, and category.\n\n"
                    "Tip: Use Dutchie 'Product Sales Report' (qty) without editing headers."
                )
                st.stop()

            sales_raw = sales_raw.rename(
                columns={
                    name_col_sales: "product_name",
                    qty_col_sales: "unitssold",
                    mc_col: "mastercategory",
                }
            )
            if sales_sku_col:
                sales_raw = sales_raw.rename(columns={sales_sku_col: "sku"})

            sales_raw["unitssold"] = pd.to_numeric(sales_raw["unitssold"], errors="coerce").fillna(0)
            sales_raw["mastercategory"] = sales_raw["mastercategory"].apply(normalize_rebelle_category)

            # Filter out accessories/all
            sales_df = sales_raw[
                ~sales_raw["mastercategory"].astype(str).str.contains("accessor", na=False)
                & (sales_raw["mastercategory"] != "all")
            ].copy()

            # Add parsed size + strain_type (for SKU drilldown / weighting)
            sales_df["packagesize"] = sales_df.apply(
                lambda row: extract_size(row.get("product_name", ""), row.get("mastercategory", "")),
                axis=1,
            )
            sales_df["strain_type"] = sales_df.apply(
                lambda row: extract_strain_type(row.get("product_name", ""), row.get("mastercategory", "")),
                axis=1,
            )

            # Aggregate sales at category+size
            sales_summary = (
                sales_df.groupby(["mastercategory", "packagesize"], dropna=False)["unitssold"]
                .sum()
                .reset_index()
            )
            sales_summary["avgunitsperday"] = (sales_summary["unitssold"] / max(int(date_diff), 1)) * float(velocity_adjustment)

            # Merge inventory summary with size-level velocity
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
                """
                If direct 28g sales exist, use them.
                Otherwise estimate ounces by converting other gram-based sales into grams -> /28.
                """
                # direct
                direct = sales_df[
                    (sales_df["mastercategory"] == cat_name) & (sales_df["packagesize"] == "28g")
                ]
                if not direct.empty:
                    units_28 = float(direct["unitssold"].sum())
                    avg_28 = (units_28 / max(int(date_diff), 1)) * float(velocity_adjustment)
                    return units_28, avg_28

                # estimate grams sold across sizes
                cat_sales = sales_df[sales_df["mastercategory"] == cat_name].copy()
                if cat_sales.empty:
                    return 0.0, 0.0

                # convert each row to grams sold
                total_grams = 0.0
                for _, r in cat_sales.iterrows():
                    sz = r.get("packagesize", "unspecified")
                    grams = _parse_grams_from_size(sz)
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
                    missing_rows.append(
                        {
                            "subcategory": cat,
                            "strain_type": "unspecified",
                            "packagesize": "28g",
                            "onhandunits": 0,
                            "mastercategory": cat,
                            "unitssold": units_28,
                            "avgunitsperday": avg_28,
                        }
                    )
                else:
                    # If it exists but has zero velocity AND we can estimate, patch it
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
                """
                If direct 500mg sales exist, use them.
                Otherwise estimate by converting other mg-based sales into total mg -> /500.
                """
                direct = sales_df[
                    (sales_df["mastercategory"] == cat_name) & (sales_df["packagesize"] == "500mg")
                ]
                if not direct.empty:
                    units_500 = float(direct["unitssold"].sum())
                    avg_500 = (units_500 / max(int(date_diff), 1)) * float(velocity_adjustment)
                    return units_500, avg_500

                cat_sales = sales_df[sales_df["mastercategory"] == cat_name].copy()
                if cat_sales.empty:
                    return 0.0, 0.0

                total_mg = 0.0
                for _, r in cat_sales.iterrows():
                    sz = r.get("packagesize", "unspecified")
                    mg = _parse_mg_from_size(sz)
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
                    edibles_missing.append(
                        {
                            "subcategory": cat,
                            "strain_type": "unspecified",
                            "packagesize": "500mg",
                            "onhandunits": 0,
                            "mastercategory": cat,
                            "unitssold": units_500,
                            "avgunitsperday": avg_500,
                        }
                    )
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
            detail["daysonhand"] = (
                detail["daysonhand"]
                .replace([np.inf, -np.inf], 0)
                .fillna(0)
                .astype(int)
            )

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

            def red_low(val):
                try:
                    v = int(val)
                    return "color:#FF3131" if v < doh_threshold else ""
                except Exception:
                    return ""

            # Category filter order
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
                """
                Export using openpyxl (no xlsxwriter).
                """
                buf = BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="Forecast")
                buf.seek(0)
                return buf.read()

            export_df = detail_view[display_cols].copy()
            excel_bytes = build_forecast_export_bytes(export_df)
            st.download_button(
                "📥 Export Forecast Table (Excel)",
                data=excel_bytes,
                file_name="forecast_table.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            # ========= SKU drilldown for flagged reorder products (weighted) =========
            # We show this inside each category expander, and only for rows that are flagged.
            # Weighted based on per-item estimated units/day.
            def sku_drilldown_table(cat, size, strain_type):
                """
                Returns per-item view for this row, combining sales + inventory hints.
                Weighted by velocity.
                """
                # sales slice
                sd = sales_df[
                    (sales_df["mastercategory"] == cat) &
                    (sales_df["packagesize"] == size)
                ].copy()

                # Try to match strain_type roughly (but don't exclude too aggressively)
                if str(strain_type).lower() != "unspecified":
                    sd = sd[sd["strain_type"].astype(str).str.lower() == str(strain_type).lower()]

                if sd.empty:
                    return pd.DataFrame()

                sd["est_units_per_day"] = (sd["unitssold"] / max(int(date_diff), 1)) * float(velocity_adjustment)

                # inventory slice
                idf = inv_df[
                    (inv_df["subcategory"] == cat) &
                    (inv_df["packagesize"] == size)
                ].copy()
                if str(strain_type).lower() != "unspecified":
                    idf = idf[idf["strain_type"].astype(str).str.lower() == str(strain_type).lower()]

                # build display
                cols = []
                if "sku" in sd.columns:
                    cols.append("sku")
                cols += ["product_name", "unitssold", "est_units_per_day"]
                sd_disp = sd[cols].copy()

                # attach onhand if possible (by name match)
                if not idf.empty:
                    idf_small = idf[["itemname", "onhandunits"]].copy()
                    idf_small = idf_small.rename(columns={"itemname": "product_name"})
                    sd_disp = pd.merge(
                        sd_disp,
                        idf_small,
                        how="left",
                        on="product_name",
                    )

                sd_disp["onhandunits"] = sd_disp.get("onhandunits", 0)
                sd_disp["onhandunits"] = pd.to_numeric(sd_disp["onhandunits"], errors="coerce").fillna(0)

                # sort weighted
                sd_disp = sd_disp.sort_values("est_units_per_day", ascending=False).head(50)

                return sd_disp

            # Expanders by category
            for cat in sorted(detail_view["subcategory"].unique(), key=cat_sort_key):
                group = detail_view[detail_view["subcategory"] == cat].copy()

                with st.expander(cat.title()):
                    g = group[display_cols].copy()
                    st.dataframe(
                        g.style.applymap(red_low, subset=["daysonhand"]),
                        use_container_width=True,
                    )

                    # For flagged lines, show “View SKUs” expanders per row
                    flagged = group[group["reorderpriority"] == "1 – Reorder ASAP"].copy()
                    if not flagged.empty:
                        st.markdown("#### 🔎 Flagged Reorder Lines — View SKUs (Weighted by Velocity)")
                        for _, r in flagged.iterrows():
                            row_label = f"{r.get('strain_type','unspecified')} • {r.get('packagesize','unspecified')} • Reorder Qty: {int(r.get('reorderqty',0))}"
                            with st.expander(f"View SKUs — {row_label}", expanded=False):
                                sku_df = sku_drilldown_table(
                                    cat=r.get("subcategory"),
                                    size=r.get("packagesize"),
                                    strain_type=r.get("strain_type"),
                                )
                                if sku_df.empty:
                                    st.info("No matching SKU-level sales rows found for this slice.")
                                else:
                                    st.dataframe(sku_df, use_container_width=True)

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

    else:
        st.info("Upload inventory + product sales files to continue.")


# ============================================================
# PAGE 2 – TRENDS (NEW PAGE; DOES NOT CHANGE EXISTING LAYOUT)
# ============================================================
elif section == "📈 Trends":
    st.subheader("📈 Trends")

    st.markdown(
        "This page reads the same uploaded Dutchie/BLAZE exports (if present) and surfaces "
        "quick signals: category mix, package-size mix, and velocity movers.\n\n"
        "**Note:** If you haven’t uploaded files yet, go to **Inventory Dashboard** first."
    )

    # Pull cached data (uploaded on Inventory Dashboard page)
    inv_df_raw = st.session_state.inv_raw_df
    sales_raw_df = st.session_state.sales_raw_df
    extra_sales_df = st.session_state.extra_sales_df

    if sales_raw_df is None:
        st.info("Upload at least the Product Sales report on the Inventory Dashboard page to see Trends.")
        st.stop()

    # ---- Trend settings (adjustable run rates) ----
    st.sidebar.markdown("### 📈 Trend Settings")
    trend_days = st.sidebar.slider("Trend window (days)", 7, 120, 30, key="trend_days")
    compare_days = st.sidebar.slider("Comparison window (prior days)", 7, 120, 30, key="compare_days")
    run_rate_multiplier = st.sidebar.number_input("Run-rate multiplier", 0.1, 3.0, 1.0, 0.1, key="run_rate_mult")

    # Normalize sales columns similarly to inventory page
    sales = sales_raw_df.copy()
    sales.columns = sales.columns.astype(str).str.lower()

    sales_name_aliases = [
        "product", "productname", "product title", "producttitle",
        "productid", "name", "item", "itemname", "skuname",
        "sku", "description", "product name", "product_name"
    ]
    name_col_sales = detect_column(sales.columns, [normalize_col(a) for a in sales_name_aliases])

    qty_aliases = [
        "quantitysold", "quantity sold",
        "qtysold", "qty sold",
        "itemsold", "item sold", "items sold",
        "unitssold", "units sold", "unit sold", "unitsold", "units",
        "totalunits", "total units",
        "quantity", "qty",
    ]
    qty_col_sales = detect_column(sales.columns, [normalize_col(a) for a in qty_aliases])

    mc_aliases = [
        "mastercategory", "category", "master_category",
        "productcategory", "product category",
        "department", "dept", "subcategory", "productcategoryname",
        "product category name"
    ]
    mc_col = detect_column(sales.columns, [normalize_col(a) for a in mc_aliases])

    # Optional revenue / net sales columns (for pricing trends)
    rev_aliases = [
        "netsales", "net sales", "sales", "totalsales", "total sales",
        "revenue", "grosssales", "gross sales"
    ]
    rev_col = detect_column(sales.columns, [normalize_col(a) for a in rev_aliases])

    if not (name_col_sales and qty_col_sales and mc_col):
        st.error(
            "Could not detect required columns in Product Sales report for Trends.\n\n"
            "Need: product name + units sold + category."
        )
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

    # ---- Trend math (since Dutchie exports often don't include daily timestamps in these reports) ----
    # We treat the "trend window" as a run-rate lens: units/day = units_sold / trend_days * multiplier.
    # Comparison uses compare_days.
    cat_units = sales.groupby("mastercategory", dropna=False)["unitssold"].sum().reset_index()
    cat_units["units_per_day"] = (cat_units["unitssold"] / max(int(trend_days), 1)) * float(run_rate_multiplier)

    # Mix by category
    total_units = float(cat_units["unitssold"].sum()) if not cat_units.empty else 0.0
    cat_units["unit_share"] = np.where(total_units > 0, cat_units["unitssold"] / total_units, 0.0)

    st.markdown("### Category Mix (Units)")
    st.dataframe(
        cat_units.sort_values("unitssold", ascending=False),
        use_container_width=True
    )

    # Mix by package size (all categories)
    size_units = sales.groupby("packagesize", dropna=False)["unitssold"].sum().reset_index()
    size_units["units_per_day"] = (size_units["unitssold"] / max(int(trend_days), 1)) * float(run_rate_multiplier)
    st.markdown("### Package Size Mix (Units)")
    st.dataframe(size_units.sort_values("unitssold", ascending=False), use_container_width=True)

    # Movers by "velocity" (units/day) at SKU level
    st.markdown("### Top Movers (SKU-level)")
    sku_cols = ["product_name", "mastercategory", "strain_type", "packagesize", "unitssold"]
    if "revenue" in sales.columns:
        sku_cols.append("revenue")
    sku_view = sales[sku_cols].copy()
    sku_view["units_per_day"] = (sku_view["unitssold"] / max(int(trend_days), 1)) * float(run_rate_multiplier)

    if "revenue" in sku_view.columns:
        sku_view["avg_price"] = np.where(sku_view["unitssold"] > 0, sku_view["revenue"] / sku_view["unitssold"], 0.0)

    st.dataframe(sku_view.sort_values("units_per_day", ascending=False).head(50), use_container_width=True)

    # If inventory is available, show "fast movers low stock" quick hit
    if inv_df_raw is not None:
        inv_df = inv_df_raw.copy()
        inv_df.columns = inv_df.columns.astype(str).str.strip().str.lower()

        inv_name_aliases = [
            "product", "productname", "item", "itemname", "name", "skuname",
            "skuid", "product name", "product_name", "product title", "title"
        ]
        inv_cat_aliases = [
            "category", "subcategory", "productcategory", "department",
            "mastercategory", "product category", "cannabis", "product_category"
        ]
        inv_qty_aliases = [
            "available", "onhand", "onhandunits", "quantity", "qty",
            "quantityonhand", "instock", "currentquantity", "current quantity",
            "inventoryavailable", "inventory available", "available quantity"
        ]
        name_col = detect_column(inv_df.columns, [normalize_col(a) for a in inv_name_aliases])
        cat_col = detect_column(inv_df.columns, [normalize_col(a) for a in inv_cat_aliases])
        qty_col = detect_column(inv_df.columns, [normalize_col(a) for a in inv_qty_aliases])

        if name_col and cat_col and qty_col:
            inv_df = inv_df.rename(columns={name_col: "itemname", cat_col: "subcategory", qty_col: "onhandunits"})
            inv_df["subcategory"] = inv_df["subcategory"].apply(normalize_rebelle_category)
            inv_df["packagesize"] = inv_df.apply(lambda r: extract_size(r.get("itemname", ""), r.get("subcategory", "")), axis=1)
            inv_df["strain_type"] = inv_df.apply(lambda r: extract_strain_type(r.get("itemname", ""), r.get("subcategory", "")), axis=1)
            inv_df["onhandunits"] = pd.to_numeric(inv_df["onhandunits"], errors="coerce").fillna(0)

            inv_small = inv_df[["itemname", "subcategory", "packagesize", "strain_type", "onhandunits"]].copy()
            sku_tmp = sku_view.rename(columns={"product_name": "itemname", "mastercategory": "subcategory"}).copy()
            merged = pd.merge(
                sku_tmp,
                inv_small,
                how="left",
                on=["itemname", "subcategory", "packagesize", "strain_type"],
            )
            merged["onhandunits"] = pd.to_numeric(merged.get("onhandunits", 0), errors="coerce").fillna(0)

            # "risk score": high velocity and low onhand
            merged["risk_score"] = merged["units_per_day"] / np.maximum(merged["onhandunits"], 1)
            st.markdown("### Fast Movers + Low Stock (SKU-level)")
            st.dataframe(
                merged.sort_values("risk_score", ascending=False).head(50),
                use_container_width=True
            )
        else:
            st.info("Inventory file is loaded but Trends couldn't auto-detect columns for a stock overlay.")

    # Optional: Pricing signal if revenue exists
    if "revenue" in sales.columns:
        st.markdown("### Pricing Signals (If Revenue is in Your Export)")
        price_view = sku_view.copy()
        price_view = price_view[price_view["unitssold"] > 0].copy()
        price_view = price_view.sort_values("avg_price", ascending=False)
        st.dataframe(price_view.head(50), use_container_width=True)
        st.caption("If your sales export includes revenue/net sales, this page computes a simple avg price (revenue ÷ units).")

    # Optional external market benchmark notes (kept lightweight)
    st.markdown("---")
    st.markdown("#### Market Context (MA)")
    st.caption("If you’re benchmarking pricing, Headset’s MA market page is a good outside reference for category pricing and market mix.")


# ============================================================
# PAGE 3 – PO BUILDER
# ============================================================
else:
    st.subheader("🧾 Purchase Order Builder")

    st.markdown(
        "The words above each PO field are white on the dark background for clarity."
    )

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

    num_lines = st.number_input("Number of Line Items", 1, 50, 5)

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
        (po_df["SKU"].astype(str).str.strip() != "") |
        (po_df["Description"].astype(str).str.strip() != "") |
        (po_df["Qty"] > 0)
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


# =========================
# FOOTER
# =========================
st.markdown("---")
year = datetime.now().year
st.markdown(
    f'<div class="footer">{LICENSE_FOOTER} • © {year}</div>',
    unsafe_allow_html=True,
)
