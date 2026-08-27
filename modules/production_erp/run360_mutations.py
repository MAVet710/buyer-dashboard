"""Production Run 360 mutation semantics layered on the generic preview engine."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryLot, ProductionOrder
from modules.production_erp.models import ProductionQAEvent, ProductionRunEvent, ProductionRunOutput
from modules.production_erp.mutations import ProductionMutationService


class ProductionRun360MutationService(ProductionMutationService):
    """Keep QA state changes attached to material that actually exists.

    A whole-run QA hold still records an auditable run-level QA event and moves
    the order on hold, but untouched planned output rows are not inventory and
    must not be converted to quarantine merely because they are part of the
    plan. Realized/WIP/quarantine/released/rework outputs remain in scope.
    """

    @staticmethod
    def _realized_output(output: ProductionRunOutput) -> bool:
        return bool(
            float(output.actual_quantity or 0) > 0
            or output.lot_id
            or output.status != "planned"
        )

    def _preview_qa(
        self,
        session: Session,
        order: ProductionOrder,
        payload: dict[str, Any],
        *,
        lock: bool,
    ) -> dict[str, Any]:
        preview = super()._preview_qa(session, order, payload, lock=lock)
        output_id = str(payload.get("output_id") or "").strip() or None
        event_type = str(payload.get("event_type") or "").strip()
        result = str(payload.get("result") or "pending").strip()

        query = select(ProductionRunOutput).where(ProductionRunOutput.production_order_id == order.id)
        if output_id:
            query = query.where(ProductionRunOutput.id == output_id)
        outputs = list(session.scalars(query))
        realized = [row for row in outputs if self._realized_output(row)]

        if event_type == "hold" or result == "failed":
            non_output_consequences = [
                row
                for row in preview["consequences"]
                if row.get("after") != "Quarantine / unavailable"
            ]
            preview["consequences"] = non_output_consequences + [
                {
                    "label": row.label,
                    "before": str(row.status).replace("_", " ").title(),
                    "after": "Quarantine / unavailable",
                }
                for row in realized
                if row.status not in {"waste", "destroyed"}
            ]
            preview["details"]["target_output_ids"] = sorted(row.id for row in realized)
        elif event_type == "release" and result == "passed":
            releasable = [row for row in realized if row.status in {"quarantine", "rework"}]
            preview["details"]["target_output_ids"] = sorted(row.id for row in releasable)
            if not releasable:
                preview["warnings"] = [
                    row
                    for row in preview["warnings"]
                    if "no production output rows" not in str(row.get("message") or "").casefold()
                ]
                preview["warnings"].append(
                    {
                        "severity": "warning",
                        "message": "There are no realized quarantined/rework outputs to release; this will only record the QA decision.",
                    }
                )
        return preview

    @staticmethod
    def _apply_qa(
        session: Session,
        organization_id: str,
        facility_id: str,
        order: ProductionOrder,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        output_id = str(payload.get("output_id") or "").strip() or None
        event_type = str(payload.get("event_type") or "").strip()
        result = str(payload.get("result") or "pending").strip()
        event = ProductionQAEvent(
            organization_id=organization_id,
            facility_id=facility_id,
            production_order_id=order.id,
            output_id=output_id,
            event_type=event_type,
            result=result,
            document_reference=str(payload.get("document_reference") or ""),
            notes=str(payload.get("notes") or ""),
            actor=actor,
        )
        session.add(event)
        outputs_query = select(ProductionRunOutput).where(ProductionRunOutput.production_order_id == order.id)
        if output_id:
            outputs_query = outputs_query.where(ProductionRunOutput.id == output_id)
        outputs = [
            row
            for row in session.scalars(outputs_query)
            if ProductionRun360MutationService._realized_output(row)
        ]
        if event_type == "hold" or result == "failed":
            order.status = "on_hold"
            for output in outputs:
                if output.status not in {"waste", "destroyed"}:
                    output.status = "quarantine"
                if output.lot_id:
                    lot = session.get(InventoryLot, output.lot_id)
                    if lot:
                        lot.status = "quarantine"
                        lot.location_code = "QA-HOLD"
        elif event_type == "release" and result == "passed":
            for output in outputs:
                if output.status in {"quarantine", "rework"}:
                    output.status = "released"
                    if output.lot_id:
                        lot = session.get(InventoryLot, output.lot_id)
                        if lot:
                            lot.status = "available"
                            if lot.location_code == "QA-HOLD":
                                lot.location_code = "UNASSIGNED"
            if order.status == "on_hold":
                completed = session.scalar(
                    select(ProductionRunEvent.id).where(
                        ProductionRunEvent.production_order_id == order.id,
                        ProductionRunEvent.event_type == "completed",
                    ).limit(1)
                )
                order.status = "complete" if completed else "in_progress"
        session.flush()
        return {
            "qa_event_id": event.id,
            "event_type": event_type,
            "result": result,
            "output_id": output_id,
            "order_status": order.status,
            "affected_output_ids": [row.id for row in outputs],
        }
