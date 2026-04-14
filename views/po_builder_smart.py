import streamlit as st

from doobielogic_client import buyer_intelligence
from ui.components import render_section_header


def render_smart_po_builder(df):
    render_section_header("Smart PO Builder", "Auto-generate orders using Doobie recommendations")

    if df is None:
        st.warning("No buyer dataset available")
        return

    if st.button("Generate Smart PO"):
        result, err = buyer_intelligence(
            question="What should I reorder right now with quantities?",
            state="MA",
            inventory_payload=df.to_dict(orient="list"),
        )

        if err:
            st.error(err)
            return

        st.markdown(result.get("answer", ""))

        recs = result.get("recommendations", [])
        if recs:
            st.markdown("### Suggested Orders")
            for r in recs:
                st.write(f"- {r}")
