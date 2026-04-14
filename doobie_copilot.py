import streamlit as st
from doobielogic_client import buyer_intelligence, extraction_intelligence
from doobie_settings import doobie_config_summary


def render_doobie_copilot(app_mode: str, section: str, buyer_payload=None, extraction_payload=None, state: str = "MA"):
    with st.sidebar.expander("🧠 Doobie Copilot", expanded=False):
        cfg = doobie_config_summary()
        if not cfg["configured"]:
            st.warning("DoobieLogic not configured. Add DOOBIELOGIC_URL in secrets.")
            return

        st.caption("Doobie-only copilot. Routes all questions through the DoobieLogic backend.")
        st.write(f"Mode: {app_mode}")
        st.write(f"Section: {section}")

        question = st.text_area(
            "Ask Doobie",
            value="What should I focus on next in this section?",
            key=f"doobie_copilot_question_{section}",
            height=100,
        )

        if st.button("Run Doobie Copilot", key=f"run_doobie_copilot_{section}"):
            with st.spinner("Thinking with DoobieLogic..."):
                if "Extraction" in app_mode or "Extraction" in section:
                    payload = extraction_payload if isinstance(extraction_payload, dict) else {}
                    result, err = extraction_intelligence(question=question, state=state, run_payload=payload)
                else:
                    payload = buyer_payload if isinstance(buyer_payload, dict) else {}
                    result, err = buyer_intelligence(question=question, state=state, inventory_payload=payload)

            if err:
                st.error(err)
            elif result:
                st.markdown(result.get("answer", ""))
                recs = result.get("recommendations", [])
                if recs:
                    st.markdown("#### Suggested next moves")
                    for rec in recs:
                        st.write(f"- {rec}")
