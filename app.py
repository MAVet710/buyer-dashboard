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
except ImportError:
    PLOTLY_AVAILABLE = False

# ------------------------------------------------------------
# OPTIONAL / SAFE IMPORT FOR OPENAI (AI INVENTORY CHECK)
# ------------------------------------------------------------
OPENAI_AVAILABLE = False
ai_client = None
try:
    from openai import OpenAI

    # Try multiple places / key names for the API key
    OPENAI_API_KEY = (
        st.secrets.get("OPENAI_API_KEY", None)
        or st.secrets.get("openai_api_key", None)
    )

    # Nested style: [openai]["api_key"]
    if OPENAI_API_KEY is None and "openai" in st.secrets:
        maybe = st.secrets["openai"]
        if isinstance(maybe, dict):
            OPENAI_API_KEY = maybe.get("api_key")

    # Environment fallback
    if OPENAI_API_KEY is None:
        OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", None)

    if OPENAI_API_KEY and str(OPENAI_API_KEY).strip():
        ai_client = OpenAI(api_key=str(OPENAI_API_KEY).strip())
        OPENAI_AVAILABLE = True
    else:
        OPENAI_AVAILABLE = False
except Exception:
    OPENAI_AVAILABLE = False

# =========================
# CONFIG & BRANDING
# =========================
CLIENT_NAME = "Rebelle Cannabis"
APP_TITLE = f"{CLIENT_NAME} Purchasing Dashboard"
APP_TAGLINE = "Streamlined purchasing visibility powered by Dutchie / BLAZE data."
LICENSE_FOOTER = f"Licensed exclusively to {CLIENT_NAME} • Powered by MAVet710 Analytics"

# 🔐 TRIAL SETTINGS
TRIAL_KEY = "rebelle24"        # Rebelle 24-hour trial key
TRIAL_DURATION_HOURS = 24

# 👑 ADMIN CREDS
ADMIN_USERNAME = "God"
ADMIN_PASSWORD = "Major420"

# ✅ Canonical Rebelle category names (values, not column names)
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

# Tab icon (favicon)
page_icon_url = (
    "https://raw.githubusercontent.com/MAVet710/Rebelle-Purchasing-Dash/"
    "ef50d34e20caf45231642e957137d6141082dbb9/rebelle.jpg"
)

st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
    page_icon=page_icon_url,
)

# Background image
background_url = (
    "https://raw.githubusercontent.com/MAVet710/Rebelle-Purchasing-Dash/"
    "ef50d34e20caf45231642e957137d6141082dbb9/rebelle%20main.png"
)

# =========================
# SESSION STATE DEFAULTS
# =========================
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "trial_start" not in st.session_state:
    st.session_state.trial_start = None
if "metric_filter" not in st.session_state:
    st.session_state.metric_filter = "All"   # All / Reorder ASAP
if "inv_raw_df" not in st.session_state:
    st.session_state.inv_raw_df = None
if "sales_raw_df" not in st.session_state:
    st.session_state.sales_raw_df = None
if "extra_sales_df" not in st.session_state:
    st.session_state.extra_sales_df = None
if "theme" not in st.session_state:
    st.session_state.theme = "Dark"  # Dark by default

theme = st.session_state.theme

# =========================
# GLOBAL STYLING (theme-aware)
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

    /* Sidebar: light, high-contrast for typing */
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
    """Map similar names to canonical Rebelle categories."""
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


