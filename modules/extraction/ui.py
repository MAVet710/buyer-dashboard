"""Low-click Extraction ERP workspace with Run 360 pop-out drawers."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import math
from typing import Any, Callable, MutableMapping

import pandas as pd
import streamlit as st

from modules.coman.db import ComanDatabaseConfigurationError, create_coman_engine
from modules.coman.repository import ComanRepository
from services.workspace_navigation import (
    BUYER_WORKSPACE,
    METRC_INTEGRATIONS_SECTION,
    RETAIL_OPS,
    queue_workspace_navigation,
)

from .analytics import build_extraction_exceptions, build_run_board
from .repository import ExtractionRepository
from .traceability import ExtractionTraceabilityService
from .workflows import get_extraction_workflow, list_extraction_workflows


EDIT_ROLES = frozenset({"dev", "admin", "planner", "supervisor", "operator", "qa"})
QA_RELEASE_ROLES = frozenset({"dev", "admin", "supervisor", "qa"})


def _drawer_css() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stDialog"] > div[role="dialog"] {
            margin-left: auto !important;
            margin-right: 0 !important;
            min-height: 100vh !important;
            max-height: 100vh !important;
            border-radius: 18px 0 0 18px !important;
            border-left: 1px solid rgba(255,154,60,.28) !important;
        }
        .extraction-attention {
            border:1px solid rgba(231,152,78,.20);
            border-radius:14px;
            padding:.7rem .8rem;
            margin:.3rem 0;
            background:rgba(231,152,78,.04);
        }
        .extraction-attention strong {color:#F4B36F!important;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _scope(state: MutableMapping[str, Any]) -> tuple[str, str]:
    return (
        str(state.get("active_organization_id") or "").strip(),
        str(state.get("active_facility_id") or "").strip(),
    )


def _actor(state: MutableMapping[str, Any]) -> str:
    return str(
        state.get("auth_username")
        or state.get("auth_user_email")
        or state.get("display_user")
        or "operator"
    ).strip()


def _role(state: MutableMapping[str, Any]) -> str:
    return str(state.get("auth_user_role") or "read_only").strip().casefold()


def _can_edit(state: MutableMapping[str, Any]) -> bool:
    return _role(state) in EDIT_ROLES


def _can_release(state: MutableMapping[str, Any]) -> bool:
    return _role(state) in QA_RELEASE_ROLES


@contextmanager
def _popover(label: str, *, use_container_width: bool = True):
    if hasattr(st, "popover"):
        with st.popover(label, use_container_width=use_container_width):
            yield
    else:
        with st.expander(label, expanded=False):
            yield


def _as_frame(rows: list[Any], columns: dict[str, str]) -> pd.DataFrame:
    data: list[dict[str, Any]] = []
    for row in rows:
        data.append({label: getattr(row, field, None) for label, field in columns.items()})
    return pd.DataFrame(data)


def _route_traceability(state: MutableMapping[str, Any]) -> None:
    queue_workspace_navigation(
        state,
        group=RETAIL_OPS,
        workspace=BUYER_WORKSPACE,
        buyer_section=METRC_INTEGRATIONS_SECTION,
    )
    state["extraction_run_360_open"] = False
    st.rerun()


def _render_new_run_dialog(
    state: MutableMapping[str, Any],
    repository: ExtractionRepository,
    organization_id: str,
    facility_id: str,
) -> None:
    workflows = list_extraction_workflows()

    def _body() -> None:
        st.caption("Create the durable production object first. Inputs, stages, outputs, QA and COGS attach to this run.")
        workflow_labels = {workflow.label: workflow for workflow in workflows}
        with st.form("extraction_new_run_form", clear_on_submit=False):
            c1, c2 = st.columns(2)
            with c1:
                batch = st.text_input("Batch / Run ID")
                workflow_label = st.selectbox("Workflow", list(workflow_labels))
                strain = st.text_input("Strain / cultivar")
            with c2:
                product_family = st.text_input("Target product family")
                operator = st.text_input("Lead operator", value=_actor(state))
                license_number = st.text_input("Facility license", value=str(state.get("metrc_license_number") or ""))
            notes = st.text_area("Run notes", height=90)
            submitted = st.form_submit_button("Create run", type="primary", use_container_width=True)
        if submitted:
            workflow = workflow_labels[workflow_label]
            try:
                run = repository.create_run(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    batch_number=batch,
                    method=workflow.method,
                    workflow_key=workflow.key,
                    actor=_actor(state),
                    product_family=product_family,
                    strain=strain,
                    operator=operator,
                    license_number=license_number,
                    notes=notes,
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                state["extraction_selected_run_id"] = run.id
                state["extraction_run_360_open"] = True
                st.success(f"{run.batch_number} created.")
                st.rerun()

    if hasattr(st, "dialog"):
        @st.dialog("New Extraction Run", width="large")
        def _dialog() -> None:
            _body()
        _dialog()
    else:
        with st.container(border=True):
            _body()


def _lot_lookup(coman: ComanRepository, organization_id: str, facility_id: str) -> dict[str, Any]:
    return {lot.id: lot for lot in coman.list_inventory_lots(organization_id, facility_id)}


def _product_lookup(coman: ComanRepository, organization_id: str) -> dict[str, Any]:
    return {product.id: product for product in coman.list_products(organization_id)}


def _render_overview(
    state: MutableMapping[str, Any],
    snapshot: dict[str, Any],
    repository: ExtractionRepository,
    organization_id: str,
    facility_id: str,
) -> None:
    run = snapshot["run"]
    mass = snapshot["mass_balance"]
    cogs = snapshot["cogs"]
    metrics = st.columns(4)
    metrics[0].metric("Consumed input", f"{mass['consumed_input']:,.2f}")
    metrics[1].metric("Recorded output", f"{mass['recorded_output']:,.2f}")
    metrics[2].metric("Yield", f"{mass['yield_pct']:,.2f}%")
    metrics[3].metric("Run COGS", f"${cogs['total']:,.2f}")

    st.write(
        f"**Method:** {run.method}  \n"
        f"**Workflow:** {snapshot['workflow'].label}  \n"
        f"**Current stage:** {snapshot['workflow'].stage_label(run.current_stage_key)}  \n"
        f"**Status:** {run.status.title()}  \n"
        f"**Release:** {run.release_status.title()}  \n"
        f"**Strain:** {run.strain or 'Not set'}  \n"
        f"**Operator:** {run.operator or 'Not set'}"
    )

    stage_labels = [stage.label for stage in snapshot["workflow"].stages]
    current_index = next(
        (index for index, stage in enumerate(snapshot["workflow"].stages) if stage.key == run.current_stage_key),
        0,
    )
    st.caption("Workflow progress")
    st.progress(min(1.0, (current_index + 1) / max(1, len(stage_labels))))
    st.caption(" → ".join(stage_labels))

    if snapshot.get("toll_job"):
        toll = snapshot["toll_job"]
        st.info(
            f"Toll processing · ${float(toll.processing_fee_usd):,.2f} fee · "
            f"invoice {toll.invoice_status} · payment {toll.payment_status}"
        )

    if _can_edit(state):
        with _popover("Run notes"):
            notes = st.text_area(
                "Notes",
                value=run.notes or "",
                key=f"extraction_notes_{run.id}",
                height=120,
            )
            if st.button("Save notes", key=f"extraction_save_notes_{run.id}", use_container_width=True):
                repository.update_run_notes(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    run_id=run.id,
                    notes=notes,
                    actor=_actor(state),
                )
                st.rerun()


def _render_inputs(
    state: MutableMapping[str, Any],
    snapshot: dict[str, Any],
    repository: ExtractionRepository,
    coman: ComanRepository,
    organization_id: str,
    facility_id: str,
) -> None:
    run = snapshot["run"]
    inputs = snapshot["inputs"]
    lots = _lot_lookup(coman, organization_id, facility_id)
    products = _product_lookup(coman, organization_id)
    rows = []
    for item in inputs:
        lot = lots.get(item.lot_id)
        product = products.get(lot.product_id) if lot else None
        rows.append(
            {
                "input_id": item.id,
                "Product": product.name if product else "",
                "Lot": lot.lot_code if lot else item.lot_id,
                "Metrc": lot.compliance_package_id if lot else "",
                "Reserved": item.reserved_quantity,
                "Consumed": item.consumed_quantity,
                "Remaining": max(0.0, item.reserved_quantity - item.consumed_quantity),
                "Unit": item.unit,
                "Input Cost": item.input_cost_usd,
                "Status": item.status,
            }
        )
    if rows:
        st.dataframe(pd.DataFrame(rows).drop(columns=["input_id"]), hide_index=True, width="stretch")
    else:
        st.info("No source lots are attached yet.")

    if not _can_edit(state):
        return

    available = repository.list_available_lots(organization_id, facility_id)
    with _popover("Reserve source lot"):
        if not available:
            st.info("No released inventory is currently available after production, commercial, and extraction reservations.")
        else:
            labels = {
                f"{row['product_name']} · {row['lot_code']} · {row['available']:,.2f} {row['unit']} available": row
                for row in available
            }
            selected = labels[st.selectbox("Source lot", list(labels), key=f"extract_reserve_lot_{run.id}")]
            quantity = st.number_input(
                "Reserve quantity",
                min_value=0.0,
                max_value=float(selected["available"]),
                value=min(float(selected["available"]), max(0.0, float(selected["available"]))),
                step=0.1,
                key=f"extract_reserve_qty_{run.id}",
            )
            if st.button("Reserve", type="primary", key=f"extract_reserve_submit_{run.id}", use_container_width=True):
                try:
                    repository.reserve_input(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        run_id=run.id,
                        lot_id=selected["lot_id"],
                        quantity=quantity,
                        actor=_actor(state),
                        unit=selected["unit"],
                    )
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.rerun()

    open_inputs = [item for item in inputs if item.status in {"reserved", "partial"}]
    with _popover("Consume reserved material"):
        if not open_inputs:
            st.info("Reserve a source lot first.")
        else:
            input_labels = {}
            for item in open_inputs:
                lot = lots.get(item.lot_id)
                remaining = max(0.0, item.reserved_quantity - item.consumed_quantity)
                input_labels[f"{lot.lot_code if lot else item.lot_id} · {remaining:,.2f} {item.unit} remaining"] = item
            selected_input = input_labels[
                st.selectbox("Reserved input", list(input_labels), key=f"extract_consume_input_{run.id}")
            ]
            remaining = max(0.0, selected_input.reserved_quantity - selected_input.consumed_quantity)
            consume_qty = st.number_input(
                "Consume quantity",
                min_value=0.0,
                max_value=float(remaining),
                value=float(remaining),
                step=0.1,
                key=f"extract_consume_qty_{run.id}",
            )
            if st.button("Post consumption", type="primary", key=f"extract_consume_submit_{run.id}", use_container_width=True):
                try:
                    repository.consume_input(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        run_input_id=selected_input.id,
                        quantity=consume_qty,
                        actor=_actor(state),
                    )
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.rerun()


def _render_process(
    state: MutableMapping[str, Any],
    snapshot: dict[str, Any],
    repository: ExtractionRepository,
    organization_id: str,
    facility_id: str,
) -> None:
    run = snapshot["run"]
    workflow = snapshot["workflow"]
    events = snapshot["stages"]
    if events:
        frame = _as_frame(
            events,
            {
                "Time": "occurred_at",
                "Stage": "stage_key",
                "Event": "event_type",
                "Input g": "input_weight_g",
                "Output g": "output_weight_g",
                "Loss g": "loss_weight_g",
                "Operator": "operator",
                "Notes": "notes",
            },
        )
        frame["Stage"] = frame["Stage"].map(lambda value: workflow.stage_label(str(value)))
        st.dataframe(frame, hide_index=True, width="stretch")
    else:
        st.info("No durable stage events yet.")

    if not _can_edit(state):
        return
    with _popover("Record stage update"):
        stage_map = {stage.label: stage.key for stage in workflow.stages}
        default_index = next(
            (index for index, stage in enumerate(workflow.stages) if stage.key == run.current_stage_key),
            0,
        )
        stage_label = st.selectbox(
            "Stage",
            list(stage_map),
            index=default_index,
            key=f"extract_stage_key_{run.id}",
        )
        event_type = st.selectbox(
            "Event",
            ["measurement", "completed", "started", "note", "deviation", "hold", "released"],
            key=f"extract_stage_event_{run.id}",
        )
        c1, c2, c3 = st.columns(3)
        input_g = c1.number_input("Input g", min_value=0.0, value=0.0, step=0.1, key=f"extract_stage_in_{run.id}")
        output_g = c2.number_input("Output g", min_value=0.0, value=0.0, step=0.1, key=f"extract_stage_out_{run.id}")
        loss_g = c3.number_input("Loss g", min_value=0.0, value=0.0, step=0.1, key=f"extract_stage_loss_{run.id}")
        loss_reason = st.text_input("Loss / deviation reason", key=f"extract_stage_reason_{run.id}")
        notes = st.text_area("Operator note", height=80, key=f"extract_stage_notes_{run.id}")
        if st.button("Record event", type="primary", key=f"extract_stage_submit_{run.id}", use_container_width=True):
            try:
                repository.record_stage_event(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    run_id=run.id,
                    stage_key=stage_map[stage_label],
                    event_type=event_type,
                    actor=_actor(state),
                    input_weight_g=input_g if input_g > 0 else None,
                    output_weight_g=output_g if output_g > 0 else None,
                    loss_weight_g=loss_g if loss_g > 0 else None,
                    loss_reason=loss_reason,
                    notes=notes,
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                st.rerun()


def _render_outputs_qa(
    state: MutableMapping[str, Any],
    snapshot: dict[str, Any],
    repository: ExtractionRepository,
    coman: ComanRepository,
    organization_id: str,
    facility_id: str,
) -> None:
    run = snapshot["run"]
    outputs = snapshot["outputs"]
    products = _product_lookup(coman, organization_id)
    output_rows = []
    for output in outputs:
        product = products.get(output.product_id)
        output_rows.append(
            {
                "Output": output.output_label,
                "Product": product.name if product else output.product_id,
                "Qty": output.quantity,
                "Unit": output.unit,
                "Status": output.status,
                "COA": output.coa_status,
                "Metrc": output.compliance_package_id,
                "Allocated COGS": output.output_cost_usd,
            }
        )
    if output_rows:
        st.dataframe(pd.DataFrame(output_rows), hide_index=True, width="stretch")
    else:
        st.info("No output packages have been created yet.")

    if _can_edit(state):
        with _popover("Create output / WIP package"):
            eligible = [product for product in products.values() if product.item_type in {"cannabis", "wip", "finished_good"}]
            if not eligible:
                st.info("Create a canonical Product Master item before recording extraction output.")
            else:
                product_map = {f"{product.name} · {product.sku}": product for product in eligible}
                selected_product = product_map[
                    st.selectbox("Output product", list(product_map), key=f"extract_output_product_{run.id}")
                ]
                c1, c2 = st.columns(2)
                lot_code = c1.text_input("Internal lot / batch code", value=f"{run.batch_number}-OUT", key=f"extract_output_lot_{run.id}")
                quantity = c2.number_input("Output quantity", min_value=0.0, step=0.1, key=f"extract_output_qty_{run.id}")
                output_label = st.text_input("Output label", value=selected_product.name, key=f"extract_output_label_{run.id}")
                if st.button("Create quarantined output", type="primary", key=f"extract_output_submit_{run.id}", use_container_width=True):
                    try:
                        repository.create_output(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            run_id=run.id,
                            product_id=selected_product.id,
                            lot_code=lot_code,
                            quantity=quantity,
                            actor=_actor(state),
                            output_label=output_label,
                            unit=selected_product.base_unit,
                        )
                    except Exception as exc:
                        st.error(str(exc))
                    else:
                        st.rerun()

    st.markdown("#### QA / release")
    qa = snapshot["qa_events"]
    if qa:
        st.dataframe(
            _as_frame(
                qa,
                {
                    "Time": "occurred_at",
                    "Event": "event_type",
                    "Result": "result",
                    "COA": "coa_reference",
                    "Deviation": "deviation_code",
                    "Actor": "actor",
                    "Notes": "notes",
                },
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("No QA events recorded.")

    if _can_edit(state) and outputs:
        with _popover("Record QA event"):
            output_map = {f"#{output.position} · {output.output_label}": output for output in outputs}
            selected_output = output_map[
                st.selectbox("Output", list(output_map), key=f"extract_qa_output_{run.id}")
            ]
            event = st.selectbox(
                "QA event",
                ["sample_submitted", "coa_attached", "failure", "retest", "remediation", "deviation", "hold"],
                key=f"extract_qa_event_{run.id}",
            )
            result = st.selectbox(
                "Result",
                ["pending", "passed", "failed", "not_applicable"],
                key=f"extract_qa_result_{run.id}",
            )
            coa = st.text_input("COA / lab document reference", key=f"extract_qa_coa_{run.id}")
            deviation = st.text_input("Deviation code", key=f"extract_qa_deviation_{run.id}")
            note = st.text_area("QA note", height=80, key=f"extract_qa_note_{run.id}")
            if st.button("Record QA", type="primary", key=f"extract_qa_submit_{run.id}", use_container_width=True):
                try:
                    repository.record_qa_event(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        run_id=run.id,
                        output_id=selected_output.id,
                        event_type=event,
                        result=result,
                        actor=_actor(state),
                        coa_reference=coa,
                        deviation_code=deviation,
                        notes=note,
                    )
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.rerun()

    if _can_release(state) and outputs and run.status != "complete":
        all_passed = all(output.coa_status == "passed" for output in outputs if output.status in {"wip", "quarantine"})
        if all_passed:
            if st.button("Release run + output inventory", type="primary", key=f"extract_release_{run.id}", use_container_width=True):
                try:
                    repository.record_qa_event(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        run_id=run.id,
                        event_type="release",
                        result="passed",
                        actor=_actor(state),
                        notes="QA release approved from Run 360.",
                    )
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.rerun()
        else:
            st.warning("Release is locked until every quarantined output has a passed COA.")


def _render_cogs(
    state: MutableMapping[str, Any],
    snapshot: dict[str, Any],
    repository: ExtractionRepository,
    organization_id: str,
    facility_id: str,
) -> None:
    run = snapshot["run"]
    cogs = snapshot["cogs"]
    cols = st.columns(4)
    cols[0].metric("Materials", f"${cogs['material']:,.2f}")
    cols[1].metric("Labor", f"${cogs['labor']:,.2f}")
    cols[2].metric("Packaging", f"${cogs['packaging']:,.2f}")
    cols[3].metric("Total", f"${cogs['total']:,.2f}")
    st.caption(f"Cost per recorded output unit: ${cogs['cost_per_output_unit']:,.4f}")

    events = snapshot["cost_events"]
    if events:
        st.dataframe(
            _as_frame(
                events,
                {
                    "Time": "occurred_at",
                    "Category": "category",
                    "Amount": "amount_usd",
                    "Qty": "quantity",
                    "Unit": "unit",
                    "Rate": "unit_rate_usd",
                    "Source": "source_type",
                    "Actor": "actor",
                    "Notes": "notes",
                },
            ),
            hide_index=True,
            width="stretch",
        )
    if not _can_edit(state):
        return
    with _popover("Add cost"):
        category = st.selectbox(
            "Category",
            ["labor", "packaging", "processing", "overhead", "waste", "other"],
            key=f"extract_cost_category_{run.id}",
        )
        amount = st.number_input("Amount USD", min_value=0.0, step=1.0, key=f"extract_cost_amount_{run.id}")
        note = st.text_input("Cost note", key=f"extract_cost_note_{run.id}")
        if st.button("Post cost", type="primary", key=f"extract_cost_submit_{run.id}", use_container_width=True):
            try:
                repository.add_cost_event(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    run_id=run.id,
                    category=category,
                    amount_usd=amount,
                    actor=_actor(state),
                    notes=note,
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                st.rerun()


def _render_traceability(
    state: MutableMapping[str, Any],
    snapshot: dict[str, Any],
    traceability: ExtractionTraceabilityService,
    organization_id: str,
    facility_id: str,
) -> None:
    run = snapshot["run"]
    transactions = snapshot["traceability"]
    if transactions:
        st.dataframe(
            _as_frame(
                transactions,
                {
                    "Requested": "requested_at",
                    "Provider": "provider",
                    "Operation": "operation_type",
                    "Status": "status",
                    "Reference": "external_reference",
                    "Error": "error_message",
                },
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("No state-system actions are attached to this run yet.")

    outputs = [output for output in snapshot["outputs"] if output.status not in {"waste", "destroyed"}]
    if _can_edit(state) and outputs:
        with _popover("Queue output package creation"):
            output_map = {f"#{output.position} · {output.output_label} · {output.quantity:,.2f} {output.unit}": output for output in outputs}
            selected_output = output_map[
                st.selectbox("Output", list(output_map), key=f"extract_metrc_output_{run.id}")
            ]
            tag = st.text_input(
                "New package tag",
                value=selected_output.compliance_package_id or "",
                key=f"extract_metrc_tag_{run.id}",
                help="Scan or enter an unused state-system package tag.",
            )
            item = st.text_input(
                "Metrc Item name",
                key=f"extract_metrc_item_{run.id}",
                help="Use the exact Item name mapped to the canonical output product.",
            )
            location = st.text_input("Metrc location (optional)", key=f"extract_metrc_location_{run.id}")
            if st.button("Validate + queue", type="primary", key=f"extract_metrc_queue_{run.id}", use_container_width=True):
                try:
                    transaction = traceability.queue_output_package_creation(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        run_id=run.id,
                        output_id=selected_output.id,
                        new_tag=tag,
                        metrc_item_name=item,
                        actor=_actor(state),
                        location=location,
                        is_finished_good=selected_output.status == "released",
                    )
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Queued traceability transaction {transaction.id[:8]}…")
                    st.rerun()

    if st.button("Open Traceability Operations", key=f"extract_open_traceability_{run.id}", use_container_width=True):
        _route_traceability(state)


def _render_history(snapshot: dict[str, Any]) -> None:
    rows = []
    for event in snapshot["stages"]:
        rows.append(
            {
                "Time": event.occurred_at,
                "Type": "Process",
                "Event": f"{event.stage_key} · {event.event_type}",
                "Actor": event.operator,
                "Detail": event.notes or event.loss_reason,
            }
        )
    for event in snapshot["qa_events"]:
        rows.append(
            {
                "Time": event.occurred_at,
                "Type": "QA",
                "Event": f"{event.event_type} · {event.result}",
                "Actor": event.actor,
                "Detail": event.notes or event.coa_reference,
            }
        )
    for event in snapshot["cost_events"]:
        rows.append(
            {
                "Time": event.occurred_at,
                "Type": "COGS",
                "Event": f"{event.category} · ${event.amount_usd:,.2f}",
                "Actor": event.actor,
                "Detail": event.notes,
            }
        )
    for event in snapshot["traceability"]:
        rows.append(
            {
                "Time": event.requested_at,
                "Type": "Traceability",
                "Event": f"{event.operation_type} · {event.status}",
                "Actor": event.requested_by,
                "Detail": event.error_message or event.external_reference,
            }
        )
    if not rows:
        st.info("No run history yet.")
        return
    frame = pd.DataFrame(rows).sort_values("Time", ascending=False)
    st.dataframe(frame, hide_index=True, width="stretch")


def render_run_360_dialog(
    state: MutableMapping[str, Any],
    repository: ExtractionRepository,
    coman: ComanRepository,
    traceability: ExtractionTraceabilityService,
    organization_id: str,
    facility_id: str,
    run_id: str,
) -> None:
    snapshot = repository.run_360(organization_id, facility_id, run_id)
    run = snapshot["run"]
    _drawer_css()

    def _body() -> None:
        close_col, title_col = st.columns([1, 5])
        if close_col.button("Close", key=f"extract_360_close_{run.id}"):
            state["extraction_run_360_open"] = False
            st.rerun()
        with title_col:
            st.caption("RUN 360 · durable production object")
            st.markdown(f"## {run.batch_number}")
            st.caption(f"{run.method} · {snapshot['workflow'].label} · {run.status.title()}")

        overview, inputs, process, outputs_qa, cogs, compliance, history = st.tabs(
            ["Overview", "Inputs", "Process", "Outputs + QA", "COGS", "Traceability", "History"]
        )
        with overview:
            _render_overview(state, snapshot, repository, organization_id, facility_id)
        with inputs:
            _render_inputs(state, snapshot, repository, coman, organization_id, facility_id)
        with process:
            _render_process(state, snapshot, repository, organization_id, facility_id)
        with outputs_qa:
            _render_outputs_qa(state, snapshot, repository, coman, organization_id, facility_id)
        with cogs:
            _render_cogs(state, snapshot, repository, organization_id, facility_id)
        with compliance:
            _render_traceability(state, snapshot, traceability, organization_id, facility_id)
        with history:
            _render_history(snapshot)

    if hasattr(st, "dialog"):
        @st.dialog("Run 360", width="large")
        def _dialog() -> None:
            _body()
        _dialog()
    else:
        with st.container(border=True):
            _body()


def _render_legacy_dialog(legacy_renderer: Callable[[], None]) -> None:
    _drawer_css()
    if hasattr(st, "dialog"):
        @st.dialog("Legacy Extraction Tools", width="large")
        def _dialog() -> None:
            st.caption("Compatibility view while the durable Run 360 workflow replaces the older session-state tools.")
            legacy_renderer()
        _dialog()
    else:
        legacy_renderer()


def render_extraction_workspace(
    state: MutableMapping[str, Any] | None = None,
    *,
    legacy_renderer: Callable[[], None] | None = None,
) -> None:
    """Render the durable Extraction command center with one-click Run 360 drawers."""

    state = state or st.session_state
    organization_id, facility_id = _scope(state)
    st.markdown("## Extraction Operations")
    st.caption("Run board first. Click a run once to open its full production, QA, COGS and traceability context.")
    if not organization_id or not facility_id:
        st.info("Select an organization and facility before using durable Extraction operations.")
        return
    try:
        engine = create_coman_engine()
        repository = ExtractionRepository(engine)
        coman = ComanRepository(engine)
        traceability = ExtractionTraceabilityService(engine)
        board = build_run_board(engine, organization_id, facility_id, include_closed=True)
    except ComanDatabaseConfigurationError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error(f"Extraction ERP could not load: {exc}")
        return

    active = board[board["Status"].isin(["Planned", "Queued", "Active", "Hold", "Qa"])] if not board.empty else board
    qa_hold = int(active["Status"].isin(["Hold", "Qa"]).sum()) if not active.empty else 0
    trace_exceptions = int(active["Traceability Exceptions"].sum()) if not active.empty else 0
    wip_value = float(active["COGS"].sum()) if not active.empty else 0.0
    top = st.columns(4)
    top[0].metric("Active Runs", f"{len(active):,}")
    top[1].metric("QA / Holds", f"{qa_hold:,}")
    top[2].metric("Traceability Exceptions", f"{trace_exceptions:,}")
    top[3].metric("Active Run COGS", f"${wip_value:,.0f}")

    action_cols = st.columns([1, 1, 4])
    if _can_edit(state) and action_cols[0].button("New Run", type="primary", use_container_width=True):
        _render_new_run_dialog(state, repository, organization_id, facility_id)
    if legacy_renderer is not None and action_cols[1].button("Legacy Tools", use_container_width=True):
        _render_legacy_dialog(legacy_renderer)

    exceptions = build_extraction_exceptions(board)
    if exceptions:
        st.markdown("### Needs attention")
        for index, item in enumerate(exceptions[:5]):
            label_col, action_col = st.columns([6, 1])
            with label_col:
                st.markdown(
                    f"<div class='extraction-attention'><strong>{item.title}</strong><br/><span>{item.detail}</span></div>",
                    unsafe_allow_html=True,
                )
            with action_col:
                if st.button("Open", key=f"extract_exception_open_{index}_{item.run_id}", use_container_width=True):
                    state["extraction_selected_run_id"] = item.run_id
                    state["extraction_run_360_open"] = True
                    st.rerun()

    st.markdown("### Run board")
    if board.empty:
        st.info("No durable extraction runs yet. Create the first run to begin.")
    else:
        f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
        search = f1.text_input("Search runs", placeholder="Batch, strain, method…", label_visibility="collapsed", key="extract_board_search")
        statuses = ["All"] + sorted(board["Status"].dropna().astype(str).unique().tolist())
        status_filter = f2.selectbox("Status", statuses, label_visibility="collapsed", key="extract_board_status")
        methods = ["All"] + sorted(board["Method"].dropna().astype(str).unique().tolist())
        method_filter = f3.selectbox("Method", methods, label_visibility="collapsed", key="extract_board_method")
        show_closed = f4.toggle("Closed", value=False, key="extract_board_closed")

        filtered = board.copy()
        if not show_closed:
            filtered = filtered[~filtered["Status"].isin(["Complete", "Cancelled", "Failed"])]
        if status_filter != "All":
            filtered = filtered[filtered["Status"] == status_filter]
        if method_filter != "All":
            filtered = filtered[filtered["Method"] == method_filter]
        if str(search or "").strip():
            needle = str(search).strip().casefold()
            haystack = filtered[["Run", "Method", "Stage", "Status", "Strain", "Attention"]].fillna("").astype(str).agg(" ".join, axis=1).str.casefold()
            filtered = filtered[haystack.str.contains(needle, regex=False)]

        display_columns = [
            "Run",
            "Stage",
            "Method",
            "Input",
            "Output",
            "Yield %",
            "COGS",
            "Cost / Output",
            "Release",
            "Attention",
        ]
        display = filtered[display_columns].copy()
        selected_run_id = ""
        try:
            event = st.dataframe(
                display,
                hide_index=True,
                width="stretch",
                on_select="rerun",
                selection_mode="single-row",
                key="extraction_run_board_table",
            )
            selected_rows = list(getattr(getattr(event, "selection", None), "rows", []) or [])
            if selected_rows:
                selected_position = int(selected_rows[0])
                if 0 <= selected_position < len(filtered):
                    selected_run_id = str(filtered.iloc[selected_position]["run_id"])
        except TypeError:
            st.dataframe(display, hide_index=True, width="stretch")
            labels = filtered["Run"].astype(str).tolist()
            if labels:
                chosen = st.selectbox("Open run", labels, key="extraction_run_board_fallback")
                if st.button("Open Run 360", key="extraction_run_board_fallback_open"):
                    selected_run_id = str(filtered.loc[filtered["Run"].astype(str) == chosen, "run_id"].iloc[0])

        if selected_run_id:
            state["extraction_selected_run_id"] = selected_run_id
            state["extraction_run_360_open"] = True

    selected = str(state.get("extraction_selected_run_id") or "").strip()
    if selected and bool(state.get("extraction_run_360_open", False)):
        render_run_360_dialog(
            state,
            repository,
            coman,
            traceability,
            organization_id,
            facility_id,
            selected,
        )
