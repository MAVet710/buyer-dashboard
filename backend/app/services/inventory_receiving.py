from __future__ import annotations

import json

from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent, InventoryLot, InventoryTransaction, Product, utc_now
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
                    reason=f"{operation.title()} inventory received",
                    reference=payload.manifest_reference.strip() or package_id or lot_code,
                    actor=actor,
                )
                session.add(transaction)
                session.flush()
                session.add(
                    AuditEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        entity_type="inventory_lot",
                        entity_id=lot.id,
                        action=f"{operation}_inventory_received",
                        actor=actor,
                        changes_json=json.dumps({**metadata, "quantity": payload.quantity, "unit": unit}, sort_keys=True),
                    )
                )
                results.append(
                    InventoryReceiptResult(
                        lot_id=lot.id,
                        transaction_id=transaction.id,
                        operation=operation,
                        status=status,
                    )
                )
        return results
