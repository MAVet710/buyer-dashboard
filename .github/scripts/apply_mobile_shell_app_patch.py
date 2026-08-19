from __future__ import annotations

from pathlib import Path
import re


def _newline(raw: str) -> str:
    return "\r\n" if raw.count("\r\n") >= max(1, raw.count("\n") // 2) else "\n"


# ---------------------------------------------------------------------------
# app.py: stop rendering the duplicate legacy Buyer controls in flat-shell mode
# ---------------------------------------------------------------------------
app_path = Path("app.py")
raw = app_path.read_text(encoding="utf-8", newline="")
nl = _newline(raw)

pattern = re.compile(
    r"# =========================\r?\n"
    r"# GLOBAL DATA MODE SELECTOR \(BUYER OPERATIONS ONLY\)\r?\n"
    r"# =========================\r?\n"
    r"[\s\S]*?"
    r"if section == INVENTORY_COUNTS_SECTION:",
    re.MULTILINE,
)

replacement = """# =========================
# BUYER OPERATIONS SHELL STATE
# =========================
_flat_navigation_active = bool(st.session_state.get("flat_navigation_enabled", False)) and not bool(
    st.session_state.get("legacy_navigation_enabled", False)
)

# The approved flat shell owns the visible navigation and data-mode control.
# Classic mode keeps the original widgets below as a compatibility fallback.
if _flat_navigation_active:
    data_mode = str(st.session_state.get("data_mode") or "📁 Uploads")
    if data_mode not in {"📁 Uploads", "🔴 Dutchie Live"}:
        data_mode = "📁 Uploads"
        st.session_state["data_mode"] = data_mode
else:
    st.sidebar.markdown("---")
    data_mode = st.sidebar.selectbox(
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
section_groups = buyer_section_groups(
    is_admin=st.session_state.get("is_admin", False),
    user_role=str(st.session_state.get("auth_user_role") or "trial"),
    admin_exports_enabled=_feature_enabled("admin_exports", default_enabled=True),
)

if _flat_navigation_active:
    _allowed_buyer_sections = [
        page
        for pages in section_groups.values()
        for page in pages
    ]
    section = str(st.session_state.get("buyer_section") or "")
    if section not in _allowed_buyer_sections:
        section = _allowed_buyer_sections[0]
        st.session_state["buyer_section"] = section
    st.session_state["buyer_section_group"] = next(
        (
            group
            for group, pages in section_groups.items()
            if section in pages
        ),
        next(iter(section_groups)),
    )
else:
    saved_buyer_section = st.session_state.get("buyer_section")
    saved_retail_area = next(
        (
            group
            for group, sections in section_groups.items()
            if saved_buyer_section in sections
        ),
        next(iter(section_groups)),
    )
    if st.session_state.get("buyer_section_group") not in section_groups:
        st.session_state["buyer_section_group"] = saved_retail_area

    retail_area = st.sidebar.selectbox(
        "Retail Area",
        list(section_groups),
        key="buyer_section_group",
        help="Choose a task area, then select the tool you need.",
    )
    visible_section_options = section_groups[retail_area]
    if st.session_state.get("buyer_section") not in visible_section_options:
        st.session_state["buyer_section"] = visible_section_options[0]

    section = st.sidebar.radio(
        "Tool",
        visible_section_options,
        key="buyer_section",
        help="Buyer Operations tools are grouped to keep navigation clean on desktop and mobile.",
    )

if section == INVENTORY_COUNTS_SECTION:""".replace("\n", nl)

raw, count = pattern.subn(replacement, raw, count=1)
if count != 1:
    raise SystemExit(f"Expected one Buyer shell block in app.py; patched {count}.")
app_path.write_text(raw, encoding="utf-8", newline="")


# ---------------------------------------------------------------------------
# Product 360: true right-side drawer desktop, full-screen mobile
# ---------------------------------------------------------------------------
p360_path = Path("modules/navigation/product_360.py")
p360 = p360_path.read_text(encoding="utf-8", newline="")
pnl = _newline(p360)

drawer_pattern = re.compile(
    r"def _drawer_css\(\) -> None:\r?\n[\s\S]*?\r?\ndef _render_product_body",
    re.MULTILINE,
)
drawer_replacement = """def _drawer_css() -> None:
    st.markdown(
        \"\"\"
        <style>
        div[data-testid="stDialog"] {
            align-items: stretch !important;
            justify-content: flex-end !important;
            padding: 0 !important;
        }
        div[data-testid="stDialog"] > div[role="dialog"] {
            position: fixed !important;
            top: 0 !important;
            right: 0 !important;
            bottom: 0 !important;
            left: auto !important;
            width: min(570px, 92vw) !important;
            max-width: 570px !important;
            height: 100dvh !important;
            max-height: 100dvh !important;
            margin: 0 !important;
            padding: 1rem 1rem 2rem !important;
            overflow-y: auto !important;
            border: 0 !important;
            border-left: 1px solid rgba(231,152,78,.28) !important;
            border-radius: 18px 0 0 18px !important;
            background: linear-gradient(155deg,#171915,#0d0f0d) !important;
            box-shadow: -24px 0 70px rgba(0,0,0,.48) !important;
        }
        div[data-testid="stDialog"] > div[role="dialog"] > div {
            max-width: 100% !important;
        }
        @media (max-width: 768px) {
            div[data-testid="stDialog"] > div[role="dialog"] {
                width: 100vw !important;
                max-width: 100vw !important;
                height: 100dvh !important;
                max-height: 100dvh !important;
                padding: .72rem .7rem 4rem !important;
                border-left: 0 !important;
                border-radius: 0 !important;
            }
            div[data-testid="stDialog"] > div[role="dialog"] div[data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
                gap: .45rem !important;
            }
            div[data-testid="stDialog"] > div[role="dialog"] div[data-testid="column"] {
                min-width: min(100%, 145px) !important;
                flex: 1 1 145px !important;
            }
        }
        </style>
        \"\"\",
        unsafe_allow_html=True,
    )


def _render_product_body""".replace("\n", pnl)

p360, count = drawer_pattern.subn(drawer_replacement, p360, count=1)
if count != 1:
    raise SystemExit(f"Expected one Product 360 drawer CSS block; patched {count}.")

old_search_css = """        <style>
        .st-key-buyer_dash_global_search {position: relative; z-index: 30;}
        .st-key-buyer_dash_global_search input {font-size: .95rem;}
        </style>""".replace("\n", pnl)
new_search_css = """        <style>
        .st-key-buyer_dash_global_search {z-index: 30;}
        .st-key-buyer_dash_global_search input {font-size: .95rem;}
        </style>""".replace("\n", pnl)
if old_search_css not in p360:
    raise SystemExit("Product 360 global-search CSS anchor not found.")
p360 = p360.replace(old_search_css, new_search_css, 1)
p360_path.write_text(p360, encoding="utf-8", newline="")

print("Applied responsive shell integration patch.")
