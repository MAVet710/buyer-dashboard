"""Keep Production Run 360 QA and state aligned with canonical durable truth."""

from __future__ import annotations

from sqlalchemy import event, func, inspect, select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryLot, Product, ProductionOrder
from modules.inventory_quality.service import LotQualityService

from .models import ProductionCostEvent, ProductionQAEvent, ProductionRunEvent, ProductionRunOutput


_REGISTERED = False


def _pending_or_persisted(session: Session, model, object_id: str | None):
    if not object_id:
        return None
    for row in session.new:
        if isinstance(row, model) and getattr(row, "id", None) == object_id:
            return row
    with session.no_autoflush:
        return session.get(model, object_id)


def _order_for(session: Session, row) -> ProductionOrder:
    order = _pending_or_persisted(session, ProductionOrder, row.production_order_id)
    if order is None:
        raise ValueError("Production child record references a missing production order.")
    if row.organization_id != order.organization_id or row.facility_id != order.facility_id:
        raise ValueError("Production child organization/facility scope does not match its production order.")
    return order


def _status_before_flush(order: ProductionOrder) -> str:
    history = inspect(order).attrs.status.history
    if history.deleted:
        return str(history.deleted[0] or "").casefold()
    return str(order.status or "").casefold()


def _measured_disposition(session: Session, order: ProductionOrder) -> tuple[float, float]:
    with session.no_autoflush:
        output = float(
            session.scalar(
                select(func.coalesce(func.sum(ProductionRunOutput.actual_quantity), 0.0)).where(
                    ProductionRunOutput.organization_id == order.organization_id,
                    ProductionRunOutput.facility_id == order.facility_id,
                    ProductionRunOutput.production_order_id == order.id,
                )
            )
            or 0.0
        )
        waste = float(
            session.scalar(
                select(func.coalesce(func.sum(ProductionRunEvent.waste_quantity), 0.0)).where(
                    ProductionRunEvent.organization_id == order.organization_id,
                    ProductionRunEvent.facility_id == order.facility_id,
                    ProductionRunEvent.production_order_id == order.id,
                    ProductionRunEvent.event_type == "waste",
                )
            )
            or 0.0
        )
    for pending in session.new:
        if (
            isinstance(pending, ProductionRunOutput)
            and pending.organization_id == order.organization_id
            and pending.facility_id == order.facility_id
            and pending.production_order_id == order.id
        ):
            output += max(0.0, float(pending.actual_quantity or 0.0))
        elif (
            isinstance(pending, ProductionRunEvent)
            and pending.organization_id == order.organization_id
            and pending.facility_id == order.facility_id
            and pending.production_order_id == order.id
        ):
            waste += max(0.0, float(pending.waste_quantity or 0.0))
    return output, waste


def _validate_run_event(session: Session, row: ProductionRunEvent) -> None:
    order = _order_for(session, row)
    before = _status_before_flush(order)
    if row.event_type == "completed" and before != "in_progress":
        raise ValueError("Production must be in progress before it can be completed.")
    if row.event_type == "release" and before != "on_hold":
        raise ValueError("A production release event requires the run to be on hold.")
    if before == "cancelled":
        raise ValueError("Cancelled production runs cannot accept execution events.")
    if before == "complete" and row.event_type in {"hold", "waste", "rework", "completed"}:
        raise ValueError("Completed production runs are closed to new execution-state changes.")
    if row.event_type == "completed":
        output, waste = _measured_disposition(session, order)
        if output <= 1e-9 and waste <= 1e-9:
            raise ValueError(
                "Production cannot be completed without measured output or explicit waste disposition."
            )


