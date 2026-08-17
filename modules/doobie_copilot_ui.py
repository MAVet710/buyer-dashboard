"""Streamlit presentation for the shared workspace AI agent surface."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
import os

import streamlit as st

from services.agent_registry import resolve_agent_profile
from services.gemini_agent import GeminiWorkspaceAgent, datasets_from_session


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
    """Render the specialist for the current workspace with Gemini-first fallback."""

    profile = resolve_agent_profile(app_mode, section)
    gemini = GeminiWorkspaceAgent(api_key=_gemini_key(), profile=profile)
    gemini_enabled = gemini.enabled
    doobie_enabled = access_enabled()

    with st.sidebar.expander(f"🧠 {profile.name}", expanded=False):
        if not gemini_enabled and not doobie_enabled:
            st.caption(f"{profile.name} needs a Gemini API key or a connected Doobie backend.")
            if status() == "waking_up":
                st.caption("Doobie AI is waking up. Retry in a moment.")
            if st.button("Retry AI Connection", key=f"retry_ai_status_{profile.key}"):
                refresh()
                rerun()
            return

        active_provider = "Gemini (free-tier configured)" if gemini_enabled else provider_name
        active_status = "connected" if gemini_enabled else status()
        st.caption(profile.description)
        st.write(f"AI Provider: {active_provider}")
        st.write(f"Status: {active_status}")
        st.caption("Mode: read-only analysis. This agent has no write, submit, inventory-adjustment, METRC, or Dutchie action tools.")

        history_key = f"workspace_agent_history_{profile.key}"
        history = st.session_state.setdefault(history_key, [])
        if history:
            with st.expander("Recent conversation", expanded=False):
                for item in history[-8:]:
                    speaker = "You" if item.get("role") == "user" else profile.name
                    st.markdown(f"**{speaker}:** {item.get('content', '')}")

        if not gemini_enabled and st.button("Refresh Doobie Status", key=f"refresh_doobie_ai_status_{profile.key}"):
            refresh()
            rerun()

        if profile.suggested_questions:
            st.caption("Try: " + " · ".join(profile.suggested_questions[:2]))
        default_question = profile.suggested_questions[0] if profile.suggested_questions else "What needs my attention?"
        question = st.text_area(
            f"Ask {profile.name}",
            value=default_question,
            key=f"workspace_agent_question_{profile.key}",
            height=100,
        )
        if st.button(f"Run {profile.name}", key=f"run_workspace_agent_{profile.key}"):
            try:
                if gemini_enabled:
                    datasets = datasets_from_session(
                        st.session_state,
                        app_mode=app_mode,
                        section=section,
                        profile=profile,
                    )
                    answer = gemini.run(
                        question,
                        datasets,
                        app_mode=app_mode,
                        section=section,
                        history=history,
                        profile=profile,
                    )
                else:
                    answer = run_copilot(question, app_mode, section, history=history)
            except Exception as exc:
                if doobie_enabled:
                    answer = run_copilot(question, app_mode, section, history=history)
                    st.caption(f"Gemini unavailable, used Doobie fallback: {exc}")
                else:
                    answer = f"{profile.name} is temporarily unavailable: {exc}"
            history.extend(
                [
                    {"role": "user", "content": str(question or "").strip()},
                    {"role": "assistant", "content": str(answer or "").strip()},
                ]
            )
            st.session_state[history_key] = history[-20:]
            st.markdown(answer)
        if st.button("Clear agent conversation", key=f"clear_workspace_agent_history_{profile.key}"):
            st.session_state[history_key] = []
            rerun()