def extract_strain_type(name, subcat):
    """
    Strain/type logic:

    - Base: indica / sativa / hybrid / cbd / unspecified
    - Vapes: detect oil type (distillate, live resin / LLR, cured resin, rosin)
    - Edibles: detect form (gummy, chocolate)
    - Concentrates: detect RSO
    - Pre-rolls: keep 'infused' logic
    - Disposables: keep disposable logic for vapes
    """
    s = str(name).lower()
    cat = str(subcat).lower()

    # Base strain call
    base = "unspecified"
    if "indica" in s:
        base = "indica"
    elif "sativa" in s:
        base = "sativa"
    elif "hybrid" in s:
        base = "hybrid"
    elif "cbd" in s:
        base = "cbd"

    # Flags
    vape_flag = any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"])
    preroll_flag = any(k in s for k in ["pre roll", "preroll", "pre-roll", "joint"])

    # --- VAPES: oil type detection ---
    oil = None
    if "vape" in cat or vape_flag:
        if any(k in s for k in ["live resin", "llr", "liquid live resin"]):
            oil = "live resin"
        elif "cured resin" in s:
            oil = "cured resin"
        elif "rosin" in s:
            oil = "rosin"
        elif any(k in s for k in ["distillate", "disty"]):
            oil = "distillate"

    # Disposables (vapes)
    if ("disposable" in s or "dispos" in s) and vape_flag:
        if oil:
            oil = f"{oil} disposable"
        else:
            # If we don't know oil, still tag disposable
            if base != "unspecified":
                return f"{base} disposable"
            return "disposable"

    # Infused pre-rolls
    if "infused" in s and preroll_flag:
        return base + " infused" if base != "unspecified" else "infused"

    # --- EDIBLES: form detection (gummy / chocolate) ---
    if "edible" in cat or "edibles" in cat:
        form = None
        if any(k in s for k in ["gummy", "gummies", "chew", "fruit chew"]):
            form = "gummy"
        elif any(k in s for k in ["chocolate", "choc "]):
            form = "chocolate"

        if form:
            if base != "unspecified":
                return f"{base} {form}"
            return form

    # --- CONCENTRATES: RSO tagging ---
    if "concentrate" in cat or "concentrates" in cat:
        if "rso" in s or "rick simpson" in s:
            if base != "unspecified":
                return f"{base} rso"
            return "rso"

    # If we have an oil type for vapes, return that layered with base
    if oil:
        if base != "unspecified":
            return f"{base} {oil}"
        return oil

    return base


def extract_size(text, context=None):
    s = str(text).lower()

    # mg doses
    mg = re.search(r"(\d+(\.\d+)?\s?mg)", s)
    if mg:
        return mg.group(1).replace(" ", "")

    # grams / ounces: normalize 1oz/1 oz/28g to "28g"
    g = re.search(r"((?:\d+\.?\d*|\.\d+)\s?(g|oz))", s)
    if g:
        val = g.group(1).replace(" ", "")
        val_lower = val.lower()
        if val_lower in ["1oz", "1.0oz", "28g", "28.0g"]:
            return "28g"
        return val_lower

    # 0.5g style vapes (if "vape", "cart", "pen", "pod" appears)
    if any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"]):
        half = re.search(r"\b0\.5\b|\b\.5\b", s)
        if half:
            return "0.5g"

    return "unspecified"


def read_inventory_file(uploaded_file):
    """
    Read inventory CSV or Excel while being robust to 3–5 line headers
    (e.g., Dutchie/BLAZE 'Export Date / From Date / To Date' at the top).
    """
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)

    if name.endswith(".csv"):
        tmp = pd.read_csv(uploaded_file, header=None)
    else:
        tmp = pd.read_excel(uploaded_file, header=None)

    header_row = 0
    max_scan = min(10, len(tmp))
    for i in range(max_scan):
        row_text = " ".join(str(v) for v in tmp.iloc[i].tolist()).lower()
        if any(tok in row_text for tok in ["product", "item", "sku", "name"]):
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
    (Dutchie 'Total Sales by Product' style) and uses that as the header.
    """
    uploaded_file.seek(0)
    tmp = pd.read_excel(uploaded_file, header=None)
    header_row = 0
    max_scan = min(15, len(tmp))
    for i in range(max_scan):
        row_text = " ".join(str(v) for v in tmp.iloc[i].tolist()).lower()
        if "category" in row_text and ("product" in row_text or "name" in row_text):
            header_row = i
            break
    uploaded_file.seek(0)
    df = pd.read_excel(uploaded_file, header=header_row)
    return df


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

    # Keep payload modest
    sample = detail_view.copy()
    # Focus on lines that actually matter to a buyer
    sample = sample.sort_values(
        ["reorderpriority", "daysonhand"], ascending=[True, True]
    )
    sample = sample.head(80)

    # Only send the key columns
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
Each row is a category/size/strain combo with its sales and coverage.

Fields:
- mastercategory / subcategory (normalized product category)
- strain_type (indica / sativa / hybrid / disposable / infused / gummy / chocolate / rso etc.)
- packagesize (like 3.5g, 1g, 5mg, 28g, 500mg)
- onhandunits (current inventory units in stock)
- unitssold (units sold in the lookback window)
- avgunitsperday (velocity estimate)
- daysonhand (coverage in days)
- reorderqty (suggested buy quantity)
- reorderpriority (1=ASAP, 2=Watch, 3=Comfortable, 4=Dead)

Target days on hand: {doh_threshold}

Data (JSON list of rows):
{json.dumps(sample_records, indent=2)}

Tasks:
1. Call out any rows that look obviously wrong or risky
   (for example: 0 onhand but lots of units sold, DOH way above 120,
   or suggest reorder but DOH is already high).
2. Briefly explain what a buyer should pay attention to in this slice:
   - top 3 categories that are in danger of stockout
   - anything that looks dead/overbought and could be discounted down.
3. Keep it short, punchy, and buyer-friendly. No code, just bullet-style advice.
"""

    try:
        resp = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a sharp, no-BS cannabis retail buyer coach.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=600,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"AI check failed: {e}"


