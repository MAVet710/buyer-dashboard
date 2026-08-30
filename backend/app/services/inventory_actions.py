from __future__ import annotations

import json

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent, InventoryLot, InventoryTransaction


class InventoryActionService:
    """Small, auditable inventory actions that do not change quantity.

    Provider/state-system mutations are intentionally handled separately. A local
    move changes only DoobieLogic's operational room/location and creates a durable
    audit event. Callers must not present this as a completed Metrc move.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def move_lots(
        self,
        organization_id: str,
        facility_id: str,
        *,
        lot_ids: list[str],
        destination_location: str,
        actor: str,
        reason: str = "Inventory moved",
    ) -> dict:
        ids = list(dict.fromkeys(str(value or "").strip() for value in lot_ids if str(value or "").strip()))
        destination = str(destination_location or "").strip()
        if not ids:
            raise ValueError("Select at least one inventory package to move.")
        if not destination:
            raise ValueError("Choose a destination location.")
        if len(destination) > 120:
            raise ValueError("Destination location is too long.")

        moved: list[dict] = []
        with Session(self.engine) as session, session.begin():
            rows = list(
                session.scalars(
                    select(InventoryLot).where(
                        InventoryLot.organization_id == organization_id,
                        InventoryLot.facility_id == facility_id,
                        InventoryLot.id.in_(ids),
                    )
                )
            )
            by_id = {row.id: row for row in rows}
            missing = [lot_id for lot_id in ids if lot_id not in by_id]
            if missing:
                raise ValueError("One or more selected inventory lots were not found in the active facility.")

            for lot_id in ids:
                lot = by_id[lot_id]
                previous = str(lot.location_code or "").strip()
                if previous == destination:
                    continue
                # A location action must never alter the inventory quantity ledger.
                balance = float(
                    session.scalar(
                        select(InventoryTransaction.quantity_delta)
                        .where(InventoryTransaction.lot_id == lot.id)
                        .order_by(InventoryTransaction.occurred_at.desc())
                        .limit(1)
                    )
                    or 0.0
                )
                lot.location_code = destination
                changes = {
                    "from_location": previous,
                    "to_location": destination,
                    "quantity_mutated": False,
                    "latest_transaction_delta_unchanged": balance,
                    "metrc_mutated": False,
                    "reason": str(reason or "Inventory moved").strip(),
                }
                session.add(
                    AuditEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        entity_type="inventory_lot",
                        entity_id=lot.id,
                        action="inventory_moved",
                        actor=actor,
                        changes_json=json.dumps(changes, sort_keys=True),
                    )
                )
                moved.append(
                    {
                        "lot_id": lot.id,
                        "package_id": lot.compliance_package_id or lot.lot_code,
                        "from_location": previous,
                        "to_location": destination,
                    }
                )

        return {
            "moved": moved,
            "moved_count": len(moved),
            "destination_location": destination,
            "inventory_quantity_mutated": False,
            "metrc_status": "not_changed",
            "message": "DoobieLogic location updated. Metrc was not changed by this local move.",
        }
