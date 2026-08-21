import pandas as pd
import streamlit as st

from doobielogic_client import buyer_intelligence
from services.purchasing_context import purchasing_frame
from ui.components import render_section_header


def render_smart_po_builder(df=None):
    render_section_header("Smart PO Builder", "Auto-generate orders using Doobie recommendations")

    if not isinstance(df, pd.DataFrame) or df.empty:
        df = purchasing_frame(st.session_state)
    if not isinstance(df, pd.DataFrame) or df.empty:
        st.warning("No purchasing data is available for the active facility yet.")
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
