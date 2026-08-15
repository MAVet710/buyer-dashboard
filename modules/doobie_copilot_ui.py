"""Streamlit presentation for the shared Doobie sidebar copilot."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st


def render_doobie_sidebar_copilot(
    *,
    app_mode: str,
    section: str,
    provider_name: str,
    access_enabled: Callable[[], bool],
    status: Callable[[], str],
    refresh: Callable[[], Any],
    rerun: Callable[[], Any],
    run_copilot: Callable[..., str],
) -> None:
    """Render the stateful, multi-turn Doobie sidebar experience."""

    with st.sidebar.expander("🧠 Main AI Copilot", expanded=False):
        if not access_enabled():
            if status() == "waking_up":
                st.caption("Doobie AI is waking up. Retry in a moment.")
            else:
                st.caption("Connect Doobie AI to enable this feature.")
            if st.button("Retry Doobie Connection", key="retry_doobie_ai_status"):
                refresh()
                rerun()
            return
        st.caption("Use this assistant across buyer, compliance, and extraction workflows.")
        st.write(f"AI Provider: {provider_name}")
        st.write(f"Status: {status()}")

        history_key = "doobie_copilot_history"
        history = st.session_state.setdefault(history_key, [])
        if history:
            with st.expander("Recent conversation", expanded=False):
                for item in history[-8:]:
                    speaker = "You" if item.get("role") == "user" else "Doobie"
                    st.markdown(f"**{speaker}:** {item.get('content', '')}")

        if st.button("Refresh Doobie Status", key="refresh_doobie_ai_status"):
            refresh()
            rerun()

        question = st.text_area(
            "Ask the AI copilot",
            value="What should I focus on next in this section?",
            key="main_ai_copilot_question",
            height=100,
        )
        if st.button("Run Copilot", key="run_main_ai_copilot"):
            answer = run_copilot(question, app_mode, section, history=history)
            history.extend(
                [
                    {"role": "user", "content": str(question or "").strip()},
                    {"role": "assistant", "content": str(answer or "").strip()},
                ]
            )
            st.session_state[history_key] = history[-20:]
            st.markdown(answer)
        if st.button("Clear Doobie conversation", key="clear_main_ai_copilot_history"):
            st.session_state[history_key] = []
            rerun()
