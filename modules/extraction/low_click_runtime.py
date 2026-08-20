"""Low-click Run 360 actions for routine extraction floor work.

Advanced process history stays in the Process tab. The Overview exposes the one
thing an operator does repeatedly: complete the current stage and advance.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, MutableMapping

import streamlit as st


def quick_stage_transition(workflow: Any, current_stage_key: str) -> tuple[str, str, str]:
    """Return current label, next key and next label for a routine completion."""
    current = str(current_stage_key or "").strip()
    current_label = workflow.stage_label(current)
    next_key = str(workflow.next_stage(current) or "").strip()
    next_label = workflow.stage_label(next_key) if next_key else ""
    return current_label, next_key, next_label


def _render_quick_stage_action(
    state: MutableMapping[str, Any],
    snapshot: dict[str, Any],
    repository: Any,
    organization_id: str,
    facility_id: str,
) -> None:
    from modules.extraction import ui

    run = snapshot["run"]
    if not ui._can_edit(state) or run.status not in {"planned", "queued", "active"}:
        return
    current_label, next_key, next_label = quick_stage_transition(
        snapshot["workflow"], run.current_stage_key
    )
    if not next_key:
        return

    st.markdown("#### Current work")
    st.caption(f"{current_label} → {next_label}")
    output_col, action_col = st.columns([1.35, 1])
    output_g = output_col.number_input(
        "Observed output (g)",
        min_value=0.0,
        value=0.0,
        step=0.1,
        key=f"extract_quick_output_{run.id}",
        help="Optional. Leave at 0 when this stage has no measured output.",
    )
    note_key = f"extract_quick_note_{run.id}"
    if hasattr(st, "popover"):
        with st.popover("Note / exception", use_container_width=True):
            st.text_area(
                "Operator note",
                key=note_key,
                height=80,
                placeholder="Optional note. Advanced measurements stay in Process.",
            )
    else:
        state.setdefault(note_key, "")

    with action_col:
        st.caption("Advance run")
        complete = st.button(
            f"Complete → {next_label}",
            type="primary",
            use_container_width=True,
            key=f"extract_quick_complete_{run.id}",
        )
    if not complete:
        return

    try:
        repository.record_stage_event(
            organization_id=organization_id,
            facility_id=facility_id,
            run_id=run.id,
            stage_key=run.current_stage_key,
            event_type="completed",
            actor=ui._actor(state),
            output_weight_g=float(output_g) if float(output_g) > 0 else None,
            notes=str(state.get(note_key) or "").strip(),
        )
    except Exception as exc:
        st.error(str(exc))
    else:
        state[note_key] = ""
        st.rerun()


def install_extraction_low_click_ui() -> None:
    """Add the floor action to Run 360 Overview exactly once."""
    from modules.extraction import ui

    original = ui._render_overview
    if getattr(original, "_low_click_wrapper", False):
        return

    @wraps(original)
    def low_click_overview(
        state: MutableMapping[str, Any],
        snapshot: dict[str, Any],
        repository: Any,
        organization_id: str,
        facility_id: str,
    ) -> None:
        _render_quick_stage_action(
            state,
            snapshot,
            repository,
            organization_id,
            facility_id,
        )
        original(
            state,
            snapshot,
            repository,
            organization_id,
            facility_id,
        )

    low_click_overview._low_click_wrapper = True
    ui._render_overview = low_click_overview