# =========================
# 🔐 THEME TOGGLE + ADMIN + TRIAL GATE
# =========================

# Theme toggle in sidebar
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
    admin_user = st.sidebar.text_input("Username", key="admin_user")
    admin_pass = st.sidebar.text_input("Password", type="password", key="admin_pass")
    if st.sidebar.button("Login as Admin"):
        if admin_user == ADMIN_USERNAME and admin_pass == ADMIN_PASSWORD:
            st.session_state.is_admin = True
            st.sidebar.success("✅ Admin mode enabled.")
        else:
            st.sidebar.error("❌ Invalid admin credentials.")
else:
    st.sidebar.success("👑 Admin mode: unlimited access")
    if st.sidebar.button("Logout Admin"):
        st.session_state.is_admin = False
        st.experimental_rerun()

trial_now = datetime.now()

if not st.session_state.is_admin:
    st.sidebar.markdown("### 🔐 Trial Access")

    if st.session_state.trial_start is None:
        trial_key_input = st.sidebar.text_input(
            "Enter trial key", type="password", key="trial_key_input"
        )
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
st.markdown(f"**Client:** {CLIENT_NAME}")
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
# PAGE SWITCH
# =========================
section = st.sidebar.radio(
    "App Section",
    ["📊 Inventory Dashboard", "🧾 PO Builder"],
    index=0,
)

