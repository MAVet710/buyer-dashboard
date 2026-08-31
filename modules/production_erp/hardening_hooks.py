"""Keep Production Run 360 QA aligned with canonical lot-quality evidence."""

from __future__ import annotations

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from modules.inventory_quality.service import LotQualityService

from .models import ProductionQAEvent, ProductionRunOutput


_REGISTERED = False


def _apply_event(session: Session, event_row: ProductionQAEvent) -> None:
    outputs: list[ProductionRunOutput] = []
    if event_row.output_id:
        output = session.get(ProductionRunOutput, event_row.output_id)
        if output is not None:
            outputs = [output]
    elif event_row.event_type == "release":
        with session.no_autoflush:
            outputs = list(
                session.scalars(
                    select(ProductionRunOutput).where(
                        ProductionRunOutput.production_order_id == event_row.production_order_id,
                        ProductionRunOutput.lot_id.is_not(None),
                    )
                )
            )

    for output in outputs:
        if not output.lot_id:
            continue
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
        if isinstance(row, ProductionQAEvent):
            _apply_event(session, row)


def register_hardening_hooks() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    event.listen(Session, "before_flush", _before_flush)
    _REGISTERED = True


register_hardening_hooks()
