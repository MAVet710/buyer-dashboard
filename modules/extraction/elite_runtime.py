"""Low-click competitive performance layer for durable Extraction Run 360.

This intentionally patches the additive Extraction ERP UI at import time instead
of rewriting the large legacy app. Run 360 stays the single operating surface.
"""

from __future__ import annotations

from typing import Any, MutableMapping

import pandas as pd
import streamlit as st

from modules.coman.db import create_coman_engine

from .analytics import ExtractionException
from .performance import ExtractionPerformanceService


_PATCHED = False
_EDIT_ROLES = frozenset({"dev", "admin", "planner", "supervisor", "operator", "qa"})


def _actor(state: MutableMapping[str, Any]) -> str:
    return str(
        state.get("auth_username")
        or state.get("auth_user_email")
        or state.get("display_user")
        or "operator"
    ).strip()


def _can_edit(state: MutableMapping[str, Any]) -> bool:
    return str(state.get("auth_user_role") or "read_only").strip().casefold() in _EDIT_ROLES


def _fmt_delta(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "No peer baseline"
    sign = "+" if float(value) > 0 else ""
    return f"{sign}{float(value):,.2f}{suffix}"


def _render_performance_intelligence(
    state: MutableMapping[str, Any],
    snapshot: dict[str, Any],
    organization_id: str,
    facility_id: str,
) -> None:
    run = snapshot["run"]
    try:
        service = ExtractionPerformanceService(create_coman_engine())
        metrics = service.run_metrics(organization_id, facility_id, run.id)
        benchmark = service.peer_benchmark(organization_id, facility_id, run.id)
    except Exception as exc:
        st.caption(f"Performance intelligence unavailable: {exc}")
        return

    st.markdown("#### Performance intelligence")
    st.caption("Deterministic economics + like-for-like peer benchmarking. AI is not the source of these numbers.")
    cards = st.columns(4)
    cards[0].metric("Projected output value", f"${metrics['projected_output_value']:,.0f}")
    cards[1].metric("Projected gross profit", f"${metrics['projected_gross_profit']:,.0f}")
    cards[2].metric("Projected margin", f"{metrics['projected_margin_pct']:,.1f}%")
    cards[3].metric("Cycle time", f"{metrics['cycle_hours']:,.1f} hr")

    peer_cards = st.columns(4)
    peer_cards[0].metric(
        "Yield vs peers",
        f"{metrics['yield_pct']:,.2f}%",
        delta=_fmt_delta(benchmark.get("yield_delta"), " pts"),
    )
    peer_cards[1].metric(
        "Cost / output",
        f"${metrics['cost_per_output']:,.4f}",
        delta=_fmt_delta(benchmark.get("cost_delta"), ""),
        delta_color="inverse",
    )
    peer_cards[2].metric("Solvent recovery", f"{metrics['solvent_recovery_pct']:,.1f}%")
    peer_cards[3].metric("Resource cost / output", f"${metrics['resource_cost_per_output']:,.4f}")

    if metrics["unmapped_outputs"]:
        missing = ", ".join(sorted(set(str(item) for item in metrics["unmapped_outputs"] if item)))
        st.warning(
            "Projected value is incomplete because these outputs do not have a current Product Master wholesale/retail value: "
            + missing
        )

    detail_col, resource_col = st.columns(2)
    with detail_col:
        with st.popover("Peer benchmark", use_container_width=True):
            peer_count = int(benchmark.get("peer_count") or 0)
            st.caption(f"Compared with {peer_count} recent run(s) using the same workflow template.")
            if peer_count <= 0:
                st.info("Complete more runs with this workflow to build a useful peer baseline.")
            else:
                summary = pd.DataFrame(
                    [
                        {
                            "Metric": "Yield %",
                            "This run": metrics["yield_pct"],
                            "Peer median": benchmark.get("yield_median"),
                            "Delta": benchmark.get("yield_delta"),
                        },
                        {
                            "Metric": "Cost / output",
                            "This run": metrics["cost_per_output"],
                            "Peer median": benchmark.get("cost_per_output_median"),
                            "Delta": benchmark.get("cost_delta"),
                        },
                        {
                            "Metric": "Cycle hours",
                            "This run": metrics["cycle_hours"],
                            "Peer median": benchmark.get("cycle_hours_median"),
                            "Delta": benchmark.get("cycle_delta"),
                        },
                        {
                            "Metric": "Solvent recovery %",
                            "This run": metrics["solvent_recovery_pct"],
                            "Peer median": benchmark.get("solvent_recovery_median"),
                            "Delta": benchmark.get("solvent_recovery_delta"),
                        },
                    ]
                )
                st.dataframe(summary, hide_index=True, width="stretch")
                p1, p2 = st.columns(2)
                yield_pctile = benchmark.get("yield_percentile")
                cost_pctile = benchmark.get("cost_percentile")
                p1.metric("Yield percentile", f"{float(yield_pctile):.0f}th" if yield_pctile is not None else "—")
                p2.metric("Cost-efficiency percentile", f"{float(cost_pctile):.0f}th" if cost_pctile is not None else "—")
                peers = list(benchmark.get("peers") or [])[:12]
                if peers:
                    frame = pd.DataFrame(peers)
                    columns = [
                        "batch_number",
                        "yield_pct",
                        "cost_per_output",
                        "cycle_hours",
                        "solvent_recovery_pct",
                        "projected_margin_pct",
                    ]
                    st.caption("Recent comparable runs")
                    st.dataframe(frame[[column for column in columns if column in frame.columns]], hide_index=True, width="stretch")

    with resource_col:
        with st.popover("Resources / solvent", use_container_width=True):
            if not service.resource_table_ready():
                st.info("Apply migration 0022_extraction_intel to enable the durable resource ledger.")
            else:
                events = service.list_resource_events(organization_id, facility_id, run.id)
                if events:
                    frame = pd.DataFrame(
                        [
                            {
                                "Time": event.occurred_at,
                                "Stage": event.stage_key,
                                "Type": event.resource_type,
                                "Resource": event.resource_name,
                                "Used": event.quantity,
                                "Recovered": event.recovered_quantity,
                                "Unit": event.unit,
                                "Cost": event.cost_usd,
                            }
                            for event in events
                        ]
                    )
                    st.dataframe(frame, hide_index=True, width="stretch")
                else:
                    st.caption("No resource usage has been recorded for this run yet.")

                if _can_edit(state):
                    st.divider()
                    resource_type = st.selectbox(
                        "Resource type",
                        ["solvent", "gas", "utility", "water", "consumable", "other"],
                        key=f"extract_resource_type_{run.id}",
                    )
                    resource_name = st.text_input("Resource", key=f"extract_resource_name_{run.id}")
                    c1, c2 = st.columns(2)
                    quantity = c1.number_input(
                        "Used",
                        min_value=0.0,
                        step=0.1,
                        key=f"extract_resource_qty_{run.id}",
                    )
                    unit = c2.text_input("Unit", value="g", key=f"extract_resource_unit_{run.id}")
                    recovered = st.number_input(
                        "Recovered (optional)",
                        min_value=0.0,
                        max_value=float(quantity) if quantity > 0 else 0.0,
                        value=0.0,
                        step=0.1,
                        key=f"extract_resource_recovered_{run.id}",
                    )
                    cost = st.number_input(
                        "Resource cost USD",
                        min_value=0.0,
                        step=1.0,
                        key=f"extract_resource_cost_{run.id}",
                    )
                    notes = st.text_input("Note", key=f"extract_resource_note_{run.id}")
                    if st.button(
                        "Record resource usage",
                        type="primary",
                        use_container_width=True,
                        key=f"extract_resource_submit_{run.id}",
                    ):
                        try:
                            service.record_resource_usage(
                                organization_id=organization_id,
                                facility_id=facility_id,
                                run_id=run.id,
                                stage_key=run.current_stage_key,
                                resource_type=resource_type,
                                resource_name=resource_name,
                                quantity=quantity,
                                unit=unit,
                                recovered_quantity=recovered if recovered > 0 else None,
                                cost_usd=cost,
                                notes=notes,
                                actor=_actor(state),
                            )
                        except Exception as exc:
                            st.error(str(exc))
                        else:
                            st.rerun()


def _performance_exceptions(board: pd.DataFrame, base_builder) -> list[ExtractionException]:
    existing = list(base_builder(board))
    if board is None or board.empty:
        return existing

    active = board[~board["Status"].isin(["Complete", "Cancelled", "Failed"])].copy()
    if active.empty:
        return existing

    added: list[ExtractionException] = []
    for method, group in active.groupby("Method", dropna=False):
        yield_values = pd.to_numeric(group["Yield %"], errors="coerce")
        yield_values = yield_values[yield_values > 0]
        cost_values = pd.to_numeric(group["Cost / Output"], errors="coerce")
        cost_values = cost_values[cost_values > 0]
        yield_median = float(yield_values.median()) if len(yield_values) >= 3 else None
        cost_median = float(cost_values.median()) if len(cost_values) >= 3 else None
        for _, row in group.iterrows():
            run_id = str(row.get("run_id") or "")
            batch = str(row.get("Run") or "Run")
            run_yield = float(row.get("Yield %") or 0.0)
            run_cost = float(row.get("Cost / Output") or 0.0)
            if yield_median and run_yield > 0 and run_yield < yield_median * 0.80:
                added.append(
                    ExtractionException(
                        severity="warning",
                        priority=58,
                        run_id=run_id,
                        batch_number=batch,
                        title=f"{batch}: yield is materially below peers",
                        detail=(
                            f"{run_yield:.2f}% yield vs {yield_median:.2f}% median for active {method} runs."
                        ),
                        action="Open Performance",
                    )
                )
            if cost_median and run_cost > cost_median * 1.25:
                added.append(
                    ExtractionException(
                        severity="review",
                        priority=52,
                        run_id=run_id,
                        batch_number=batch,
                        title=f"{batch}: cost per output is above peers",
                        detail=(
                            f"${run_cost:.4f} vs ${cost_median:.4f} median for active {method} runs."
                        ),
                        action="Open COGS",
                    )
                )
    return sorted(existing + added, key=lambda item: (-item.priority, item.batch_number, item.title))


def install_extraction_performance_ui() -> None:
    """Install Run 360 performance intelligence once per Python process."""

    global _PATCHED
    if _PATCHED:
        return
    import modules.extraction.ui as ui

    original_overview = ui._render_overview
    original_exceptions = ui.build_extraction_exceptions

    def overview_wrapper(state, snapshot, repository, organization_id, facility_id):
        original_overview(state, snapshot, repository, organization_id, facility_id)
        _render_performance_intelligence(state, snapshot, organization_id, facility_id)

    def exception_wrapper(board):
        return _performance_exceptions(board, original_exceptions)

    ui._render_overview = overview_wrapper
    ui.build_extraction_exceptions = exception_wrapper
    _PATCHED = True
