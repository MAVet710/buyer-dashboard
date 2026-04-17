import streamlit as st

from doobie_settings import doobie_config_summary
from services.doobie_client import DoobieClient


def render_doobie_copilot(app_mode: str, section: str, buyer_payload=None, extraction_payload=None, state: str = "MA"):
    st.markdown("### 🛰️ Doobie Copilot Chat")
    cfg = doobie_config_summary()
    if not cfg["configured"]:
        st.caption("AI unavailable")
        return

    client = DoobieClient(base_url=cfg["url"], api_key=cfg["api_key"])
    if not client.enabled:
        st.caption("AI unavailable")
        return

    chat_key = f"doobie_chat_{section}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    st.caption("Doobie support layer only. Buyer Dashboard remains source of truth.")
    st.write(f"Mode: {app_mode} · Section: {section} · State: {state}")

    for msg in st.session_state[chat_key]:
        if msg["role"] == "user":
            st.markdown(f"**You:** {msg['text']}")
        else:
            st.markdown(f"**Doobie:** {msg['text']}")

    question = st.text_input(
        "Ask Doobie",
        key=f"doobie_copilot_question_{section}",
        placeholder="What should I focus on next in this section?",
    )

    in_flight_key = f"doobie_copilot_inflight_{section}"
    submit = st.button(
        "Submit to Copilot",
        key=f"run_doobie_copilot_{section}",
        disabled=bool(st.session_state.get(in_flight_key)),
    )
    if submit and question.strip():
        st.session_state[in_flight_key] = True
        try:
            with st.spinner("Doobie is thinking..."):
                context_data = {
                    "state": state,
                    "buyer": buyer_payload if isinstance(buyer_payload, dict) else {},
                    "extraction": extraction_payload if isinstance(extraction_payload, dict) else {},
                }
                result = client.copilot(question=question.strip(), data=context_data, persona="support")
            st.session_state[chat_key].append({"role": "user", "text": question.strip()})
            st.session_state[chat_key].append({"role": "assistant", "text": result.get("answer", "Doobie is currently unavailable.")})
            st.rerun()
        finally:
            st.session_state[in_flight_key] = False
