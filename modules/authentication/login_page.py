"""Branded, mobile-first entry experience for DoobieLogic."""

from __future__ import annotations

from dataclasses import dataclass
import html

import streamlit as st


@dataclass(frozen=True)
class LoginSubmission:
    """One explicit action from the authentication page."""

    action: str = ""
    username: str = ""
    password: str = ""
    trial_key: str = ""


def render_login_page(
    *,
    brand_image_url: str,
    storage_connected: bool,
    lockout_message: str = "",
    notice_message: str = "",
) -> LoginSubmission:
    """Render login in the main viewport so it works naturally on phones."""

    safe_mark = html.escape(str(brand_image_url or ""), quote=True)
    storage_label = "Secure cloud workspace available" if storage_connected else "Cloud storage needs configuration"
    storage_tone = "ready" if storage_connected else "attention"

    st.markdown(
        """
        <style>
        [data-testid="stSidebar"], [data-testid="collapsedControl"] { display: none !important; }
        [data-testid="stToolbar"], [data-testid="stDecoration"] { visibility: hidden !important; }
        .block-container { max-width: 1180px !important; padding-top: 2.2rem !important; }
        .dl-login-shell {
            display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(330px, .85fr);
            gap: 1.1rem; align-items: stretch; margin: clamp(.2rem, 3vh, 2rem) auto 1rem;
        }
        .dl-login-story, .dl-login-form-card {
            border: 1px solid var(--dl-border); border-radius: 24px;
            background: linear-gradient(145deg, var(--dl-surface-raised), var(--dl-surface));
            box-shadow: 0 24px 70px var(--dl-shadow); overflow: hidden;
        }
        .dl-login-story { position: relative; min-height: 540px; padding: clamp(2rem, 5vw, 4rem); }
        .dl-login-story::after {
            position: absolute; width: 360px; height: 360px; right: -150px; bottom: -170px;
            content: ""; border-radius: 50%;
            background: radial-gradient(circle, rgba(231,152,78,.24), transparent 68%);
        }
        .dl-login-brand { display: flex; align-items: center; gap: .85rem; margin-bottom: 3.6rem; }
        .dl-login-brand img { width: 48px; height: 48px; object-fit: cover; border-radius: 14px; }
        .dl-login-kicker { color: var(--dl-copper) !important; font-size: .68rem; font-weight: 850;
            letter-spacing: .18em; text-transform: uppercase; }
        .dl-login-brand-name { font-size: 1.05rem; font-weight: 780; }
        .dl-login-story h1 { max-width: 680px; margin: 0 0 1rem; font-size: clamp(2.15rem, 5vw, 4.25rem) !important; }
        .dl-login-story > p { max-width: 620px; color: var(--dl-text-soft) !important; font-size: 1rem; }
        .dl-login-points { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: .65rem; margin-top: 2.2rem; }
        .dl-login-point { padding: .8rem .9rem; border: 1px solid var(--dl-border); border-radius: 13px;
            background: var(--dl-surface-soft); font-size: .82rem; font-weight: 670; }
        .dl-login-form-card { padding: clamp(1.35rem, 3vw, 2.2rem); }
        .dl-login-form-card h2 { margin: .35rem 0 .25rem; }
        .dl-login-status { display: inline-flex; gap: .45rem; align-items: center; margin: .65rem 0 1.2rem;
            padding: .35rem .62rem; border: 1px solid var(--dl-border); border-radius: 999px;
            color: var(--dl-text-soft) !important; font-size: .72rem; font-weight: 700; }
        .dl-login-status::before { width: 7px; height: 7px; content: ""; border-radius: 50%; background: var(--dl-green); }
        .dl-login-status.attention::before { background: var(--dl-yellow); }
        .dl-login-help { margin-top: 1rem; color: var(--dl-text-faint) !important; font-size: .75rem; }
        @media (max-width: 820px) {
            .block-container { padding: .75rem .72rem 3rem !important; }
            .dl-login-shell { grid-template-columns: 1fr; margin-top: .25rem; }
            .dl-login-story { min-height: auto; padding: 1.4rem; }
            .dl-login-brand { margin-bottom: 1.8rem; }
            .dl-login-story h1 { font-size: 2.15rem !important; }
            .dl-login-points { grid-template-columns: 1fr 1fr; }
        }
        @media (max-width: 430px) {
            .dl-login-points { grid-template-columns: 1fr; }
            .dl-login-form-card { padding: 1rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    story, login = st.columns([1.15, .85], gap="medium")
    with story:
        st.markdown(
            f"""
            <section class="dl-login-story">
              <div class="dl-login-brand">
                <img src="{safe_mark}" alt="DoobieLogic mark" />
                <div><div class="dl-login-kicker">DOOBIELOGIC</div><div class="dl-login-brand-name">Operations Intelligence</div></div>
              </div>
              <h1>Run cannabis operations with clarity.</h1>
              <p>One secure workspace for retail inventory, purchasing, compliance, production, Co-Man execution, and commercial fulfillment.</p>
              <div class="dl-login-points">
                <div class="dl-login-point">Retail inventory intelligence</div>
                <div class="dl-login-point">Mobile inventory audits</div>
                <div class="dl-login-point">Co-Man capacity planning</div>
                <div class="dl-login-point">Executive-ready reporting</div>
              </div>
            </section>
            """,
            unsafe_allow_html=True,
        )

    action = LoginSubmission()
    with login:
        with st.container(border=True):
            st.markdown("## Welcome back")
            st.caption("Sign in to your company workspace.")
            st.markdown(
                f'<div class="dl-login-status {storage_tone}">{html.escape(storage_label)}</div>',
                unsafe_allow_html=True,
            )
            if lockout_message:
                st.error(lockout_message)
            elif notice_message:
                st.info(notice_message)
            with st.form("commercial_login_form", clear_on_submit=False):
                username = st.text_input("Username", key="unified_login_username")
                password = st.text_input("Password", type="password", key="unified_login_password")
                submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
            if submitted:
                action = LoginSubmission(
                    action="login",
                    username=str(username or "").strip(),
                    password=str(password or ""),
                )

            with st.expander("Have a trial key?", expanded=False):
                with st.form("commercial_trial_form", clear_on_submit=False):
                    trial_key = st.text_input("Trial key", type="password", key="trial_key_input")
                    trial_submitted = st.form_submit_button("Activate 24-hour trial", width="stretch")
                if trial_submitted:
                    action = LoginSubmission(action="trial", trial_key=str(trial_key or "").strip())

            st.markdown(
                '<div class="dl-login-help">Access is organization-scoped and activity is retained for operational accountability. Contact your company administrator if you need an account.</div>',
                unsafe_allow_html=True,
            )
    return action
