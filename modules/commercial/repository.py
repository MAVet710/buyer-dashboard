"""Tenant-safe commercial order and inventory-ledger operations."""

from __future__ import annotations

from datetime import date, datetime, time
import json
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import (
    AuditEvent,
    CommercialOrder,
    CommercialOrderLine,
    Facility,
    InventoryLot,
    InventoryTransaction,
    Organization,
    OrderLotAllocation,
    Product,
    TradePartner,
    utc_now,
)


OPEN_ORDER_STATUSES = {
    "draft",
    "confirmed",
    "allocated",
    "partially_fulfilled",
}


class CommercialRepository:
    def __init__(self, engine: Engine):
        self._session_factory = sessionmaker(
            bind=engine,
            expire_on_commit=False,
            future=True,
        )

    def create_trade_partner(
        self,
        organization_id: str,
        *,
        name: str,
        partner_type: str,
        actor: str,
        **details: Any,
    ) -> TradePartner:
        normalized_type = str(partner_type).strip().lower()
        if normalized_type not in {"customer", "vendor", "both"}:
            raise ValueError("Partner type must be customer, vendor, or both.")
        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("Partner name is required.")
        partner = TradePartner(
            organization_id=organization_id,
            name=clean_name,
            partner_type=normalized_type,
            license_or_registration=str(details.get("license_or_registration") or ""),
            contact_name=str(details.get("contact_name") or ""),
            contact_email=str(details.get("contact_email") or ""),
            contact_phone=str(details.get("contact_phone") or ""),
            payment_terms=str(details.get("payment_terms") or "Net 30"),
        )
        with self._session_factory.begin() as session:
            self._require_organization(session, organization_id)
            session.add(partner)
            session.flush()
            self._audit(
                session,
                organization_id,
                None,
                "trade_partner",
                partner.id,
                "created",
                actor,
                {"partner_type": normalized_type, "name": clean_name},
            )
        return partner

    def list_trade_partners(
        self,
        organization_id: str,
        *,
        active_only: bool = True,
    ) -> list[TradePartner]:
        with self._session_factory() as session:
            statement = select(TradePartner).where(
                TradePartner.organization_id == organization_id
            )
            if active_only:
                statement = statement.where(TradePartner.active.is_(True))
            return list(session.scalars(statement.order_by(TradePartner.name)))

    def create_order(
        self,
        *,
        organization_id: str,
        facility_id: str,
        partner_id: str,
        order_number: str,
        order_type: str,
        order_date: date,
        due_date: date | None,
        lines: list[dict[str, Any]],
        actor: str,
        external_reference: str = "",
        notes: str = "",
    ) -> CommercialOrder:
        normalized_type = str(order_type).strip().lower()
        if normalized_type not in {"sales", "purchase"}:
            raise ValueError("Order type must be sales or purchase.")
        clean_number = str(order_number).strip().upper()
        if not clean_number:
            raise ValueError("Order number is required.")
        if not lines:
            raise ValueError("At least one order line is required.")

        with self._session_factory.begin() as session:
            facility = session.get(Facility, facility_id)
            if not facility or facility.organization_id != organization_id:
                raise ValueError("Facility does not belong to the organization.")
            partner = session.get(TradePartner, partner_id)
            if not partner or partner.organization_id != organization_id or not partner.active:
                raise ValueError("Trade partner was not found in this organization.")
            required_partner_type = "customer" if normalized_type == "sales" else "vendor"
            if partner.partner_type not in {required_partner_type, "both"}:
                raise ValueError(
                    f"{normalized_type.title()} orders require a {required_partner_type} partner."
                )

            order = CommercialOrder(
                organization_id=organization_id,
                facility_id=facility_id,
                partner_id=partner.id,
                order_number=clean_number,
                order_type=normalized_type,
                order_date=order_date,
                due_at=datetime.combine(due_date, time.min) if due_date else None,
                external_reference=str(external_reference or ""),
                notes=str(notes or ""),
                created_by=actor,
                updated_by=actor,
            )
            session.add(order)
            session.flush()

            for position, raw in enumerate(lines, start=1):
                product = session.get(Product, str(raw.get("product_id") or ""))
                if not product or product.organization_id != organization_id or not product.active:
                    raise ValueError("Every order line must use an active organization product.")
                quantity = float(raw.get("quantity") or 0)
                unit_price = float(raw.get("unit_price") or 0)
                if quantity <= 0:
                    raise ValueError("Order-line quantity must be greater than zero.")
                if unit_price < 0:
                    raise ValueError("Order-line price cannot be negative.")
                session.add(
                    CommercialOrderLine(
                        organization_id=organization_id,
                        commercial_order_id=order.id,
                        product_id=product.id,
                        position=position,
                        description=str(raw.get("description") or product.name),
                        sku_snapshot=product.sku,
                        quantity=quantity,
                        unit=str(raw.get("unit") or product.base_unit),
                        unit_price=unit_price,
                        notes=str(raw.get("notes") or ""),
                    )
                )

            self._audit(
                session,
                organization_id,
                facility_id,
                "commercial_order",
                order.id,
                "created",
                actor,
                {
                    "order_number": clean_number,
                    "order_type": normalized_type,
                    "partner_id": partner.id,
                    "line_count": len(lines),
                },
            )
        return order

    def list_orders(
        self,
        organization_id: str,
        facility_id: str,
        *,
        open_only: bool = False,
    ) -> list[CommercialOrder]:
        with self._session_factory() as session:
            statement = select(CommercialOrder).where(
                CommercialOrder.organization_id == organization_id,
                CommercialOrder.facility_id == facility_id,
            )
            if open_only:
                statement = statement.where(CommercialOrder.status.in_(OPEN_ORDER_STATUSES))
            return list(
                session.scalars(
                    statement.order_by(
                        CommercialOrder.due_at.is_(None),
                        CommercialOrder.due_at,
                        CommercialOrder.created_at.desc(),
                    )
                )
            )

    def list_order_lines(
        self,
        organization_id: str,
        *,
        order_id: str | None = None,
    ) -> list[CommercialOrderLine]:
        with self._session_factory() as session:
            statement = select(CommercialOrderLine).where(
                CommercialOrderLine.organization_id == organization_id
            )
            if order_id:
                statement = statement.where(
                    CommercialOrderLine.commercial_order_id == order_id
                )
            return list(
                session.scalars(
                    statement.order_by(
                        CommercialOrderLine.commercial_order_id,
                        CommercialOrderLine.position,
                    )
                )
            )

    def list_allocations(
        self,
        organization_id: str,
        facility_id: str,
        *,
        order_id: str | None = None,
    ) -> list[OrderLotAllocation]:
        with self._session_factory() as session:
            statement = select(OrderLotAllocation).where(
                OrderLotAllocation.organization_id == organization_id,
                OrderLotAllocation.facility_id == facility_id,
            )
            if order_id:
                statement = statement.where(
                    OrderLotAllocation.commercial_order_id == order_id
                )
            return list(
                session.scalars(statement.order_by(OrderLotAllocation.created_at))
            )

    def confirm_order(
        self,
        order_id: str,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
    ) -> CommercialOrder:
        return self._update_order_status(
            order_id,
            organization_id=organization_id,
            facility_id=facility_id,
            status="confirmed",
            actor=actor,
        )

    def cancel_order(
        self,
        order_id: str,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
    ) -> CommercialOrder:
        with self._session_factory.begin() as session:
            order = self._require_order(
                session,
                order_id,
                organization_id,
                facility_id,
            )
            if order.status == "fulfilled":
                raise ValueError("A fulfilled order cannot be cancelled.")
            order.status = "cancelled"
            order.updated_by = actor
            allocations = session.scalars(
                select(OrderLotAllocation).where(
                    OrderLotAllocation.commercial_order_id == order.id,
                    OrderLotAllocation.status.in_(["reserved", "partial"]),
                )
            )
            for allocation in allocations:
                allocation.status = "released"
            self._audit(
                session,
                organization_id,
                facility_id,
                "commercial_order",
                order.id,
                "cancelled",
                actor,
                {},
            )
            return order

    def set_payment_status(
        self,
        order_id: str,
        *,
        organization_id: str,
        facility_id: str,
        payment_status: str,
        actor: str,
    ) -> CommercialOrder:
        allowed = {"not_invoiced", "draft", "sent", "partial", "paid", "overdue"}
        normalized = str(payment_status).strip().lower()
        if normalized not in allowed:
            raise ValueError("Unsupported payment status.")
        with self._session_factory.begin() as session:
            order = self._require_order(
                session,
                order_id,
                organization_id,
                facility_id,
            )
            previous = order.payment_status
            order.payment_status = normalized
            order.updated_by = actor
            self._audit(
                session,
                organization_id,
                facility_id,
                "commercial_order",
                order.id,
                "payment_status_changed",
                actor,
                {"from": previous, "to": normalized},
            )
            return order

    def allocate_lot(
        self,
        *,
        organization_id: str,
        facility_id: str,
        order_line_id: str,
        lot_id: str,
        quantity: float,
        actor: str,
    ) -> OrderLotAllocation:
        requested = float(quantity)
        if requested <= 0:
            raise ValueError("Allocation quantity must be greater than zero.")
        with self._session_factory.begin() as session:
            line = session.get(CommercialOrderLine, order_line_id)
            if not line or line.organization_id != organization_id:
                raise ValueError("Order line was not found.")
            order = self._require_order(
                session,
                line.commercial_order_id,
                organization_id,
                facility_id,
            )
            if order.order_type != "sales":
                raise ValueError("Only sales orders reserve outbound lots.")
            if order.status not in OPEN_ORDER_STATUSES:
                raise ValueError("This order is not open for allocation.")
            lot = session.get(InventoryLot, lot_id)
            if (
                not lot
                or lot.organization_id != organization_id
                or lot.facility_id != facility_id
                or lot.product_id != line.product_id
                or lot.status not in {"available", "released"}
            ):
                raise ValueError("The lot is not an available match for this order line.")

            active_allocated = float(
                session.scalar(
                    select(
                        func.coalesce(
                            func.sum(
                                OrderLotAllocation.quantity
                                - OrderLotAllocation.fulfilled_quantity
                            ),
                            0.0,
                        )
                    ).where(
                        OrderLotAllocation.organization_id == organization_id,
                        OrderLotAllocation.facility_id == facility_id,
                        OrderLotAllocation.lot_id == lot_id,
                        OrderLotAllocation.status.in_(["reserved", "partial"]),
                    )
                )
                or 0.0
            )
            balance = self._lot_balance(session, organization_id, lot_id)
            if requested > balance - active_allocated + 1e-9:
                raise ValueError("Allocation exceeds unreserved lot inventory.")

            line_allocated = float(
                session.scalar(
                    select(func.coalesce(func.sum(OrderLotAllocation.quantity), 0.0)).where(
                        OrderLotAllocation.commercial_order_line_id == line.id,
                        OrderLotAllocation.status.in_(["reserved", "partial", "fulfilled"]),
                    )
                )
                or 0.0
            )
            if requested > line.quantity - line_allocated + 1e-9:
                raise ValueError("Allocation exceeds the remaining order-line quantity.")

            allocation = session.scalar(
                select(OrderLotAllocation).where(
                    OrderLotAllocation.commercial_order_line_id == line.id,
                    OrderLotAllocation.lot_id == lot.id,
                )
            )
            if allocation is None:
                allocation = OrderLotAllocation(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    commercial_order_id=order.id,
                    commercial_order_line_id=line.id,
                    lot_id=lot.id,
                    quantity=requested,
                    reserved_by=actor,
                )
                session.add(allocation)
            elif allocation.status == "released":
                allocation.quantity = requested
                allocation.fulfilled_quantity = 0.0
                allocation.status = "reserved"
                allocation.reserved_by = actor
            else:
                allocation.quantity += requested
                allocation.status = "reserved"

            order.status = "allocated"
            order.updated_by = actor
            session.flush()
            self._audit(
                session,
                organization_id,
                facility_id,
                "commercial_order",
                order.id,
                "lot_allocated",
                actor,
                {
                    "line_id": line.id,
                    "lot_id": lot.id,
                    "quantity": requested,
                },
            )
            return allocation

    def post_fulfillment(
        self,
        *,
        organization_id: str,
        facility_id: str,
        order_line_id: str,
        lot_id: str,
        quantity: float,
        actor: str,
        reference: str = "",
    ) -> InventoryTransaction:
        fulfilled = float(quantity)
        if fulfilled <= 0:
            raise ValueError("Fulfillment quantity must be greater than zero.")
        with self._session_factory.begin() as session:
            line = session.get(CommercialOrderLine, order_line_id)
            if not line or line.organization_id != organization_id:
                raise ValueError("Order line was not found.")
            order = self._require_order(
                session,
                line.commercial_order_id,
                organization_id,
                facility_id,
            )
            if order.status in {"draft", "cancelled", "fulfilled"}:
                raise ValueError("Confirm the order before posting fulfillment.")
            lot = session.get(InventoryLot, lot_id)
            if (
                not lot
                or lot.organization_id != organization_id
                or lot.facility_id != facility_id
                or lot.product_id != line.product_id
            ):
                raise ValueError("The selected lot does not match this order line.")
            if fulfilled > line.quantity - line.fulfilled_quantity + 1e-9:
                raise ValueError("Fulfillment exceeds the remaining order-line quantity.")

            allocation = None
            if order.order_type == "sales":
                allocation = session.scalar(
                    select(OrderLotAllocation).where(
                        OrderLotAllocation.commercial_order_line_id == line.id,
                        OrderLotAllocation.lot_id == lot.id,
                        OrderLotAllocation.status.in_(["reserved", "partial"]),
                    )
                )
                if (
                    allocation is None
                    or fulfilled
                    > allocation.quantity - allocation.fulfilled_quantity + 1e-9
                ):
                    raise ValueError("Sales fulfillment requires enough reserved lot quantity.")
                if fulfilled > self._lot_balance(session, organization_id, lot.id) + 1e-9:
                    raise ValueError("Shipment would make lot inventory negative.")

            delta = fulfilled if order.order_type == "purchase" else -fulfilled
            transaction_type = "receipt" if order.order_type == "purchase" else "shipment"
            transaction = InventoryTransaction(
                organization_id=organization_id,
                facility_id=facility_id,
                lot_id=lot.id,
                transaction_type=transaction_type,
                quantity_delta=delta,
                unit=line.unit,
                commercial_order_id=order.id,
                commercial_order_line_id=line.id,
                reason=f"{order.order_type.title()} order fulfillment",
                reference=str(reference or order.order_number),
                actor=actor,
            )
            session.add(transaction)
            line.fulfilled_quantity += fulfilled
            if allocation is not None:
                allocation.fulfilled_quantity += fulfilled
                allocation.status = (
                    "fulfilled"
                    if allocation.fulfilled_quantity >= allocation.quantity - 1e-9
                    else "partial"
                )

            session.flush()
            order_lines = list(
                session.scalars(
                    select(CommercialOrderLine).where(
                        CommercialOrderLine.commercial_order_id == order.id
                    )
                )
            )
            all_fulfilled = all(
                item.fulfilled_quantity >= item.quantity - 1e-9
                for item in order_lines
            )
            any_fulfilled = any(item.fulfilled_quantity > 0 for item in order_lines)
            order.status = (
                "fulfilled"
                if all_fulfilled
                else "partially_fulfilled"
                if any_fulfilled
                else order.status
            )
            order.updated_by = actor
            self._audit(
                session,
                organization_id,
                facility_id,
                "commercial_order",
                order.id,
                "fulfillment_posted",
                actor,
                {
                    "line_id": line.id,
                    "lot_id": lot.id,
                    "quantity": fulfilled,
                    "transaction_type": transaction_type,
                    "reference": transaction.reference,
                },
            )
            return transaction

    def list_commercial_transactions(
        self,
        organization_id: str,
        facility_id: str,
    ) -> list[InventoryTransaction]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(InventoryTransaction)
                    .where(
                        InventoryTransaction.organization_id == organization_id,
                        InventoryTransaction.facility_id == facility_id,
                        InventoryTransaction.commercial_order_id.is_not(None),
                    )
                    .order_by(InventoryTransaction.occurred_at.desc())
                )
            )

    def _update_order_status(
        self,
        order_id: str,
        *,
        organization_id: str,
        facility_id: str,
        status: str,
        actor: str,
    ) -> CommercialOrder:
        with self._session_factory.begin() as session:
            order = self._require_order(
                session,
                order_id,
                organization_id,
                facility_id,
            )
            if order.status != "draft":
                raise ValueError("Only draft orders can be confirmed.")
            order.status = status
            order.updated_by = actor
            self._audit(
                session,
                organization_id,
                facility_id,
                "commercial_order",
                order.id,
                "confirmed",
                actor,
                {},
            )
            return order

    @staticmethod
    def _lot_balance(session: Session, organization_id: str, lot_id: str) -> float:
        return float(
            session.scalar(
                select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                    InventoryTransaction.organization_id == organization_id,
                    InventoryTransaction.lot_id == lot_id,
                )
            )
            or 0.0
        )

    @staticmethod
    def _require_order(
        session: Session,
        order_id: str,
        organization_id: str,
        facility_id: str,
    ) -> CommercialOrder:
        order = session.get(CommercialOrder, order_id)
        if (
            not order
            or order.organization_id != organization_id
            or order.facility_id != facility_id
        ):
            raise ValueError("Commercial order was not found in this facility.")
        return order

    @staticmethod
    def _require_organization(session: Session, organization_id: str) -> None:
        if not session.get(Organization, organization_id):
            raise ValueError("Organization was not found.")

    @staticmethod
    def _audit(
        session: Session,
        organization_id: str,
        facility_id: str | None,
        entity_type: str,
        entity_id: str,
        action: str,
        actor: str,
        changes: dict[str, Any],
    ) -> None:
        session.add(
            AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor=actor,
                changes_json=json.dumps(changes, default=str),
                occurred_at=utc_now(),
            )
        )
