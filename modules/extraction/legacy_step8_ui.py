"""Streamlit-only Step 8 controls for the legacy Extraction Command Center.

This module keeps the seven-tab legacy page intact while adding the same
method-specific workflow, formulation, stage-output and traceability concepts
used by the durable React/FastAPI extraction workspace.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from core.session_keys import EXTRACTION_RUNS
from modules.extraction.workflows import (
    TERPENE_HANDLING_MODES,
    calculate_final_output_g,
    calculate_terpene_weight_g,
    default_workflow_for_method,
    get_extraction_workflow,
    method_aware_stage_fields,
    workflows_for_method,
)

PROCESS_EVENTS_KEY = "ecc_process_events_v2"

_STAGE_FIELD_LABELS = {
    "extraction_output_g": "Extraction Output (g)",
    "purge_output_g": "Purge / Recovery Output (g)",
    "crystallization_output_g": "Crystallization Output (g)",
    "sauce_fraction_g": "Sauce Fraction (g)",
    "diamond_fraction_g": "Diamond Fraction (g)",
    "crude_output_g": "Crude Output (g)",
    "winterized_output_g": "Winterized Output (g)",
    "filtered_output_g": "Filtered Output (g)",
    "decarbed_output_g": "Decarbed Output (g)",
    "distillate_output_g": "Distillate Output (g)",
    "wash_output_g": "Wash Output (g)",
    "dried_hash_output_g": "Dried Hash Output (g)",
    "sift_output_g": "Sift Output (g)",
    "rosin_output_g": "Rosin Output (g)",
}


def _safe_method_workflows(method: str):
    candidates = workflows_for_method(method)
    if candidates:
        return candidates
    try:
        return (default_workflow_for_method(method),)
    except ValueError:
        return ()


def render_step8_run_fields(
    *,
    method: str,
    legacy_metrc_input: str,
    legacy_metrc_output: str,
    explicit_finished_output_g: float,
) -> dict[str, Any]:
    """Render additive Step 8 fields inside the existing Add Run Record form."""
    workflows = _safe_method_workflows(method)
    if not workflows:
        st.info("No method-specific workflow template is configured for this method yet.")
        return {"final_output_g": float(explicit_finished_output_g or 0.0)}

    workflow_labels = [workflow.label for workflow in workflows]
    selected_label = st.selectbox(
        "Workflow Template",
        workflow_labels,
        key=f"ecc_workflow_template_v2_{method}",
    )
    workflow = next((row for row in workflows if row.label == selected_label), workflows[0])

    st.caption("Method-aware workflow: " + " → ".join(
        f"{stage.label}{' (optional)' if stage.optional else ''}"
        for stage in workflow.stages
        if not stage.qa_gate and not stage.release_gate
    ))

    p1, p2, p3 = st.columns(3)
    with p1:
        intermediate_product_type = st.text_input(
            "Intermediate Product Type",
            key="ecc_intermediate_product_type_v2",
        )
        final_product_type = st.text_input(
            "Final Product Type",
            key="ecc_final_product_type_v2",
        )
    with p2:
        metrc_intermediate_package_id = st.text_input(
            "METRC Intermediate Package ID",
            key="ecc_metrc_intermediate_package_v2",
        )
        metrc_distillate_package_id = ""
        if method in {"Ethanol", "CO2"}:
            metrc_distillate_package_id = st.text_input(
                "METRC Distillate Package ID",
                key="ecc_metrc_distillate_package_v2",
            )
    with p3:
        metrc_formulation_package_id = ""
        if workflow.has_stage("formulation"):
            metrc_formulation_package_id = st.text_input(
                "METRC Formulation Package ID",
                key="ecc_metrc_formulation_package_v2",
            )
        st.text_input(
            "METRC Final Package ID",
            value=str(legacy_metrc_output or ""),
            key="ecc_metrc_final_package_display_v2",
            disabled=True,
            help="Uses the legacy METRC Package ID - Output field above so old workflows remain unchanged.",
        )

    stage_outputs: dict[str, float] = {}
    relevant_fields = method_aware_stage_fields(method)
    if relevant_fields:
        st.markdown("#### Method Stage Outputs")
        output_cols = st.columns(3)
        for index, field in enumerate(relevant_fields):
            with output_cols[index % 3]:
                stage_outputs[field] = st.number_input(
                    _STAGE_FIELD_LABELS.get(field, field.replace("_", " ").title()),
                    min_value=0.0,
                    step=0.1,
                    key=f"ecc_stage_output_{field}_v2",
                )

    formulation_used = False
    formulation_base_g = 0.0
    terpene_handling_mode = "Native / No Add-Back"
    terpene_type = ""
    terpene_source = ""
    terpene_percentage = 0.0
    terpene_weight_override = 0.0
    terpene_weight_g = 0.0

    if workflow.has_stage("formulation"):
        formulation_used = st.checkbox("Formulation Used", key="ecc_formulation_used_v2")
        if formulation_used:
            f1, f2, f3 = st.columns(3)
            with f1:
                formulation_base_g = st.number_input(
                    "Formulation Base (g)",
                    min_value=0.0,
                    step=0.1,
                    key="ecc_formulation_base_g_v2",
                )
            with f2:
                terpene_handling_mode = st.selectbox(
                    "Terpene Handling",
                    list(TERPENE_HANDLING_MODES),
                    key="ecc_terpene_handling_v2",
                )
            if terpene_handling_mode != "Native / No Add-Back":
                with f3:
                    terpene_type = st.text_input("Terpene Type", key="ecc_terpene_type_v2")
                f4, f5, f6 = st.columns(3)
                with f4:
                    terpene_source = st.text_input("Terpene Source", key="ecc_terpene_source_v2")
                with f5:
                    terpene_percentage = st.number_input(
                        "Terpene %",
                        min_value=0.0,
                        max_value=20.0,
                        step=0.1,
                        key="ecc_terpene_pct_v2",
                    )
                with f6:
                    terpene_weight_override = st.number_input(
                        "Terpene Weight Override (g)",
                        min_value=0.0,
                        step=0.1,
                        key="ecc_terpene_weight_override_v2",
                        help="Leave at 0 to calculate from formulation base × terpene percentage.",
                    )
                terpene_weight_g = calculate_terpene_weight_g(
                    formulation_base_g,
                    terpene_percentage,
                    terpene_weight_override if terpene_weight_override > 0 else None,
                )
                st.caption(f"Calculated terpene addition: {terpene_weight_g:,.3f} g")

    final_output_g = calculate_final_output_g(
        workflow.key,
        stage_outputs,
        formulation_used=formulation_used,
        formulation_base_g=formulation_base_g,
        terpene_weight_g=terpene_weight_g,
        explicit_finished_output_g=explicit_finished_output_g,
    )
    st.info(
        f"Step 8 final-output preview: {final_output_g:,.3f} g"
        + (" · manual Finished Output override" if explicit_finished_output_g > 0 else "")
    )

    return {
        "workflow_template": workflow.key,
        "intermediate_product_type": intermediate_product_type,
        "final_product_type": final_product_type,
        "metrc_input_package_id": str(legacy_metrc_input or ""),
        "metrc_intermediate_package_id": metrc_intermediate_package_id,
        "metrc_distillate_package_id": metrc_distillate_package_id,
        "metrc_formulation_package_id": metrc_formulation_package_id,
        "metrc_final_package_id": str(legacy_metrc_output or ""),
        "formulation_used": formulation_used,
        "formulation_base_g": formulation_base_g,
        "terpene_handling_mode": terpene_handling_mode,
        "terpene_type": terpene_type,
        "terpene_source": terpene_source,
        "terpene_percentage": terpene_percentage,
        "terpene_weight_g": terpene_weight_g,
        "final_output_g": final_output_g,
        **stage_outputs,
    }


def _events_frame() -> pd.DataFrame:
    value = st.session_state.get(PROCESS_EVENTS_KEY)
    if isinstance(value, pd.DataFrame):
        return value.copy()
    return pd.DataFrame(
        columns=[
            "run_index",
            "batch_id_internal",
            "workflow_template",
            "stage_key",
            "stage_label",
            "event_type",
            "stage_output_field",
            "input_weight_g",
            "output_weight_g",
            "loss_weight_g",
            "loss_reason",
            "metrc_stage_input_id",
            "metrc_stage_output_id",
            "intermediate_product_type",
            "final_product_type",
            "operator",
            "notes",
            "occurred_at",
        ]
    )


def _latest_stage_measurements(events: pd.DataFrame, run_index: int) -> dict[str, float]:
    if events.empty:
        return {}
    scoped = events[events["run_index"].astype(str) == str(run_index)].copy()
    if scoped.empty:
        return {}
    result: dict[str, float] = {}
    for _, row in scoped.iterrows():
        output = pd.to_numeric(row.get("output_weight_g"), errors="coerce")
        if pd.notna(output) and float(output) > 0:
            stage_key = str(row.get("stage_key") or "")
            if stage_key:
                result[stage_key] = float(output)
        field = str(row.get("stage_output_field") or "")
        if field and pd.notna(output) and float(output) > 0:
            result[field] = float(output)
    return result


def render_legacy_process_tracker(run_df: pd.DataFrame) -> None:
    """Render the Process Tracker inside the existing Run Analytics tab."""
    st.markdown("### Process Tracker")
    st.caption("Stage-by-stage legacy tracker. The DoobieLogic Run 360 tracker is the durable production record.")
    if run_df is None or run_df.empty:
        st.info("Add a run before recording process-stage events.")
        return

    labels = []
    for index, row in run_df.iterrows():
        batch = str(row.get("batch_id_internal") or "").strip() or f"Run {index + 1}"
        method = str(row.get("method") or "")
        labels.append((index, f"{batch} · {method}"))
    label_to_index = {label: index for index, label in labels}
    selected_label = st.selectbox("Process Tracker Run", list(label_to_index), key="ecc_process_run_v2")
    run_index = label_to_index[selected_label]
    row = run_df.loc[run_index]
    method = str(row.get("method") or "BHO")

    workflow_key = str(row.get("workflow_template") or "").strip()
    try:
        workflow = get_extraction_workflow(workflow_key) if workflow_key else default_workflow_for_method(method)
    except ValueError:
        st.warning("This run does not have a valid method workflow template yet.")
        return

    show_optional = st.checkbox("Show Optional Workflow Stages", value=True, key="ecc_process_optional_v2")
    stages = [stage for stage in workflow.stages if not stage.qa_gate and not stage.release_gate and (show_optional or not stage.optional)]
    stage_labels = [f"{stage.label}{' (optional)' if stage.optional else ''}" for stage in stages]
    selected_stage_label = st.selectbox("Process Stage", stage_labels, key="ecc_process_stage_v2")
    stage = stages[stage_labels.index(selected_stage_label)]

    events = _events_frame()
    scoped_events = events[events["run_index"].astype(str) == str(run_index)] if not events.empty else events
    if not scoped_events.empty:
        st.dataframe(scoped_events.drop(columns=["run_index"], errors="ignore"), use_container_width=True, hide_index=True)
    else:
        st.info("No process events recorded for this run yet.")

    e1, e2, e3 = st.columns(3)
    with e1:
        event_type = st.selectbox(
            "Event Type",
            ["measurement", "completed", "started", "note", "deviation", "hold", "released"],
            key="ecc_process_event_type_v2",
        )
        input_weight_g = st.number_input("Stage Input (g)", min_value=0.0, step=0.1, key="ecc_process_input_g_v2")
        output_weight_g = st.number_input("Stage Output (g)", min_value=0.0, step=0.1, key="ecc_process_output_g_v2")
    with e2:
        loss_weight_g = st.number_input("Stage Loss (g)", min_value=0.0, step=0.1, key="ecc_process_loss_g_v2")
        loss_reason = st.text_input("Loss / Deviation Reason", key="ecc_process_loss_reason_v2")
        operator = st.text_input("Stage Operator", value=str(row.get("operator") or ""), key="ecc_process_operator_v2")
    with e3:
        metrc_stage_input_id = st.text_input("METRC Stage Input ID", key="ecc_process_metrc_input_v2")
        metrc_stage_output_id = st.text_input("METRC Stage Output ID", key="ecc_process_metrc_output_v2")
        notes = st.text_area("Stage Notes", key="ecc_process_notes_v2")

    stage_output_field = ""
    if stage.output_fields:
        stage_output_field = st.selectbox(
            "Stage Output Field",
            list(stage.output_fields),
            format_func=lambda value: _STAGE_FIELD_LABELS.get(value, value.replace("_", " ").title()),
            key="ecc_process_output_field_v2",
        )

    p1, p2 = st.columns(2)
    with p1:
        intermediate_product_type = st.text_input(
            "Tracker Intermediate Product Type",
            value=str(row.get("intermediate_product_type") or ""),
            key="ecc_process_intermediate_type_v2",
        )
    with p2:
        final_product_type = st.text_input(
            "Tracker Final Product Type",
            value=str(row.get("final_product_type") or ""),
            key="ecc_process_final_type_v2",
        )

    formulation_updates: dict[str, Any] = {}
    if stage.key == "formulation":
        st.markdown("#### Formulation")
        f1, f2, f3 = st.columns(3)
        with f1:
            formulation_base_g = st.number_input(
                "Tracker Formulation Base (g)",
                min_value=0.0,
                step=0.1,
                value=float(row.get("formulation_base_g") or 0.0),
                key="ecc_process_formulation_base_v2",
            )
        with f2:
            terpene_mode = st.selectbox(
                "Tracker Terpene Handling",
                list(TERPENE_HANDLING_MODES),
                index=list(TERPENE_HANDLING_MODES).index(str(row.get("terpene_handling_mode") or "Native / No Add-Back"))
                if str(row.get("terpene_handling_mode") or "Native / No Add-Back") in TERPENE_HANDLING_MODES else 0,
                key="ecc_process_terpene_mode_v2",
            )
        terpene_pct = 0.0
        terpene_weight = 0.0
        terpene_type = str(row.get("terpene_type") or "")
        terpene_source = str(row.get("terpene_source") or "")
        if terpene_mode != "Native / No Add-Back":
            with f3:
                terpene_pct = st.number_input(
                    "Tracker Terpene %",
                    min_value=0.0,
                    max_value=20.0,
                    step=0.1,
                    value=float(row.get("terpene_percentage") or 0.0),
                    key="ecc_process_terpene_pct_v2",
                )
            f4, f5, f6 = st.columns(3)
            with f4:
                terpene_type = st.text_input("Tracker Terpene Type", value=terpene_type, key="ecc_process_terpene_type_v2")
            with f5:
                terpene_source = st.text_input("Tracker Terpene Source", value=terpene_source, key="ecc_process_terpene_source_v2")
            with f6:
                manual_weight = st.number_input(
                    "Tracker Terpene Weight Override (g)",
                    min_value=0.0,
                    step=0.1,
                    value=float(row.get("terpene_weight_g") or 0.0),
                    key="ecc_process_terpene_weight_v2",
                )
            terpene_weight = calculate_terpene_weight_g(
                formulation_base_g,
                terpene_pct,
                manual_weight if manual_weight > 0 else None,
            )
        formulation_updates = {
            "formulation_used": True,
            "formulation_base_g": formulation_base_g,
            "terpene_handling_mode": terpene_mode,
            "terpene_type": terpene_type,
            "terpene_source": terpene_source,
            "terpene_percentage": terpene_pct,
            "terpene_weight_g": terpene_weight,
        }
        st.caption(f"Calculated terpene addition: {terpene_weight:,.3f} g")

    if st.button("Record Process Event", key="ecc_record_process_event_v2"):
        event_row = {
            "run_index": run_index,
            "batch_id_internal": str(row.get("batch_id_internal") or ""),
            "workflow_template": workflow.key,
            "stage_key": stage.key,
            "stage_label": stage.label,
            "event_type": event_type,
            "stage_output_field": stage_output_field,
            "input_weight_g": input_weight_g or None,
            "output_weight_g": output_weight_g or None,
            "loss_weight_g": loss_weight_g or None,
            "loss_reason": loss_reason,
            "metrc_stage_input_id": metrc_stage_input_id,
            "metrc_stage_output_id": metrc_stage_output_id,
            "intermediate_product_type": intermediate_product_type,
            "final_product_type": final_product_type,
            "operator": operator,
            "notes": notes,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        events = pd.concat([events, pd.DataFrame([event_row])], ignore_index=True)
        st.session_state[PROCESS_EVENTS_KEY] = events

        source = st.session_state.get(EXTRACTION_RUNS)
        if isinstance(source, pd.DataFrame) and run_index in source.index:
            source = source.copy()
            source.at[run_index, "workflow_template"] = workflow.key
            source.at[run_index, "intermediate_product_type"] = intermediate_product_type
            source.at[run_index, "final_product_type"] = final_product_type
            source.at[run_index, "metrc_stage_input_id"] = metrc_stage_input_id
            source.at[run_index, "metrc_stage_output_id"] = metrc_stage_output_id
            if stage_output_field and output_weight_g > 0:
                source.at[run_index, stage_output_field] = output_weight_g
            for key, value in formulation_updates.items():
                source.at[run_index, key] = value

            values = {
                field: float(source.at[run_index, field] or 0.0)
                if field in source.columns and pd.notna(source.at[run_index, field]) else 0.0
                for field in method_aware_stage_fields(method)
            }
            values.update(_latest_stage_measurements(events, run_index))
            resolved = calculate_final_output_g(
                workflow.key,
                values,
                formulation_used=bool(source.at[run_index, "formulation_used"])
                if "formulation_used" in source.columns and pd.notna(source.at[run_index, "formulation_used"]) else False,
                formulation_base_g=float(source.at[run_index, "formulation_base_g"] or 0.0)
                if "formulation_base_g" in source.columns and pd.notna(source.at[run_index, "formulation_base_g"]) else 0.0,
                terpene_weight_g=float(source.at[run_index, "terpene_weight_g"] or 0.0)
                if "terpene_weight_g" in source.columns and pd.notna(source.at[run_index, "terpene_weight_g"]) else 0.0,
                explicit_finished_output_g=(output_weight_g if stage.key == "final_output" else None),
            )
            if resolved > 0:
                source.at[run_index, "final_output_g"] = resolved
                source.at[run_index, "finished_output_g"] = resolved
                input_g = float(source.at[run_index, "input_weight_g"] or 0.0) if "input_weight_g" in source.columns else 0.0
                source.at[run_index, "yield_pct"] = (resolved / input_g * 100.0) if input_g else 0.0
            st.session_state[EXTRACTION_RUNS] = source
        st.success("Process event recorded and Step 8 output state refreshed.")
        st.rerun()
