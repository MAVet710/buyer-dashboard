"""Streamlit first-login policy acceptance gate."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from modules.legal_acceptance.policies import (
    CURRENT_PRIVACY_POLICY,
    CURRENT_TERMS_POLICY,
    PRIVACY_TEXT,
    STATEMENT_VERSION,
    TERMS_TEXT,
)
from services.legal_acceptance_store import LegalAcceptanceStore


ACCEPTANCE_STATEMENT = (
    "I have read and agree to the Terms of Service and acknowledge the Privacy Policy. "
    "I confirm that I am at least 21 years old and authorized to use DoobieLogic for my organization."
)


def render_legal_acceptance_gate(
    *,
    store: LegalAcceptanceStore,
    user_id: str | None,
    organization_id: str | None,
    role: str,
    rerun: Callable[[], None],
    sign_out: Callable[[], None],
    environment: str = "production",
) -> bool:
    """Return True when the authenticated user may enter the application."""

    clean_role = str(role or "").strip().casefold()
    if not user_id:
        if clean_role == "dev":
            st.warning(
                "Legal acceptance is not yet durable for this legacy DEV account. "
                "Connect it to the application user database before customer launch."
            )
            return True
        _render_blocked_state(
            "This account is not connected to durable user storage, so acceptance cannot be recorded.",
            sign_out,
        )
        return False

    if not store.available():
        if clean_role == "dev":
            st.warning(
                "The legal acceptance migration has not been applied. DEV access is temporarily "
                "allowed so the database can be configured; customer accounts remain fail-closed."
            )
            return True
        _render_blocked_state(
            "The agreement service is temporarily unavailable. Access remains paused because "
            "DoobieLogic cannot securely record acceptance.",
            sign_out,
        )
        return False

    if store.has_accepted(
        user_id=user_id,
        terms_version=CURRENT_TERMS_POLICY.version,
        privacy_version=CURRENT_PRIVACY_POLICY.version,
    ):
        return True

    st.title("Welcome to DoobieLogic")
    st.caption("Review the beta agreements before entering your operations workspace.")
    st.info(
        "DoobieLogic supports operational decisions for regulated cannabis businesses. "
        "Qualified personnel must review outputs before applying them to live systems."
    )
    terms_tab, privacy_tab = st.tabs(["Terms of Service", "Privacy Policy"])
    with terms_tab:
        st.markdown(TERMS_TEXT)
    with privacy_tab:
        st.markdown(PRIVACY_TEXT)

    key_suffix = f"{user_id}_{CURRENT_TERMS_POLICY.version}_{CURRENT_PRIVACY_POLICY.version}"
    accepted = st.checkbox(
        ACCEPTANCE_STATEMENT,
        key=f"legal_policy_acceptance_checkbox_{key_suffix}",
    )
    action_col, sign_out_col = st.columns([1.25, 1])
    with action_col:
        submit = st.button(
            "Accept and continue",
            type="primary",
            disabled=not accepted,
            key=f"legal_policy_acceptance_submit_{key_suffix}",
            width="stretch",
        )
    with sign_out_col:
        if st.button(
            "Sign out",
            key=f"legal_policy_acceptance_sign_out_{key_suffix}",
            width="stretch",
        ):
            sign_out()
            rerun()

    st.caption(
        "DoobieLogic is an operational tool, not legal or regulatory advice. Your organization "
        "remains responsible for verifying data and complying with applicable requirements."
    )

    if submit:
        try:
            ip_address, user_agent = _request_metadata()
            store.record_acceptance(
                user_id=user_id,
                organization_id=organization_id,
                terms=CURRENT_TERMS_POLICY,
                privacy=CURRENT_PRIVACY_POLICY,
                statement_version=STATEMENT_VERSION,
                acceptance_method="first_login",
                environment=environment,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            st.success("Agreement recorded securely.")
            rerun()
        except Exception:
            st.error(
                "We could not securely record your acceptance. Your account has not been changed. "
                "Please try again or contact support."
            )
    return False


def _render_blocked_state(message: str, sign_out: Callable[[], None]) -> None:
    st.title("Agreement unavailable")
    st.error(message)
    if st.button("Sign out", key="legal_policy_blocked_sign_out"):
        sign_out()


def _request_metadata() -> tuple[str, str]:
    try:
        headers = st.context.headers
        forwarded = str(headers.get("X-Forwarded-For", ""))
        ip_address = forwarded.split(",", 1)[0].strip()
        user_agent = str(headers.get("User-Agent", ""))
        return ip_address, user_agent
    except Exception:
        return "", ""

