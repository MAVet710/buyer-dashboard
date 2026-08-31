"""Govern final Extraction release mass reconciliation.

Intermediate/WIP handoffs remain strict: operators must explicitly reconcile the
material state before creating the handoff. Final QA release has a different
boundary because the remaining source mass is often spent plant material or
other process residual rather than another sellable extract output. At the
release boundary we therefore persist the remaining mass as a clearly labeled,
auditable closeout residual instead of letting it silently disappear.

The event is deliberately marked as system-derived/unclassified. It does not
pretend the residual was externally reported as waste, and a future waste or
compliance workflow may classify it more specifically.
"""

from __future__ import annotations

from .material_backbone import _latest_completed_losses, _run_inputs, _run_outputs
from .models import ExtractionRun
from .repository import ExtractionRepository
from .workflows import get_extraction_workflow


_ORIGINAL_RECORD_QA_EVENT = ExtractionRepository.record_qa_event
_INSTALLED = False
_TOLERANCE_MIN_G = 0.01
_TOLERANCE_FRACTION = 0.001


def _reconcile_release_residual(
    self: ExtractionRepository,
    *,
    organization_id: str,
    facility_id: str,
    run_id: str,
    actor: str,
) -> None:
    """Persist remaining final-run mass as an explicit closeout residual event."""

    with self._session_factory() as session:
        run = self._require_run(session, organization_id, facility_id, run_id)
        inputs = _run_inputs(session, run)
        outputs = _run_outputs(session, run)
        consumed = sum(max(0.0, float(row.consumed_quantity or 0.0)) for row in inputs)
        recorded_output = sum(max(0.0, float(row.quantity or 0.0)) for row in outputs)
        explicit_loss = _latest_completed_losses(session, run)
        residual = consumed - recorded_output - explicit_loss
        tolerance = max(_TOLERANCE_MIN_G, consumed * _TOLERANCE_FRACTION)
        if residual <= tolerance:
            return

        workflow = get_extraction_workflow(run.workflow_key)
        qa_stage = next((row.key for row in workflow.stages if row.qa_gate), None)
        stage_key = qa_stage or run.current_stage_key or workflow.first_stage

    self.record_stage_event(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run_id,
        stage_key=stage_key,
        event_type="completed",
        actor=actor,
        input_weight_g=consumed,
        output_weight_g=recorded_output,
        loss_weight_g=residual,
        loss_reason="System-derived unclassified extraction closeout residual",
        notes=(
            "DoobieLogic reconciled consumed source mass not present in durable output at final QA release. "
            "This is an auditable process residual, not an external waste/disposal submission; classify it more "
            "specifically when facility SOP or compliance workflow requires that distinction."
        ),
    )


def _record_qa_event_with_release_reconciliation(
    self: ExtractionRepository,
    *,
    organization_id: str,
    facility_id: str,
    run_id: str,
    event_type: str,
    result: str,
    actor: str,
    output_id: str | None = None,
    coa_reference: str = "",
    deviation_code: str = "",
    notes: str = "",
):
    normalized_event = str(event_type or "").strip().casefold()
    normalized_result = str(result or "").strip().casefold()
    if normalized_event == "release" and normalized_result == "passed":
        _reconcile_release_residual(
            self,
            organization_id=organization_id,
            facility_id=facility_id,
            run_id=run_id,
            actor=actor,
        )
    return _ORIGINAL_RECORD_QA_EVENT(
        self,
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run_id,
        event_type=event_type,
        result=result,
        actor=actor,
        output_id=output_id,
        coa_reference=coa_reference,
        deviation_code=deviation_code,
        notes=notes,
    )


def register_release_reconciliation() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    ExtractionRepository.record_qa_event = _record_qa_event_with_release_reconciliation
    _INSTALLED = True


register_release_reconciliation()
