"""Streamlit presentation for the shared AI sidebar copilot."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
import os

import streamlit as st

from services.gemini_agent import GeminiBuyerAgent, datasets_from_session


def _gemini_key() -> str:
    value = str(os.getenv("GEMINI_API_KEY") or "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get("GEMINI_API_KEY") or "").strip()
    except Exception:
        return ""


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
    """Render Buyer Agent with Gemini-first, Doobie fallback behavior."""

    gemini = GeminiBuyerAgent(api_key=_gemini_key())
    gemini_enabled = gemini.enabled
    doobie_enabled = access_enabled()

    with st.sidebar.expander("🧠 Buyer Agent", expanded=False):
        if not gemini_enabled and not doobie_enabled:
            st.caption("Buyer Agent needs a Gemini API key or a connected Doobie backend.")
            if status() == "waking_up":
                st.caption("Doobie AI is waking up. Retry in a moment.")
            if st.button("Retry AI Connection", key="retry_doobie_ai_status"):
                refresh()
                rerun()
            return

        active_provider = "Gemini (free-tier configured)" if gemini_enabled else provider_name
        active_status = "connected" if gemini_enabled else status()
        st.caption("Ask questions about the inventory and sales data already loaded in Buyer Dashboard.")
        st.write(f"AI Provider: {active_provider}")
        st.write(f"Status: {active_status}")
        if gemini_enabled:
            st.caption("Gemini tools are read-only. The agent cannot change inventory, place orders, or write to METRC/Dutchie.")

        history_key = "buyer_agent_history"
        history = st.session_state.setdefault(history_key, [])
        if history:
            with st.expander("Recent conversation", expanded=False):
                for item in history[-8:]:
                    speaker = "You" if item.get("role") == "user" else "Buyer Agent"
                    st.markdown(f"**{speaker}:** {item.get('content', '')}")

        if not gemini_enabled and st.button("Refresh Doobie Status", key="refresh_doobie_ai_status"):
            refresh()
            rerun()

        question = st.text_area(
            "Ask Buyer Agent",
            value="What should I focus on next in this section?",
            key="main_ai_copilot_question",
            height=100,
        )
        if st.button("Run Buyer Agent", key="run_main_ai_copilot"):
            try:
                if gemini_enabled:
                    datasets = datasets_from_session(st.session_state)
                    answer = gemini.run(question, datasets, app_mode=app_mode, section=section, history=history)
                else:
                    answer = run_copilot(question, app_mode, section, history=history)
            except Exception as exc:
                if doobie_enabled:
                    answer = run_copilot(question, app_mode, section, history=history)
                    st.caption(f"Gemini unavailable, used Doobie fallback: {exc}")
                else:
                    answer = f"Buyer Agent is temporarily unavailable: {exc}"
            history.extend(
                [
                    {"role": "user", "content": str(question or "").strip()},
                    {"role": "assistant", "content": str(answer or "").strip()},
                ]
            )
            st.session_state[history_key] = history[-20:]
            st.markdown(answer)
        if st.button("Clear Buyer Agent conversation", key="clear_main_ai_copilot_history"):
            st.session_state[history_key] = []
            rerun()
