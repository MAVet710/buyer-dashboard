"""Cross-domain Extraction hardening hooks.

These hooks keep Extraction on the shared inventory truth without making the
Extraction UI the only safe mutation path. They enforce workflow-compatible
feedstock, attach actual consumption/output to the canonical material graph,
mirror QA/COA results into canonical lot evidence, propagate actual output COGS,
and keep consumer-ready finished goods out of the Extraction source picker.
"""

from __future__ import annotations

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryLot, Product, new_id
from modules.inventory_quality.service import LotQualityService
from modules.material_lineage.models import (
    MaterialTransformation,
    MaterialTransformationInput,
    MaterialTransformationLoss,
    MaterialTransformationOutput,
)
from modules.product_master.models import ProductMasterProfile

from .inventory_eligibility import classify_extraction_inventory
from .models import ExtractionQAEvent, ExtractionRun, ExtractionRunInput, ExtractionRunOutput
from .repository import ExtractionRepository
from .workflow_eligibility import is_workflow_input_eligible


_REGISTERED = False
_ORIGINAL_LIST_AVAILABLE_LOTS = ExtractionRepository.list_available_lots


def _pending(session: Session, cls, predicate):
    return next((row for row in session.new if isinstance(row, cls) and predicate(row)), None)


def _transformation(session: Session, run: ExtractionRun, actor: str) -> MaterialTransformation:
    pending = _pending(
        session,
        MaterialTransformation,
        lambda row: row.organization_id == run.organization_id
        and row.facility_id == run.facility_id
        and row.transformation_type == "extraction_run"
        and row.source_entity_type == "extraction_run"
        and row.source_entity_id == run.id,
    )
    if pending is not None:
        return pending
    with session.no_autoflush:
        row = session.scalar(
            select(MaterialTransformation).where(
                MaterialTransformation.organization_id == run.organization_id,
                MaterialTransformation.facility_id == run.facility_id,
                MaterialTransformation.transformation_type == "extraction_run",
                MaterialTransformation.source_entity_type == "extraction_run",
                MaterialTransformation.source_entity_id == run.id,
            )
        )
    if row is None:
        row = MaterialTransformation(
            id=new_id(),
            organization_id=run.organization_id,
            facility_id=run.facility_id,
            transformation_type="extraction_run",
            source_entity_type="extraction_run",
            source_entity_id=run.id,
            status="open",
            actor=str(actor or run.updated_by or run.created_by or "system"),
            notes=f"Extraction run {run.batch_number}",
        )
        session.add(row)
    return row


def _attach_consumption(session: Session, record: ExtractionRunInput, delta: float) -> None:
    if delta <= 1e-9:
        return
    run = session.get(ExtractionRun, record.run_id)
    lot = session.get(InventoryLot, record.lot_id)
    if run is None or lot is None:
        return
    transform = _transformation(session, run, record.reserved_by)
    purpose = str(record.role or "primary_input")
    pending = _pending(
        session,
        MaterialTransformationInput,
        lambda row: row.transformation_id == transform.id
        and row.entity_type == "inventory_lot"
        and row.entity_id == record.lot_id
        and row.purpose == purpose,
    )
    if pending is not None:
        pending.quantity = float(pending.quantity or 0.0) + delta
        return
    with session.no_autoflush:
        existing = session.scalar(
            select(MaterialTransformationInput).where(
                MaterialTransformationInput.transformation_id == transform.id,
                MaterialTransformationInput.entity_type == "inventory_lot",
                MaterialTransformationInput.entity_id == record.lot_id,
                MaterialTransformationInput.purpose == purpose,
            )
        )
    if existing is not None:
        existing.quantity = float(existing.quantity or 0.0) + delta
        return
    session.add(
        MaterialTransformationInput(
            id=new_id(),
            organization_id=run.organization_id,
            facility_id=run.facility_id,
            transformation_id=transform.id,
            entity_type="inventory_lot",
            entity_id=record.lot_id,
            lot_id=record.lot_id,
            product_id=lot.product_id,
            quantity=delta,
            unit=record.unit,
            purpose=purpose,
            measurement_basis="actual",
        )
    )


