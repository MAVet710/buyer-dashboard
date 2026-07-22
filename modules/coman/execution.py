"""Atomic production execution for reserved Co-Man inventory."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    AuditEvent,
    InventoryLot,
    InventoryTransaction,
    MaterialReservation,
    Product,
    ProductionActual,
    ProductionOrder,
    utc_now,
)


@dataclass(frozen=True)
class ProductionStartResult:
    production_order_id: str
    reservations_consumed: int
    inventory_transactions_posted: int


@dataclass(frozen=True)
class ProductionFinishResult:
    production_order_id: str
    output_lot_id: str
    output_quantity: float


class ProductionExecutionService:
    """Convert reservations into auditable consumption and finished output."""

    def __init__(self, engine: Engine):
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @staticmethod
    def _balance(session: Session, lot_id: str) -> float:
        return float(
            session.scalar(
                select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                    InventoryTransaction.lot_id == lot_id
                )
            )
            or 0.0
        )

    @staticmethod
    def _order(session: Session, order_id: str, organization_id: str, facility_id: str) -> ProductionOrder:
        order = session.get(ProductionOrder, order_id)
        if not order or order.organization_id != organization_id or order.facility_id != facility_id:
            raise ValueError("Production order was not found in this facility.")
        return order

    @staticmethod
    def _audit(
        session: Session,
        *,
        organization_id: str,
        facility_id: str,
        entity_type: str,
        entity_id: str,
        action: str,
        actor: str,
        changes: dict,
    ) -> None:
        session.add(
            AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor=actor,
                changes_json=json.dumps(changes),
            )
        )

    def release_reservation(
        self,
        reservation_id: str,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        reason: str = "",
    ) -> MaterialReservation:
        with self._sessions.begin() as session:
            reservation = session.get(MaterialReservation, reservation_id)
            if not reservation or reservation.organization_id != organization_id or reservation.facility_id != facility_id:
                raise ValueError("Material reservation was not found in this facility.")
            if reservation.status != "reserved":
                raise ValueError("Only active reservations can be released.")
            reservation.status = "released"
            self._audit(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="material_reservation",
                entity_id=reservation.id,
                action="released",
                actor=actor,
                changes={
                    "production_order_id": reservation.production_order_id,
                    "lot_id": reservation.lot_id,
                    "quantity": reservation.quantity,
                    "unit": reservation.unit,
                    "reason": str(reason or ""),
                },
            )
            return reservation

    def release_order_reservations(
        self,
        production_order_id: str,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        reason: str = "",
    ) -> int:
        with self._sessions.begin() as session:
            self._order(session, production_order_id, organization_id, facility_id)
            reservations = list(
                session.scalars(
                    select(MaterialReservation).where(
                        MaterialReservation.production_order_id == production_order_id,
                        MaterialReservation.organization_id == organization_id,
                        MaterialReservation.facility_id == facility_id,
                        MaterialReservation.status == "reserved",
                    )
                )
            )
            for reservation in reservations:
                reservation.status = "released"
                self._audit(
                    session,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="material_reservation",
                    entity_id=reservation.id,
                    action="released",
                    actor=actor,
                    changes={
                        "production_order_id": production_order_id,
                        "lot_id": reservation.lot_id,
                        "quantity": reservation.quantity,
                        "unit": reservation.unit,
                        "reason": str(reason or ""),
                    },
                )
            return len(reservations)

    def start_production(
        self,
        production_order_id: str,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
    ) -> ProductionStartResult:
        with self._sessions.begin() as session:
            order = self._order(session, production_order_id, organization_id, facility_id)
            if order.status in {"complete", "cancelled"}:
                raise ValueError("Completed or cancelled orders cannot be started.")
            reservations = list(
                session.scalars(
                    select(MaterialReservation).where(
                        MaterialReservation.production_order_id == production_order_id,
                        MaterialReservation.organization_id == organization_id,
                        MaterialReservation.facility_id == facility_id,
                        MaterialReservation.status == "reserved",
                    )
                )
            )
            if not reservations:
                raise ValueError("Reserve material before starting production.")

            lots: dict[str, InventoryLot] = {}
            for reservation in reservations:
                lot = session.get(InventoryLot, reservation.lot_id)
                if not lot or lot.organization_id != organization_id or lot.facility_id != facility_id:
                    raise ValueError("A reserved inventory lot is no longer available.")
                if self._balance(session, lot.id) + 1e-9 < float(reservation.quantity):
                    raise ValueError(f"Lot {lot.lot_code} no longer has enough inventory to satisfy its reservation.")
                lots[lot.id] = lot

            for reservation in reservations:
                lot = lots[reservation.lot_id]
                session.add(
                    InventoryTransaction(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        lot_id=lot.id,
                        transaction_type="production_consume",
                        quantity_delta=-float(reservation.quantity),
                        unit=reservation.unit,
                        production_order_id=production_order_id,
                        reason="Consumed reserved material at production start",
                        reference=order.order_number,
                        actor=actor,
                    )
                )
                reservation.status = "consumed"
                self._audit(
                    session,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="material_reservation",
                    entity_id=reservation.id,
                    action="consumed",
                    actor=actor,
                    changes={"production_order_id": production_order_id, "lot_code": lot.lot_code, "quantity": reservation.quantity, "unit": reservation.unit},
                )

            previous = order.status
            order.status = "in_progress"
            order.updated_by = actor
            self._audit(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="production_order",
                entity_id=order.id,
                action="production_started",
                actor=actor,
                changes={"from": previous, "to": "in_progress", "reservations_consumed": len(reservations)},
            )
            return ProductionStartResult(order.id, len(reservations), len(reservations))

    def finish_production(
        self,
        production_order_id: str,
        *,
        organization_id: str,
        facility_id: str,
        output_product_id: str,
        output_lot_code: str,
        output_quantity: float,
        output_unit: str,
        actual_units: int,
        scrap_units: int,
        rework_units: int,
        actual_machine_hours: float,
        actual_labor_hours: float,
        actor: str,
        location_code: str = "FINISHED-GOODS",
        compliance_package_id: str = "",
        notes: str = "",
    ) -> ProductionFinishResult:
        if float(output_quantity) <= 0:
            raise ValueError("Finished output quantity must be greater than zero.")
        if any(value < 0 for value in (int(actual_units), int(scrap_units), int(rework_units))):
            raise ValueError("Actual, scrap, and rework units cannot be negative.")
        if float(actual_machine_hours) < 0 or float(actual_labor_hours) < 0:
            raise ValueError("Actual production hours cannot be negative.")
        lot_code = str(output_lot_code or "").strip()
        if not lot_code:
            raise ValueError("A finished-goods lot code is required.")

        with self._sessions.begin() as session:
            order = self._order(session, production_order_id, organization_id, facility_id)
            if order.status != "in_progress":
                raise ValueError("Production must be in progress before it can be finished.")
            product = session.get(Product, output_product_id)
            if not product or product.organization_id != organization_id or product.item_type not in {"wip", "finished_good"}:
                raise ValueError("A WIP or finished-good output product is required.")
            if session.scalar(select(InventoryLot.id).where(InventoryLot.facility_id == facility_id, InventoryLot.lot_code == lot_code)):
                raise ValueError("That finished-goods lot code already exists in this facility.")

            lot = InventoryLot(
                organization_id=organization_id,
                facility_id=facility_id,
                product_id=product.id,
                lot_code=lot_code,
                compliance_package_id=str(compliance_package_id or ""),
                location_code=str(location_code or "FINISHED-GOODS").strip().upper(),
                status="available",
                received_at=utc_now(),
                notes=str(notes or ""),
            )
            session.add(lot)
            session.flush()
            unit = str(output_unit or product.base_unit)
            session.add(
                InventoryTransaction(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    lot_id=lot.id,
                    transaction_type="production_output",
                    quantity_delta=float(output_quantity),
                    unit=unit,
                    production_order_id=order.id,
                    reason="Finished production output",
                    reference=order.order_number,
                    actor=actor,
                )
            )
            actual = session.scalar(select(ProductionActual).where(ProductionActual.production_order_id == order.id))
            if actual is None:
                actual = ProductionActual(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    production_order_id=order.id,
                    recorded_by=actor,
                )
                session.add(actual)
            actual.actual_units = int(actual_units)
            actual.scrap_units = int(scrap_units)
            actual.rework_units = int(rework_units)
            actual.actual_machine_hours = float(actual_machine_hours)
            actual.actual_labor_hours = float(actual_labor_hours)
            actual.completed_at = utc_now()
            actual.notes = str(notes or "")
            actual.recorded_by = actor
            order.status = "complete"
            order.updated_by = actor
            self._audit(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="production_order",
                entity_id=order.id,
                action="production_finished",
                actor=actor,
                changes={
                    "output_lot_id": lot.id,
                    "output_lot_code": lot.lot_code,
                    "output_product_id": product.id,
                    "output_quantity": float(output_quantity),
                    "output_unit": unit,
                    "actual_units": int(actual_units),
                    "scrap_units": int(scrap_units),
                    "rework_units": int(rework_units),
                },
            )
            return ProductionFinishResult(order.id, lot.id, float(output_quantity))
