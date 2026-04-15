import streamlit as st
from doobielogic_client_v2 import department_intelligence
from core.session_keys import BUYER_READY, EXTRACTION_RUNS, INV_RAW, SALES_RAW


def run_section(scope, question, payload):
    response, err = department_intelligence(scope, question, payload=payload)
    if err:
        st.error(err)
        return
    if response:
        st.markdown(response.get("answer", ""))
        recs = response.get("recommendations", [])
        if recs:
            st.markdown("#### Recommended Actions")
            for r in recs:
                st.write(f"- {r}")


def render_buyer_ai():
    df = st.session_state.get(BUYER_READY)
    if df is not None:
        run_section("buyer", "What should I reorder, watch, and markdown?", df.to_dict())


def render_extraction_ai():
    df = st.session_state.get(EXTRACTION_RUNS)
    if df is not None:
        run_section("extraction", "What process issues matter most?", df.to_dict())


def render_exec_ai():
    inv = st.session_state.get(INV_RAW)
    sales = st.session_state.get(SALES_RAW)
    payload = {
        "inventory": inv.to_dict() if inv is not None else {},
        "sales": sales.to_dict() if sales is not None else {},
    }
    run_section("executive", "Give me a top level business summary and risks", payload)