def _attach_output(session: Session, output: ExtractionRunOutput) -> None:
    if not output.lot_id:
        return
    run = session.get(ExtractionRun, output.run_id)
    if run is None:
        return
    transform = _transformation(session, run, run.updated_by)
    pending = _pending(
        session,
        MaterialTransformationOutput,
        lambda row: row.transformation_id == transform.id and row.lot_id == output.lot_id,
    )
    if pending is not None:
        pending.quantity = float(output.quantity)
        pending.unit = output.unit
        return
    with session.no_autoflush:
        existing = session.scalar(
            select(MaterialTransformationOutput).where(
                MaterialTransformationOutput.transformation_id == transform.id,
                MaterialTransformationOutput.lot_id == output.lot_id,
            )
        )
    if existing is None:
        session.add(
            MaterialTransformationOutput(
                id=new_id(),
                organization_id=run.organization_id,
                facility_id=run.facility_id,
                transformation_id=transform.id,
                lot_id=output.lot_id,
                product_id=output.product_id,
                quantity=float(output.quantity),
                unit=output.unit,
                purpose="extraction_output",
                measurement_basis="actual",
            )
        )
    else:
        existing.quantity = float(output.quantity)
        existing.unit = output.unit


def _mirror_qa(session: Session, event_row: ExtractionQAEvent) -> None:
    if not event_row.output_id:
        if event_row.event_type == "release" and event_row.result == "passed":
            run = session.get(ExtractionRun, event_row.run_id)
            if run is not None:
                transform = _transformation(session, run, event_row.actor)
                transform.status = "committed"
                transform.actor = event_row.actor
                _record_residual_loss(session, run, transform)
        return
    output = session.get(ExtractionRunOutput, event_row.output_id)
    if output is None or not output.lot_id:
        return
    if event_row.result == "passed":
        previous = LotQualityService.read(session, output.lot_id)
        reference = str(event_row.coa_reference or (previous.coa_reference if previous else "")).strip()
        if reference:
            LotQualityService.set_evidence(
                session,
                lot_id=output.lot_id,
                lab_testing_state="Passed",
                coa_reference=reference,
                coa_url=previous.coa_url if previous else "",
                thca_percent=previous.thca_percent if previous else None,
                tac_percent=previous.tac_percent if previous else None,
                total_terpenes_percent=previous.total_terpenes_percent if previous else None,
                evidence_source="extraction_qa",
                actor=event_row.actor,
            )
    elif event_row.result == "failed":
        previous = LotQualityService.read(session, output.lot_id)
        LotQualityService.set_evidence(
            session,
            lot_id=output.lot_id,
            lab_testing_state="Failed",
            coa_reference=str(event_row.coa_reference or (previous.coa_reference if previous else "")).strip(),
            evidence_source="extraction_qa",
            actor=event_row.actor,
        )


def _record_residual_loss(session: Session, run: ExtractionRun, transform: MaterialTransformation) -> None:
    with session.no_autoflush:
        inputs = list(session.scalars(select(ExtractionRunInput).where(ExtractionRunInput.run_id == run.id)))
        outputs = list(session.scalars(select(ExtractionRunOutput).where(ExtractionRunOutput.run_id == run.id)))
    if not inputs or not outputs:
        return
    units = {str(row.unit or "").casefold() for row in inputs + outputs}
    if units != {"g"}:
        return
    residual = max(
        0.0,
        sum(float(row.consumed_quantity or 0.0) for row in inputs)
        - sum(float(row.quantity or 0.0) for row in outputs if row.status != "destroyed"),
    )
    if residual <= 1e-9:
        return
    with session.no_autoflush:
        existing = session.scalar(
            select(MaterialTransformationLoss).where(
                MaterialTransformationLoss.transformation_id == transform.id,
                MaterialTransformationLoss.loss_type == "extraction_process_loss",
            )
        )
    if existing is None:
        session.add(
            MaterialTransformationLoss(
                id=new_id(),
                organization_id=run.organization_id,
                facility_id=run.facility_id,
                transformation_id=transform.id,
                quantity=residual,
                unit="g",
                loss_type="extraction_process_loss",
                measurement_basis="actual",
                reason="Consumed extraction input not present in recorded output",
            )
        )
    else:
        existing.quantity = residual


