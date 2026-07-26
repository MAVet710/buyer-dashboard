"""Premium application shell for the DoobieLogic Streamlit workspace.

This module intentionally sits on top of the legacy theme.  The application has
many mature workflows with their own markup, so a final shared CSS layer gives
them one visual language without rewriting business screens.
"""

from __future__ import annotations

import html

import streamlit as st


def load_premium_shell(theme: str = "Dark") -> str:
    """Return the final, theme-aware design-system layer."""

    is_dark = str(theme).strip().lower() != "light"
    palette = {
        "canvas": "#080A09" if is_dark else "#F3F4F1",
        "canvas_alt": "#0C0F0D" if is_dark else "#E9ECE7",
        "surface": "rgba(17, 20, 18, .92)" if is_dark else "rgba(255, 255, 255, .94)",
        "surface_solid": "#111412" if is_dark else "#FFFFFF",
        "surface_raised": "rgba(24, 28, 25, .96)" if is_dark else "rgba(255, 255, 255, .98)",
        "surface_soft": "rgba(255, 255, 255, .035)" if is_dark else "rgba(22, 31, 25, .035)",
        "text": "#F5F7F4" if is_dark else "#172019",
        "text_soft": "#AAB4AC" if is_dark else "#5E6B61",
        "text_faint": "#758078" if is_dark else "#7C887F",
        "border": "rgba(255, 255, 255, .085)" if is_dark else "rgba(23, 32, 25, .10)",
        "border_strong": "rgba(255, 255, 255, .15)" if is_dark else "rgba(23, 32, 25, .18)",
        "shadow": "rgba(0, 0, 0, .40)" if is_dark else "rgba(25, 35, 27, .12)",
        "sidebar": "rgba(10, 13, 11, .97)" if is_dark else "rgba(249, 250, 247, .98)",
        "input": "rgba(5, 7, 6, .72)" if is_dark else "rgba(255, 255, 255, .95)",
    }

    return f"""
    <style>
    :root {{
        --dl-canvas: {palette["canvas"]};
        --dl-canvas-alt: {palette["canvas_alt"]};
        --dl-surface: {palette["surface"]};
        --dl-surface-solid: {palette["surface_solid"]};
        --dl-surface-raised: {palette["surface_raised"]};
        --dl-surface-soft: {palette["surface_soft"]};
        --dl-text: {palette["text"]};
        --dl-text-soft: {palette["text_soft"]};
        --dl-text-faint: {palette["text_faint"]};
        --dl-border: {palette["border"]};
        --dl-border-strong: {palette["border_strong"]};
        --dl-shadow: {palette["shadow"]};
        --dl-sidebar: {palette["sidebar"]};
        --dl-input: {palette["input"]};
        --dl-copper: #E7984E;
        --dl-copper-bright: #F4B36F;
        --dl-copper-deep: #B96523;
        --dl-green: #58D68D;
        --dl-blue: #67A9FF;
        --dl-yellow: #F0C75E;
        --dl-red: #FF7171;
        --dl-radius-sm: 10px;
        --dl-radius-md: 14px;
        --dl-radius-lg: 20px;
        --dl-radius-xl: 26px;
        --dl-ring: 0 0 0 3px rgba(231, 152, 78, .20);
    }}

    html, body, [class*="css"] {{
        color: var(--dl-text);
        font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont,
            "Segoe UI", sans-serif;
        font-variant-numeric: tabular-nums;
        text-rendering: optimizeLegibility;
    }}

    body {{
        background: var(--dl-canvas);
    }}

    .stApp {{
        color: var(--dl-text);
        background:
            radial-gradient(circle at 76% -10%, rgba(231, 152, 78, .11), transparent 30rem),
            radial-gradient(circle at 18% 22%, rgba(64, 117, 82, .08), transparent 26rem),
            linear-gradient(145deg, var(--dl-canvas-alt), var(--dl-canvas) 58%) !important;
        background-attachment: fixed !important;
    }}

    [data-testid="stHeader"] {{
        background: transparent;
    }}

    [data-testid="stToolbar"] {{
        opacity: .72;
    }}

    .block-container {{
        width: min(100%, 1560px) !important;
        max-width: 1560px !important;
        padding: 1.45rem 2.15rem 4rem !important;
        color: var(--dl-text) !important;
        background: transparent !important;
        border: 0 !important;
        border-radius: 0 !important;
        box-shadow: none !important;
    }}

    .block-container *:not(input):not(textarea):not(select):not(option) {{
        color: inherit;
    }}

    h1, h2, h3, h4, h5, h6 {{
        color: var(--dl-text) !important;
        font-weight: 760 !important;
        letter-spacing: -.035em !important;
    }}

    h1 {{
        font-size: clamp(2rem, 4vw, 3rem) !important;
        line-height: 1.02 !important;
    }}

    h2 {{
        font-size: clamp(1.45rem, 2.6vw, 2rem) !important;
    }}

    p, label, [data-testid="stCaptionContainer"], .stMarkdown {{
        line-height: 1.55;
    }}

    .block-container [data-testid="stCaptionContainer"] {{
        color: var(--dl-text-soft) !important;
    }}

    .block-container a {{
        color: var(--dl-copper-bright) !important;
    }}

    hr {{
        border-color: var(--dl-border) !important;
        margin: 1.15rem 0 !important;
    }}

    /* Product chrome */
    .premium-commandbar {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        min-height: 62px;
        margin: 0 0 1rem;
        padding: .72rem .82rem .72rem .9rem;
        border: 1px solid var(--dl-border);
        border-radius: var(--dl-radius-lg);
        background: linear-gradient(135deg, var(--dl-surface-raised), var(--dl-surface));
        box-shadow: 0 16px 50px var(--dl-shadow), inset 0 1px rgba(255, 255, 255, .035);
        backdrop-filter: blur(18px);
    }}

    .premium-commandbar__identity {{
        display: flex;
        align-items: center;
        min-width: 0;
        gap: .72rem;
    }}

    .premium-commandbar__mark {{
        display: grid;
        place-items: center;
        width: 38px;
        height: 38px;
        flex: 0 0 auto;
        color: #201307 !important;
        background: linear-gradient(145deg, var(--dl-copper-bright), var(--dl-copper));
        border-radius: 12px;
        box-shadow: 0 8px 24px rgba(231, 152, 78, .25);
        font-size: .78rem;
        font-weight: 850;
        letter-spacing: -.04em;
    }}

    .premium-commandbar__kicker,
    .premium-sidebar-brand__kicker {{
        color: var(--dl-copper) !important;
        font-size: .64rem;
        font-weight: 800;
        letter-spacing: .17em;
        text-transform: uppercase;
    }}

    .premium-commandbar__title {{
        overflow: hidden;
        color: var(--dl-text) !important;
        font-size: .98rem;
        font-weight: 760;
        line-height: 1.15;
        text-overflow: ellipsis;
        white-space: nowrap;
    }}

    .premium-commandbar__context {{
        display: flex;
        align-items: center;
        justify-content: flex-end;
        flex-wrap: wrap;
        gap: .42rem;
    }}

    .premium-context-pill {{
        display: inline-flex;
        align-items: center;
        gap: .35rem;
        min-height: 31px;
        padding: .25rem .62rem;
        color: var(--dl-text-soft) !important;
        background: var(--dl-surface-soft);
        border: 1px solid var(--dl-border);
        border-radius: 999px;
        font-size: .72rem;
        font-weight: 680;
        white-space: nowrap;
    }}

    .premium-context-pill--live::before {{
        width: 7px;
        height: 7px;
        content: "";
        background: var(--dl-green);
        border-radius: 50%;
        box-shadow: 0 0 0 4px rgba(88, 214, 141, .10);
    }}

    /* Sidebar */
    [data-testid="stSidebar"] {{
        width: 300px !important;
        color: var(--dl-text) !important;
        background:
            radial-gradient(circle at 20% 0%, rgba(231, 152, 78, .10), transparent 17rem),
            var(--dl-sidebar) !important;
        border-right: 1px solid var(--dl-border) !important;
        box-shadow: 22px 0 60px rgba(0, 0, 0, .18);
    }}

    [data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
        padding: 1rem .9rem 4rem !important;
    }}

    [data-testid="stSidebar"] * {{
        color: var(--dl-text) !important;
    }}

    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
        gap: .42rem;
    }}

    .premium-sidebar-brand {{
        display: flex;
        align-items: center;
        gap: .72rem;
        margin: -.1rem 0 .85rem;
        padding: .72rem;
        border: 1px solid var(--dl-border);
        border-radius: 16px;
        background: linear-gradient(145deg, rgba(255, 255, 255, .055), rgba(255, 255, 255, .018));
        box-shadow: inset 0 1px rgba(255, 255, 255, .035);
    }}

    .premium-sidebar-brand img {{
        width: 38px;
        height: 38px;
        flex: 0 0 auto;
        object-fit: cover;
        border: 1px solid rgba(255, 255, 255, .12);
        border-radius: 12px;
        box-shadow: 0 8px 22px rgba(0, 0, 0, .28);
    }}

    .premium-sidebar-brand__name {{
        color: var(--dl-text) !important;
        font-size: .92rem;
        font-weight: 780;
        line-height: 1.15;
    }}

    .premium-sidebar-brand__release {{
        display: inline-flex;
        margin-top: .35rem;
        padding: .16rem .42rem;
        color: var(--dl-copper-bright) !important;
        background: rgba(231, 152, 78, .10);
        border: 1px solid rgba(231, 152, 78, .22);
        border-radius: 999px;
        font-size: .56rem;
        font-weight: 800;
        letter-spacing: .08em;
        text-transform: uppercase;
    }}

    [data-testid="stSidebar"] h3 {{
        margin: .75rem 0 .2rem !important;
        color: var(--dl-text-soft) !important;
        font-size: .68rem !important;
        font-weight: 800 !important;
        letter-spacing: .13em !important;
        text-transform: uppercase;
    }}

    [data-testid="stSidebar"] [data-testid="stAlert"] {{
        padding: .58rem .65rem !important;
        font-size: .78rem !important;
    }}

    /* Inputs, pickers, and uploads */
    [data-baseweb="input"] > div,
    [data-baseweb="select"] > div,
    [data-baseweb="textarea"] > div,
    [data-testid="stNumberInput"] > div > div,
    [data-testid="stDateInput"] > div > div {{
        min-height: 42px;
        color: var(--dl-text) !important;
        background: var(--dl-input) !important;
        border: 1px solid var(--dl-border-strong) !important;
        border-radius: var(--dl-radius-sm) !important;
        box-shadow: inset 0 1px rgba(255, 255, 255, .02);
        transition: border-color .16s ease, box-shadow .16s ease, background .16s ease;
    }}

    [data-baseweb="input"] > div:focus-within,
    [data-baseweb="select"] > div:focus-within,
    [data-baseweb="textarea"] > div:focus-within {{
        border-color: var(--dl-copper) !important;
        box-shadow: var(--dl-ring) !important;
    }}

    input, textarea, [data-baseweb="select"] span {{
        color: var(--dl-text) !important;
    }}

    [data-testid="stFileUploader"] {{
        padding: .25rem;
        border: 1px solid var(--dl-border);
        border-radius: var(--dl-radius-md);
        background: var(--dl-surface-soft);
    }}

    [data-testid="stFileUploaderDropzone"] {{
        min-height: 112px;
        background: transparent !important;
        border: 1px dashed var(--dl-border-strong) !important;
        border-radius: 11px !important;
    }}

    /* Buttons */
    .stButton > button,
    .stDownloadButton > button,
    [data-testid="stFormSubmitButton"] > button,
    [data-testid="stPopover"] button {{
        min-height: 42px;
        padding: .48rem .88rem !important;
        color: var(--dl-text) !important;
        background: linear-gradient(180deg, rgba(255, 255, 255, .075), rgba(255, 255, 255, .025)) !important;
        border: 1px solid var(--dl-border-strong) !important;
        border-radius: var(--dl-radius-sm) !important;
        box-shadow: 0 7px 20px rgba(0, 0, 0, .12);
        font-weight: 720 !important;
        letter-spacing: -.01em;
        transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease !important;
    }}

    .stButton > button[kind="primary"],
    .stDownloadButton > button[kind="primary"],
    [data-testid="stFormSubmitButton"] > button[kind="primary"] {{
        color: #211307 !important;
        background: linear-gradient(145deg, var(--dl-copper-bright), var(--dl-copper)) !important;
        border-color: rgba(255, 211, 165, .52) !important;
        box-shadow: 0 10px 26px rgba(185, 101, 35, .20);
    }}

    .stButton > button:hover,
    .stDownloadButton > button:hover,
    [data-testid="stFormSubmitButton"] > button:hover {{
        transform: translateY(-1px);
        border-color: rgba(231, 152, 78, .68) !important;
        box-shadow: 0 10px 28px rgba(0, 0, 0, .22), var(--dl-ring);
    }}

    /* Cards and data surfaces */
    .tile-card, .chart-card, .section-header-card, .hero, .ai-brief,
    .search-shell, .ex-kpi, div[data-testid="stMetric"],
    [data-testid="stVerticalBlockBorderWrapper"] {{
        background: linear-gradient(145deg, var(--dl-surface-raised), var(--dl-surface)) !important;
        border-color: var(--dl-border) !important;
        box-shadow: 0 16px 44px var(--dl-shadow), inset 0 1px rgba(255, 255, 255, .028) !important;
    }}

    .tile-card, .chart-card, .section-header-card, .hero, .ai-brief {{
        border-radius: var(--dl-radius-lg) !important;
    }}

    .section-header-card {{
        padding: 1.2rem 1.35rem !important;
    }}

    .section-header-card::after {{
        background: radial-gradient(circle, rgba(231, 152, 78, .16), transparent 68%) !important;
    }}

    .block-container .section-kicker,
    .block-container .metric-label {{
        color: var(--dl-copper) !important;
    }}

    .block-container .section-subtitle,
    .block-container .metric-help,
    .block-container .hero p,
    .block-container .chart-subtitle {{
        color: var(--dl-text-soft) !important;
    }}

    .block-container .inv-priority-fresh {{ color: var(--dl-green) !important; }}
    .block-container .inv-priority-aging {{ color: var(--dl-yellow) !important; }}
    .block-container .inv-priority-priorityrun {{ color: var(--dl-copper) !important; }}
    .block-container .inv-priority-stale {{ color: var(--dl-red) !important; }}

    div[data-testid="stMetric"] {{
        min-height: 114px;
        padding: 1rem 1.05rem !important;
        border-radius: var(--dl-radius-md) !important;
    }}

    div[data-testid="stMetric"] label {{
        color: var(--dl-text-soft) !important;
        font-size: .73rem !important;
        font-weight: 760 !important;
        letter-spacing: .08em;
        text-transform: uppercase;
    }}

    div[data-testid="stMetricValue"] {{
        color: var(--dl-text) !important;
        font-size: 1.65rem !important;
        font-weight: 780 !important;
        letter-spacing: -.04em;
    }}

    /* Tables */
    [data-testid="stDataFrame"], [data-testid="stDataEditor"] {{
        overflow: hidden;
        background: var(--dl-surface) !important;
        border: 1px solid var(--dl-border) !important;
        border-radius: var(--dl-radius-md) !important;
        box-shadow: 0 14px 40px var(--dl-shadow) !important;
    }}

    .dataframe thead th {{
        color: var(--dl-text-soft) !important;
        background: var(--dl-surface-solid) !important;
        border-bottom: 1px solid var(--dl-border-strong) !important;
        font-size: .72rem !important;
        font-weight: 780 !important;
        letter-spacing: .06em;
        text-transform: uppercase;
    }}

    .dataframe tbody td {{
        color: var(--dl-text) !important;
        background: transparent !important;
        border-bottom: 1px solid var(--dl-border) !important;
    }}

    .dataframe tbody tr:hover td {{
        background: rgba(231, 152, 78, .055) !important;
    }}

    /* Tabs, expanders, notices */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {{
        gap: .3rem;
        padding: .28rem;
        background: var(--dl-surface-soft);
        border: 1px solid var(--dl-border);
        border-radius: 13px;
    }}

    [data-testid="stTabs"] [data-baseweb="tab"] {{
        min-height: 40px;
        padding: .42rem .78rem;
        border-radius: 9px !important;
        color: var(--dl-text-soft) !important;
        font-size: .82rem;
        font-weight: 700;
    }}

    [data-testid="stTabs"] [aria-selected="true"] {{
        color: var(--dl-text) !important;
        background: var(--dl-surface-raised) !important;
        box-shadow: 0 5px 16px rgba(0, 0, 0, .16);
    }}

    [data-testid="stTabs"] [data-baseweb="tab-highlight"] {{
        display: none;
    }}

    [data-testid="stExpander"] {{
        overflow: hidden;
        background: var(--dl-surface-soft) !important;
        border: 1px solid var(--dl-border) !important;
        border-radius: var(--dl-radius-md) !important;
        box-shadow: none !important;
    }}

    [data-testid="stExpander"] summary {{
        min-height: 44px;
        font-weight: 690;
    }}

    [data-testid="stAlert"] {{
        border: 1px solid var(--dl-border-strong) !important;
        border-radius: var(--dl-radius-md) !important;
        box-shadow: 0 10px 28px rgba(0, 0, 0, .12) !important;
    }}

    [data-testid="stProgress"] > div > div > div > div {{
        background: linear-gradient(90deg, var(--dl-copper-deep), var(--dl-copper-bright)) !important;
    }}

    /* Scrollbars */
    * {{
        scrollbar-color: rgba(231, 152, 78, .36) transparent;
        scrollbar-width: thin;
    }}

    *::-webkit-scrollbar {{
        width: 8px;
        height: 8px;
    }}

    *::-webkit-scrollbar-thumb {{
        background: rgba(231, 152, 78, .30);
        border: 2px solid transparent;
        border-radius: 999px;
        background-clip: padding-box;
    }}

    @media (max-width: 900px) {{
        .block-container {{
            padding: 1rem 1rem 4.75rem !important;
        }}

        .premium-commandbar {{
            align-items: flex-start;
            flex-direction: column;
        }}

        .premium-commandbar__context {{
            justify-content: flex-start;
        }}
    }}

    @media (max-width: 768px) {{
        .stApp {{
            background-attachment: scroll !important;
        }}

        [data-testid="stSidebar"] {{
            width: min(88vw, 320px) !important;
        }}

        [data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
            padding: .8rem .75rem 4.5rem !important;
        }}

        .block-container {{
            padding: .85rem .72rem 5.2rem !important;
        }}

        .premium-commandbar {{
            margin-bottom: .72rem;
            padding: .68rem;
            border-radius: 16px;
        }}

        .premium-commandbar__context {{
            width: 100%;
        }}

        .premium-context-pill {{
            min-height: 34px;
        }}

        [data-testid="stTabs"] [data-baseweb="tab-list"] {{
            overflow-x: auto;
            flex-wrap: nowrap;
            -webkit-overflow-scrolling: touch;
        }}

        [data-testid="stTabs"] [data-baseweb="tab"] {{
            flex: 0 0 auto;
            min-height: 44px;
        }}

        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] > button,
        [data-testid="stPopover"] button {{
            min-height: 44px;
        }}
    }}

    @media (max-width: 430px) {{
        .premium-commandbar__context {{
            display: grid;
            grid-template-columns: 1fr 1fr;
        }}

        .premium-context-pill {{
            justify-content: center;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .premium-context-pill:first-child {{
            grid-column: 1 / -1;
        }}

        div[data-testid="stMetric"] {{
            min-height: 98px;
        }}
    }}

    @media (prefers-reduced-motion: reduce) {{
        *, *::before, *::after {{
            scroll-behavior: auto !important;
            transition-duration: .01ms !important;
            animation-duration: .01ms !important;
            animation-iteration-count: 1 !important;
        }}
    }}
    </style>
    """


