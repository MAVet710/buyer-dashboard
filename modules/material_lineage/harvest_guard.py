"""Atomic preview/commit guard for cultivation harvest output allocation."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select

from modules.coman.models import InventoryLot, InventoryTransaction, utc_now
from modules.cultivation.models import CultivationHarvestPlant, CultivationPlant
from modules.operational_moats.models import CultivationHarvest

from .models import MaterialTransformationLoss
from .service import MaterialLineageService


class GuardedHarvestAllocationService(MaterialLineageService):
    """Require an exact, current Harvest 360 consequence preview before inventory posting."""

    @staticmethod
    def _jsonable(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): GuardedHarvestAllocationService._jsonable(item) for key, item in sorted(value.items())}
        if isinstance(value, (list, tuple)):
            return [GuardedHarvestAllocationService._jsonable(item) for item in value]
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value

    @classmethod
    def _preview_key(cls, preview: dict[str, Any]) -> str:
        material = {
            "harvest_id": preview.get("harvest_id"),
            "harvest_code": preview.get("harvest_code"),
            "status": preview.get("status"),
            "outputs": preview.get("outputs") or [],
            "losses": preview.get("losses") or [],
            "reconciliation": preview.get("reconciliation") or {},
            "state": preview.get("state") or {},
        }
        encoded = json.dumps(cls._jsonable(material), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _reject_closed(preview: dict[str, Any]) -> None:
        if str(preview.get("status") or "").casefold() == "completed":
            raise ValueError(
                "Completed harvest material disposition is closed. Reopen through a governed correction workflow before changing inventory genealogy."
            )

    def preview_harvest_allocation(
        self,
        *,
        organization_id: str,
        facility_id: str,
        harvest_id: str,
        outputs: list[dict[str, Any]],
        losses: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        preview = super().preview_harvest_allocation(
            organization_id=organization_id,
            facility_id=facility_id,
            harvest_id=harvest_id,
            outputs=outputs,
            losses=losses,
        )
        self._reject_closed(preview)
        return preview | {"preview_key": self._preview_key(preview)}

    def commit_harvest_allocation(
        self,
        *,
        organization_id: str,
        facility_id: str,
        harvest_id: str,
        outputs: list[dict[str, Any]],
        losses: list[dict[str, Any]] | None,
        preview_key: str,
        actor: str,
    ) -> dict[str, Any]:
        if not str(preview_key or "").strip():
            raise ValueError("Review the exact harvest allocation preview before posting inventory.")
        with self.sessions.begin() as session:
            preview = self._preview_harvest_allocation(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                harvest_id=harvest_id,
                outputs=outputs,
                losses=losses or [],
                lock=True,
            )
            self._reject_closed(preview)
            current_key = self._preview_key(preview)
            if current_key != preview_key:
                raise ValueError(
                    "This harvest allocation preview is stale. Review the current measured weight, existing allocations, and outputs again before posting inventory."
                )
            if preview["blocker_count"]:
                raise ValueError("Resolve harvest allocation blockers before posting inventory.")

            harvest = session.get(CultivationHarvest, harvest_id)
            if harvest is None:
                raise ValueError("Harvest was not found in the active cultivation facility.")
            transformation = self.transformation(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                transformation_type="harvest_allocation",
                source_entity_type="harvest",
                source_entity_id=harvest_id,
                actor=actor,
                notes=f"Harvest output allocation for {harvest.harvest_code}",
            )
            links = list(
                session.scalars(
                    select(CultivationHarvestPlant).where(CultivationHarvestPlant.harvest_id == harvest_id)
                )
            )
            plant_ids = [row.plant_id for row in links]
            plants = {
                row.id: row
                for row in session.scalars(
                    select(CultivationPlant).where(
                        CultivationPlant.id.in_(plant_ids or ["__none__"]),
                        CultivationPlant.organization_id == organization_id,
                        CultivationPlant.facility_id == facility_id,
                    )
                )
            }
            for plant_id in plant_ids:
                plant = plants.get(plant_id)
                if plant:
                    self.add_input(
                        session,
                        transformation,
                        entity_type="plant",
                        entity_id=plant.id,
                        quantity=0,
                        unit="",
                        purpose="source_plant",
                        accumulate=False,
                    )

            output_lot_ids: list[str] = []
            for row in preview["outputs"]:
                lot = InventoryLot(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    product_id=row["product_id"],
                    lot_code=row["lot_code"],
                    compliance_package_id=row["compliance_package_id"],
                    location_code=row["location_code"],
                    status=row["status"],
                    received_at=utc_now(),
                    notes=f"Created from cultivation harvest {harvest.harvest_code}.",
                )
                session.add(lot)
                session.flush()
                output_lot_ids.append(lot.id)
                session.add(
                    InventoryTransaction(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        lot_id=lot.id,
                        transaction_type="harvest_output",
                        quantity_delta=row["quantity"],
                        unit=row["unit"],
                        production_order_id=None,
                        commercial_order_id=None,
                        commercial_order_line_id=None,
                        reason=f"Cultivation harvest output: {row['purpose']}",
                        reference=harvest.harvest_code,
                        actor=actor,
                    )
                )
                self.add_output(
                    session,
                    transformation,
                    lot_id=lot.id,
                    product_id=row["product_id"],
                    quantity=row["quantity"],
                    unit=row["unit"],
                    purpose=row["purpose"],
                    measurement_basis=row["measurement_basis"],
                )
            for row in preview["losses"]:
                session.add(
                    MaterialTransformationLoss(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        transformation_id=transformation.id,
                        quantity=row["quantity"],
                        unit=row["unit"],
                        loss_type=row["loss_type"],
                        measurement_basis=row["measurement_basis"],
                        reason=row["reason"],
                    )
                )
            transformation.status = "committed"
            return {
                "transformation_id": transformation.id,
                "harvest_id": harvest_id,
                "harvest_code": harvest.harvest_code,
                "output_lot_ids": output_lot_ids,
                "reconciliation": preview["reconciliation"],
                "preview_key": current_key,
            }