# ============================================================
# PAGE 1 – INVENTORY DASHBOARD
# ============================================================
if section == "📊 Inventory Dashboard":

    # Data source selector (for future hooks)
    st.sidebar.markdown("### 🧩 Data Source")
    data_source = st.sidebar.selectbox(
        "Select POS / Data Source",
        ["BLAZE", "Dutchie"],
        index=0,
        help="Changes how column names are interpreted. Files are still just CSV/XLSX exports.",
    )

    st.sidebar.header("📂 Upload Core Reports")

    # Accept both CSV and Excel for inventory
    inv_file = st.sidebar.file_uploader("Inventory File (CSV or Excel)", type=["csv", "xlsx", "xls"])
    product_sales_file = st.sidebar.file_uploader(
        "Product Sales Report (qty-based Excel)", type=["xlsx", "xls"]
    )
    extra_sales_file = st.sidebar.file_uploader(
        "Optional Extra Sales Detail (revenue)",
        type=["xlsx", "xls"],
        help="Optional: Dutchie 'Total Sales by Product' or similar. "
             "Currently **ignored for velocity** until revenue views are added.",
    )

    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Forecast Settings")
    doh_threshold = st.sidebar.number_input("Target Days on Hand", 1, 60, 21)
    velocity_adjustment = st.sidebar.number_input("Velocity Adjustment", 0.01, 5.0, 0.5)
    date_diff = st.sidebar.slider("Days in Sales Period", 7, 90, 60)

    # Cache raw dataframes when new files are uploaded
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
            # Not critical – we can ignore failures here
            st.session_state.extra_sales_df = None

    if st.session_state.inv_raw_df is not None and st.session_state.sales_raw_df is not None:
        try:
            inv_df = st.session_state.inv_raw_df.copy()
            sales_raw = st.session_state.sales_raw_df.copy()

            # -------- INVENTORY --------
            inv_df.columns = inv_df.columns.str.strip().str.lower()

            # Auto-detect core inventory columns (supports BLAZE & Dutchie)
            inv_name_aliases = [
                "product", "productname", "item", "itemname", "name", "skuname",
                "skuid", "product name"
            ]
            inv_cat_aliases = [
                "category", "subcategory", "productcategory", "department",
                "mastercategory", "product category", "cannabis"
            ]
            inv_qty_aliases = [
                "available", "onhand", "onhandunits", "quantity", "qty",
                "quantityonhand", "instock", "currentquantity", "current quantity",
                "inventoryavailable", "inventory available"
            ]

            name_col = detect_column(inv_df.columns, [normalize_col(a) for a in inv_name_aliases])
            cat_col = detect_column(inv_df.columns, [normalize_col(a) for a in inv_cat_aliases])
            qty_col = detect_column(inv_df.columns, [normalize_col(a) for a in inv_qty_aliases])

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

            inv_df["onhandunits"] = pd.to_numeric(inv_df["onhandunits"], errors="coerce").fillna(0)
            # normalize to Rebelle canonical categories
            inv_df["subcategory"] = inv_df["subcategory"].apply(normalize_rebelle_category)

            # Strain Type + Package Size
            inv_df["strain_type"] = inv_df.apply(
                lambda x: extract_strain_type(x["itemname"], x["subcategory"]), axis=1
            )
            inv_df["packagesize"] = inv_df.apply(
                lambda x: extract_size(x["itemname"], x["subcategory"]), axis=1
            )

            # Group inventory by subcategory + strain + size
            inv_summary = (
                inv_df.groupby(["subcategory", "strain_type", "packagesize"])["onhandunits"]
                .sum()
                .reset_index()
            )

            # -------- SALES (qty-based ONLY) --------
            sales_raw.columns = sales_raw.columns.astype(str).str.lower()

            # Auto-detect product name column
            sales_name_aliases = [
                "product", "productname", "product title", "producttitle",
                "productid", "name", "item", "itemname", "skuname",
                "sku", "description", "product name"
            ]
            name_col_sales = detect_column(
                sales_raw.columns, [normalize_col(a) for a in sales_name_aliases]
            )

            # Auto-detect quantity/units sold column – STRICTLY counts, not $$
            qty_aliases = [
                "quantitysold", "quantity sold",
                "qtysold", "qty sold",
                "itemsold", "item sold", "items sold",
                "unitssold", "units sold", "unit sold", "unitsold", "units",
                "totalunits", "total units",
                "quantity", "qty",
            ]
            qty_col_sales = detect_column(
                sales_raw.columns, [normalize_col(a) for a in qty_aliases]
            )

            # Extra safety: if the matched column is clearly a revenue column, reject it
            if qty_col_sales is not None:
                norm_qty_name = normalize_col(qty_col_sales)
                revenue_like = {
                    "sales", "netsales", "totalsales", "retailvalue",
                    "grosssales", "saleamount"
                }
                if norm_qty_name in revenue_like:
                    qty_col_sales = None

            # Auto-detect category/mastercategory column
            mc_aliases = [
                "mastercategory", "category", "master_category",
                "productcategory", "product category",
                "department", "dept", "subcategory", "productcategoryname",
                "product category name"
            ]
            mc_col = detect_column(sales_raw.columns, [normalize_col(a) for a in mc_aliases])

            if not (name_col_sales and qty_col_sales and mc_col):
                st.error(
                    "Product Sales file detected but could not find required columns.\n\n"
                    "Looked for some variant of: product / product name, quantity or items sold, "
                    "and category or product category.\n\n"
                    "Tip: Use Dutchie 'Product Sales' or Blaze 'Sales by Product' exports "
                    "without manually editing the headers."
                )
                st.stop()

            # Normalize to internal names
            sales_raw = sales_raw.rename(
                columns={
                    name_col_sales: "product_name",
                    qty_col_sales: "unitssold",
                    mc_col: "mastercategory",
                }
            )

            sales_raw["unitssold"] = pd.to_numeric(
                sales_raw["unitssold"], errors="coerce"
            ).fillna(0)

            # normalize categories here as well
            sales_raw["mastercategory"] = sales_raw["mastercategory"].apply(normalize_rebelle_category)

            # Filter out accessories / 'all' (anything with "accessor")
            sales_df = sales_raw[
                ~sales_raw["mastercategory"].astype(str).str.contains("accessor")
                & (sales_raw["mastercategory"] != "all")
            ].copy()

            # Add package size on the sales side (granular per size)
            sales_df["packagesize"] = sales_df.apply(
                lambda row: extract_size(row["product_name"], row["mastercategory"]),
                axis=1,
            )

            # Category + size level velocity
            sales_summary = (
                sales_df.groupby(["mastercategory", "packagesize"])["unitssold"]
                .sum()
                .reset_index()
            )
            sales_summary["avgunitsperday"] = (
                sales_summary["unitssold"] / max(date_diff, 1)
            ) * velocity_adjustment

            # Merge inventory summary with size-level velocity
            detail = pd.merge(
                inv_summary,
                sales_summary,
                how="left",
                left_on=["subcategory", "packagesize"],
                right_on=["mastercategory", "packagesize"],
            ).fillna(0)

            # --- Ensure Flower 28g / 1oz always shows ---
            flower_mask = detail["subcategory"].str.contains("flower", na=False)
            flower_cats = detail.loc[flower_mask, "subcategory"].unique()

            missing_rows = []
            for cat in flower_cats:
                if not ((detail["subcategory"] == cat) & (detail["packagesize"] == "28g")).any():
                    missing_rows.append(
                        {
                            "subcategory": cat,
                            "strain_type": "unspecified",
                            "packagesize": "28g",
                            "onhandunits": 0,
                            "mastercategory": cat,
                            "unitssold": 0,
                            "avgunitsperday": 0,
                        }
                    )

            if missing_rows:
                detail = pd.concat([detail, pd.DataFrame(missing_rows)], ignore_index=True)

            # --- Ensure Edibles 500mg high-dose row always shows (acts like 28g for flower) ---
            edibles_mask = detail["subcategory"].str.contains("edible", na=False)
            edibles_cats = detail.loc[edibles_mask, "subcategory"].unique()

            edibles_missing = []
            for cat in edibles_cats:
                if not ((detail["subcategory"] == cat) & (detail["packagesize"] == "500mg")).any():
                    edibles_missing.append(
                        {
                            "subcategory": cat,
                            "strain_type": "unspecified",
                            "packagesize": "500mg",
                            "onhandunits": 0,
                            "mastercategory": cat,
                            "unitssold": 0,
                            "avgunitsperday": 0,
                        }
                    )

            if edibles_missing:
                detail = pd.concat([detail, pd.DataFrame(edibles_missing)], ignore_index=True)

            # DOH + Reorder (granular per row)
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
                if row["daysonhand"] <= 7:
                    return "1 – Reorder ASAP"
                if row["daysonhand"] <= 21:
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
            reorder_asap = (detail["reorderpriority"] == "1 – Reorder ASAP").sum()

            col1, col2 = st.columns(2)
            with col1:
                if st.button(
                    f"Units Sold (Granular Size-Level): {total_units}",
                    key="btn_total_units",
                ):
                    st.session_state.metric_filter = "All"
            with col2:
                if st.button(
                    f"Reorder ASAP (Lines): {reorder_asap}",
                    key="btn_reorder_asap",
                ):
                    st.session_state.metric_filter = "Reorder ASAP"

            # Apply metric filter to detail for display
            if st.session_state.metric_filter == "Reorder ASAP":
                detail_view = detail[detail["reorderpriority"] == "1 – Reorder ASAP"].copy()
            else:
                detail_view = detail.copy()

            st.markdown(
                f"*Current filter:* **{st.session_state.metric_filter}**"
            )

            st.markdown("### Forecast Table")

            def red_low(val):
                try:
                    v = int(val)
                    return "color:#FF3131" if v < doh_threshold else ""
                except Exception:
                    return ""

            # Category filter (ordered by Rebelle categories first) **after** metric filter
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

            # Make sure cannabis type (strain_type) is visible
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

            # Use same category ordering for expanders
            for cat in sorted(detail_view["subcategory"].unique(), key=cat_sort_key):
                group = detail_view[detail_view["subcategory"] == cat]
                with st.expander(cat.title()):
                    g = group[display_cols].copy()
                    st.dataframe(
                        g.style.applymap(red_low, subset=["daysonhand"]),
                        use_container_width=True,
                    )

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
                    "Streamlit secrets. Add one to turn this on."
                )

        except Exception as e:
            st.error(f"Error: {e}")

    else:
        st.info("Upload inventory + product sales files to continue.")

# ============================================================
# PAGE 2 – PO BUILDER
# ============================================================
else:
    st.subheader("🧾 Purchase Order Builder")

    st.markdown(
        "The words above each PO field are white on the dark background for clarity."
    )

    # -------------------------
    # HEADER INFO
    # -------------------------
    st.markdown("### PO Header")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="po-label">Store / Ship-To Name</div>', unsafe_allow_html=True)
        store_name = st.text_input("", value="Rebelle Cannabis", key="store_name")

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

    # -------------------------
    # LINE ITEMS
    # -------------------------
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

    # -------------------------
    # TOTALS + PDF EXPORT
    # -------------------------
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
            file_name=f"PO_{po_number or 'rebelle'}.pdf",
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
