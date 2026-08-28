"""One inventory-availability truth shared by Production, Wholesale, and Active Inventory."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import (
    CommercialOrder,
    CommercialOrderLine,
    InventoryLot,
    InventoryTransaction,
    MaterialReservation,
    OrderLotAllocation,
    Product,
    ProductionOrder,
    TradePartner,
)

_ACTIVE_LOT_STATUSES = {"available", "released"}
_ACTIVE_SALES_STATUSES = {"confirmed", "allocated", "partially_fulfilled"}
_ACTIVE_ALLOCATION_STATUSES = {"reserved", "partial"}
_PASSED_LAB_STATES = {"passed", "testpassed", "released", "pass"}


def _metadata(lot: InventoryLot) -> dict[str, Any]:
    try:
        value = json.loads(lot.notes or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _lab_state(value: Any) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _passed_coa_hint(lot: InventoryLot) -> bool:
    meta = _metadata(lot)
    return bool(str(meta.get("coa_reference") or "").strip()) and _lab_state(meta.get("lab_testing_state")) in _PASSED_LAB_STATES


class InventoryAvailabilityService:
    """Project physical inventory after every active organizational claim.

    Physical balance remains append-only in InventoryTransaction. This service layers
    active Production reservations, hard Commercial lot allocations, and unallocated
    confirmed sales commitments on top of that ledger so every workspace sees the
    same usable quantity without creating a second inventory table.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def facility_snapshot(self, organization_id: str, facility_id: str) -> dict[str, Any]:
        with self._sessions() as session:
            return self.build(session, organization_id, facility_id)

    @staticmethod
    def build(session: Session, organization_id: str, facility_id: str) -> dict[str, Any]:
        lots = list(session.scalars(select(InventoryLot).where(
            InventoryLot.organization_id == organization_id,
            InventoryLot.facility_id == facility_id,
        ).order_by(InventoryLot.received_at.asc().nullsfirst(), InventoryLot.lot_code.asc())))
        product_ids = {row.product_id for row in lots}
        products = {
            row.id: row
            for row in session.scalars(select(Product).where(
                Product.organization_id == organization_id,
                Product.id.in_(product_ids),
            ))
        } if product_ids else {}

        balances = {
            lot_id: float(quantity or 0.0)
            for lot_id, quantity in session.execute(
                select(
                    InventoryTransaction.lot_id,
                    func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0),
                ).where(
                    InventoryTransaction.organization_id == organization_id,
                    InventoryTransaction.facility_id == facility_id,
                ).group_by(InventoryTransaction.lot_id)
            ).all()
        }

        production_orders = {
            row.id: row
            for row in session.scalars(select(ProductionOrder).where(
                ProductionOrder.organization_id == organization_id,
                ProductionOrder.facility_id == facility_id,
            ))
        }
        production_reservations = list(session.scalars(select(MaterialReservation).where(
            MaterialReservation.organization_id == organization_id,
            MaterialReservation.facility_id == facility_id,
            MaterialReservation.status == "reserved",
        )))

        sales_orders = list(session.scalars(select(CommercialOrder).where(
            CommercialOrder.organization_id == organization_id,
            CommercialOrder.facility_id == facility_id,
            CommercialOrder.order_type == "sales",
            CommercialOrder.status.in_(_ACTIVE_SALES_STATUSES),
        )))
        sales_order_by_id = {row.id: row for row in sales_orders}
        sales_order_ids = set(sales_order_by_id)
        sales_lines = list(session.scalars(select(CommercialOrderLine).where(
            CommercialOrderLine.organization_id == organization_id,
            CommercialOrderLine.commercial_order_id.in_(sales_order_ids),
        ))) if sales_order_ids else []
        sales_line_by_id = {row.id: row for row in sales_lines}

        allocations = list(session.scalars(select(OrderLotAllocation).where(
            OrderLotAllocation.organization_id == organization_id,
            OrderLotAllocation.facility_id == facility_id,
            OrderLotAllocation.status.in_(_ACTIVE_ALLOCATION_STATUSES),
        )))
        partners = {
            row.id: row
            for row in session.scalars(select(TradePartner).where(TradePartner.organization_id == organization_id))
        }

        production_reserved_by_lot: dict[str, float] = defaultdict(float)
        wholesale_reserved_by_lot: dict[str, float] = defaultdict(float)
        allocated_by_line: dict[str, float] = defaultdict(float)
        claims_by_lot: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for reservation in production_reservations:
            quantity = max(0.0, float(reservation.quantity or 0.0))
            production_reserved_by_lot[reservation.lot_id] += quantity
            order = production_orders.get(reservation.production_order_id)
            claims_by_lot[reservation.lot_id].append({
                "source": "production",
                "claim_type": "reserved",
                "quantity": quantity,
                "reference_id": reservation.production_order_id,
                "reference": getattr(order, "order_number", reservation.production_order_id),
                "label": f"Production {getattr(order, 'order_number', reservation.production_order_id)}",
            })

        for allocation in allocations:
            remaining = max(0.0, float(allocation.quantity or 0.0) - float(allocation.fulfilled_quantity or 0.0))
            if remaining <= 0:
                continue
            wholesale_reserved_by_lot[allocation.lot_id] += remaining
            allocated_by_line[allocation.commercial_order_line_id] += remaining
            order = sales_order_by_id.get(allocation.commercial_order_id)
            partner = partners.get(getattr(order, "partner_id", "")) if order else None
            claims_by_lot[allocation.lot_id].append({
                "source": "wholesale",
                "claim_type": "lot_reserved",
                "quantity": remaining,
                "reference_id": allocation.commercial_order_id,
                "reference": getattr(order, "order_number", allocation.commercial_order_id),
                "customer": getattr(partner, "name", ""),
                "label": f"Wholesale {getattr(order, 'order_number', allocation.commercial_order_id)}",
            })

        lot_rows: dict[str, dict[str, Any]] = {}
        lots_by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for lot in lots:
            on_hand = max(0.0, balances.get(lot.id, 0.0))
            production_reserved = max(0.0, production_reserved_by_lot.get(lot.id, 0.0))
            wholesale_reserved = max(0.0, wholesale_reserved_by_lot.get(lot.id, 0.0))
            active = str(lot.status or "").casefold() in _ACTIVE_LOT_STATUSES
            physical_free = max(0.0, on_hand - production_reserved - wholesale_reserved) if active else 0.0
            row = {
                "lot": lot,
                "product": products.get(lot.product_id),
                "on_hand": on_hand,
                "production_reserved": production_reserved,
                "wholesale_reserved": wholesale_reserved,
                "wholesale_committed": 0.0,
                "reserved": production_reserved + wholesale_reserved,
                "available": physical_free,
                "physical_free": physical_free,
                "claims": list(claims_by_lot.get(lot.id, [])),
                "active": active,
            }
            lot_rows[lot.id] = row
            lots_by_product[lot.product_id].append(row)

        soft_commitments: list[dict[str, Any]] = []
        for line in sales_lines:
            order = sales_order_by_id.get(line.commercial_order_id)
            if not order:
                continue
            remaining_line = max(0.0, float(line.quantity or 0.0) - float(line.fulfilled_quantity or 0.0))
            unallocated = max(0.0, remaining_line - allocated_by_line.get(line.id, 0.0))
            if unallocated <= 0:
                continue
            partner = partners.get(order.partner_id)
            soft_commitments.append({
                "line_id": line.id,
                "product_id": line.product_id,
                "quantity": unallocated,
                "order_id": order.id,
                "order_number": order.order_number,
                "customer": getattr(partner, "name", ""),
                "status": order.status,
                "due_at": order.due_at,
                "created_at": order.created_at,
            })

        soft_commitments.sort(key=lambda row: (
            str(row.get("due_at") or "9999-12-31"),
            str(row.get("created_at") or ""),
            str(row.get("order_number") or ""),
        ))
        uncovered_by_product: dict[str, float] = defaultdict(float)
        for commitment in soft_commitments:
            remaining = float(commitment["quantity"])
            candidates = sorted(
                lots_by_product.get(commitment["product_id"], []),
                key=lambda row: (
                    0 if _passed_coa_hint(row["lot"]) else 1,
                    str(row["lot"].expiration_at or "9999-12-31"),
                    str(row["lot"].received_at or "9999-12-31"),
                    row["lot"].lot_code,
                ),
            )
            for row in candidates:
                room = max(0.0, float(row["physical_free"]) - float(row["wholesale_committed"]))
                if room <= 0 or remaining <= 0:
                    continue
                claimed = min(room, remaining)
                row["wholesale_committed"] += claimed
                row["claims"].append({
                    "source": "wholesale",
                    "claim_type": "committed",
                    "quantity": claimed,
                    "reference_id": commitment["order_id"],
                    "reference": commitment["order_number"],
                    "customer": commitment["customer"],
                    "label": f"Wholesale {commitment['order_number']}",
                })
                remaining -= claimed
            if remaining > 1e-9:
                uncovered_by_product[commitment["product_id"]] += remaining

        by_product: dict[str, dict[str, Any]] = {}
        for product_id, product_lots in lots_by_product.items():
            on_hand = sum(float(row["on_hand"]) for row in product_lots)
            production_reserved = sum(float(row["production_reserved"]) for row in product_lots)
            wholesale_reserved = sum(float(row["wholesale_reserved"]) for row in product_lots)
            wholesale_committed = sum(float(row["wholesale_committed"]) for row in product_lots)
            for row in product_lots:
                row["reserved"] = row["production_reserved"] + row["wholesale_reserved"] + row["wholesale_committed"]
                row["available"] = max(0.0, row["on_hand"] - row["reserved"]) if row["active"] else 0.0
            by_product[product_id] = {
                "product_id": product_id,
                "on_hand": on_hand,
                "production_reserved": production_reserved,
                "wholesale_reserved": wholesale_reserved,
                "wholesale_committed": wholesale_committed,
                "reserved": production_reserved + wholesale_reserved + wholesale_committed,
                "available": sum(float(row["available"]) for row in product_lots),
                "uncovered_commitment": float(uncovered_by_product.get(product_id, 0.0)),
            }

        return {
            "lots": list(lot_rows.values()),
            "by_lot": lot_rows,
            "by_product": by_product,
            "uncovered_commitments": dict(uncovered_by_product),
        }
