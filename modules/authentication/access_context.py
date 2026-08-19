"""Authenticated organization and facility context selector.

Tenant context is operational state, not navigation state. Keep it available in
the desktop sidebar and expose the same controls in the main column on narrow
screens so mobile users never depend on a collapsed Streamlit sidebar.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

import streamlit as st


# Session data that must never survive an organization/facility switch. Durable
# repositories repopulate these caches for the newly selected tenant.
_TENANT_CACHE_KEYS = {
    "inv_raw_df",
    "sales_raw_df",
    "extra_sales_df",
    "delivery_raw_df",
    "daily_sales_raw_df",
    "detail_cached_df",
    "detail_product_cached_df",
    "active_inventory_df",
    "active_sales_df",
    "compliance_sources_df",
    "ecc_inventory_log",
    "ecc_run_log",
    "ecc_client_jobs",
    "ecc_job_log",
    "quarantined_items",
    "_cache_inv",
    "_cache_sales",
    "_cache_extra_sales",
    "_cache_quarantine",
    "_durable_data_hub_scope",
    "_durable_data_hub_restored_scope",
    "_durable_data_hub_retry_after",
    "_durable_data_hub_error",
    "_sandbox_supabase_restored",
    "_sandbox_supabase_persisted",
    "_sandbox_supabase_source_count",
    "_sandbox_supabase_error",
    "_full_app_demo_version",
    "_full_app_demo_sections",
    "demo_data_banner",
    "demo_upload_catalog",
    "demo_company_profile",
    "demo_catalog_df",
    "demo_budget_df",
    "demo_commercial_partners_df",
    "demo_commercial_orders_df",
    "demo_commercial_order_lines_df",
    "demo_commercial_ledger_df",
    "demo_production_orders_df",
    "demo_production_machines_df",
    "demo_production_crew_df",
    "demo_nomenclature_catalog_df",
    "demo_nomenclature_manifest_df",
    "data_hub_import_history",
    "product_360_selected_name",
    "product_360_open",
    "product_360_po_seed",
}


def clear_tenant_cache(state: MutableMapping[str, Any]) -> None:
    """Drop tenant-scoped session cache before a context switch."""

    for key in _TENANT_CACHE_KEYS:
        state.pop(key, None)
    state.pop("_context_hydrated_scope", None)


def set_active_organization(state: MutableMapping[str, Any], organization: Any) -> bool:
    """Set the active organization and return True when its ID changed."""

    new_id = str(getattr(organization, "id", "") or "")
    current_id = str(state.get("active_organization_id") or "")
    changed = bool(current_id and current_id != new_id)
    if changed:
        clear_tenant_cache(state)
        state["active_facility_id"] = None
        state["active_facility_name"] = ""
    state["active_organization_id"] = getattr(organization, "id", None)
    state["active_organization_name"] = str(getattr(organization, "name", "") or "")
    return changed


def set_active_facility(state: MutableMapping[str, Any], facility: Any) -> bool:
    """Set the active facility and return True when its ID changed."""

    new_id = str(getattr(facility, "id", "") or "")
    current_id = str(state.get("active_facility_id") or "")
    changed = bool(current_id and current_id != new_id)
    if changed:
        clear_tenant_cache(state)
    state["active_facility_id"] = getattr(facility, "id", None)
    state["active_facility_name"] = str(getattr(facility, "name", "") or "")
    return changed


def hydrate_selected_context(
    state: MutableMapping[str, Any],
    *,
    organization: Any,
    facility: Any,
    role: str,
) -> tuple[bool, str]:
    """Hydrate durable tenant data once the organization/facility is known."""

    organization_id = str(getattr(organization, "id", "") or "")
    facility_id = str(getattr(facility, "id", "") or "")
    if not organization_id or not facility_id:
        return False, ""

    scope = f"{organization_id}|{facility_id}"
    is_sandbox = str(getattr(organization, "slug", "") or "").strip().casefold() == "dev-sandbox"

    # DEV Sandbox has 20+ linked datasets. Rebuild the whole living demo from
    # the durable Supabase source set, not only the four retail Data Hub caches.
    if is_sandbox:
        inventory = state.get("inv_raw_df")
        sales = state.get("sales_raw_df")
        has_inventory = bool(inventory is not None and not getattr(inventory, "empty", True))
        has_sales = bool(sales is not None and not getattr(sales, "empty", True))
        needs_hydration = (
            state.get("_context_hydrated_scope") != scope
            or not has_inventory
            or not has_sales
            or not state.get("_sandbox_supabase_restored")
        )
        if needs_hydration:
            try:
                from services.demo_data import ensure_full_app_demo_session

                actor = str(
                    state.get("admin_user")
                    or state.get("user_user")
                    or state.get("auth_user_id")
                    or role
                    or "system"
                )
                result = ensure_full_app_demo_session(state, actor=actor)
                state["_context_hydrated_scope"] = scope
                if result.seeded and state.get("_sandbox_supabase_restored"):
                    return True, "DEV Sandbox restored from Supabase."
                if result.seeded:
                    return True, "DEV Sandbox baseline loaded and persisted to Supabase."
            except Exception as exc:
                message = str(exc).strip() or "DEV Sandbox could not hydrate from Supabase."
                state["_sandbox_supabase_error"] = message
                return False, message
        return bool(state.get("_sandbox_supabase_restored") or has_inventory), ""

    # Real tenants use the normal active Data Hub source hydration path.
    if state.get("_context_hydrated_scope") != scope:
        try:
            from modules.data_hub import restore_durable_retail_sources

            _count, error = restore_durable_retail_sources(state, force=True)
            if error:
                return False, error
            state["_context_hydrated_scope"] = scope
        except Exception as exc:
            return False, str(exc).strip() or "Durable tenant data could not be restored."
    return True, ""


def _mobile_context_css() -> None:
    st.markdown(
        """
        <style>
        .st-key-mobile_access_context { display: none; }
        @media (max-width: 768px) {
          .st-key-mobile_access_context {
            display: block !important;
            margin: .15rem 0 .55rem !important;
            padding: .5rem .62rem .18rem !important;
            border: 1px solid rgba(255,255,255,.10) !important;
            border-radius: 14px !important;
            background: linear-gradient(145deg,rgba(24,28,25,.96),rgba(17,20,18,.94)) !important;
            box-shadow: 0 10px 30px rgba(0,0,0,.18) !important;
          }
          .st-key-mobile_access_context [data-testid="stExpander"] {
            border: 0 !important;
            background: transparent !important;
          }
          .st-key-mobile_access_context [data-testid="stExpander"] details summary {
            padding: .35rem .1rem !important;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_access_context(*, user_store, rerun) -> None:
    state = st.session_state
    role = str(state.get("auth_user_role") or "trial")
    user_id = state.get("auth_user_id")
    assigned_org_id = state.get("auth_organization_id")

    organizations = user_store.list_organizations(active_only=False)
    organizations_by_id = {str(item.id): item for item in organizations}

    if role == "dev":
        sandbox_exists = any(item.slug == "dev-sandbox" for item in organizations)
        if not sandbox_exists:
            try:
                user_store.ensure_dev_sandbox()
                organizations = user_store.list_organizations(active_only=False)
                organizations_by_id = {str(item.id): item for item in organizations}
                sandbox_exists = any(item.slug == "dev-sandbox" for item in organizations)
            except Exception:
                sandbox_exists = False

        visible_organizations = [
            item
            for item in organizations
            if not (sandbox_exists and item.slug == "doobielogic-demo-simulation")
        ]
        if not visible_organizations:
            st.sidebar.warning("No organizations are available. Check the Supabase connection.")
            return

        current_org_id = str(state.get("active_organization_id") or "")
        selected_org = next(
            (item for item in visible_organizations if str(item.id) == current_org_id),
            next(
                (item for item in visible_organizations if item.slug == "dev-sandbox"),
                visible_organizations[0],
            ),
        )
        set_active_organization(state, selected_org)
    else:
        if not assigned_org_id:
            st.sidebar.warning("This account is not assigned to an organization.")
            state["active_organization_id"] = None
            state["active_organization_name"] = ""
            state["active_facility_id"] = None
            state["active_facility_name"] = ""
            return
        selected_org = organizations_by_id.get(str(assigned_org_id))
        if selected_org is None:
            st.sidebar.warning("Your assigned organization could not be loaded.")
            return
        set_active_organization(state, selected_org)
        visible_organizations = [selected_org]

    facilities = user_store.list_facilities(
        selected_org.id,
        user_id=user_id if role not in {"dev", "admin"} else None,
    )
    if not facilities:
        st.sidebar.caption("No accessible facilities")
        state["active_facility_id"] = None
        state["active_facility_name"] = ""
        return

    current_facility_id = str(state.get("active_facility_id") or "")
    selected_facility = next(
        (item for item in facilities if str(item.id) == current_facility_id),
        next(
            (item for item in facilities if str(item.code).casefold() == "sandbox"),
            facilities[0],
        ),
    )
    set_active_facility(state, selected_facility)

    org_labels = {
        (
            "DEV Sandbox · Complete Demo"
            if item.slug == "dev-sandbox"
            else f"{item.name} ({item.slug})"
        ): item
        for item in visible_organizations
    }
    facility_labels = {f"{item.name} ({item.code})": item for item in facilities}
    active_org_label = next(
        label for label, item in org_labels.items() if str(item.id) == str(selected_org.id)
    )
    active_facility_label = next(
        label
        for label, item in facility_labels.items()
        if str(item.id) == str(selected_facility.id)
    )

    def sync_org(widget_key: str) -> None:
        label = str(state.get(widget_key) or "")
        item = org_labels.get(label)
        if item is not None:
            set_active_organization(state, item)
            state.pop("_context_hydrated_scope", None)

    def sync_facility(widget_key: str) -> None:
        label = str(state.get(widget_key) or "")
        item = facility_labels.get(label)
        if item is not None:
            set_active_facility(state, item)
            state.pop("_context_hydrated_scope", None)

    # Both desktop and mobile widget surfaces always mirror the actual tenant.
    for key in ("dev_org_context", "mobile_dev_org_context"):
        if role == "dev" and state.get(key) != active_org_label:
            state[key] = active_org_label
    for key in ("facility_context", "mobile_facility_context"):
        if state.get(key) != active_facility_label:
            state[key] = active_facility_label

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Workspace Context")
    st.sidebar.caption(f"Role: {role.upper().replace('_', ' ')}")
    if role == "dev":
        st.sidebar.selectbox(
            "Organization",
            list(org_labels),
            key="dev_org_context",
            on_change=sync_org,
            args=("dev_org_context",),
        )
    else:
        st.sidebar.info(selected_org.name)
    st.sidebar.selectbox(
        "Facility",
        list(facility_labels),
        key="facility_context",
        on_change=sync_facility,
        args=("facility_context",),
    )
    st.sidebar.caption(f"Timezone: {selected_facility.timezone_name}")

    # Main-column fallback for phones. CSS keeps this hidden on desktop while
    # the same active IDs continue driving all tenant-scoped queries.
    _mobile_context_css()
    with st.container(key="mobile_access_context"):
        with st.expander(
            f"{selected_org.name} · {selected_facility.name}",
            expanded=False,
        ):
            st.caption("ORGANIZATION / FACILITY")
            if role == "dev":
                st.selectbox(
                    "Organization",
                    list(org_labels),
                    key="mobile_dev_org_context",
                    on_change=sync_org,
                    args=("mobile_dev_org_context",),
                )
            else:
                st.info(selected_org.name)
            st.selectbox(
                "Facility",
                list(facility_labels),
                key="mobile_facility_context",
                on_change=sync_facility,
                args=("mobile_facility_context",),
            )

    hydrated, hydration_message = hydrate_selected_context(
        state,
        organization=selected_org,
        facility=selected_facility,
        role=role,
    )
    if hydration_message:
        if hydrated:
            st.sidebar.caption(hydration_message)
        else:
            st.sidebar.warning(hydration_message)
