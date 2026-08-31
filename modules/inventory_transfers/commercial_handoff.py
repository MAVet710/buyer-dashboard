from __future__ import annotations

import json

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import (
    AuditEvent,
    CommercialOrder,
    CommercialOrderLine,
    Facility,
    InventoryLot,
    InventoryTransaction,
    OrderLotAllocation,
    Product,
    utc_now,
)
from modules.inventory_availability.service import InventoryAvailabilityService

from .models import InventoryTransfer, InventoryTransferLine
from .service import InventoryTransferService


class CommercialTransferHandoffService:
    """Use the licensed transfer as the one physical movement for wholesale fulfillment.

    A sales order first reserves a specific lot. When that order requires a cross-license
    move, this service consumes only the reservation owned by that order line and writes
    the transfer-out transaction with the commercial order references on the same ledger
    row. This avoids a wholesale shipment decrement followed by a second transfer-out
    decrement for the same cannabis.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.transfers = InventoryTransferService(engine)

    def dispatch(
        self,
        organization_id: str,
        source_facility_id: str,
        *,
        destination_facility_id: str,
        manifest_reference: str,
        lines: list[dict],
        actor: str,
        external_transfer_id: str = "",
        notes: str = "",
    ) -> dict:
        manifest = str(manifest_reference or "").strip()
        if not manifest:
            raise ValueError("A manifest or transfer reference is required.")
        if not lines:
            raise ValueError("Select at least one reserved wholesale package for the transfer.")

        normalized: list[tuple[str, float, str]] = []
        seen: set[str] = set()
        for row in lines:
            lot_id = str(row.get("source_lot_id") or "").strip()
            quantity = float(row.get("quantity") or 0.0)
            order_line_id = str(row.get("commercial_order_line_id") or "").strip()
            if not lot_id or quantity <= 0 or not order_line_id:
                raise ValueError("Wholesale transfer lines require a source lot, quantity, and sales order line.")
            if lot_id in seen:
                raise ValueError("A source package can appear only once on one transfer.")
            seen.add(lot_id)
            normalized.append((lot_id, quantity, order_line_id))

        with self.sessions.begin() as session:
            source = session.get(Facility, source_facility_id)
            destination = session.get(Facility, destination_facility_id)
            if not source or not source.active or source.organization_id != organization_id:
                raise ValueError("Source facility was not found in the active organization.")
            if not destination or not destination.active or destination.organization_id != organization_id:
                raise ValueError("Destination facility was not found in the active organization.")
            if source.id == destination.id:
                raise ValueError("Source and destination facilities must be different licenses/locations.")
            existing = session.scalar(
                select(InventoryTransfer.id).where(
                    InventoryTransfer.organization_id == organization_id,
                    InventoryTransfer.manifest_reference == manifest,
                )
            )
            if existing:
                raise ValueError("That manifest or transfer reference already exists in this organization.")

            lot_ids = [lot_id for lot_id, _, _ in normalized]
            lots = list(
                session.scalars(
                    select(InventoryLot)
                    .where(
                        InventoryLot.id.in_(lot_ids),
                        InventoryLot.organization_id == organization_id,
                        InventoryLot.facility_id == source_facility_id,
                    )
                    .with_for_update()
                )
            )
            by_lot = {row.id: row for row in lots}
            if len(by_lot) != len(normalized):
                raise ValueError("One or more reserved wholesale packages were not found in the active source facility.")

            availability = InventoryAvailabilityService.build(session, organization_id, source_facility_id)
            transfer = InventoryTransfer(
                organization_id=organization_id,
                source_facility_id=source.id,
                destination_facility_id=destination.id,
                source_license_number=source.license_number,
                destination_license_number=destination.license_number,
                source_facility_name=source.name,
                destination_facility_name=destination.name,
                manifest_reference=manifest,
                external_transfer_id=str(external_transfer_id or "").strip(),
                status="shipped",
                notes=str(notes or "").strip(),
                created_by=str(actor or "system").strip() or "system",
                shipped_at=utc_now(),
            )
            session.add(transfer)
            session.flush()

            affected_orders: set[str] = set()
            commercial_refs: list[dict] = []
            for lot_id, quantity, order_line_id in normalized:
                lot = by_lot[lot_id]
                product = session.get(Product, lot.product_id)
                if not product or product.organization_id != organization_id:
                    raise ValueError("Source package Product Master mapping is invalid.")

                line = session.scalar(
                    select(CommercialOrderLine)
                    .where(
                        CommercialOrderLine.id == order_line_id,
                        CommercialOrderLine.organization_id == organization_id,
                    )
                    .with_for_update()
                )
                if not line:
                    raise ValueError("The staged wholesale order line no longer exists.")
                order = session.scalar(
                    select(CommercialOrder)
                    .where(
                        CommercialOrder.id == line.commercial_order_id,
                        CommercialOrder.organization_id == organization_id,
                        CommercialOrder.facility_id == source_facility_id,
                    )
                    .with_for_update()
                )
                if not order or order.order_type != "sales" or order.status in {"draft", "cancelled", "fulfilled"}:
                    raise ValueError("The staged wholesale sales order is no longer eligible for transfer fulfillment.")
                if line.product_id != lot.product_id:
                    raise ValueError("The staged wholesale package no longer matches its sales-order product.")

                allocation = session.scalar(
                    select(OrderLotAllocation)
                    .where(
                        OrderLotAllocation.organization_id == organization_id,
                        OrderLotAllocation.facility_id == source_facility_id,
                        OrderLotAllocation.commercial_order_line_id == line.id,
                        OrderLotAllocation.lot_id == lot.id,
                        OrderLotAllocation.status.in_(["reserved", "partial"]),
                    )
                    .with_for_update()
                )
                if not allocation:
                    raise ValueError("Reserve this exact package on the wholesale order before preparing its licensed transfer.")

                allocation_remaining = max(0.0, float(allocation.quantity) - float(allocation.fulfilled_quantity))
                line_remaining = max(0.0, float(line.quantity) - float(line.fulfilled_quantity))
                if quantity > allocation_remaining + 1e-9 or quantity > line_remaining + 1e-9:
                    raise ValueError("Transfer quantity exceeds the quantity reserved for this wholesale order line.")

                claim = availability["by_lot"].get(lot.id) or {}
                physical_on_hand = float(claim.get("on_hand") or 0.0)
                free_after_other_claims = float(claim.get("available") or 0.0) + allocation_remaining
                if quantity > physical_on_hand + 1e-9:
                    raise ValueError("Transfer quantity exceeds physical on-hand inventory.")
                if quantity > free_after_other_claims + 1e-9:
                    labels = [
                        str(row.get("label") or "")
                        for row in claim.get("claims") or []
                        if row.get("label") and str(row.get("reference_id") or "") != order.id
                    ]
                    suffix = f" Other active commitments: {', '.join(labels[:5])}." if labels else ""
                    raise ValueError("Transfer quantity conflicts with inventory reserved for other work." + suffix)

                transaction = InventoryTransaction(
                    organization_id=organization_id,
                    facility_id=source_facility_id,
                    lot_id=lot.id,
                    transaction_type="transfer_out",
                    quantity_delta=-quantity,
                    unit=product.base_unit,
                    commercial_order_id=order.id,
                    commercial_order_line_id=line.id,
                    reason=f"Wholesale order {order.order_number} fulfilled by cross-license transfer to {destination.name}",
                    reference=manifest,
                    actor=str(actor or "system").strip() or "system",
                )
                session.add(transaction)
                session.flush()

                transfer_line = InventoryTransferLine(
                    organization_id=organization_id,
                    transfer_id=transfer.id,
                    source_lot_id=lot.id,
                    product_id=lot.product_id,
                    quantity=quantity,
                    unit=product.base_unit,
                    source_lot_code=lot.lot_code,
                    source_package_id=lot.compliance_package_id,
                    source_transaction_id=transaction.id,
                    status="shipped",
                )
                session.add(transfer_line)

                line.fulfilled_quantity += quantity
                allocation.fulfilled_quantity += quantity
                allocation.status = "fulfilled" if allocation.fulfilled_quantity >= allocation.quantity - 1e-9 else "partial"
                affected_orders.add(order.id)
                commercial_refs.append(
                    {
                        "order_id": order.id,
                        "order_number": order.order_number,
                        "order_line_id": line.id,
                        "lot_id": lot.id,
                        "quantity": quantity,
                    }
                )

            session.flush()
            for order_id in affected_orders:
                self._recalculate_order_status(session, order_id)

            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=source_facility_id,
                    entity_type="inventory_transfer",
                    entity_id=transfer.id,
                    action="wholesale_inventory_transfer_dispatched",
                    actor=str(actor or "system").strip() or "system",
                    changes_json=json.dumps(
                        {
                            "manifest_reference": manifest,
                            "destination_facility_id": destination.id,
                            "destination_license_number": destination.license_number,
                            "commercial_fulfillments": commercial_refs,
                        },
                        sort_keys=True,
                    ),
                )
            )
            transfer_id = transfer.id

        return self.transfers.detail(organization_id, transfer_id)

    def cancel(
        self,
        organization_id: str,
        source_facility_id: str,
        transfer_id: str,
        *,
        actor: str,
        reason: str = "",
    ) -> dict:
        """Cancel a commercial handoff and restore both inventory and reservation state."""
        with self.sessions.begin() as session:
            transfer = session.scalar(
                select(InventoryTransfer)
                .where(
                    InventoryTransfer.id == transfer_id,
                    InventoryTransfer.organization_id == organization_id,
                    InventoryTransfer.source_facility_id == source_facility_id,
                )
                .with_for_update()
            )
            if not transfer:
                raise ValueError("Transfer was not found for the active source facility.")
            if transfer.status == "cancelled":
                raise ValueError("Transfer is already cancelled.")
            if transfer.status in {"partially_received", "received"}:
                raise ValueError("A transfer cannot be cancelled after destination receipt has started; create a return transfer instead.")

            lines = list(
                session.scalars(
                    select(InventoryTransferLine)
                    .where(InventoryTransferLine.transfer_id == transfer.id)
                    .with_for_update()
                )
            )
            affected_orders: set[str] = set()
            for transfer_line in lines:
                if transfer_line.status != "shipped":
                    raise ValueError("Only fully unreceived transfers can be cancelled.")
                source_tx = session.get(InventoryTransaction, transfer_line.source_transaction_id)
                if not source_tx or not source_tx.commercial_order_line_id or not source_tx.commercial_order_id:
                    raise ValueError("This transfer is not a wholesale handoff transfer.")

                order_line = session.scalar(
                    select(CommercialOrderLine)
                    .where(CommercialOrderLine.id == source_tx.commercial_order_line_id)
                    .with_for_update()
                )
                order = session.scalar(
                    select(CommercialOrder)
                    .where(CommercialOrder.id == source_tx.commercial_order_id)
                    .with_for_update()
                )
                allocation = session.scalar(
                    select(OrderLotAllocation)
                    .where(
                        OrderLotAllocation.commercial_order_line_id == source_tx.commercial_order_line_id,
                        OrderLotAllocation.lot_id == transfer_line.source_lot_id,
                    )
                    .with_for_update()
                )
                if not order_line or not order or not allocation:
                    raise ValueError("Wholesale reservation state is missing; cancellation requires human review.")

                quantity = float(transfer_line.quantity)
                order_line.fulfilled_quantity = max(0.0, float(order_line.fulfilled_quantity) - quantity)
                allocation.fulfilled_quantity = max(0.0, float(allocation.fulfilled_quantity) - quantity)
                allocation.status = "reserved" if allocation.fulfilled_quantity <= 1e-9 else "partial"
                affected_orders.add(order.id)

                session.add(
                    InventoryTransaction(
                        organization_id=organization_id,
                        facility_id=source_facility_id,
                        lot_id=transfer_line.source_lot_id,
                        transaction_type="transfer_cancel_return",
                        quantity_delta=quantity,
                        unit=transfer_line.unit,
                        commercial_order_id=order.id,
                        commercial_order_line_id=order_line.id,
                        reason="Cross-license wholesale transfer cancelled before receipt",
                        reference=transfer.manifest_reference,
                        actor=str(actor or "system").strip() or "system",
                    )
                )
                transfer_line.status = "cancelled"

            for order_id in affected_orders:
                self._recalculate_order_status(session, order_id)
            transfer.status = "cancelled"
            transfer.cancelled_at = utc_now()
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=source_facility_id,
                    entity_type="inventory_transfer",
                    entity_id=transfer.id,
                    action="wholesale_inventory_transfer_cancelled",
                    actor=str(actor or "system").strip() or "system",
                    changes_json=json.dumps({"reason": str(reason or "").strip()}, sort_keys=True),
                )
            )
        return self.transfers.detail(organization_id, transfer_id)

    def is_commercial_handoff(self, organization_id: str, source_facility_id: str, transfer_id: str) -> bool:
        with self.sessions() as session:
            transfer = session.scalar(
                select(InventoryTransfer).where(
                    InventoryTransfer.id == transfer_id,
                    InventoryTransfer.organization_id == organization_id,
                    InventoryTransfer.source_facility_id == source_facility_id,
                )
            )
            if not transfer:
                return False
            line = session.scalar(select(InventoryTransferLine).where(InventoryTransferLine.transfer_id == transfer.id))
            if not line:
                return False
            transaction = session.get(InventoryTransaction, line.source_transaction_id)
            return bool(transaction and transaction.commercial_order_line_id and transaction.commercial_order_id)

    @staticmethod
    def _recalculate_order_status(session, order_id: str) -> None:
        order = session.get(CommercialOrder, order_id)
        if not order:
            return
        lines = list(session.scalars(select(CommercialOrderLine).where(CommercialOrderLine.commercial_order_id == order_id)))
        if lines and all(float(row.fulfilled_quantity) >= float(row.quantity) - 1e-9 for row in lines):
            order.status = "fulfilled"
            return
        if any(float(row.fulfilled_quantity) > 1e-9 for row in lines):
            order.status = "partially_fulfilled"
            return
        active_allocations = int(
            session.scalar(
                select(func.count(OrderLotAllocation.id)).where(
                    OrderLotAllocation.commercial_order_id == order_id,
                    OrderLotAllocation.status.in_(["reserved", "partial"]),
                )
            )
            or 0
        )
        order.status = "allocated" if active_allocations else "confirmed"
