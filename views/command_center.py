import streamlit as st
import pandas as pd

from doobie_copilot import render_doobie_copilot
from doobie_panels import render_doobie_status, run_buyer_doobie, run_extraction_doobie
from ui.components import render_metric_card, render_section_header


def _safe_len(df) -> int:
    return int(len(df)) if isinstance(df, pd.DataFrame) else 0


def render_command_center():
    buyer_df = st.session_state.get("detail_product_cached_df")
    extraction_df = st.session_state.get("ecc_run_log")
    inv_df = st.session_state.get("inv_raw_df")
    sales_df = st.session_state.get("sales_raw_df")

    render_section_header(
        "Command Center",
        "Doobie-powered operations shell with a cleaner commercial layout. Manual uploads stay intact while sections migrate out of the legacy app.",
    )
    render_doobie_status()

    top = st.columns(4)
    with top[0]:
        render_metric_card("Inventory Rows", f"{_safe_len(inv_df):,}", "Current uploaded inventory rows")
    with top[1]:
        render_metric_card("Sales Rows", f"{_safe_len(sales_df):,}", "Current uploaded sales rows")
    with top[2]:
        render_metric_card("Buyer Rows", f"{_safe_len(buyer_df):,}", "Prepared buyer intelligence rows")
    with top[3]:
        render_metric_card("Extraction Runs", f"{_safe_len(extraction_df):,}", "Prepared extraction run rows")

    buyer_tab, extraction_tab, copilot_tab, migration_tab = st.tabs([
        "🧠 Buyer Brief",
        "🧪 Extraction Brief",
        "🛰️ Doobie Copilot",
        "🧱 Migration Status",
    ])

    with buyer_tab:
        render_section_header("Buyer Intelligence", "Routes only through DoobieLogic.")
        if buyer_df is None or getattr(buyer_df, "empty", True):
            st.info("No prepared buyer dataset found yet. Use the legacy Inventory Dashboard upload flow, then return here.")
        else:
            if st.button("Generate Buyer Brief", key="command_center_buyer_brief"):
                run_buyer_doobie(buyer_df, state="MA")
            st.dataframe(buyer_df.head(100), use_container_width=True, hide_index=True)

    with extraction_tab:
        render_section_header("Extraction Intelligence", "Routes only through DoobieLogic.")
        if extraction_df is None or getattr(extraction_df, "empty", True):
            st.info("No extraction run log loaded yet. Use the extraction workspace, then return here.")
        else:
            if st.button("Generate Extraction Brief", key="command_center_extraction_brief"):
                run_extraction_doobie(extraction_df, state="MA")
            st.dataframe(extraction_df.head(100), use_container_width=True, hide_index=True)

    with copilot_tab:
        render_section_header("Doobie Copilot", "Unified copilot with no direct OpenAI sidebar path.")
        render_doobie_copilot(
            app_mode="🛒 Buyer Operations",
            section="Command Center",
            buyer_payload=buyer_df.to_dict(orient="list") if isinstance(buyer_df, pd.DataFrame) else {},
            extraction_payload=extraction_df.to_dict(orient="list") if isinstance(extraction_df, pd.DataFrame) else {},
            state="MA",
        )

    with migration_tab:
        render_section_header("Migration Status", "Commercial-ready cleanup plan")
        st.markdown("""
- Legacy `app.py` still contains old AI paths and the full upload workflow.
- New modular shell is ready for Doobie-only routing.
- Next migration target should be Inventory Dashboard and PO Builder into dedicated modules.
- After that, retire old AI helper functions entirely and promote this shell to the default entrypoint.
""")
