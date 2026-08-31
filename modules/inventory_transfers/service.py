from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import AuditEvent, Facility, InventoryLot, InventoryTransaction, Product, utc_now
from modules.inventory_availability.service import InventoryAvailabilityService
from modules.inventory_quality.service import LotQualityService

from .models import InventoryTransfer, InventoryTransferLine


class InventoryTransferService:
    """Two-sided cross-license inventory transfer lifecycle.

    The source facility dispatches against its own physical/available ledger. The
    destination facility receives into its own ledger later. The durable transfer
    line connects both lots without letting one facility context mutate the other.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

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
            raise ValueError("Select at least one source package for the transfer.")
        normalized: list[tuple[str, float]] = []
        seen: set[str] = set()
        for row in lines:
            lot_id = str(row.get("source_lot_id") or "").strip()
            quantity = float(row.get("quantity") or 0.0)
            if not lot_id or quantity <= 0:
                raise ValueError("Every transfer line requires a source lot and quantity greater than zero.")
            if lot_id in seen:
                raise ValueError("A source package can appear only once on one transfer.")
            seen.add(lot_id)
            normalized.append((lot_id, quantity))

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

            lots = list(
                session.scalars(
                    select(InventoryLot)
                    .where(
                        InventoryLot.id.in_([lot_id for lot_id, _ in normalized]),
                        InventoryLot.organization_id == organization_id,
                        InventoryLot.facility_id == source_facility_id,
                    )
                    .with_for_update()
                )
            )
            by_id = {row.id: row for row in lots}
            if len(by_id) != len(normalized):
                raise ValueError("One or more source packages were not found in the active source facility.")

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

            line_ids: list[str] = []
            for lot_id, quantity in normalized:
                lot = by_id[lot_id]
                claim = availability["by_lot"].get(lot.id)
                available = float((claim or {}).get("available") or 0.0)
                if quantity > available + 1e-9:
                    labels = [str(row.get("label") or "") for row in (claim or {}).get("claims") or [] if row.get("label")]
                    suffix = f" Active commitments: {', '.join(labels[:5])}." if labels else ""
                    raise ValueError(
                        f"Transfer quantity for {lot.lot_code} exceeds available inventory by {quantity - available:,.4f}." + suffix
                    )
                product = session.get(Product, lot.product_id)
                if not product or product.organization_id != organization_id:
                    raise ValueError("Source package Product Master mapping is invalid.")
                transaction = InventoryTransaction(
                    organization_id=organization_id,
                    facility_id=source_facility_id,
                    lot_id=lot.id,
                    transaction_type="transfer_out",
                    quantity_delta=-quantity,
                    unit=product.base_unit,
                    reason=f"Cross-license transfer dispatched to {destination.name}",
                    reference=manifest,
                    actor=str(actor or "system").strip() or "system",
                )
                session.add(transaction)
                session.flush()
                line = InventoryTransferLine(
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
                session.add(line)
                session.flush()
                line_ids.append(line.id)

            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=source_facility_id,
                    entity_type="inventory_transfer",
                    entity_id=transfer.id,
                    action="inventory_transfer_dispatched",
                    actor=str(actor or "system").strip() or "system",
                    changes_json=json.dumps(
                        {
                            "manifest_reference": manifest,
                            "destination_facility_id": destination.id,
                            "destination_license_number": destination.license_number,
                            "line_count": len(line_ids),
                        },
                        sort_keys=True,
                    ),
                )
            )
            transfer_id = transfer.id
        return self.detail(organization_id, transfer_id)

    def receive_line(
        self,
        organization_id: str,
        destination_facility_id: str,
        transfer_id: str,
        line_id: str,
        *,
        operation: str,
        actor: str,
        lot_code: str = "",
        package_id: str = "",
        location: str = "RECEIVING",
        notes: str = "",
    ) -> dict:
        operation = str(operation or "").strip().casefold()
        if operation not in {"retail", "production"}:
            raise ValueError("Destination operation must be retail or production.")
        with self.sessions.begin() as session:
            transfer = session.scalar(
                select(InventoryTransfer)
                .where(
                    InventoryTransfer.id == transfer_id,
                    InventoryTransfer.organization_id == organization_id,
                    InventoryTransfer.destination_facility_id == destination_facility_id,
                )
                .with_for_update()
            )
            if not transfer:
                raise ValueError("Transfer was not found for the active destination facility.")
            if transfer.status in {"cancelled", "received"}:
                raise ValueError(f"Transfer is already {transfer.status}.")
            line = session.scalar(
                select(InventoryTransferLine)
                .where(
                    InventoryTransferLine.id == line_id,
                    InventoryTransferLine.transfer_id == transfer.id,
                    InventoryTransferLine.organization_id == organization_id,
                )
                .with_for_update()
            )
            if not line:
                raise ValueError("Transfer line was not found.")
            if line.status != "shipped" or line.destination_lot_id:
                raise ValueError("Transfer line has already been received or cancelled.")
            source_lot = session.get(InventoryLot, line.source_lot_id)
            if not source_lot or source_lot.organization_id != organization_id or source_lot.facility_id != transfer.source_facility_id:
                raise ValueError("Transfer source lineage is no longer valid.")
            product = session.get(Product, line.product_id)
            if not product or product.organization_id != organization_id or not product.active:
                raise ValueError("Transferred Product Master item is not active in this organization.")

            destination_package = str(package_id or line.source_package_id).strip()
            destination_lot_code = str(lot_code or destination_package or line.source_lot_code).strip()
            if not destination_lot_code:
                raise ValueError("A destination package or lot identifier is required.")
            duplicate_conditions = [InventoryLot.lot_code == destination_lot_code]
            if destination_package:
                duplicate_conditions.append(InventoryLot.compliance_package_id == destination_package)
            duplicate = session.scalar(
                select(InventoryLot.id).where(
                    InventoryLot.organization_id == organization_id,
                    InventoryLot.facility_id == destination_facility_id,
                    or_(*duplicate_conditions),
                )
            )
            if duplicate:
                raise ValueError("That destination package or lot already exists in the active facility.")

            metadata = {
                "operation": operation,
                "source_name": transfer.source_facility_name,
                "manifest_reference": transfer.manifest_reference,
                "transfer_id": transfer.id,
                "transfer_line_id": line.id,
                "source_facility_id": transfer.source_facility_id,
                "source_license_number": transfer.source_license_number,
                "source_lot_id": source_lot.id,
                "source_package_id": line.source_package_id,
                "notes": str(notes or "").strip(),
            }
            lot = InventoryLot(
                organization_id=organization_id,
                facility_id=destination_facility_id,
                product_id=line.product_id,
                lot_code=destination_lot_code,
                compliance_package_id=destination_package,
                external_inventory_id=destination_package,
                barcode_value=destination_package or destination_lot_code,
                location_code=str(location or "RECEIVING").strip() or "RECEIVING",
                status=str(source_lot.status or "available"),
                received_at=utc_now(),
                expiration_at=source_lot.expiration_at,
                notes=json.dumps(metadata, sort_keys=True),
            )
            session.add(lot)
            session.flush()
            transaction = InventoryTransaction(
                organization_id=organization_id,
                facility_id=destination_facility_id,
                lot_id=lot.id,
                transaction_type="transfer_in",
                quantity_delta=float(line.quantity),
                unit=line.unit,
                reason=f"Cross-license transfer received from {transfer.source_facility_name}",
                reference=transfer.manifest_reference,
                actor=str(actor or "system").strip() or "system",
            )
            session.add(transaction)
            session.flush()
            self._copy_quality_evidence(session, source_lot.id, lot.id, actor)

            line.destination_lot_id = lot.id
            line.destination_transaction_id = transaction.id
            line.destination_lot_code = lot.lot_code
            line.destination_package_id = lot.compliance_package_id
            line.received_quantity = float(line.quantity)
            line.status = "received"
            line.received_at = utc_now()

            remaining = int(
                session.scalar(
                    select(func.count(InventoryTransferLine.id)).where(
                        InventoryTransferLine.transfer_id == transfer.id,
                        InventoryTransferLine.status == "shipped",
                        InventoryTransferLine.id != line.id,
                    )
                )
                or 0
            )
            if remaining == 0:
                transfer.status = "received"
                transfer.received_at = utc_now()
            else:
                transfer.status = "partially_received"

            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=destination_facility_id,
                    entity_type="inventory_transfer",
                    entity_id=transfer.id,
                    action="inventory_transfer_line_received",
                    actor=str(actor or "system").strip() or "system",
                    changes_json=json.dumps(
                        {
                            "manifest_reference": transfer.manifest_reference,
                            "line_id": line.id,
                            "source_lot_id": source_lot.id,
                            "destination_lot_id": lot.id,
                            "quantity": line.quantity,
                            "unit": line.unit,
                        },
                        sort_keys=True,
                    ),
                )
            )
        return self.detail(organization_id, transfer_id)

    def cancel(
        self,
        organization_id: str,
        source_facility_id: str,
        transfer_id: str,
        *,
        actor: str,
        reason: str = "",
    ) -> dict:
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
            for line in lines:
                if line.status != "shipped":
                    raise ValueError("Only fully unreceived transfers can be cancelled.")
                session.add(
                    InventoryTransaction(
                        organization_id=organization_id,
                        facility_id=source_facility_id,
                        lot_id=line.source_lot_id,
                        transaction_type="transfer_cancel_return",
                        quantity_delta=float(line.quantity),
                        unit=line.unit,
                        reason="Cross-license transfer cancelled before receipt",
                        reference=transfer.manifest_reference,
                        actor=str(actor or "system").strip() or "system",
                    )
                )
                line.status = "cancelled"
            transfer.status = "cancelled"
            transfer.cancelled_at = utc_now()
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=source_facility_id,
                    entity_type="inventory_transfer",
                    entity_id=transfer.id,
                    action="inventory_transfer_cancelled",
                    actor=str(actor or "system").strip() or "system",
                    changes_json=json.dumps({"reason": str(reason or "").strip()}, sort_keys=True),
                )
            )
        return self.detail(organization_id, transfer_id)

    def list_for_facility(self, organization_id: str, facility_id: str, direction: str = "both") -> list[dict]:
        direction = str(direction or "both").strip().casefold()
        if direction not in {"inbound", "outbound", "both"}:
            raise ValueError("Transfer direction must be inbound, outbound, or both.")
        with self.sessions() as session:
            statement = select(InventoryTransfer).where(InventoryTransfer.organization_id == organization_id)
            if direction == "inbound":
                statement = statement.where(InventoryTransfer.destination_facility_id == facility_id)
            elif direction == "outbound":
                statement = statement.where(InventoryTransfer.source_facility_id == facility_id)
            else:
                statement = statement.where(
                    or_(
                        InventoryTransfer.source_facility_id == facility_id,
                        InventoryTransfer.destination_facility_id == facility_id,
                    )
                )
            transfers = list(session.scalars(statement.order_by(InventoryTransfer.shipped_at.desc())))
            ids = [row.id for row in transfers]
            lines = list(
                session.scalars(
                    select(InventoryTransferLine).where(InventoryTransferLine.transfer_id.in_(ids or ["__none__"]))
                )
            )
            products = {
                row.id: row
                for row in session.scalars(
                    select(Product).where(Product.id.in_({line.product_id for line in lines} or {"__none__"}))
                )
            }
        by_transfer: dict[str, list[InventoryTransferLine]] = {}
        for line in lines:
            by_transfer.setdefault(line.transfer_id, []).append(line)
        return [self._payload(row, by_transfer.get(row.id, []), products, facility_id) for row in transfers]

    def detail(self, organization_id: str, transfer_id: str, facility_id: str | None = None) -> dict:
        with self.sessions() as session:
            transfer = session.get(InventoryTransfer, transfer_id)
            if not transfer or transfer.organization_id != organization_id:
                raise ValueError("Transfer was not found in the active organization.")
            if facility_id and facility_id not in {transfer.source_facility_id, transfer.destination_facility_id}:
                raise ValueError("Transfer is not visible from the active facility.")
            lines = list(
                session.scalars(
                    select(InventoryTransferLine)
                    .where(InventoryTransferLine.transfer_id == transfer.id)
                    .order_by(InventoryTransferLine.created_at, InventoryTransferLine.id)
                )
            )
            products = {
                row.id: row
                for row in session.scalars(
                    select(Product).where(Product.id.in_({line.product_id for line in lines} or {"__none__"}))
                )
            }
        return self._payload(transfer, lines, products, facility_id)

    @staticmethod
    def _copy_quality_evidence(session: Session, source_lot_id: str, destination_lot_id: str, actor: str) -> None:
        evidence = LotQualityService.read(session, source_lot_id)
        if evidence is None:
            return
        LotQualityService.set_evidence(
            session,
            lot_id=destination_lot_id,
            lab_testing_state=evidence.lab_testing_state,
            coa_reference=evidence.coa_reference,
            coa_url=evidence.coa_url,
            thca_percent=evidence.thca_percent,
            tac_percent=evidence.tac_percent,
            total_terpenes_percent=evidence.total_terpenes_percent,
            evidence_source="inherited:facility_transfer",
            inherited_from_lot_id=source_lot_id,
            actor=str(actor or "system").strip() or "system",
        )

    @staticmethod
    def _payload(
        transfer: InventoryTransfer,
        lines: Iterable[InventoryTransferLine],
        products: dict[str, Product],
        facility_id: str | None,
    ) -> dict:
        direction = "outbound" if facility_id == transfer.source_facility_id else "inbound" if facility_id == transfer.destination_facility_id else ""
        return {
            "id": transfer.id,
            "organization_id": transfer.organization_id,
            "source_facility_id": transfer.source_facility_id,
            "destination_facility_id": transfer.destination_facility_id,
            "source_facility_name": transfer.source_facility_name,
            "destination_facility_name": transfer.destination_facility_name,
            "source_license_number": transfer.source_license_number,
            "destination_license_number": transfer.destination_license_number,
            "manifest_reference": transfer.manifest_reference,
            "external_transfer_id": transfer.external_transfer_id,
            "status": transfer.status,
            "direction": direction,
            "notes": transfer.notes,
            "created_by": transfer.created_by,
            "shipped_at": transfer.shipped_at,
            "received_at": transfer.received_at,
            "cancelled_at": transfer.cancelled_at,
            "lines": [
                {
                    "id": line.id,
                    "source_lot_id": line.source_lot_id,
                    "destination_lot_id": line.destination_lot_id,
                    "product_id": line.product_id,
                    "product_name": getattr(products.get(line.product_id), "name", ""),
                    "quantity": float(line.quantity),
                    "received_quantity": float(line.received_quantity),
                    "unit": line.unit,
                    "source_lot_code": line.source_lot_code,
                    "source_package_id": line.source_package_id,
                    "destination_lot_code": line.destination_lot_code,
                    "destination_package_id": line.destination_package_id,
                    "source_transaction_id": line.source_transaction_id,
                    "destination_transaction_id": line.destination_transaction_id,
                    "status": line.status,
                    "received_at": line.received_at,
                }
                for line in lines
            ],
        }
