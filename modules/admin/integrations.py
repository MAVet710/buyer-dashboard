"""Role-aware METRC and platform integration administration UI."""

from datetime import datetime

import streamlit as st

from services.doobie_config import mask_api_key, test_doobie_connection
from services.metrc_client import get_default_metrc_integrator_key, test_metrc_connection
from services.workspace_navigation import can_manage_ai_integrations


def render_user_metrc_integrations_page(*, user_integrations_store, current_identity, resolve_metrc_integrator_key, rerun, save_user_integrations) -> None:
    """Render account-scoped METRC settings without exposing AI controls."""

    username, _ = current_identity()
    if not username:
        st.error("Sign in to manage your METRC integration.")
        return

    st.subheader("🔗 METRC Integrations")
    st.caption(
        "Connect the METRC account and licensed facility used by your workflows. "
        "These settings are stored for your app account only."
    )

    if not user_integrations_store.available:
        st.warning(
            "Durable integration storage is unavailable. Settings will remain in this "
            "session but may need to be entered again later."
        )

    integrator_key = resolve_metrc_integrator_key()
    with st.container(border=True):
        st.markdown("### METRC")
        st.caption(
            "The app performs a read-only facility check. Your METRC user key is "
            "masked after it is saved."
        )
        st.text_input(
            "METRC User API Key",
            value="",
            key="user_metrc_api_key_input",
            type="password",
            help="Leave blank to keep the currently saved key.",
        )
        st.text_input(
            "METRC State",
            value=str(st.session_state.get("metrc_state") or ""),
            key="user_metrc_state_input",
            placeholder="e.g., CA, MA, MI, or https://api-ca.metrc.com",
        )
        st.text_input(
            "METRC License / Facility",
            value=str(st.session_state.get("metrc_license") or ""),
            key="user_metrc_license_input",
            help="The license number the app should verify in METRC facilities.",
        )
        st.caption(
            f"Saved user key: "
            f"{mask_api_key(str(st.session_state.get('metrc_api_key') or '')) or '(not set)'}"
        )
        st.caption(
            f"Integrator key: "
            f"{'configured' if integrator_key else 'not configured by the DEV team'}"
        )
        st.caption(
            f"Status: **{st.session_state.get('user_metrc_status') or 'not_connected'}**"
        )
        st.caption(
            f"Last validated: "
            f"**{st.session_state.get('user_metrc_last_validated') or 'never'}**"
        )

        test_col, save_col, clear_col = st.columns(3)
        if test_col.button("Test Connection", key="user_metrc_test_btn"):
            state = str(st.session_state.get("user_metrc_state_input") or "").strip()
            license_name = str(
                st.session_state.get("user_metrc_license_input") or ""
            ).strip()
            api_key = str(
                st.session_state.get("user_metrc_api_key_input")
                or st.session_state.get("metrc_api_key")
                or ""
            ).strip()
            result = test_metrc_connection(
                state=state,
                user_api_key=api_key,
                integrator_api_key=integrator_key,
                license_number=license_name,
            )
            st.session_state.user_metrc_status = str(
                result.get("status") or "failed"
            )
            if result.get("ok"):
                st.session_state.user_metrc_last_validated = (
                    datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
                )
                st.success(
                    str(result.get("message") or "METRC connection succeeded.")
                )
                st.caption(
                    f"Facilities visible: {result.get('facility_count', 0)}"
                )
                if result.get("license_found") is False:
                    st.warning(
                        "The connection works, but this license was not found "
                        "for the supplied METRC user key."
                    )
            else:
                st.warning(
                    str(result.get("message") or "METRC connection test failed.")
                )

        if save_col.button(
            "Save",
            key="user_metrc_save_btn",
            type="primary",
        ):
            candidate_key = str(
                st.session_state.get("user_metrc_api_key_input") or ""
            ).strip()
            if candidate_key:
                st.session_state.metrc_api_key = candidate_key
            st.session_state.metrc_state = str(
                st.session_state.get("user_metrc_state_input") or ""
            ).strip()
            st.session_state.metrc_license = str(
                st.session_state.get("user_metrc_license_input") or ""
            ).strip()
            save_user_integrations()
            st.success("Your METRC settings were saved.")

        if clear_col.button("Clear / Reset", key="user_metrc_clear_btn"):
            st.session_state.metrc_api_key = ""
            st.session_state.metrc_state = ""
            st.session_state.metrc_license = ""
            st.session_state.user_metrc_status = "not_connected"
            st.session_state.user_metrc_last_validated = None
            st.session_state.user_metrc_api_key_input = ""
            st.session_state.user_metrc_state_input = ""
            st.session_state.user_metrc_license_input = ""
            save_user_integrations()
            st.success("Your METRC settings were cleared.")
            rerun()


