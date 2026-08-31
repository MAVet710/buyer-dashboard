"""Fail-closed integrity guards for canonical Co-Man operational records.

The application deliberately stores organization/facility scope on durable child
records so every operational query can be tenant-safe.  Foreign keys alone do
not guarantee that those scope columns agree with the referenced lot/order.
These hooks reject mismatched writes before they can poison inventory, production
closeout, QA, or compliance decisions.
"""

from __future__ import annotations

import math

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from .models import (
    Facility,
    InventoryLot,
    InventoryTransaction,
    MaterialReservation,
    OrderLotAllocation,
    Product,
    ProductionActual,
    ProductionOrder,
)

_REGISTERED = False
_ACTIVE_ALLOCATION_STATUSES = {"reserved", "partial"}


def _pending_or_persisted(session: Session, model, object_id: str | None):
    if not object_id:
        return None
    for row in session.new:
        if isinstance(row, model) and getattr(row, "id", None) == object_id:
            return row
    with session.no_autoflush:
        return session.get(model, object_id)


def _require_scope(*, row, parent, label: str) -> None:
    if parent is None:
        raise ValueError(f"{label} reference was not found.")
    if getattr(parent, "organization_id", None) != getattr(row, "organization_id", None):
        raise ValueError(f"{label} organization does not match the child record scope.")
    parent_facility = getattr(parent, "facility_id", None)
    row_facility = getattr(row, "facility_id", None)
    if parent_facility is not None and row_facility is not None and parent_facility != row_facility:
        raise ValueError(f"{label} facility does not match the child record scope.")


def _active_claims(session: Session, lot_id: str, organization_id: str, facility_id: str) -> float:
    with session.no_autoflush:
        production = float(
            session.scalar(
                select(func.coalesce(func.sum(MaterialReservation.quantity), 0.0)).where(
                    MaterialReservation.organization_id == organization_id,
                    MaterialReservation.facility_id == facility_id,
                    MaterialReservation.lot_id == lot_id,
                    MaterialReservation.status == "reserved",
                )
            )
            or 0.0
        )
        wholesale = float(
            session.scalar(
                select(
                    func.coalesce(
                        func.sum(OrderLotAllocation.quantity - OrderLotAllocation.fulfilled_quantity),
                        0.0,
                    )
                ).where(
                    OrderLotAllocation.organization_id == organization_id,
                    OrderLotAllocation.facility_id == facility_id,
                    OrderLotAllocation.lot_id == lot_id,
                    OrderLotAllocation.status.in_(_ACTIVE_ALLOCATION_STATUSES),
                )
            )
            or 0.0
        )
    for row in session.new:
        if (
            isinstance(row, MaterialReservation)
            and row.organization_id == organization_id
            and row.facility_id == facility_id
            and row.lot_id == lot_id
            and row.status == "reserved"
        ):
            production += max(0.0, float(row.quantity or 0.0))
        elif (
            isinstance(row, OrderLotAllocation)
            and row.organization_id == organization_id
            and row.facility_id == facility_id
            and row.lot_id == lot_id
            and row.status in _ACTIVE_ALLOCATION_STATUSES
        ):
            wholesale += max(0.0, float(row.quantity or 0.0) - float(row.fulfilled_quantity or 0.0))
    return max(0.0, production) + max(0.0, wholesale)


def _physical_balance(session: Session, lot_id: str, organization_id: str, facility_id: str) -> float:
    with session.no_autoflush:
        balance = float(
            session.scalar(
                select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                    InventoryTransaction.organization_id == organization_id,
                    InventoryTransaction.facility_id == facility_id,
                    InventoryTransaction.lot_id == lot_id,
                )
            )
            or 0.0
        )
    for row in session.new:
        if (
            isinstance(row, InventoryTransaction)
            and row.organization_id == organization_id
            and row.facility_id == facility_id
            and row.lot_id == lot_id
        ):
            balance += float(row.quantity_delta or 0.0)
    return balance


def _validate_lot(session: Session, lot: InventoryLot) -> None:
    facility = _pending_or_persisted(session, Facility, lot.facility_id)
    _require_scope(row=lot, parent=facility, label="Inventory lot facility")
    product = _pending_or_persisted(session, Product, lot.product_id)
    if product is None or product.organization_id != lot.organization_id:
        raise ValueError("Inventory lot product does not belong to the lot organization.")


def _validate_transaction(session: Session, tx: InventoryTransaction) -> None:
    delta = float(tx.quantity_delta or 0.0)
    if not math.isfinite(delta) or abs(delta) <= 1e-12:
        raise ValueError("Inventory ledger quantity must be a finite non-zero movement.")
    lot = _pending_or_persisted(session, InventoryLot, tx.lot_id)
    _require_scope(row=tx, parent=lot, label="Inventory transaction lot")
    if tx.production_order_id:
        order = _pending_or_persisted(session, ProductionOrder, tx.production_order_id)
        _require_scope(row=tx, parent=order, label="Inventory transaction production order")
    if tx.transaction_type == "inventory_adjustment" and delta < 0:
        projected = _physical_balance(session, tx.lot_id, tx.organization_id, tx.facility_id)
        claims = _active_claims(session, tx.lot_id, tx.organization_id, tx.facility_id)
        if projected + 1e-9 < claims:
            raise ValueError(
                "Inventory adjustment would reduce physical stock below active Production/Wholesale commitments. "
                "Release or reconcile those commitments first."
            )


def _validate_reservation(session: Session, reservation: MaterialReservation) -> None:
    if reservation.status == "reserved" and float(reservation.quantity or 0.0) <= 0:
        raise ValueError("Active material reservations must have a positive quantity.")
    lot = _pending_or_persisted(session, InventoryLot, reservation.lot_id)
    order = _pending_or_persisted(session, ProductionOrder, reservation.production_order_id)
    _require_scope(row=reservation, parent=lot, label="Material reservation lot")
    _require_scope(row=reservation, parent=order, label="Material reservation production order")


def _validate_actual(session: Session, actual: ProductionActual) -> None:
    order = _pending_or_persisted(session, ProductionOrder, actual.production_order_id)
    _require_scope(row=actual, parent=order, label="Production actual order")


def _before_flush(session: Session, _flush_context, _instances) -> None:
    candidates = list(session.new) + list(session.dirty)
    for row in candidates:
        if isinstance(row, InventoryLot):
            _validate_lot(session, row)
        elif isinstance(row, InventoryTransaction):
            _validate_transaction(session, row)
        elif isinstance(row, MaterialReservation):
            _validate_reservation(session, row)
        elif isinstance(row, ProductionActual):
            _validate_actual(session, row)


def register_integrity_hooks() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    event.listen(Session, "before_flush", _before_flush)
    _REGISTERED = True


register_integrity_hooks()