def _propagate_output_cost(session: Session, output: ExtractionRunOutput) -> None:
    quantity = float(output.quantity or 0.0)
    total_cost = float(output.output_cost_usd or 0.0)
    if quantity <= 0 or total_cost <= 0:
        return
    product = session.get(Product, output.product_id)
    if product is not None:
        product.unit_cost = round(total_cost / quantity, 6)


def _validate_input(session: Session, record: ExtractionRunInput) -> None:
    run = session.get(ExtractionRun, record.run_id)
    lot = session.get(InventoryLot, record.lot_id)
    if run is None or lot is None:
        return
    product = session.get(Product, lot.product_id)
    if product is None:
        return
    profile = session.get(ProductMasterProfile, product.id)
    allowed, reason = is_workflow_input_eligible(product, profile, run.workflow_key)
    if not allowed:
        raise ValueError(f"Extraction input is not eligible for this workflow: {reason}.")


def _filtered_available_lots(self: ExtractionRepository, organization_id: str, facility_id: str) -> list[dict]:
    rows = _ORIGINAL_LIST_AVAILABLE_LOTS(self, organization_id, facility_id)
    if not rows:
        return []
    product_ids = {str(row.get("product_id") or "") for row in rows if row.get("product_id")}
    with self._session_factory() as session:
        products = {
            row.id: row
            for row in session.scalars(
                select(Product).where(Product.organization_id == organization_id, Product.id.in_(product_ids))
            )
        }
        profiles = {
            row.product_id: row
            for row in session.scalars(
                select(ProductMasterProfile).where(
                    ProductMasterProfile.organization_id == organization_id,
                    ProductMasterProfile.product_id.in_(product_ids),
                )
            )
        }
    eligible: list[dict] = []
    for row in rows:
        product = products.get(str(row.get("product_id") or ""))
        if product is None:
            continue
        profile = profiles.get(product.id)
        if profile is not None and not profile.production_enabled:
            continue
        classification = classify_extraction_inventory(
            item_type=product.item_type,
            product_name=product.name,
            sku=product.sku,
            base_unit=product.base_unit,
            category=profile.category if profile else "",
            subcategory=profile.subcategory if profile else "",
            product_format=profile.product_format if profile else "",
        )
        if classification.eligible:
            eligible.append(row)
    return eligible


def _before_flush(session: Session, _flush_context, _instances) -> None:
    for row in list(session.new):
        if isinstance(row, ExtractionRunInput):
            _validate_input(session, row)
        elif isinstance(row, ExtractionRunOutput):
            _attach_output(session, row)
        elif isinstance(row, ExtractionQAEvent):
            _mirror_qa(session, row)

    for row in list(session.dirty):
        if isinstance(row, ExtractionRunInput):
            history = inspect(row).attrs.consumed_quantity.history
            if history.has_changes():
                old = float(history.deleted[0] if history.deleted else 0.0)
                new = float(row.consumed_quantity or 0.0)
                _attach_consumption(session, row, new - old)
        elif isinstance(row, ExtractionRunOutput):
            history = inspect(row).attrs.output_cost_usd.history
            if history.has_changes():
                _propagate_output_cost(session, row)


def register_hardening_hooks() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    event.listen(Session, "before_flush", _before_flush)
    ExtractionRepository.list_available_lots = _filtered_available_lots
    _REGISTERED = True


register_hardening_hooks()
