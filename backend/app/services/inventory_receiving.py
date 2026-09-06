from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from modules.canonical_cannabis import operational_correlation_id
from modules.coman.audit import record_audit_event
from modules.coman.models import (
    CommercialOrder,
    CommercialOrderLine,
    InventoryLot,
    InventoryTransaction,
    Product,
    utc_now,
)
from ..schemas.inventory import InventoryReceiptCreate, InventoryReceiptResult


class InventoryReceiptBatchService:
    """Post one reviewed inbound receipt atomically.

    Streamlit reviewed the whole inbound transfer before posting it. The web
    version therefore cannot loop independent receipt requests and leave a
    half-posted manifest when one row fails. All reviewed rows are validated and
    committed in one database transaction.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def post(
        self,
        organization_id: str,
        facility_id: str,
        *,
        operation: str,
        rows: list[InventoryReceiptCreate],
        actor: str,
    ) -> list[InventoryReceiptResult]:
        if operation not in {"retail", "production"}:
            raise ValueError("Unsupported inventory operation.")
        if not rows:
            raise ValueError("At least one reviewed inbound package is required.")
        if len(rows) > 500:
            raise ValueError("One receipt may contain at most 500 packages.")

        batch_correlation_id = f"receiving:{uuid4()}"
        prepared: list[tuple[InventoryReceiptCreate, str, str, str, str, dict]] = []
        identities: set[str] = set()
        for payload in rows:
            lot_code = (payload.lot_code or payload.package_id).strip()
            package_id = payload.package_id.strip()
            unit = payload.unit.strip()
            if not lot_code:
                raise ValueError("Every inbound row requires a package or lot identifier.")
            if not unit:
                raise ValueError(f"A unit of measure is required for {package_id or lot_code}.")
            if payload.commercial_order_line_id and not payload.commercial_order_id:
                raise ValueError("A purchase-order line cannot be received without its purchase order.")
            identity = (package_id or lot_code).casefold()
            if identity in identities:
                raise ValueError(f"Duplicate package or lot in reviewed receipt: {package_id or lot_code}.")
            identities.add(identity)
            metadata = {
                "operation": operation,
                "source_name": payload.source_name.strip(),
                "manifest_reference": payload.manifest_reference.strip(),
                "lab_testing_state": payload.lab_testing_state.strip(),
                "coa_reference": payload.coa_reference.strip(),
                "commercial_order_id": payload.commercial_order_id.strip(),
                "commercial_order_line_id": payload.commercial_order_line_id.strip(),
                "notes": payload.notes.strip(),
                "receipt_mode": "reviewed_inbound_batch",
            }
            lab_state = payload.lab_testing_state.casefold().replace(" ", "")
            status = "available" if lab_state in {"", "testpassed", "passed", "released"} else "hold"
            prepared.append((payload, lot_code, package_id, unit, status, metadata))

        results: list[InventoryReceiptResult] = []
        with Session(self.engine) as session, session.begin():
            product_ids = {payload.product_id for payload, *_ in prepared}
            products = {row.id: row for row in session.scalars(select(Product).where(Product.id.in_(product_ids)))}
            for product_id in product_ids:
                product = products.get(product_id)
                if not product or product.organization_id != organization_id or not product.active:
                    raise ValueError("Every mapped product must exist in the active organization.")

            order_ids = {
                payload.commercial_order_id.strip()
                for payload, *_ in prepared
                if payload.commercial_order_id.strip()
            }
            orders = {
                row.id: row
                for row in session.scalars(
                    select(CommercialOrder).where(
                        CommercialOrder.organization_id == organization_id,
                        CommercialOrder.facility_id == facility_id,
                        CommercialOrder.id.in_(order_ids),
                    )
                )
            } if order_ids else {}
            for order_id in order_ids:
                order = orders.get(order_id)
                if not order or order.order_type != "purchase" or order.status == "cancelled":
                    raise ValueError("Linked purchase order must be active in this organization and facility.")

            line_ids = {
                payload.commercial_order_line_id.strip()
                for payload, *_ in prepared
                if payload.commercial_order_line_id.strip()
            }
            order_lines = {
                row.id: row
                for row in session.scalars(
                    select(CommercialOrderLine).where(
                        CommercialOrderLine.organization_id == organization_id,
                        CommercialOrderLine.id.in_(line_ids),
                    )
                )
            } if line_ids else {}
            for payload, *_ in prepared:
                order_id = payload.commercial_order_id.strip()
                line_id = payload.commercial_order_line_id.strip()
                if not line_id:
                    continue
                line = order_lines.get(line_id)
                if not line or line.commercial_order_id != order_id or line.product_id != payload.product_id:
                    raise ValueError("Linked purchase-order line must match the received product and purchase order.")
                if line.unit.strip().casefold() != payload.unit.strip().casefold():
                    raise ValueError("Received unit must match the linked purchase-order line unit.")
                if line.fulfilled_quantity + payload.quantity > line.quantity + 1e-9:
                    raise ValueError("Receipt would exceed the linked purchase-order line quantity.")

            touched_order_ids: set[str] = set()
            for payload, lot_code, package_id, unit, status, metadata in prepared:
                duplicate_conditions = [InventoryLot.lot_code == lot_code]
                if package_id:
                    duplicate_conditions.append(InventoryLot.compliance_package_id == package_id)
                duplicate = session.scalar(
                    select(InventoryLot.id).where(
                        InventoryLot.organization_id == organization_id,
                        InventoryLot.facility_id == facility_id,
                        or_(*duplicate_conditions),
                    )
                )
                if duplicate:
                    raise ValueError(f"Package or lot already exists in the active facility: {package_id or lot_code}.")

                product = products[payload.product_id]
                order_id = payload.commercial_order_id.strip()
                line_id = payload.commercial_order_line_id.strip()
                correlation_id = (
                    operational_correlation_id("purchase_order", order_id)
                    if order_id
                    else batch_correlation_id
                )
                lot = InventoryLot(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    product_id=product.id,
                    lot_code=lot_code,
                    compliance_package_id=package_id,
                    external_inventory_id=package_id,
                    barcode_value=package_id or lot_code,
                    location_code=payload.location.strip() or "RECEIVING",
                    status=status,
                    received_at=utc_now(),
                    expiration_at=payload.expiration_at,
                    notes=json.dumps(metadata, sort_keys=True),
                )
                session.add(lot)
                session.flush()
                transaction = InventoryTransaction(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    lot_id=lot.id,
                    transaction_type="receive",
                    quantity_delta=payload.quantity,
                    unit=unit,
                    commercial_order_id=order_id or None,
                    commercial_order_line_id=line_id or None,
                    reason=f"{operation.title()} inventory received",
                    reference=payload.manifest_reference.strip() or package_id or lot_code,
                    actor=actor,
                )
                session.add(transaction)
                session.flush()

                if line_id:
                    line = order_lines[line_id]
                    line.fulfilled_quantity += payload.quantity
                    touched_order_ids.add(order_id)

                record_audit_event(
                    session,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="inventory_lot",
                    entity_id=lot.id,
                    action=f"{operation}_inventory_received",
                    actor=actor,
                    changes={**metadata, "quantity": payload.quantity, "unit": unit},
                    source="user",
                    reason="Reviewed inbound batch posted to authoritative inventory.",
                    correlation_id=correlation_id,
                    after={
                        "status": status,
                        "quantity": payload.quantity,
                        "unit": unit,
                        "location_code": lot.location_code,
                        "compliance_package_id": package_id,
                    },
                    metadata={
                        "inventory_transaction_id": transaction.id,
                        "commercial_order_id": order_id,
                        "commercial_order_line_id": line_id,
                    },
                )
                results.append(
                    InventoryReceiptResult(
                        lot_id=lot.id,
                        transaction_id=transaction.id,
                        operation=operation,
                        status=status,
                    )
                )

            if touched_order_ids:
                all_order_lines = list(
                    session.scalars(
                        select(CommercialOrderLine).where(
                            CommercialOrderLine.organization_id == organization_id,
                            CommercialOrderLine.commercial_order_id.in_(touched_order_ids),
                        )
                    )
                )
                lines_by_order: dict[str, list[CommercialOrderLine]] = {}
                for line in all_order_lines:
                    lines_by_order.setdefault(line.commercial_order_id, []).append(line)
                for order_id in touched_order_ids:
                    order = orders[order_id]
                    linked_lines = lines_by_order.get(order_id, [])
                    prior_status = order.status
                    if linked_lines and all(line.fulfilled_quantity >= line.quantity - 1e-9 for line in linked_lines):
                        order.status = "fulfilled"
                    elif any(line.fulfilled_quantity > 0 for line in linked_lines):
                        order.status = "partially_fulfilled"
                    order.updated_by = actor
                    record_audit_event(
                        session,
                        organization_id=organization_id,
                        facility_id=facility_id,
                        entity_type="commercial_order",
                        entity_id=order.id,
                        action="purchase_order_receiving_posted",
                        actor=actor,
                        changes={
                            "order_number": order.order_number,
                            "order_type": "purchase",
                            "from_status": prior_status,
                            "to_status": order.status,
                        },
                        source="user",
                        reason="Reviewed inventory receipt fulfilled linked purchase-order material.",
                        correlation_id=operational_correlation_id("purchase_order", order.id),
                        before={"status": prior_status},
                        after={"status": order.status},
                    )
        return results
