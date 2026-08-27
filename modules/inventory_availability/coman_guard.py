"""Install organization-wide availability guards onto the legacy Co-Man repository API."""

from __future__ import annotations

import json

import modules.coman as coman_package
from modules.coman import repository as repository_module
from modules.coman.models import AuditEvent, InventoryLot, MaterialReservation, ProductionOrder

from .service import InventoryAvailabilityService


def install_coman_availability_guard() -> None:
    base = repository_module.ComanRepository
    if getattr(base, "_organization_availability_guarded", False):
        return

    class AvailabilityAwareComanRepository(base):
        _organization_availability_guarded = True

        def reserve_material(self, organization_id: str, facility_id: str, *, production_order_id: str, lot_id: str, quantity: float, unit: str, actor: str) -> MaterialReservation:
            requested = float(quantity)
            if requested <= 0:
                raise ValueError("Reservation quantity must be positive.")
            with self._session_factory.begin() as session:
                order = session.get(ProductionOrder, production_order_id)
                lot = session.get(InventoryLot, lot_id)
                if not order or order.organization_id != organization_id or order.facility_id != facility_id:
                    raise ValueError("Production order was not found in this facility.")
                if not lot or lot.organization_id != organization_id or lot.facility_id != facility_id or lot.status not in {"available", "released"}:
                    raise ValueError("An available inventory lot is required.")
                snapshot = InventoryAvailabilityService.build(session, organization_id, facility_id)
                available = max(0.0, float(snapshot["by_lot"].get(lot.id, {}).get("available", 0.0) or 0.0))
                if requested > available + 1e-9:
                    raise ValueError("Reservation exceeds organization-wide available inventory after Wholesale and Production commitments.")
                record = MaterialReservation(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    production_order_id=production_order_id,
                    lot_id=lot_id,
                    quantity=requested,
                    unit=unit,
                    reserved_by=actor,
                )
                session.add(record)
                session.flush()
                session.add(AuditEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="material_reservation",
                    entity_id=record.id,
                    action="reserved",
                    actor=actor,
                    changes_json=json.dumps({"lot_id": lot_id, "quantity": requested, "unit": unit, "available_before": available}),
                ))
                return record

        def post_inventory_transaction(self, organization_id: str, facility_id: str, *, lot_id: str, transaction_type: str, quantity_delta: float, unit: str, actor: str, production_order_id: str | None = None, reason: str = "", reference: str = ""):
            delta = float(quantity_delta)
            if delta < 0:
                with self._session_factory() as session:
                    snapshot = InventoryAvailabilityService.build(session, organization_id, facility_id)
                    available = max(0.0, float(snapshot["by_lot"].get(lot_id, {}).get("available", 0.0) or 0.0))
                if -delta > available + 1e-9:
                    raise ValueError("Inventory movement exceeds quantity available after organization-wide commitments.")
            return super().post_inventory_transaction(
                organization_id,
                facility_id,
                lot_id=lot_id,
                transaction_type=transaction_type,
                quantity_delta=delta,
                unit=unit,
                actor=actor,
                production_order_id=production_order_id,
                reason=reason,
                reference=reference,
            )

    repository_module.ComanRepository = AvailabilityAwareComanRepository
    coman_package.ComanRepository = AvailabilityAwareComanRepository