def _validate_output(session: Session, row: ProductionRunOutput) -> None:
    order = _order_for(session, row)
    product = _pending_or_persisted(session, Product, row.product_id)
    if product is None or product.organization_id != order.organization_id:
        raise ValueError("Production output Product Master scope does not match the production order.")
    if row.lot_id:
        lot = _pending_or_persisted(session, InventoryLot, row.lot_id)
        if lot is None:
            raise ValueError("Production output references a missing inventory lot.")
        if lot.organization_id != order.organization_id or lot.facility_id != order.facility_id:
            raise ValueError("Production output lot scope does not match the production order.")
        if lot.product_id != row.product_id:
            raise ValueError("Production output lot product does not match the production output product.")


def _validate_qa(session: Session, row: ProductionQAEvent) -> None:
    order = _order_for(session, row)
    if not row.output_id:
        return
    output = _pending_or_persisted(session, ProductionRunOutput, row.output_id)
    if output is None:
        raise ValueError("Production QA event references a missing production output.")
    if output.production_order_id != order.id:
        raise ValueError("Production QA output is not part of the referenced production order.")
    if output.organization_id != row.organization_id or output.facility_id != row.facility_id:
        raise ValueError("Production QA output scope does not match the QA event scope.")


def _apply_event(session: Session, event_row: ProductionQAEvent) -> None:
    outputs: list[ProductionRunOutput] = []
    if event_row.output_id:
        output = _pending_or_persisted(session, ProductionRunOutput, event_row.output_id)
        if output is not None:
            outputs = [output]
    elif event_row.event_type == "release":
        with session.no_autoflush:
            outputs = list(
                session.scalars(
                    select(ProductionRunOutput).where(
                        ProductionRunOutput.organization_id == event_row.organization_id,
                        ProductionRunOutput.facility_id == event_row.facility_id,
                        ProductionRunOutput.production_order_id == event_row.production_order_id,
                        ProductionRunOutput.lot_id.is_not(None),
                    )
                )
            )
        outputs.extend(
            row
            for row in session.new
            if isinstance(row, ProductionRunOutput)
            and row.organization_id == event_row.organization_id
            and row.facility_id == event_row.facility_id
            and row.production_order_id == event_row.production_order_id
            and row.lot_id
            and row not in outputs
        )

    for output in outputs:
        if not output.lot_id:
            continue
        if output.organization_id != event_row.organization_id or output.facility_id != event_row.facility_id:
            raise ValueError("QA evidence cannot cross organization/facility boundaries.")
        lot = _pending_or_persisted(session, InventoryLot, output.lot_id)
        if lot is None or lot.organization_id != event_row.organization_id or lot.facility_id != event_row.facility_id:
            raise ValueError("QA evidence target lot is outside the QA event scope.")
        previous = LotQualityService.read(session, output.lot_id)
        reference = str(event_row.document_reference or (previous.coa_reference if previous else "")).strip()
        if event_row.result == "passed" and reference:
            LotQualityService.set_evidence(
                session,
                lot_id=output.lot_id,
                lab_testing_state="Passed",
                coa_reference=reference,
                coa_url=previous.coa_url if previous else "",
                thca_percent=previous.thca_percent if previous else None,
                tac_percent=previous.tac_percent if previous else None,
                total_terpenes_percent=previous.total_terpenes_percent if previous else None,
                evidence_source="production_qa",
                actor=event_row.actor,
            )
        elif event_row.result == "failed":
            LotQualityService.set_evidence(
                session,
                lot_id=output.lot_id,
                lab_testing_state="Failed",
                coa_reference=reference,
                evidence_source="production_qa",
                actor=event_row.actor,
            )


def _before_flush(session: Session, _flush_context, _instances) -> None:
    for row in list(session.new):
        if isinstance(row, ProductionRunEvent):
            _validate_run_event(session, row)
        elif isinstance(row, ProductionRunOutput):
            _validate_output(session, row)
        elif isinstance(row, ProductionQAEvent):
            _validate_qa(session, row)
            _apply_event(session, row)
        elif isinstance(row, ProductionCostEvent):
            _order_for(session, row)


def register_hardening_hooks() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    event.listen(Session, "before_flush", _before_flush)
    _REGISTERED = True


register_hardening_hooks()