def render_sidebar_identity(brand_image_url: str) -> None:
    """Render the compact product identity at the top of the sidebar."""

    st.sidebar.markdown(
        f"""
        <div class="premium-sidebar-brand">
            <img src="{html.escape(brand_image_url, quote=True)}" alt="DoobieLogic mark" />
            <div>
                <div class="premium-sidebar-brand__kicker">DOOBIELOGIC</div>
                <div class="premium-sidebar-brand__name">Operations Intelligence</div>
                <div class="premium-sidebar-brand__release">Commercial Ops · Jul 2026</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_commandbar(
    *,
    user_name: str,
    role: str,
    storage_connected: bool,
) -> None:
    """Render a small, responsive command bar above the active workspace."""

    storage_label = "Cloud connected" if storage_connected else "Local session"
    safe_user = html.escape(str(user_name or "Operator"))
    safe_role = html.escape(str(role or "trial").replace("_", " ").title())
    st.markdown(
        f"""
        <div class="premium-commandbar">
            <div class="premium-commandbar__identity">
                <div class="premium-commandbar__mark">DL</div>
                <div>
                    <div class="premium-commandbar__kicker">DOOBIELOGIC</div>
                    <div class="premium-commandbar__title">Cannabis Operations Cloud</div>
                </div>
            </div>
            <div class="premium-commandbar__context">
                <span class="premium-context-pill premium-context-pill--live">{storage_label}</span>
                <span class="premium-context-pill">{safe_role}</span>
                <span class="premium-context-pill">{safe_user}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