def render_admin_integrations_page(*, user_integrations_store, current_identity, resolve_metrc_integrator_key, rerun, save_user_integrations, save_global_integrations) -> None:
    if not can_manage_ai_integrations(st.session_state.get("auth_user_role")):
        render_user_metrc_integrations_page(
            user_integrations_store=user_integrations_store,
            current_identity=current_identity,
            resolve_metrc_integrator_key=resolve_metrc_integrator_key,
            rerun=rerun,
            save_user_integrations=save_user_integrations,
        )
        return
    if not st.session_state.get("is_admin", False):
        st.error("Level DEV access is required.")
        return

    st.subheader("🧠 AI & METRC Integrations")
    st.caption("Level DEV platform credentials and connection settings.")

    if not st.session_state.get("_global_integrations_store_available"):
        st.warning("Global integrations persistence is unavailable in this environment.")

    last_by = str(st.session_state.get("global_integrations_updated_by") or "n/a")
    last_at = str(st.session_state.get("global_integrations_updated_at") or "n/a")
    st.caption(f"Last updated by: **{last_by}** • Updated at: **{last_at}**")

    admin_user = str(st.session_state.get("admin_user") or "admin")

    with st.container(border=True):
        st.markdown("### Doobie")
        st.caption("Shared default connection used when session override is not present.")
        st.text_input(
            "Doobie Base URL",
            value=str(st.session_state.get("global_doobie_base_url") or ""),
            key="admin_global_doobie_base_url_input",
            placeholder="https://doobie.yourdomain.com",
        )
        st.text_input(
            "Doobie Service API Key",
            value="",
            key="admin_global_doobie_api_key_input",
            type="password",
            help="Leave blank to keep the currently saved key.",
        )
        st.caption(
            f"Saved key: {mask_api_key(str(st.session_state.get('global_doobie_api_key') or '')) or '(not set)'}"
        )
        st.caption(f"Status: **{st.session_state.get('global_doobie_status') or 'not_connected'}**")
        st.caption(
            f"Last validated: **{st.session_state.get('global_doobie_last_validated') or 'never'}**"
        )

        col_test, col_save, col_clear = st.columns(3)
        if col_test.button("Test Connection", key="admin_global_doobie_test_btn"):
            candidate_url = str(st.session_state.get("admin_global_doobie_base_url_input") or "").strip()
            candidate_key = str(
                st.session_state.get("admin_global_doobie_api_key_input")
                or st.session_state.get("global_doobie_api_key")
                or ""
            ).strip()
            result = test_doobie_connection(candidate_url, candidate_key)
            st.session_state.global_doobie_status = str(result.get("status") or "not_connected")
            if result.get("ok"):
                st.session_state.global_doobie_last_validated = result.get("validated_at")
                st.success(str(result.get("message") or "Connected"))
            else:
                st.warning(str(result.get("message") or "Connection failed"))

        if col_save.button("Save", key="admin_global_doobie_save_btn", type="primary"):
            candidate_url = str(st.session_state.get("admin_global_doobie_base_url_input") or "").strip().rstrip("/")
            candidate_key = str(st.session_state.get("admin_global_doobie_api_key_input") or "").strip()
            st.session_state.global_doobie_base_url = candidate_url
            if candidate_key:
                st.session_state.global_doobie_api_key = candidate_key
            st.session_state.global_integrations_updated_by = admin_user
            st.session_state.global_integrations_updated_at = datetime.now().isoformat(timespec="seconds")
            if save_global_integrations(updated_by=admin_user):
                st.success("Doobie global settings saved.")
            else:
                st.error("Unable to save Doobie global settings.")

        if col_clear.button("Clear / Reset", key="admin_global_doobie_clear_btn"):
            st.session_state.global_doobie_base_url = ""
            st.session_state.global_doobie_api_key = ""
            st.session_state.global_doobie_status = "not_connected"
            st.session_state.global_doobie_last_validated = None
            st.session_state.admin_global_doobie_base_url_input = ""
            st.session_state.admin_global_doobie_api_key_input = ""
            st.session_state.global_integrations_updated_by = admin_user
            st.session_state.global_integrations_updated_at = datetime.now().isoformat(timespec="seconds")
            if save_global_integrations(updated_by=admin_user):
                st.success("Doobie global settings cleared.")
            else:
                st.error("Unable to clear Doobie global settings.")

    with st.container(border=True):
        st.markdown("### METRC")
        st.caption("Read-only connection test using Metrc Basic Auth. Configure the integrator key in secrets/env as METRC_INTEGRATOR_API_KEY.")
        st.text_input(
            "METRC User API Key",
            value="",
            key="admin_global_metrc_api_key_input",
            type="password",
            help="This is the user API key generated from the Metrc account. Leave blank to keep the currently saved key.",
        )
        st.text_input(
            "METRC State",
            value=str(st.session_state.get("global_metrc_state") or ""),
            key="admin_global_metrc_state_input",
            placeholder="e.g., CA, MA, MI, or https://api-ca.metrc.com",
        )
        st.text_input(
            "METRC License / Facility",
            value=str(st.session_state.get("global_metrc_license") or ""),
            key="admin_global_metrc_license_input",
            help="Optional but recommended. The connection test verifies whether this license appears in /facilities/v2/.",
        )
        _metrc_integrator_cfg = get_default_metrc_integrator_key()
        _metrc_integrator_key = str(_metrc_integrator_cfg.get("api_key") or "").strip()
        if not _metrc_integrator_key:
            try:
                _metrc_integrator_key = str(
                    st.secrets.get("METRC_INTEGRATOR_API_KEY")
                    or st.secrets.get("METRC_SOFTWARE_API_KEY")
                    or ""
                ).strip()
            except Exception:
                _metrc_integrator_key = ""
        st.caption(
            f"Saved user key: {mask_api_key(str(st.session_state.get('global_metrc_api_key') or '')) or '(not set)'}"
        )
        st.caption(
            f"Integrator key: {'configured' if _metrc_integrator_key else 'missing METRC_INTEGRATOR_API_KEY'}"
        )
        st.caption(f"Status: **{st.session_state.get('global_metrc_status') or 'not_connected'}**")
        st.caption(
            f"Last validated: **{st.session_state.get('global_metrc_last_validated') or 'never'}**"
        )

        m_test, m_save, m_clear = st.columns(3)
        if m_test.button("Test Connection", key="admin_global_metrc_test_btn"):
            state = str(st.session_state.get("admin_global_metrc_state_input") or "").strip()
            license_name = str(st.session_state.get("admin_global_metrc_license_input") or "").strip()
            api_key = str(
                st.session_state.get("admin_global_metrc_api_key_input")
                or st.session_state.get("global_metrc_api_key")
                or ""
            ).strip()
            result = test_metrc_connection(
                state=state,
                user_api_key=api_key,
                integrator_api_key=_metrc_integrator_key,
                license_number=license_name,
            )
            st.session_state.global_metrc_status = str(result.get("status") or "failed")
            if result.get("ok"):
                st.session_state.global_metrc_last_validated = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
                st.success(str(result.get("message") or "Metrc connection succeeded."))
                st.caption(f"Endpoint: {result.get('base_url')}/facilities/v2/")
                st.caption(f"Facilities visible: {result.get('facility_count', 0)}")
                if result.get("facilities_preview"):
                    st.caption("Preview: " + ", ".join(str(x) for x in result.get("facilities_preview", [])))
                if result.get("license_found") is False:
                    st.warning("Connection works, but that license number was not found for this Metrc user key.")
            else:
                st.warning(str(result.get("message") or "Metrc connection test failed."))
                if result.get("http_status"):
                    st.caption(f"HTTP status: {result.get('http_status')}")
                if result.get("base_url"):
                    st.caption(f"Endpoint: {result.get('base_url')}/facilities/v2/")

        if m_save.button("Save", key="admin_global_metrc_save_btn", type="primary"):
            candidate_key = str(st.session_state.get("admin_global_metrc_api_key_input") or "").strip()
            st.session_state.global_metrc_state = str(st.session_state.get("admin_global_metrc_state_input") or "").strip()
            st.session_state.global_metrc_license = str(st.session_state.get("admin_global_metrc_license_input") or "").strip()
            if candidate_key:
                st.session_state.global_metrc_api_key = candidate_key
            st.session_state.global_integrations_updated_by = admin_user
            st.session_state.global_integrations_updated_at = datetime.now().isoformat(timespec="seconds")
            if save_global_integrations(updated_by=admin_user):
                st.success("METRC global settings saved.")
            else:
                st.error("Unable to save METRC global settings.")

        if m_clear.button("Clear / Reset", key="admin_global_metrc_clear_btn"):
            st.session_state.global_metrc_api_key = ""
            st.session_state.global_metrc_state = ""
            st.session_state.global_metrc_license = ""
            st.session_state.global_metrc_status = "not_connected"
            st.session_state.global_metrc_last_validated = None
            st.session_state.admin_global_metrc_api_key_input = ""
            st.session_state.admin_global_metrc_state_input = ""
            st.session_state.admin_global_metrc_license_input = ""
            st.session_state.global_integrations_updated_by = admin_user
            st.session_state.global_integrations_updated_at = datetime.now().isoformat(timespec="seconds")
            if save_global_integrations(updated_by=admin_user):
                st.success("METRC global settings cleared.")
            else:
                st.error("Unable to clear METRC global settings.")
