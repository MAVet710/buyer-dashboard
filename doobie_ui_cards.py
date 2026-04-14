import streamlit as st


def render_card(title, value, subtitle=None):
    st.markdown(f"""
    <div style='padding:15px;border-radius:10px;background:#111;color:white;margin-bottom:10px'>
        <h4>{title}</h4>
        <h2>{value}</h2>
        <p>{subtitle or ''}</p>
    </div>
    """, unsafe_allow_html=True)


def render_recommendations(recs):
    st.markdown("### 🎯 Recommended Actions")
    for r in recs:
        st.markdown(f"- {r}")
