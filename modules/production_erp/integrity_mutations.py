"""P0 integrity policy for Production Run 360 mutations.

This layer keeps the existing consequence-preview engine, but refuses to reason
from child rows whose tenant scope disagrees with the production order and
prevents terminal/release states from being used as bookkeeping shortcuts.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryLot, InventoryTransaction, MaterialReservation, Product, ProductionOrder
from modules.production_erp.models import (
    ProductionCostEvent,
    ProductionQAEvent,
    ProductionRunEvent,
    ProductionRunOutput,
)
from modules.production_erp.run360_mutations import ProductionRun360MutationService


class ProductionIntegrityMutationService(ProductionRun360MutationService):
    """Fail closed on scope poison, illegal transitions, and incomplete closeout."""

    @staticmethod
    def _assert_scope(row, order: ProductionOrder, label: str) -> None:
        if row.organization_id != order.organization_id or row.facility_id != order.facility_id:
            raise ValueError(
                f"{label} has inconsistent organization/facility scope. Reconcile the durable record before continuing."
            )

    def _assert_order_children_scoped(self, session: Session, order: ProductionOrder) -> None:
        child_models = (
            (ProductionRunEvent, "Production run event"),
            (ProductionQAEvent, "Production QA event"),
            (ProductionRunOutput, "Production output"),
            (ProductionCostEvent, "Production cost event"),
            (MaterialReservation, "Material reservation"),
        )
        for model, label in child_models:
            rows = list(
                session.scalars(
                    select(model).where(model.production_order_id == order.id)
                )
            )
            for row in rows:
                self._assert_scope(row, order, label)
                if isinstance(row, ProductionRunOutput):
                    product = session.get(Product, row.product_id)
                    if product is None or product.organization_id != order.organization_id:
                        raise ValueError(
                            "Production output Product Master scope is inconsistent with the run. Reconcile it before continuing."
                        )
                    if row.lot_id:
                        lot = session.get(InventoryLot, row.lot_id)
                        if lot is None:
                            raise ValueError("Production output references a missing inventory lot.")
                        self._assert_scope(lot, order, "Production output inventory lot")

        transactions = list(
            session.scalars(
                select(InventoryTransaction).where(
                    InventoryTransaction.production_order_id == order.id
                )
            )
        )
        for row in transactions:
            self._assert_scope(row, order, "Production inventory transaction")
            lot = session.get(InventoryLot, row.lot_id)
            if lot is None:
                raise ValueError("Production inventory transaction references a missing lot.")
            self._assert_scope(lot, order, "Production inventory transaction lot")

    def _preview_reservations(
        self,
        session: Session,
        organization_id: str,
        facility_id: str,
        order: ProductionOrder,
        *,
        lock: bool,
    ) -> dict:
        self._assert_order_children_scoped(session, order)
        if order.status in {"complete", "cancelled"}:
            raise ValueError("Completed or cancelled production runs cannot reserve material.")
        return super()._preview_reservations(
            session,
            organization_id,
            facility_id,
            order,
            lock=lock,
        )

    def _preview_run_event(self, session: Session, order: ProductionOrder, payload: dict) -> dict:
        self._assert_order_children_scoped(session, order)
        event_type = str(payload.get("event_type") or "").strip()
        current = str(order.status or "").strip().casefold()

        if current == "cancelled":
            raise ValueError("Cancelled production runs cannot accept execution events.")
        if event_type == "completed" and current != "in_progress":
            raise ValueError("Production must be in progress before it can be completed.")
        if event_type == "release" and current != "on_hold":
            raise ValueError("A run release is only valid while the production run is on hold.")
        if event_type in {"hold", "waste", "rework"} and current == "complete":
            raise ValueError("Completed production runs are closed to new execution-state changes.")

        preview = super()._preview_run_event(session, order, payload)
        if event_type != "completed":
            return preview

        actual_output = float(
            session.scalar(
                select(func.coalesce(func.sum(ProductionRunOutput.actual_quantity), 0.0)).where(
                    ProductionRunOutput.organization_id == order.organization_id,
                    ProductionRunOutput.facility_id == order.facility_id,
                    ProductionRunOutput.production_order_id == order.id,
                )
            )
            or 0.0
        )
        measured_waste = float(
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
        measured_waste += float(payload.get("waste_quantity") or 0.0)
        if actual_output <= 1e-9 and measured_waste <= 1e-9:
            preview.setdefault("warnings", []).append(
                {
                    "severity": "blocker",
                    "message": (
                        "A production run cannot be completed with no measured output or waste disposition. "
                        "Record what physically happened before closeout."
                    ),
                }
            )
        return preview

    def _preview_output_actual(
        self,
        session: Session,
        facility_id: str,
        order: ProductionOrder,
        payload: dict,
        *,
        lock: bool,
    ) -> dict:
        self._assert_order_children_scoped(session, order)
        if str(order.status or "").casefold() not in {"in_progress", "on_hold"}:
            raise ValueError("Measured production output can only be posted while the run is in progress or on hold.")
        return super()._preview_output_actual(session, facility_id, order, payload, lock=lock)

    def _preview_qa(
        self,
        session: Session,
        order: ProductionOrder,
        payload: dict,
        *,
        lock: bool,
    ) -> dict:
        self._assert_order_children_scoped(session, order)
        preview = super()._preview_qa(session, order, payload, lock=lock)
        event_type = str(payload.get("event_type") or "").strip()
        result = str(payload.get("result") or "").strip()
        if event_type == "release" and result == "passed":
            standard = self._standard_for_order(session, order)
            document_reference = str(payload.get("document_reference") or "").strip()
            if bool(getattr(standard, "qa_required", False)) and not document_reference:
                preview["warnings"] = [
                    row
                    for row in preview.get("warnings", [])
                    if "Add the COA/document reference" not in str(row.get("message") or "")
                ]
                preview.setdefault("warnings", []).append(
                    {
                        "severity": "blocker",
                        "message": "This production standard requires QA evidence. Attach the COA/document reference before release.",
                    }
                )
        return preview

    def _preview_cost(self, session: Session, order: ProductionOrder, payload: dict) -> dict:
        self._assert_order_children_scoped(session, order)
        return super()._preview_cost(session, order, payload)

    def _preview_material_consumption(
        self,
        session: Session,
        *,
        organization_id: str,
        facility_id: str,
        order: ProductionOrder,
        payload: dict,
        lock: bool,
    ) -> dict:
        self._assert_order_children_scoped(session, order)
        if str(order.status or "").casefold() not in {"in_progress", "on_hold"}:
            raise ValueError("Actual material consumption can only be posted while the run is in progress or on hold.")
        return super()._preview_material_consumption(
            session,
            organization_id=organization_id,
            facility_id=facility_id,
            order=order,
            payload=payload,
            lock=lock,
        )
