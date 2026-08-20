"""Install additive market-takeover surfaces before the legacy composition root imports them.

The runtime keeps the existing workspaces authoritative and adds low-click pop-out
entry points for migration, production execution, wholesale/finance, Doobie actions,
benchmarks, and design-partner administration.
"""

from __future__ import annotations

from functools import wraps
from typing import Any


def prepare_market_takeover_runtime(st: Any) -> None:
    if getattr(st, "_buyer_dash_market_runtime_installed", False):
        return
    st._buyer_dash_market_runtime_installed = True

    from modules.benchmarks.ui import render_benchmark_dialog
    from modules.coman.db import create_coman_engine
    from modules.commercial_finance.ui import render_wholesale_finance_dialog
    from modules.design_partners.ui import render_design_partner_dialog
    from modules.doobie_actions.ui import render_doobie_action_dialog
    from modules.migration_center.ui import render_switch_center_dialog
    from modules.production_erp.ui import render_production_control_dialog
    from services.operations_inbox_market import build_market_operations_inbox

    def _quick_actions() -> None:
        role = str(st.session_state.get("effective_role") or st.session_state.get("user_role") or "").casefold()
        cols = st.columns(6 if role in {"admin", "dev"} else 5)
        if cols[0].button("Switch", key="market_quick_switch", use_container_width=True, help="Migrate Dutchie, Distru, Metrc, or spreadsheets into Buyer Dash."):
            render_switch_center_dialog(st.session_state)
        if cols[1].button("Production", key="market_quick_production", use_container_width=True):
            render_production_control_dialog()
        if cols[2].button("Wholesale", key="market_quick_wholesale", use_container_width=True):
            render_wholesale_finance_dialog()
        if cols[3].button("Doobie Actions", key="market_quick_actions", use_container_width=True):
            render_doobie_action_dialog()
        if cols[4].button("Benchmarks", key="market_quick_benchmarks", use_container_width=True):
            render_benchmark_dialog()
        if role in {"admin", "dev"} and cols[5].button("Pilot", key="market_quick_pilot", use_container_width=True):
            render_design_partner_dialog()

    def _durable_inbox() -> None:
        organization_id = str(st.session_state.get("active_organization_id") or "").strip()
        facility_id = str(st.session_state.get("active_facility_id") or "").strip()
        if not organization_id or not facility_id:
            return
        try:
            items = build_market_operations_inbox(create_coman_engine(), organization_id, facility_id, limit=6)
        except Exception:
            return
        if not items:
            return
        st.markdown("#### Operating command center")
        st.caption("Ranked from durable operational state. Dollar impact is shown where Buyer Dash can trace it.")
        for index, item in enumerate(items):
            body, action = st.columns([5, 1.4])
            impact = f" · ${item.financial_impact:,.2f} at risk" if item.financial_impact > 0 else ""
            body.markdown(f"**{item.title}**  ")
            body.caption(f"{item.area} · {item.severity.upper()}{impact} · {item.detail}")
            if action.button(item.action_label, key=f"market_inbox_{index}_{item.key}", use_container_width=True, type="primary" if item.severity == "critical" else "secondary"):
                if item.key.startswith("market:migration:"):
                    render_switch_center_dialog(st.session_state)
                elif item.key.startswith("market:production:"):
                    render_production_control_dialog()
                elif item.key.startswith("market:finance:") or item.key.startswith("market:invoice-draft:"):
                    render_wholesale_finance_dialog()
                elif item.key.startswith("market:action:"):
                    render_doobie_action_dialog()
                elif item.key.startswith("market:extraction:"):
                    run_id = item.key.rsplit(":", 1)[-1]
                    from services.workspace_navigation import EXTRACTION_WORKSPACE, PRODUCTION_OPS, queue_workspace_navigation
                    st.session_state["extraction_selected_run_id"] = run_id
                    st.session_state["extraction_run_360_open"] = True
                    queue_workspace_navigation(st.session_state, group=PRODUCTION_OPS, workspace=EXTRACTION_WORKSPACE)
                    st.rerun()

    # Patch role Home before app.py imports the function reference.
    try:
        import modules.navigation.role_home as role_home
        original_home = role_home.render_role_home

        @wraps(original_home)
        def market_home(*args: Any, **kwargs: Any) -> Any:
            st.markdown("### Buyer Dash Command")
            _quick_actions()
            _durable_inbox()
            st.divider()
            return original_home(*args, **kwargs)

        role_home.render_role_home = market_home
    except Exception:
        pass

    # Data Hub gets a direct cutover pop-out without changing the existing guided imports.
    try:
        import modules.data_hub as data_hub
        original_data_hub = data_hub.render_data_hub_workspace

        @wraps(original_data_hub)
        def market_data_hub(*args: Any, **kwargs: Any) -> Any:
            c1, _ = st.columns([1.6, 4])
            if c1.button("Switch to Buyer Dash", type="primary", key="data_hub_switch_center", use_container_width=True):
                render_switch_center_dialog(st.session_state)
            return original_data_hub(*args, **kwargs)

        data_hub.render_data_hub_workspace = market_data_hub
    except Exception:
        pass

    # Existing production planner stays intact; execution opens in a contextual dialog.
    try:
        import modules.coman.ui as coman_ui
        original_coman = coman_ui.render_coman_workspace

        @wraps(original_coman)
        def market_coman(*args: Any, **kwargs: Any) -> Any:
            c1, _ = st.columns([1.4, 4])
            if c1.button("Production Control", type="primary", key="coman_production_control", use_container_width=True):
                render_production_control_dialog()
            return original_coman(*args, **kwargs)

        coman_ui.render_coman_workspace = market_coman
    except Exception:
        pass

    # Existing commercial order workflow stays intact; finance is a pop-out layer.
    try:
        import modules.commercial.ui as commercial_ui
        original_commercial = commercial_ui.render_commercial_workspace

        @wraps(original_commercial)
        def market_commercial(*args: Any, **kwargs: Any) -> Any:
            c1, _ = st.columns([1.5, 4])
            if c1.button("Wholesale + Finance", type="primary", key="commercial_finance_center", use_container_width=True):
                render_wholesale_finance_dialog()
            return original_commercial(*args, **kwargs)

        commercial_ui.render_commercial_workspace = market_commercial
    except Exception:
        pass
