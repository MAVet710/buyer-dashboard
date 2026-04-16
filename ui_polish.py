import html
import streamlit as st


ACCENT = "#ff9a3c"
TEXT_SECONDARY = "rgba(255,255,255,0.72)"
CARD_BG = "rgba(14,14,14,0.72)"
CARD_BORDER = "rgba(255,255,255,0.08)"


def load_polished_theme(background_url: str) -> str:
    return f"""
    <style>
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
        box-shadow: 0 18px 60px rgba(0,0,0,0.30);
    }}

    .tile-card, .chart-card, .section-header-card {{
        background: {CARD_BG};
        border: 1px solid {CARD_BORDER};
        border-radius: 20px;
        backdrop-filter: blur(16px);
        box-shadow: 0 18px 50px rgba(0,0,0,0.28);
    }}

    .metric-tile {{
        padding: 1rem 1rem 0.95rem 1rem;
        min-height: 118px;
        transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
    }}

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
        color: {ACCENT};
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

    div[data-testid="stMetric"] {{
        background: {CARD_BG};
        border: 1px solid {CARD_BORDER};
        border-radius: 18px;
        padding: .8rem .95rem;
        backdrop-filter: blur(14px);
        box-shadow: 0 12px 40px rgba(0,0,0,0.24);
    }}
    </style>
    """


def render_section_header(title: str, subtitle: str = "", kicker: str = "DoobieLogic") -> None:
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
        with col:
            st.markdown(
                f"""
                <div class=\"tile-card metric-tile\">
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
