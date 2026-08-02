"""DEV and organization-admin user management UI."""

import pandas as pd
import streamlit as st


def render_admin_user_management(*, user_store, bcrypt_available, legacy_dev_users, legacy_admin_users, hash_password, rerun) -> None:
    st.markdown("### User Management")
    st.caption("Create and manage durable app accounts stored in PostgreSQL. Passwords are bcrypt-hashed before saving.")

    if not user_store.configured:
        st.warning(
            "Durable user storage is not configured for this deployment. Set COMAN_DATABASE_URL "
            "to the Supabase Session pooler connection string. Existing secrets-based login remains available."
        )
        return

    current_admin = str(st.session_state.get("admin_user") or "admin")
    current_role = str(st.session_state.get("auth_user_role") or "admin")
    is_dev = current_role == "dev"
    current_organization_id = st.session_state.get("auth_organization_id")
    legacy_hash = legacy_dev_users.get(current_admin) or legacy_admin_users.get(current_admin, "")
    if legacy_hash.startswith(("$2a$", "$2b$", "$2y$")):
        user_store.ensure_legacy_user(
            username=current_admin,
            password_hash=legacy_hash,
            role="dev" if current_admin in legacy_dev_users else "admin",
        )

    if is_dev:
        users = user_store.list_users()
    elif current_organization_id:
        users = [
            user
            for user in user_store.list_users(current_organization_id)
            if not user.is_dev
        ]
    else:
        st.warning(
            "This admin account is not assigned to an organization. Level DEV must assign it before it can manage users."
        )
        return
    if users:
        user_rows = [
            {
                "Username": user.username,
                "Display Name": user.display_name,
                "Email": user.email,
                "Role": user.role,
                "Active": user.active,
                "Organization ID": user.organization_id or "Unassigned",
                "Must Change Password": user.must_change_password,
                "Last Login": user.last_login_at,
                "Created": user.created_at,
            }
            for user in users
        ]
        st.dataframe(pd.DataFrame(user_rows), width="stretch", hide_index=True)
    else:
        st.info("No durable users exist yet. Create the first account below.")

    if is_dev:
        organizations = user_store.list_organizations()
        with st.expander("Platform Organizations & Facilities", expanded=not organizations):
            st.caption("Level DEV creates the company and facility records that scope every other account.")
            org_tab, facility_tab = st.tabs(["Add Organization", "Add Facility"])
            with org_tab:
                with st.form("dev_create_organization", clear_on_submit=True):
                    organization_name = st.text_input("Organization name")
                    organization_slug = st.text_input("Organization slug", help="For example: acme-cannabis")
                    add_organization = st.form_submit_button("Add Organization", type="primary")
                if add_organization:
                    try:
                        user_store.create_organization(name=organization_name, slug=organization_slug)
                        st.success("Organization created.")
                        rerun()
                    except Exception as exc:
                        st.error(f"Unable to create organization: {exc}")
            with facility_tab:
                if not organizations:
                    st.info("Create an organization first.")
                else:
                    organizations_by_name = {item.name: item for item in organizations}
                    with st.form("dev_create_facility", clear_on_submit=True):
                        facility_org_name = st.selectbox("Organization", sorted(organizations_by_name))
                        facility_name = st.text_input("Facility name")
                        facility_code = st.text_input("Facility code", help="Short unique code such as MAIN or MA01.")
                        facility_timezone = st.text_input("Timezone", value="America/New_York")
                        add_facility = st.form_submit_button("Add Facility", type="primary")
                    if add_facility:
                        try:
                            user_store.create_facility(
                                organization_id=organizations_by_name[facility_org_name].id,
                                name=facility_name,
                                code=facility_code,
                                timezone_name=facility_timezone,
                            )
                            st.success("Facility created.")
                            rerun()
                        except Exception as exc:
                            st.error(f"Unable to create facility: {exc}")

    create_tab, manage_tab = st.tabs(["Create User", "Manage Existing"])
    with create_tab:
        organization_options = {"Unassigned": None}
        if is_dev:
            organization_options.update(
                {item.name: item.id for item in user_store.list_organizations()}
            )
        elif st.session_state.get("auth_organization_id"):
            organization_options = {
                "Assigned organization": st.session_state.get("auth_organization_id")
            }
        organization_label = st.selectbox(
            "Organization",
            list(organization_options),
            key="admin_create_user_organization",
        )
        selected_create_organization_id = organization_options[organization_label]
        create_facilities = (
            user_store.list_facilities(selected_create_organization_id)
            if selected_create_organization_id
            else []
        )
        create_facility_options = {
            f"{facility.name} ({facility.code})": facility.id
            for facility in create_facilities
        }
        with st.form("admin_create_durable_user", clear_on_submit=True):
            c1, c2 = st.columns(2)
            username = c1.text_input("Username", help="Letters, numbers, periods, underscores, and hyphens.")
            display_name = c2.text_input("Display name")
            email = c1.text_input("Email (optional)")
            available_roles = ["buyer", "planner", "supervisor", "operator", "qa", "read_only", "admin"]
            if is_dev:
                available_roles.append("dev")
            role = c2.selectbox("Role", available_roles)
            create_facility_labels = st.multiselect(
                "Facility access",
                list(create_facility_options),
                default=list(create_facility_options),
                help="Selected facilities are the locations this user can open. Admins can access every facility in their organization.",
            )
            password = c1.text_input("Temporary password", type="password")
            password_confirm = c2.text_input("Confirm temporary password", type="password")
            must_change = st.checkbox("Require password change", value=True)
            create_user = st.form_submit_button("Create User", type="primary")

        if create_user:
            if len(password) < 12:
                st.error("Temporary passwords must contain at least 12 characters.")
            elif password != password_confirm:
                st.error("The password confirmation does not match.")
            elif role != "dev" and not selected_create_organization_id:
                st.error("Choose an organization for every non-DEV account.")
            elif not bcrypt_available:
                st.error("bcrypt is required before users can be created.")
            else:
                try:
                    user_store.create_user(
                        username=username,
                        password_hash=hash_password(password),
                        role=role,
                        organization_id=(
                            None if role == "dev" else selected_create_organization_id
                        ),
                        display_name=display_name,
                        email=email,
                        created_by=current_admin,
                        must_change_password=must_change,
                        facility_ids=(
                            []
                            if role == "dev"
                            else [create_facility_options[label] for label in create_facility_labels]
                        ),
                    )
                    st.success(f"User '{username}' created and stored securely.")
                    rerun()
                except Exception as exc:
                    st.error(f"Unable to create user: {exc}")

    with manage_tab:
        if not users:
            st.caption("Create a user before using account management actions.")
        else:
            users_by_name = {user.username: user for user in users}
            selected_username = st.selectbox("User", sorted(users_by_name), key="admin_manage_user")
            selected_user = users_by_name[selected_username]
            if selected_user.is_dev and not is_dev:
                st.error("Only Level DEV can manage a DEV account.")
                return

            st.markdown("#### Account Details & Access")
            st.caption(
                f"Account ID: {selected_user.id}  |  Created: {selected_user.created_at or 'Unknown'}  |  "
                f"Last login: {selected_user.last_login_at or 'Never'}"
            )
            profile_left, profile_right = st.columns(2)
            edit_username = profile_left.text_input(
                "Username",
                value=selected_user.username,
                key=f"admin_edit_username_{selected_user.id}",
            )
            edit_display_name = profile_right.text_input(
                "Display name",
                value=selected_user.display_name,
                key=f"admin_edit_display_name_{selected_user.id}",
            )
            edit_email = profile_left.text_input(
                "Email",
                value=selected_user.email,
                key=f"admin_edit_email_{selected_user.id}",
            )
            editable_roles = ["buyer", "planner", "supervisor", "operator", "qa", "read_only", "admin"]
            if is_dev:
                editable_roles.append("dev")
            edit_role = profile_right.selectbox(
                "Role",
                editable_roles,
                index=editable_roles.index(selected_user.role),
                key=f"admin_edit_role_{selected_user.id}",
            )

            if is_dev:
                editable_organizations = user_store.list_organizations(active_only=False)
                edit_organization_options = {"Unassigned / Platform-wide": None}
                edit_organization_options.update(
                    {
                        f"{organization.name} ({organization.slug})"
                        + ("" if organization.active else " - Inactive"): organization.id
                        for organization in editable_organizations
                    }
                )
                current_organization_label = next(
                    (
                        label
                        for label, organization_id in edit_organization_options.items()
                        if organization_id == selected_user.organization_id
                    ),
                    "Unassigned / Platform-wide",
                )
                edit_organization_label = st.selectbox(
                    "Organization",
                    list(edit_organization_options),
                    index=list(edit_organization_options).index(current_organization_label),
                    disabled=edit_role == "dev",
                    help="DEV accounts remain platform-wide. All other roles must belong to one organization.",
                    key=f"admin_edit_organization_{selected_user.id}",
                )
                edit_organization_id = (
                    None
                    if edit_role == "dev"
                    else edit_organization_options[edit_organization_label]
                )
            else:
                edit_organization_id = current_organization_id
                st.text_input(
                    "Organization",
                    value="Assigned organization",
                    disabled=True,
                    key=f"admin_edit_organization_locked_{selected_user.id}",
                )

            edit_facility_options: dict[str, str] = {}
            assigned_facility_labels: list[str] = []
            if edit_role != "dev" and edit_organization_id:
                available_facilities = user_store.list_facilities(
                    edit_organization_id,
                    active_only=False,
                )
                edit_facility_options = {
                    f"{facility.name} ({facility.code})"
                    + ("" if facility.active else " - Inactive"): facility.id
                    for facility in available_facilities
                }
                assigned_facility_ids = {
                    facility.id
                    for facility in user_store.list_facilities(
                        edit_organization_id,
                        user_id=selected_user.id,
                        active_only=False,
                    )
                }
                assigned_facility_labels = [
                    label
                    for label, facility_id in edit_facility_options.items()
                    if facility_id in assigned_facility_ids
                ]
            edit_facility_labels = st.multiselect(
                "Facility access",
                list(edit_facility_options),
                default=assigned_facility_labels,
                disabled=edit_role == "dev" or not edit_organization_id,
                help=(
                    "Standard users can open only selected facilities. Organization admins can open all company facilities. "
                    "No selections means the user has no facility workspace access."
                ),
                key=f"admin_edit_facilities_{selected_user.id}",
            )
            state_left, state_right = st.columns(2)
            desired_active = state_left.checkbox(
                "Account active",
                value=selected_user.active,
                key=f"admin_user_active_{selected_user.id}",
            )
            desired_must_change = state_right.checkbox(
                "Require password change at next login",
                value=selected_user.must_change_password,
                key=f"admin_user_must_change_{selected_user.id}",
            )

            if st.button(
                "Save all account changes",
                type="primary",
                width="stretch",
                key=f"admin_save_user_details_{selected_user.id}",
            ):
                is_current_account = (
                    selected_user.id == st.session_state.get("auth_user_id")
                    or selected_user.username == current_admin
                )
                if is_current_account and not desired_active:
                    st.error("You cannot deactivate the account currently signed in.")
                elif is_current_account and edit_role != selected_user.role:
                    st.error("You cannot change the role of the account currently signed in.")
                elif not is_dev and edit_organization_id != current_organization_id:
                    st.error("Company admins cannot move users outside their organization.")
                elif edit_role != "dev" and not edit_organization_id:
                    st.error("Choose an organization for every non-DEV account.")
                else:
                    try:
                        updated_user = user_store.update_user(
                            selected_user.id,
                            username=edit_username,
                            display_name=edit_display_name,
                            email=edit_email,
                            role=edit_role,
                            organization_id=edit_organization_id,
                            facility_ids=[
                                edit_facility_options[label]
                                for label in edit_facility_labels
                            ],
                            active=desired_active,
                            must_change_password=desired_must_change,
                            updated_by=current_admin,
                        )
                        if is_current_account:
                            st.session_state.admin_user = updated_user.username
                        st.success("All account details and access assignments were updated.")
                        rerun()
                    except Exception as exc:
                        st.error(f"Unable to update the account: {exc}")

            st.markdown("#### Reset Password")
            reset_password = st.text_input("New temporary password", type="password", key="admin_reset_password")
            reset_confirm = st.text_input("Confirm new password", type="password", key="admin_reset_confirm")
            if st.button("Reset password", key="admin_reset_password_btn"):
                if len(reset_password) < 12:
                    st.error("Temporary passwords must contain at least 12 characters.")
                elif reset_password != reset_confirm:
                    st.error("The password confirmation does not match.")
                elif user_store.reset_password(
                    selected_user.id, hash_password(reset_password), current_admin
                ):
                    st.success("Password reset. The user will be required to change it.")
                else:
                    st.error("Unable to reset the password.")
