import streamlit as st

from doobie_learning_client import fetch_learning_summary
from ui.components import render_section_header, render_metric_card


def render_learning_view():
    render_section_header("Learning & Feedback", "Track how Doobie is improving over time")

    summary, err = fetch_learning_summary()

    if err:
        st.error(err)
        return

    if not summary:
        st.info("No learning data yet")
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        render_metric_card("Events", summary.get("event_count", 0))

    with col2:
        render_metric_card("Helpful", summary.get("helpful_count", 0))

    with col3:
        render_metric_card("Not Helpful", summary.get("not_helpful_count", 0))

    st.markdown("### Recent Feedback")
    for row in summary.get("recent", []):
        st.write(row)
