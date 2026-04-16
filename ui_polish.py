import html
import streamlit as st


ACCENT = "#ff9a3c"
TEXT_SECONDARY = "rgba(255,255,255,0.72)"
CARD_BG = "rgba(14,14,14,0.72)"
CARD_BORDER = "rgba(255,255,255,0.08)"
STATUS_COLORS = {
    "green": "#4cd388",
    "blue": "#5aa8ff",
    "yellow": "#f3c74c",
    "red": "#ff6161",
    "orange": "#ff9a3c",
}


def load_polished_theme(background_url: str) -> str:
    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    :root {{
        --accent: {ACCENT};
        --card-bg: {CARD_BG};
        --card-border: {CARD_BORDER};
        --text-secondary: {TEXT_SECONDARY};
        --green: #4cd388;
        --blue: #5aa8ff;
        --yellow: #f3c74c;
        --red: #ff6161;
        --orange: #ff9a3c;
    }}

    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
    }}

    .stApp {{
        background:
            linear-gradient(rgba(18,16,14,0.80), rgba(10,10,10,0.90)),
            url('{background_url}');
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}

    .block-container {{
        background: rgba(8,8,8,0.44) !important;
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 18px;
        box-shadow: 0 18px 60px rgba(0,0,0,0.30);
    }}

    .tile-card, .chart-card, .section-header-card {{
        background: var(--card-bg);
        border: 1px solid {CARD_BORDER};
        border-radius: 20px;
        backdrop-filter: blur(16px);
        box-shadow: 0 18px 50px rgba(0,0,0,0.28);
    }}

    .metric-tile {{
        position: relative;
        overflow: hidden;
        padding: 1rem 1rem 0.95rem 1rem;
        min-height: 118px;
        transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
    }}

    .metric-tile::before {{
        content: "";
        position: absolute;
        left: 0;
        right: 0;
        top: 0;
        height: 4px;
        background: var(--orange);
    }}
    .metric-tile.color-green::before {{ background: var(--green); }}
    .metric-tile.color-blue::before {{ background: var(--blue); }}
    .metric-tile.color-yellow::before {{ background: var(--yellow); }}
    .metric-tile.color-red::before {{ background: var(--red); }}
    .metric-tile.color-orange::before {{ background: var(--orange); }}

    .metric-tile:hover {{
        transform: translateY(-2px);
        border-color: rgba(255,154,60,0.32);
        box-shadow: 0 22px 56px rgba(0,0,0,0.34);
    }}

    .metric-label {{
        color: {TEXT_SECONDARY};
        text-transform: uppercase;
        letter-spacing: .12em;
        font-size: .72rem;
        font-weight: 700;
        margin-bottom: .45rem;
    }}

    .metric-value {{
        color: white;
        font-size: 1.95rem;
        font-weight: 800;
        line-height: 1.0;
        margin-bottom: .35rem;
    }}

    .metric-help {{
        color: rgba(255,255,255,0.62);
        font-size: .82rem;
        line-height: 1.25;
    }}

    .section-header-card {{
        padding: 1rem 1.15rem;
        margin: 0 0 1rem 0;
    }}

    .section-kicker {{
        color: var(--accent);
        text-transform: uppercase;
        letter-spacing: .16em;
        font-size: .72rem;
        font-weight: 800;
        margin-bottom: .3rem;
    }}

    .section-title {{
        color: white;
        font-size: 1.45rem;
        font-weight: 800;
        line-height: 1.05;
        margin-bottom: .2rem;
    }}

    .section-subtitle {{
        color: {TEXT_SECONDARY};
        font-size: .92rem;
        line-height: 1.35;
    }}

    .topbar {{
        display: grid;
        grid-template-columns: 1fr 130px auto auto;
        gap: 10px;
        align-items: center;
        margin: 0 0 14px 0;
    }}

    .search-shell, .pill-badge, .hero, .ai-brief, .ex-kpi {{
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: 16px;
        backdrop-filter: blur(16px);
        box-shadow: 0 12px 35px rgba(0,0,0,0.24);
    }}

    .search-shell {{
        min-height: 44px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 12px;
        font-size: .85rem;
        color: var(--text-secondary);
    }}

    .pill-badge {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 0.32rem 0.68rem;
        border-radius: 999px;
        font-weight: 700;
        font-size: .76rem;
        color: #fff;
    }}

    .action-button-chip {{
        border: none;
        border-radius: 12px;
        padding: 0.58rem 0.9rem;
        font-weight: 700;
        background: linear-gradient(135deg, rgba(255,154,60,.95), rgba(255,187,119,.92));
        color: #1b1308;
    }}

    .hero {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 1.1rem;
        margin: 0 0 14px 0;
    }}

    .hero h3 {{
        margin: 0;
        color: white;
        font-size: 1.35rem;
    }}

    .hero p {{
        margin: .2rem 0 0 0;
        color: var(--text-secondary);
        font-size: .9rem;
    }}

    .hero-user {{
        text-align: right;
    }}

    .hero-user strong {{
        display: block;
    }}

    .hero-user small {{
        color: var(--text-secondary);
    }}

    .chart-card {{
        padding: 1rem 1rem .6rem 1rem;
        margin: .35rem 0 1rem 0;
    }}

    .chart-title {{
        color: white;
        font-size: 1rem;
        font-weight: 700;
        margin-bottom: .15rem;
    }}

    .chart-subtitle {{
        color: {TEXT_SECONDARY};
        font-size: .82rem;
        margin-bottom: .65rem;
    }}

    .ai-brief {{
        padding: 1rem 1.1rem;
        margin: .45rem 0 1rem 0;
    }}

    .ai-brief h4 {{
        margin: 0 0 .5rem 0;
        font-size: 1rem;
    }}

    .ai-brief ul {{
        margin: .25rem 0 .65rem 1rem;
    }}

    .ai-brief li {{
        margin: .2rem 0;
        color: var(--text-secondary);
    }}

    .kpi-mini-grid {{
        display: grid;
        grid-template-columns: repeat(5, minmax(0,1fr));
        gap: 10px;
        margin-bottom: 10px;
    }}

    .ex-kpi {{
        padding: .72rem .8rem;
    }}

    .ex-kpi .label {{
        color: var(--text-secondary);
        font-size: .76rem;
    }}

    .ex-kpi .value {{
        font-weight: 800;
        margin-top: .15rem;
    }}

    .table-shell {{
        background: rgba(9,9,9,0.58);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 16px;
        padding: .35rem;
    }}

    .dataframe tbody tr td {{
        border-bottom: 1px solid rgba(255,255,255,0.06) !important;
    }}

    div[data-testid="stMetric"] {{
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: 18px;
        padding: .8rem .95rem;
        backdrop-filter: blur(14px);
        box-shadow: 0 12px 40px rgba(0,0,0,0.24);
    }}

    @media (max-width: 1200px) {{
        .topbar {{ grid-template-columns: 1fr; }}
        .kpi-mini-grid {{ grid-template-columns: repeat(2, minmax(0,1fr)); }}
    }}
    </style>
    """


def render_section_header(title: str, subtitle: str = "", kicker: str = "BUYER DASHBOARD") -> None:
    st.markdown(
        f"""
        <div class=\"section-header-card\">
            <div class=\"section-kicker\">{html.escape(kicker)}</div>
            <div class=\"section-title\">{html.escape(title)}</div>
            {f'<div class=\"section-subtitle\">{html.escape(subtitle)}</div>' if subtitle else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_tiles(metrics: list[dict]) -> None:
    if not metrics:
        return
    cols = st.columns(len(metrics))
    for col, metric in zip(cols, metrics):
        label = html.escape(str(metric.get("label", "")))
        value = html.escape(str(metric.get("value", "")))
        help_text = html.escape(str(metric.get("help", "")))
        color = str(metric.get("color", "orange")).lower()
        color_class = f"color-{color}" if color in STATUS_COLORS else "color-orange"
        with col:
            st.markdown(
                f"""
                <div class=\"tile-card metric-tile {color_class}\">
                    <div class=\"metric-label\">{label}</div>
                    <div class=\"metric-value\">{value}</div>
                    <div class=\"metric-help\">{help_text}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def chart_card_start(title: str, subtitle: str = "") -> None:
    st.markdown(
        f"""
        <div class=\"chart-card\">
            <div class=\"chart-title\">{html.escape(title)}</div>
            {f'<div class=\"chart-subtitle\">{html.escape(subtitle)}</div>' if subtitle else ''}
        """,
        unsafe_allow_html=True,
    )


def chart_card_end() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def render_topbar(search_placeholder: str, date_str: str) -> None:
    st.markdown(
        f"""
        <div class="topbar">
            <div class="search-shell">🔎 {html.escape(search_placeholder)} <span>⌘K</span></div>
            <div class="pill-badge">📅 {html.escape(date_str)}</div>
            <div class="pill-badge">🔔 Alerts</div>
            <div><button class="action-button-chip">Export Report</button></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_hero(greeting: str, subtitle: str, user_name: str, user_role: str) -> None:
    st.markdown(
        f"""
        <div class="hero">
            <div>
                <h3>{html.escape(greeting)}</h3>
                <p>{html.escape(subtitle)}</p>
            </div>
            <div class="hero-user">
                <strong>{html.escape(user_name)}</strong>
                <small>{html.escape(user_role)}</small>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_ai_brief(insights: list[str], actions: list[str]) -> None:
    insight_html = "".join(f"<li>{html.escape(item)}</li>" for item in insights)
    action_html = "".join(f"<span class='pill-badge' style='margin-right:6px'>{html.escape(item)}</span>" for item in actions)
    st.markdown(
        f"""
        <div class="ai-brief">
            <h4>🤖 AI Buyer Brief <small style="color:{TEXT_SECONDARY};font-weight:500;">Powered by Doobie</small></h4>
            <ul>{insight_html}</ul>
            <div>{action_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_nav_css() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            background: rgba(10,10,10,0.78) !important;
            border-right: 1px solid rgba(255,255,255,0.08);
        }
        [data-testid="stSidebar"] * {
            color: rgba(255,255,255,0.90) !important;
        }
        .sidebar-brand {
            display:flex;
            align-items:center;
            gap:8px;
            font-weight:800;
            margin-bottom:10px;
        }
        .sidebar-brand img {
            width:24px;
            height:24px;
            border-radius:6px;
        }
        .sidebar-nav-label {
            color: rgba(255,255,255,0.55);
            font-size: .72rem;
            letter-spacing: .12em;
            margin: .5rem 0 .2rem 0;
            font-weight: 800;
        }
        .sidebar-nav-item {
            border-radius: 14px;
            padding: .46rem .6rem;
            margin-bottom: .24rem;
            color: rgba(255,255,255,0.68);
            border: 1px solid transparent;
        }
        .sidebar-nav-item.active {
            background: linear-gradient(135deg, rgba(255,154,60,.95), rgba(255,187,119,.92));
            color: #1d1508 !important;
            font-weight: 800;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_pill_badge(text: str, color: str) -> None:
    safe = html.escape(text)
    c = STATUS_COLORS.get(str(color).lower(), STATUS_COLORS["orange"])
    st.markdown(
        f"<span class='pill-badge' style='background:{c};'>{safe}</span>",
        unsafe_allow_html=True,
    )


def render_action_button(label: str) -> None:
    st.markdown(
        f"<button class='action-button-chip'>{html.escape(label)}</button>",
        unsafe_allow_html=True,
    )


def render_extraction_kpi(metrics: list[dict]) -> None:
    cards = [
        (
            f"<div class='ex-kpi'><div class='label'>{html.escape(str(metric.get('label', '')))}</div>"
            f"<div class='value'>{html.escape(str(metric.get('value', '')))}</div></div>"
        )
        for metric in metrics
    ]
    st.markdown(f"<div class='kpi-mini-grid'>{''.join(cards)}</div>", unsafe_allow_html=True)


def render_inventory_table_css() -> None:
    st.markdown(
        """
        <style>
        .inv-priority-fresh { color: #4cd388; font-weight: 700; }
        .inv-priority-aging { color: #f3c74c; font-weight: 700; }
        .inv-priority-priorityrun { color: #ff9a3c; font-weight: 700; }
        .inv-priority-stale { color: #ff6161; font-weight: 700; }
        </style>
        """,
        unsafe_allow_html=True,
    )
