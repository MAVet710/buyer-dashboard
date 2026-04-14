import streamlit as st


def render_metric_card(title: str, value: str, subtitle: str = ""):
    st.markdown(
        f"""
        <div style='padding:16px;border-radius:14px;background:rgba(20,20,30,0.92);border:1px solid rgba(255,77,77,0.18);box-shadow:0 0 24px rgba(255,0,0,0.08);margin-bottom:10px'>
            <div style='font-size:0.85rem;opacity:0.8'>{title}</div>
            <div style='font-size:1.8rem;font-weight:700;color:#ffffff'>{value}</div>
            <div style='font-size:0.8rem;opacity:0.72'>{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(title: str, caption: str = ""):
    st.markdown(f"## {title}")
    if caption:
        st.caption(caption)


def render_status_pill(label: str, tone: str = "neutral"):
    palette = {
        "good": ("#113322", "#79ffb0"),
        "warn": ("#3a2b11", "#ffd166"),
        "bad": ("#3a1111", "#ff8a8a"),
        "neutral": ("#1e1e2a", "#d9d9e3"),
    }
    bg, fg = palette.get(tone, palette["neutral"])
    st.markdown(
        f"<span style='display:inline-block;padding:6px 10px;border-radius:999px;background:{bg};color:{fg};font-size:0.78rem;font-weight:600'>{label}</span>",
        unsafe_allow_html=True,
    )
