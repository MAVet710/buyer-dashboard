"""Authenticated organization and facility context selector."""

import streamlit as st


def render_access_context(*, user_store, rerun) -> None:
    role = str(st.session_state.get("auth_user_role") or "trial")
    user_id = st.session_state.get("auth_user_id")
    assigned_org_id = st.session_state.get("auth_organization_id")
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Access Context")
    st.sidebar.caption(f"Role: {role.upper().replace('_', ' ')}")

    if role == "dev":
        st.sidebar.success("LEVEL DEV · Platform-wide access")
        organizations = user_store.list_organizations()
        sandbox_exists = any(item.slug == "dev-sandbox" for item in organizations)
        if not sandbox_exists:
            st.sidebar.caption("No DEV Sandbox exists yet.")
            if st.sidebar.button("Create DEV Sandbox", key="create_dev_sandbox", width="stretch"):
                try:
                    user_store.ensure_dev_sandbox()
                    st.sidebar.success("DEV Sandbox created.")
                    rerun()
                except Exception:
                    st.sidebar.error(
                        "DEV Sandbox could not connect to Supabase. Check the database secret, then try once."
                    )
        if not organizations:
            st.sidebar.warning("No organizations are available. Check the Supabase connection.")
            st.session_state.active_organization_id = None
            st.session_state.active_organization_name = ""
            st.session_state.active_facility_id = None
            st.session_state.active_facility_name = ""
            return
        # A legacy simulation tenant may remain in databases upgraded from the
        # original demo architecture.  Once the unified DEV Sandbox exists,
        # keep that duplicate out of the selector so there is one obvious,
        # complete place for product demonstrations and QA.
        visible_organizations = [
            item
            for item in organizations
            if not (
                sandbox_exists
                and item.slug == "doobielogic-demo-simulation"
            )
        ]
        organizations_by_label = {
            (
                "DEV Sandbox · Complete Demo"
                if item.slug == "dev-sandbox"
                else f"{item.name} ({item.slug})"
            ): item
            for item in visible_organizations
        }
        labels = list(organizations_by_label)
        current_org = st.session_state.get("active_organization_id")
        current_index = next(
            (index for index, label in enumerate(labels) if organizations_by_label[label].id == current_org),
            0,
        )
        org_label = st.sidebar.selectbox("Organization", labels, index=current_index, key="dev_org_context")
        selected_org = organizations_by_label[org_label]
        st.session_state.active_organization_id = selected_org.id
        st.session_state.active_organization_name = selected_org.name
        facilities = user_store.list_facilities(selected_org.id)
    else:
        st.session_state.active_organization_id = assigned_org_id
        if not assigned_org_id:
            st.sidebar.warning("This account is not assigned to an organization.")
            st.session_state.active_organization_name = ""
            st.session_state.active_facility_id = None
            st.session_state.active_facility_name = ""
            return
        organizations = {item.id: item for item in user_store.list_organizations(active_only=False)}
        assigned_org = organizations.get(assigned_org_id)
        st.session_state.active_organization_name = (
            assigned_org.name if assigned_org else "Assigned organization"
        )
        st.sidebar.info(assigned_org.name if assigned_org else "Assigned organization")
        facilities = user_store.list_facilities(
            assigned_org_id,
            user_id=user_id if role != "admin" else None,
        )

    if not facilities:
        st.sidebar.caption("No accessible facilities")
        st.session_state.active_facility_id = None
        st.session_state.active_facility_name = ""
        return
    facilities_by_label = {f"{item.name} ({item.code})": item for item in facilities}
    facility_labels = list(facilities_by_label)
    current_facility = st.session_state.get("active_facility_id")
    facility_index = next(
        (index for index, label in enumerate(facility_labels) if facilities_by_label[label].id == current_facility),
        0,
    )
    facility_label = st.sidebar.selectbox("Facility", facility_labels, index=facility_index, key="facility_context")
    selected_facility = facilities_by_label[facility_label]
    st.session_state.active_facility_id = selected_facility.id
    st.session_state.active_facility_name = selected_facility.name
    st.sidebar.caption(f"Timezone: {selected_facility.timezone_name}")
