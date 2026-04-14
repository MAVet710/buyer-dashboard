import streamlit as st
from doobielogic_client import buyer_intelligence, extraction_intelligence
from doobie_settings import doobie_config_summary


def render_doobie_status():
    cfg = doobie_config_summary()
    if not cfg["configured"]:
        st.warning("DoobieLogic not configured. Add DOOBIELOGIC_URL in secrets.")
    else:
        st.success(f"DoobieLogic connected → {cfg['url']}")
        if not cfg["has_api_key"]:
            st.warning("API key missing — running in open mode (not secure)")


def run_buyer_doobie(by_product_df, state: str = "MA"):
    payload = by_product_df.to_dict(orient="list")

    response, err = buyer_intelligence(
        question="What should I reorder, watch, and markdown?",
        state=state,
        inventory_payload=payload,
    )

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


def run_extraction_doobie(run_df, state: str = "MA"):
    payload = run_df.to_dict(orient="list")

    response, err = extraction_intelligence(
        question="What process, chemistry, and release issues matter most?",
        state=state,
        run_payload=payload,
    )

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
