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
    """Inject the approved Option-B chrome plus mobile tenant controls.

    This layer intentionally styles existing Streamlit widgets rather than
    replacing underlying business pages. It gives Buyer Dash the dense dark
    command-center feel from the approved mockup while preserving all routes,
    forms, tables, and data logic.
    """

    st.markdown(
        """
        <style>
        :root {
          --bdb-bg: #090909;
          --bdb-panel: #0f0f0f;
          --bdb-panel-2: #151310;
          --bdb-border: rgba(255,255,255,.08);
          --bdb-border-strong: rgba(255,255,255,.13);
          --bdb-text: #f6f5f2;
          --bdb-muted: #aaa49e;
          --bdb-dim: #77716c;
          --bdb-orange: #ff9a3c;
          --bdb-orange-soft: rgba(255,154,60,.12);
        }

        /* Overall desktop canvas from the approved Option B mockup. */
        .stApp {
          background:
            radial-gradient(circle at 82% -10%, rgba(255,154,60,.07), transparent 28rem),
            linear-gradient(145deg,#0b0b0b,#070707 62%) !important;
        }
        .block-container {
          width: min(100%, 1540px) !important;
          max-width: 1540px !important;
          padding: 1rem 1.25rem 4rem !important;
          background: transparent !important;
          border: 0 !important;
          border-radius: 0 !important;
          box-shadow: none !important;
        }

        /* Fixed dark rail like the reference. Tenant selector remains above nav. */
        [data-testid="stSidebar"] {
          width: 248px !important;
          background: linear-gradient(180deg,#0c0c0c,#090909) !important;
          border-right: 1px solid var(--bdb-border) !important;
          box-shadow: 18px 0 45px rgba(0,0,0,.24) !important;
        }
        [data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
          padding: .8rem .72rem 3rem !important;
        }
        [data-testid="stSidebar"] h3 {
          margin-top: .7rem !important;
          color: var(--bdb-muted) !important;
          font-size: .68rem !important;
          letter-spacing: .12em !important;
          text-transform: uppercase !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
          min-height: 38px !important;
          border-radius: 9px !important;
          background: #111 !important;
        }

        /* Reference-B page headings are simple, not giant glass cards. */
        .hero {
          margin: .2rem 0 .7rem !important;
          padding: .15rem .05rem .45rem !important;
          background: transparent !important;
          border: 0 !important;
          border-radius: 0 !important;
          box-shadow: none !important;
          backdrop-filter: none !important;
        }
        .hero h3 {
          font-size: clamp(1.85rem,3vw,2.45rem) !important;
          letter-spacing: -.045em !important;
        }
        .hero p {
          color: var(--bdb-muted) !important;
          font-size: .86rem !important;
        }
        .hero-user {
          padding: .3rem .55rem !important;
          border: 1px solid var(--bdb-border) !important;
          border-radius: 999px !important;
          background: #111 !important;
        }

        /* KPI cards: compact, dark, slightly raised. */
        div[data-testid="stMetric"] {
          position: relative !important;
          min-height: 102px !important;
          padding: .72rem .78rem .68rem !important;
          background: linear-gradient(145deg,#171512,#101010) !important;
          border: 1px solid var(--bdb-border) !important;
          border-radius: 13px !important;
          box-shadow: 0 10px 24px rgba(0,0,0,.17) !important;
          overflow: hidden !important;
        }
        div[data-testid="stMetric"]::before {
          content: "";
          position: absolute;
          left: 0;
          right: 0;
          top: 0;
          height: 3px;
          background: var(--bdb-orange);
          opacity: .92;
        }
        div[data-testid="stMetricLabel"] {
          color: var(--bdb-muted) !important;
          text-transform: uppercase !important;
          letter-spacing: .08em !important;
          font-size: .66rem !important;
          font-weight: 760 !important;
        }
        div[data-testid="stMetricValue"] {
          color: var(--bdb-text) !important;
          font-size: 1.55rem !important;
          font-weight: 820 !important;
        }

        /* Filters/actions read as one work strip instead of scattered widgets. */
        [data-testid="stForm"],
        .st-key-filter_bar,
        .st-key-action_bar {
          padding: .62rem .68rem !important;
          background: #0f0f0f !important;
          border: 1px solid var(--bdb-border) !important;
          border-radius: 12px !important;
          box-shadow: none !important;
        }
        [data-baseweb="input"] > div,
        [data-baseweb="select"] > div,
        [data-baseweb="textarea"] > div,
        [data-testid="stNumberInput"] > div > div,
        [data-testid="stDateInput"] > div > div {
          min-height: 40px !important;
          background: #101010 !important;
          border: 1px solid var(--bdb-border-strong) !important;
          border-radius: 9px !important;
          box-shadow: none !important;
        }
        [data-baseweb="input"] > div:focus-within,
        [data-baseweb="select"] > div:focus-within,
        [data-baseweb="textarea"] > div:focus-within {
          border-color: rgba(255,154,60,.66) !important;
          box-shadow: 0 0 0 3px rgba(255,154,60,.10) !important;
        }

        /* Dense operational table like the screenshot. */
        [data-testid="stDataFrame"],
        [data-testid="stDataEditor"] {
          background: #0e0e0e !important;
          border: 1px solid var(--bdb-border) !important;
          border-radius: 13px !important;
          box-shadow: 0 10px 28px rgba(0,0,0,.14) !important;
          overflow: hidden !important;
        }
        [data-testid="stDataFrame"] [role="columnheader"],
        [data-testid="stDataEditor"] [role="columnheader"] {
          background: #111 !important;
          color: var(--bdb-muted) !important;
          font-size: .72rem !important;
          font-weight: 760 !important;
        }

        /* Buttons use the compact controls from the mockup. */
        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] > button {
          min-height: 38px !important;
          padding: .4rem .72rem !important;
          border-radius: 9px !important;
          border: 1px solid var(--bdb-border-strong) !important;
          background: linear-gradient(180deg,#181818,#111) !important;
          box-shadow: none !important;
          font-size: .78rem !important;
          font-weight: 740 !important;
        }
        .stButton > button[kind="primary"],
        [data-testid="stFormSubmitButton"] > button[kind="primary"] {
          color: #1c1208 !important;
          background: linear-gradient(135deg,#ffb66e,#ff9a3c) !important;
          border-color: #ff9a3c !important;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover {
          transform: none !important;
          border-color: rgba(255,154,60,.52) !important;
          box-shadow: 0 0 0 3px rgba(255,154,60,.09) !important;
        }

        /* Work cards become true raised windows/panels. */
        .chart-card,
        .section-header-card,
        [data-testid="stExpander"] {
          background: linear-gradient(145deg,#131210,#0d0d0d) !important;
          border: 1px solid var(--bdb-border) !important;
          border-radius: 13px !important;
          box-shadow: 0 12px 30px rgba(0,0,0,.15) !important;
        }
        .chart-card {
          padding: .8rem .82rem .55rem !important;
          margin: .35rem 0 .75rem !important;
        }
        [data-testid="stTabs"] [data-baseweb="tab-list"] {
          gap: .2rem !important;
          border-bottom: 1px solid var(--bdb-border) !important;
        }
        [data-testid="stTabs"] [data-baseweb="tab"] {
          min-height: 38px !important;
          padding: .35rem .62rem !important;
          border-radius: 9px 9px 0 0 !important;
          font-size: .78rem !important;
        }

        /* Desktop Product 360 / action dialog resembles the screenshot's drawer. */
        body div[data-testid="stDialog"] {
          align-items: stretch !important;
          justify-content: flex-end !important;
          padding: 0 !important;
        }
        body div[data-testid="stDialog"] > div[role="dialog"] {
          position: fixed !important;
          top: 12px !important;
          right: 12px !important;
          bottom: 12px !important;
          left: auto !important;
          width: min(470px, 88vw) !important;
          max-width: 470px !important;
          height: calc(100dvh - 24px) !important;
          max-height: calc(100dvh - 24px) !important;
          margin: 0 !important;
          padding: .85rem .88rem 1.5rem !important;
          overflow-y: auto !important;
          border: 1px solid rgba(255,154,60,.20) !important;
          border-radius: 16px !important;
          background: linear-gradient(155deg,#171512,#0d0d0d) !important;
          box-shadow: -20px 20px 70px rgba(0,0,0,.54) !important;
        }

        /* Mobile tenant switcher: visible in main content, desktop stays sidebar-first. */
        .st-key-mobile_access_context { display: none; }

        @media (max-width: 768px) {
          [data-testid="stSidebar"] {
            width: min(86vw, 310px) !important;
          }
          .block-container {
            width: 100% !important;
            max-width: 100% !important;
            padding: .6rem .62rem 4.6rem !important;
          }
          .st-key-mobile_access_context {
            display: block !important;
            margin: .1rem 0 .5rem !important;
            padding: .45rem .58rem .16rem !important;
            border: 1px solid var(--bdb-border) !important;
            border-radius: 12px !important;
            background: linear-gradient(145deg,#151310,#0f0f0f) !important;
            box-shadow: 0 8px 24px rgba(0,0,0,.18) !important;
          }
          .st-key-mobile_access_context [data-testid="stExpander"] {
            border: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
          }
          .st-key-mobile_access_context [data-testid="stExpander"] details summary {
            padding: .3rem .05rem !important;
          }
          .hero {
            align-items: flex-start !important;
            gap: .4rem !important;
          }
          .hero-user { display: none !important; }
          div[data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: .5rem !important;
          }
          div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            min-width: min(100%, 150px) !important;
            flex: 1 1 150px !important;
          }
          div[data-testid="stMetric"] {
            min-height: 88px !important;
            padding: .58rem .62rem !important;
          }
          div[data-testid="stMetricValue"] {
            font-size: 1.28rem !important;
          }
          [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
            max-width: 100% !important;
            overflow-x: auto !important;
          }
          body div[data-testid="stDialog"] > div[role="dialog"] {
            top: 0 !important;
            right: 0 !important;
            bottom: 0 !important;
            width: 100vw !important;
            max-width: 100vw !important;
            height: 100dvh !important;
            max-height: 100dvh !important;
            padding: .68rem .65rem 4rem !important;
            border: 0 !important;
            border-radius: 0 !important;
          }
          h1 { font-size: clamp(1.7rem, 9vw, 2.2rem) !important; }
          h2 { font-size: clamp(1.3rem, 7vw, 1.72rem) !important; }
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
