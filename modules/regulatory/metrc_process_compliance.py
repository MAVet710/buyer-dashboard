from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Engine, func, select

from modules.coman.models import InventoryLot, InventoryTransaction, utc_now
from modules.cultivation.models import CultivationHarvestPlant, CultivationPlant, CultivationPlantEvent
from modules.inventory_transfers.models import InventoryTransferLine
from modules.material_lineage.models import (
    MaterialTransformation,
    MaterialTransformationInput,
    MaterialTransformationLoss,
    MaterialTransformationOutput,
)
from modules.material_lineage.service import MaterialLineageService
from modules.operational_moats.models import CultivationHarvest
from modules.package_studio.models import PackageStudioInput, PackageStudioOutput

from .metrc_process_models import (
    CultivationHarvestPlantWeight,
    CultivationManicureBatch,
    CultivationManicurePlantWeight,
    CultivationTestSample,
    CultivationWasteRecord,
    MetrcTagInventory,
    MetrcTransferControl,
)
from .metrc_process_readiness import MetrcProcessReadinessService, MetrcTransferReadinessService


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class MetrcProcessComplianceService(MetrcProcessReadinessService):
    """Guide-aligned process layer kept provider-confirmed until sandbox promotion.

    This class closes the remaining operational gaps between DoobieLogic's richer
    internal ledger and Metrc's regulatory lifecycle. It never treats local state as
    proof that a provider mutation succeeded.
    """

    def sync_available_tags(
        self,
        organization_id: str,
        facility_id: str,
        *,
        jurisdiction_code: str,
        license_number: str,
        environment: str,
        plant_records: list[dict[str, Any]],
        package_records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        result = super().sync_available_tags(
            organization_id,
            facility_id,
            jurisdiction_code=jurisdiction_code,
            license_number=license_number,
            environment=environment,
            plant_records=plant_records,
            package_records=package_records,
        )
        env = str(environment or "").strip().casefold()
        current = {
            "plant": {self._provider_label(row) for row in plant_records if self._provider_label(row)},
            "package": {self._provider_label(row) for row in package_records if self._provider_label(row)},
        }
        with self.sessions.begin() as session:
            for tag_type in ("plant", "package"):
                rows = list(session.scalars(select(MetrcTagInventory).where(
                    MetrcTagInventory.organization_id == organization_id,
                    MetrcTagInventory.facility_id == facility_id,
                    MetrcTagInventory.environment == env,
                    MetrcTagInventory.tag_type == tag_type,
                    MetrcTagInventory.status.in_(("available", "unavailable")),
                ).with_for_update()))
                for row in rows:
                    row.status = "available" if row.label in current[tag_type] else "unavailable"
        return result | {
            "stale_available_tags_fail_closed": True,
            "plant_available": len(current["plant"]),
            "package_available": len(current["package"]),
        }

    def create_test_sample(
        self,
        organization_id: str,
        facility_id: str,
        *,
        environment: str,
        source_type: str,
        source_id: str,
        package_tag: str,
        quantity: float,
        unit: str,
        actor: str,
        provider_confirmed: bool,
        provider_reference: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        env = str(environment or "").strip().casefold()
        source_kind = str(source_type or "").strip().casefold()
        if env not in {"sandbox", "production"}:
            raise ValueError("Testing sample requires sandbox or production environment.")
        if source_kind not in {"harvest", "package"} or quantity <= 0:
            raise ValueError("Testing sample requires a harvest/package source and positive quantity.")
        with self.sessions.begin() as session:
            self._facility(session, organization_id, facility_id)
            if source_kind == "harvest":
                harvest = session.get(CultivationHarvest, str(source_id or "").strip())
                if not harvest or harvest.organization_id != organization_id or harvest.facility_id != facility_id:
                    raise ValueError("Testing source harvest was not found in the active facility.")
            else:
                lot = session.get(InventoryLot, str(source_id or "").strip())
                if not lot or lot.organization_id != organization_id or lot.facility_id != facility_id:
                    raise ValueError("Testing source package was not found in the active facility.")
            tag = session.scalar(select(MetrcTagInventory).where(
                MetrcTagInventory.organization_id == organization_id,
                MetrcTagInventory.facility_id == facility_id,
                MetrcTagInventory.environment == env,
                MetrcTagInventory.tag_type == "package",
                MetrcTagInventory.label == str(package_tag or "").strip(),
                MetrcTagInventory.status == "available",
            ).with_for_update())
            if tag is None:
                raise ValueError("Testing requires an available package tag from the freshly synced Metrc facility inventory.")
            sample = CultivationTestSample(
                organization_id=organization_id,
                facility_id=facility_id,
                environment=env,
                source_type=source_kind,
                source_id=str(source_id or "").strip(),
                package_tag=tag.label,
                quantity=float(quantity),
                unit=str(unit or "").strip(),
                status="provider_confirmed" if provider_confirmed else "planned",
                provider_reference=str(provider_reference or "").strip(),
                notes=str(notes or "").strip(),
                actor=actor,
            )
            if not sample.source_id or not sample.unit:
                raise ValueError("Testing sample source and unit are required.")
            session.add(sample)
            session.flush()
            tag.status = "used" if provider_confirmed else "reserved"
            tag.reserved_for_type = "test_sample"
            tag.reserved_for_id = sample.id
            tag.reserved_at = utc_now()
            if provider_confirmed:
                tag.used_at = utc_now()
            sample_id = sample.id
        return {
            "id": sample_id,
            "environment": env,
            "package_tag": package_tag,
            "status": "provider_confirmed" if provider_confirmed else "planned",
        }

    def confirm_test_sample(
        self,
        organization_id: str,
        facility_id: str,
        sample_id: str,
        *,
        provider_reference: str,
        actor: str,
    ) -> dict[str, Any]:
        reference = str(provider_reference or "").strip()
        if not reference:
            raise ValueError("Provider confirmation requires the Metrc response/reference evidence.")
        with self.sessions.begin() as session:
            sample = session.get(CultivationTestSample, sample_id)
            if not sample or sample.organization_id != organization_id or sample.facility_id != facility_id:
                raise ValueError("Testing sample was not found in the active facility.")
            if sample.status == "cancelled":
                raise ValueError("Cancelled testing samples cannot be confirmed.")
            tag = session.scalar(select(MetrcTagInventory).where(
                MetrcTagInventory.organization_id == organization_id,
                MetrcTagInventory.facility_id == facility_id,
                MetrcTagInventory.environment == sample.environment,
                MetrcTagInventory.tag_type == "package",
                MetrcTagInventory.label == sample.package_tag,
                MetrcTagInventory.reserved_for_type == "test_sample",
                MetrcTagInventory.reserved_for_id == sample.id,
            ).with_for_update())
            if tag is None:
                raise ValueError("Testing tag reservation no longer matches this sample; reconcile before confirming.")
            sample.status = "provider_confirmed"
            sample.provider_reference = reference
            sample.actor = actor
            tag.status = "used"
            tag.used_at = utc_now()
        return {"id": sample_id, "status": "provider_confirmed", "provider_reference": reference}

    def add_plants_to_harvest(
        self,
        organization_id: str,
        facility_id: str,
        harvest_id: str,
        *,
        plant_weights: list[dict[str, Any]],
        harvest_date: date,
        actor: str,
        provider_confirmed: bool,
    ) -> dict[str, Any]:
        if not provider_confirmed:
            raise ValueError("Confirm the Metrc same-batch harvest addition before changing local plant custody.")
        weights = {str(row.get("plant_id") or "").strip(): float(row.get("wet_weight_g") or 0.0) for row in plant_weights}
        if not weights or any(value < 0 for value in weights.values()):
            raise ValueError("Provide a non-negative wet weight for every additional harvested plant.")
        with self.sessions.begin() as session:
            harvest = session.scalar(select(CultivationHarvest).where(
                CultivationHarvest.id == harvest_id,
                CultivationHarvest.organization_id == organization_id,
                CultivationHarvest.facility_id == facility_id,
            ).with_for_update())
            if not harvest or harvest.status not in {"active", "drying"}:
                raise ValueError("Only an open harvest can accept forgotten plants.")
            original_date = (_aware(harvest.harvested_at).date() if harvest.harvested_at else _aware(harvest.created_at).date())
            if original_date != harvest_date:
                raise ValueError("Additional plants must use the exact same harvest date as the existing Metrc batch.")
            transformation = session.scalar(select(MaterialTransformation).where(
                MaterialTransformation.organization_id == organization_id,
                MaterialTransformation.facility_id == facility_id,
                MaterialTransformation.transformation_type == "harvest_allocation",
                MaterialTransformation.source_entity_type == "harvest",
                MaterialTransformation.source_entity_id == harvest.id,
            ))
            if transformation:
                downstream = int(session.scalar(select(func.count(MaterialTransformationOutput.id)).where(
                    MaterialTransformationOutput.transformation_id == transformation.id
                )) or 0)
                if downstream:
                    raise ValueError("Do not add forgotten plants after harvest packaging/output has begun; reconcile with Metrc support/state workflow.")
            if session.scalar(select(CultivationWasteRecord.id).where(
                CultivationWasteRecord.organization_id == organization_id,
                CultivationWasteRecord.facility_id == facility_id,
                CultivationWasteRecord.target_type == "harvest",
                CultivationWasteRecord.target_id == harvest.id,
            )):
                raise ValueError("Do not add forgotten plants after harvest waste has been reported.")
            existing_ids = set(session.scalars(select(CultivationHarvestPlant.plant_id).where(CultivationHarvestPlant.harvest_id == harvest.id)))
            if existing_ids.intersection(weights):
                raise ValueError("One or more plants are already part of this harvest batch.")
            plants = list(session.scalars(select(CultivationPlant).where(
                CultivationPlant.organization_id == organization_id,
                CultivationPlant.facility_id == facility_id,
                CultivationPlant.id.in_(weights),
            ).with_for_update()))
            if len(plants) != len(weights) or any(row.phase != "flowering" for row in plants):
                raise ValueError("Every added plant must be an active flowering plant in this facility.")
            for plant in plants:
                session.add(CultivationHarvestPlant(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    harvest_id=harvest.id,
                    plant_id=plant.id,
                    assigned_by=actor,
                ))
                session.add(CultivationHarvestPlantWeight(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    harvest_id=harvest.id,
                    plant_id=plant.id,
                    wet_weight_g=weights[plant.id],
                    actor=actor,
                ))
                plant.phase = "harvested"
                plant.retired_at = utc_now()
                session.add(CultivationPlantEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    plant_id=plant.id,
                    event_type="added_to_existing_metrc_harvest",
                    from_value="flowering",
                    to_value="harvested",
                    reason=f"Added to harvest {harvest.harvest_code} with wet weight {weights[plant.id]:.4f} g",
                    actor=actor,
                ))
            harvest.plant_count = int(harvest.plant_count or 0) + len(plants)
            harvest.wet_weight_g = float(harvest.wet_weight_g or 0.0) + sum(weights.values())
        return {
            "harvest_id": harvest_id,
            "added_plant_count": len(weights),
            "added_wet_weight_g": sum(weights.values()),
            "harvest_date": harvest_date.isoformat(),
        }

    def add_plants_to_manicure_batch(
        self,
        organization_id: str,
        facility_id: str,
        batch_id: str,
        *,
        plant_weights: list[dict[str, Any]],
        actor: str,
        provider_confirmed: bool,
    ) -> dict[str, Any]:
        if not provider_confirmed:
            raise ValueError("Confirm the Metrc manicure-batch addition before changing local regulatory state.")
        weights = {str(row.get("plant_id") or "").strip(): float(row.get("weight_g") or 0.0) for row in plant_weights}
        if not weights or any(value <= 0 for value in weights.values()):
            raise ValueError("Provide a positive manicure weight for every additional plant.")
        with self.sessions.begin() as session:
            batch = session.scalar(select(CultivationManicureBatch).where(
                CultivationManicureBatch.id == batch_id,
                CultivationManicureBatch.organization_id == organization_id,
                CultivationManicureBatch.facility_id == facility_id,
            ).with_for_update())
            if batch is None:
                raise ValueError("Manicure batch was not found in the active facility.")
            existing = set(session.scalars(select(CultivationManicurePlantWeight.plant_id).where(
                CultivationManicurePlantWeight.manicure_batch_id == batch.id
            )))
            if existing.intersection(weights):
                raise ValueError("One or more plants are already part of this manicure batch.")
            plants = list(session.scalars(select(CultivationPlant).where(
                CultivationPlant.organization_id == organization_id,
                CultivationPlant.facility_id == facility_id,
                CultivationPlant.id.in_(weights),
            )))
            if len(plants) != len(weights) or any(row.phase != batch.source_phase for row in plants):
                raise ValueError("Additional manicure plants must exist in this facility and match the original batch phase.")
            for plant in plants:
                session.add(CultivationManicurePlantWeight(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    manicure_batch_id=batch.id,
                    plant_id=plant.id,
                    weight_g=weights[plant.id],
                ))
            batch.total_weight_g = float(batch.total_weight_g or 0.0) + sum(weights.values())
            batch.actor = actor
        return {"id": batch_id, "added_plant_count": len(weights), "added_weight_g": sum(weights.values())}

    def record_waste(
        self,
        organization_id: str,
        facility_id: str,
        *,
        actor: str,
        provider_confirmed: bool,
        **payload: Any,
    ) -> dict[str, Any]:
        if not provider_confirmed:
            raise ValueError("Confirm the required Metrc waste record before marking the regulatory event confirmed locally.")
        target_type = str(payload.get("target_type") or "").strip().casefold()
        target_id = str(payload.get("target_id") or "").strip()
        method = str(payload.get("method") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        location = str(payload.get("location") or "").strip()
        weight = float(payload.get("weight") or 0.0)
        unit = str(payload.get("unit") or "").strip().casefold()
        if target_type not in {"plant", "plant_group", "harvest"} or not target_id or not method or not reason or not location or not unit or weight < 0:
            raise ValueError("Waste requires source, method, weight/UOM, reason, date, and location.")
        if unit not in {"g", "gram", "grams"}:
            raise ValueError("Metrc readiness stores cannabis waste in canonical grams.")
        with self.sessions.begin() as session:
            self._facility(session, organization_id, facility_id)
            basis = str(payload.get("measurement_basis") or "").strip().casefold()
            if target_type == "harvest":
                harvest = session.get(CultivationHarvest, target_id)
                if not harvest or harvest.organization_id != organization_id or harvest.facility_id != facility_id:
                    raise ValueError("Waste source harvest was not found in the active facility.")
                if basis not in {"wet", "dry"}:
                    basis = "dry" if float(harvest.dry_weight_g or 0.0) > 0 else "wet"
                measured = float(harvest.dry_weight_g or 0.0) if basis == "dry" else float(harvest.wet_weight_g or 0.0)
                if measured <= 0:
                    raise ValueError(f"Record measured harvest {basis} weight before posting {basis}-basis waste.")
                transformation = MaterialLineageService.transformation(
                    session,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    transformation_type="harvest_allocation",
                    source_entity_type="harvest",
                    source_entity_id=harvest.id,
                    actor=actor,
                    notes=f"Harvest output allocation for {harvest.harvest_code}",
                )
                disposed = float(session.scalar(select(func.coalesce(func.sum(MaterialTransformationOutput.quantity), 0.0)).where(
                    MaterialTransformationOutput.transformation_id == transformation.id,
                    MaterialTransformationOutput.measurement_basis == basis,
                )) or 0.0) + float(session.scalar(select(func.coalesce(func.sum(MaterialTransformationLoss.quantity), 0.0)).where(
                    MaterialTransformationLoss.transformation_id == transformation.id,
                    MaterialTransformationLoss.measurement_basis == basis,
                )) or 0.0)
                if disposed + weight > measured + 1e-6:
                    raise ValueError("Harvest waste would over-allocate the measured material basis.")
            row = CultivationWasteRecord(
                organization_id=organization_id,
                facility_id=facility_id,
                target_type=target_type,
                target_id=target_id,
                method=method,
                material_mixed=str(payload.get("material_mixed") or "").strip(),
                weight=weight,
                unit="g",
                reason=reason,
                waste_date=payload.get("waste_date") or date.today(),
                location=location,
                notes=str(payload.get("notes") or "").strip(),
                actor=actor,
            )
            session.add(row)
            session.flush()
            if target_type == "harvest" and weight > 0:
                session.add(MaterialTransformationLoss(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    transformation_id=transformation.id,
                    quantity=weight,
                    unit="g",
                    loss_type="waste",
                    measurement_basis=basis,
                    reason=reason,
                ))
            row_id = row.id
        return {
            "id": row_id,
            "target_type": target_type,
            "target_id": target_id,
            "weight": weight,
            "unit": "g",
            "measurement_basis": basis if target_type == "harvest" else "",
        }

    def destroy_plant(
        self,
        organization_id: str,
        facility_id: str,
        plant_id: str,
        *,
        method: str,
        material_mixed: str,
        weight: float,
        unit: str,
        reason: str,
        waste_date: date,
        location: str,
        notes: str,
        actor: str,
        provider_confirmed: bool,
    ) -> dict[str, Any]:
        if not provider_confirmed:
            raise ValueError("Confirm the plant destruction/waste in Metrc before retiring the local plant record.")
        if weight < 0 or str(unit or "").strip().casefold() not in {"g", "gram", "grams"}:
            raise ValueError("Plant destruction requires a non-negative canonical gram waste weight.")
        with self.sessions.begin() as session:
            plant = session.scalar(select(CultivationPlant).where(
                CultivationPlant.id == plant_id,
                CultivationPlant.organization_id == organization_id,
                CultivationPlant.facility_id == facility_id,
            ).with_for_update())
            if not plant or plant.phase in {"harvested", "destroyed"}:
                raise ValueError("Only an active plant can be destroyed through this workflow.")
            if not str(method or "").strip() or not str(reason or "").strip() or not str(location or "").strip():
                raise ValueError("Plant destruction requires method, reason, date, and location.")
            session.add(CultivationWasteRecord(
                organization_id=organization_id,
                facility_id=facility_id,
                target_type="plant",
                target_id=plant.id,
                method=str(method).strip(),
                material_mixed=str(material_mixed or "").strip(),
                weight=float(weight),
                unit="g",
                reason=str(reason).strip(),
                waste_date=waste_date,
                location=str(location).strip(),
                notes=str(notes or "").strip(),
                actor=actor,
            ))
            before = plant.phase
            plant.phase = "destroyed"
            plant.retired_at = utc_now()
            session.add(CultivationPlantEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                plant_id=plant.id,
                event_type="destroyed_with_waste",
                from_value=before,
                to_value="destroyed",
                reason=str(reason).strip(),
                notes=str(notes or "").strip(),
                actor=actor,
            ))
        return {"plant_id": plant_id, "phase": "destroyed", "waste_weight_g": float(weight)}

    def harvest_closeout_preview(self, organization_id: str, facility_id: str, harvest_id: str) -> dict[str, Any]:
        with self.sessions() as session:
            harvest = session.get(CultivationHarvest, harvest_id)
            if not harvest or harvest.organization_id != organization_id or harvest.facility_id != facility_id:
                raise ValueError("Harvest was not found in the active facility.")
            basis = "dry" if float(harvest.dry_weight_g or 0.0) > 0 else "wet"
            measured = float(harvest.dry_weight_g or 0.0) if basis == "dry" else float(harvest.wet_weight_g or 0.0)
            if measured <= 0:
                raise ValueError("Record a measured harvest weight before closeout.")
            transformation = session.scalar(select(MaterialTransformation).where(
                MaterialTransformation.organization_id == organization_id,
                MaterialTransformation.facility_id == facility_id,
                MaterialTransformation.transformation_type == "harvest_allocation",
                MaterialTransformation.source_entity_type == "harvest",
                MaterialTransformation.source_entity_id == harvest.id,
            ))
            output_total = 0.0
            loss_total = 0.0
            moisture_total = 0.0
            output_count = 0
            if transformation:
                outputs = list(session.scalars(select(MaterialTransformationOutput).where(
                    MaterialTransformationOutput.transformation_id == transformation.id,
                    MaterialTransformationOutput.measurement_basis == basis,
                )))
                losses = list(session.scalars(select(MaterialTransformationLoss).where(
                    MaterialTransformationLoss.transformation_id == transformation.id,
                    MaterialTransformationLoss.measurement_basis == basis,
                )))
                output_total = sum(float(row.quantity or 0.0) for row in outputs)
                loss_total = sum(float(row.quantity or 0.0) for row in losses if row.loss_type != "moisture_loss")
                moisture_total = sum(float(row.quantity or 0.0) for row in losses if row.loss_type == "moisture_loss")
                output_count = len(outputs)
            remaining = measured - output_total - loss_total - moisture_total
            structured_waste = int(session.scalar(select(func.count(CultivationWasteRecord.id)).where(
                CultivationWasteRecord.organization_id == organization_id,
                CultivationWasteRecord.facility_id == facility_id,
                CultivationWasteRecord.target_type == "harvest",
                CultivationWasteRecord.target_id == harvest.id,
            )) or 0)
            return {
                "harvest_id": harvest.id,
                "harvest_code": harvest.harvest_code,
                "status": harvest.status,
                "measurement_basis": basis,
                "measured_g": measured,
                "package_or_output_count": output_count,
                "output_g": output_total,
                "reported_loss_or_waste_g": loss_total,
                "existing_moisture_loss_g": moisture_total,
                "remaining_for_moisture_loss_g": max(0.0, remaining),
                "overallocated_g": max(0.0, -remaining),
                "structured_waste_record_count": structured_waste,
                "can_finish": output_count > 0 and remaining >= -1e-6 and harvest.status in {"active", "drying"},
            }

    def finish_harvest(
        self,
        organization_id: str,
        facility_id: str,
        harvest_id: str,
        *,
        actor: str,
        provider_confirmed: bool,
        all_waste_reported: bool,
    ) -> dict[str, Any]:
        if not provider_confirmed:
            raise ValueError("Confirm the Metrc Finish Batch action before completing the harvest locally.")
        if not all_waste_reported:
            raise ValueError("Confirm all actual harvest waste has been reported before remaining weight is classified as moisture loss.")
        preview = self.harvest_closeout_preview(organization_id, facility_id, harvest_id)
        if not preview["can_finish"]:
            raise ValueError("Harvest cannot be finished until at least one output/package exists and measured material is not over-allocated.")
        with self.sessions.begin() as session:
            harvest = session.scalar(select(CultivationHarvest).where(
                CultivationHarvest.id == harvest_id,
                CultivationHarvest.organization_id == organization_id,
                CultivationHarvest.facility_id == facility_id,
            ).with_for_update())
            if not harvest or harvest.status not in {"active", "drying"}:
                raise ValueError("Only an active/drying harvest can be finished.")
            transformation = session.scalar(select(MaterialTransformation).where(
                MaterialTransformation.organization_id == organization_id,
                MaterialTransformation.facility_id == facility_id,
                MaterialTransformation.transformation_type == "harvest_allocation",
                MaterialTransformation.source_entity_type == "harvest",
                MaterialTransformation.source_entity_id == harvest.id,
            ).with_for_update())
            if transformation is None:
                raise ValueError("Harvest output genealogy must exist before finishing the batch.")
            basis = preview["measurement_basis"]
            remainder = float(preview["remaining_for_moisture_loss_g"])
            if remainder > 1e-6:
                session.add(MaterialTransformationLoss(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    transformation_id=transformation.id,
                    quantity=remainder,
                    unit="g",
                    loss_type="moisture_loss",
                    measurement_basis=basis,
                    reason="Remaining harvest weight at Metrc Finish Batch closeout",
                ))
            transformation.status = "committed"
            harvest.status = "completed"
            harvest.completed_at = harvest.completed_at or utc_now()
            session.flush()
        return self.harvest_closeout_preview(organization_id, facility_id, harvest_id)

    def discontinue_harvest(
        self,
        organization_id: str,
        facility_id: str,
        harvest_id: str,
        *,
        actor: str,
        provider_confirmed: bool,
        reason: str,
    ) -> dict[str, Any]:
        if not provider_confirmed:
            raise ValueError("Confirm the Metrc harvest discontinue/restore action before restoring plants locally.")
        with self.sessions.begin() as session:
            harvest = session.scalar(select(CultivationHarvest).where(
                CultivationHarvest.id == harvest_id,
                CultivationHarvest.organization_id == organization_id,
                CultivationHarvest.facility_id == facility_id,
            ).with_for_update())
            if not harvest or harvest.status not in {"active", "drying"}:
                raise ValueError("Only an open harvest can be discontinued.")
            created = _aware(harvest.harvested_at or harvest.created_at)
            if (_aware(utc_now()) - created).total_seconds() > 48 * 3600:
                raise ValueError("Metrc guide discontinue window has passed: this harvest is older than 48 hours.")
            if session.scalar(select(CultivationWasteRecord.id).where(
                CultivationWasteRecord.organization_id == organization_id,
                CultivationWasteRecord.facility_id == facility_id,
                CultivationWasteRecord.target_type == "harvest",
                CultivationWasteRecord.target_id == harvest.id,
            )):
                raise ValueError("Harvest cannot be discontinued after waste has been reported.")
            transformation = session.scalar(select(MaterialTransformation).where(
                MaterialTransformation.organization_id == organization_id,
                MaterialTransformation.facility_id == facility_id,
                MaterialTransformation.transformation_type == "harvest_allocation",
                MaterialTransformation.source_entity_type == "harvest",
                MaterialTransformation.source_entity_id == harvest.id,
            ))
            if transformation:
                if session.scalar(select(MaterialTransformationOutput.id).where(MaterialTransformationOutput.transformation_id == transformation.id)):
                    raise ValueError("Harvest cannot be discontinued after packages/output have been created.")
                if session.scalar(select(MaterialTransformationLoss.id).where(MaterialTransformationLoss.transformation_id == transformation.id)):
                    raise ValueError("Harvest cannot be discontinued after waste/loss has been reported.")
            links = list(session.scalars(select(CultivationHarvestPlant).where(CultivationHarvestPlant.harvest_id == harvest.id)))
            plants = list(session.scalars(select(CultivationPlant).where(CultivationPlant.id.in_([row.plant_id for row in links] or ["__none__"])).with_for_update()))
            for plant in plants:
                before = plant.phase
                plant.phase = "flowering"
                plant.retired_at = None
                session.add(CultivationPlantEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    plant_id=plant.id,
                    event_type="harvest_discontinued_restored",
                    from_value=before,
                    to_value="flowering",
                    reason=str(reason or "").strip() or f"Harvest {harvest.harvest_code} discontinued",
                    actor=actor,
                ))
            harvest.status = "cancelled"
        return {"harvest_id": harvest_id, "status": "cancelled", "restored_plant_count": len(plants)}

    def package_discontinue_preflight(
        self,
        organization_id: str,
        facility_id: str,
        lot_id: str,
    ) -> dict[str, Any]:
        with self.sessions() as session:
            lot = session.get(InventoryLot, lot_id)
            if not lot or lot.organization_id != organization_id or lot.facility_id != facility_id:
                raise ValueError("Package was not found in the active facility.")
            package_id = str(lot.compliance_package_id or "").strip()
            blockers: list[str] = []
            if not package_id:
                blockers.append("Package has no regulatory package identifier.")
            transactions = list(session.scalars(select(InventoryTransaction).where(
                InventoryTransaction.organization_id == organization_id,
                InventoryTransaction.facility_id == facility_id,
                InventoryTransaction.lot_id == lot.id,
            ).order_by(InventoryTransaction.created_at)))
            transfer_count = int(session.scalar(select(func.count(InventoryTransferLine.id)).where(
                InventoryTransferLine.organization_id == organization_id,
                InventoryTransferLine.source_lot_id == lot.id,
            )) or 0)
            material_input_count = int(session.scalar(select(func.count(MaterialTransformationInput.id)).where(
                MaterialTransformationInput.organization_id == organization_id,
                MaterialTransformationInput.lot_id == lot.id,
            )) or 0)
            studio_input_count = int(session.scalar(select(func.count(PackageStudioInput.id)).where(
                PackageStudioInput.organization_id == organization_id,
                PackageStudioInput.lot_id == lot.id,
            )) or 0)
            has_source_lineage = bool(session.scalar(select(PackageStudioOutput.id).where(PackageStudioOutput.lot_id == lot.id))) or bool(
                session.scalar(select(MaterialTransformationOutput.id).where(MaterialTransformationOutput.lot_id == lot.id))
            )
            allowed_origin_types = {"harvest_output", "package_output", "production_output", "extraction_output"}
            non_origin_transactions = [row.transaction_type for row in transactions if str(row.transaction_type or "") not in allowed_origin_types]
            if not has_source_lineage:
                blockers.append("Local source lineage is not sufficient to safely project a created-in-error restoration.")
            if non_origin_transactions or len(transactions) > 1:
                blockers.append("Package has local inventory activity after creation and is not safe to discontinue as created-in-error.")
            if transfer_count:
                blockers.append("Package has been transferred or included in a transfer.")
            if material_input_count or studio_input_count:
                blockers.append("Package has been consumed or used in a downstream transformation/repack.")
            return {
                "lot_id": lot.id,
                "package_id": package_id,
                "status": lot.status,
                "transaction_count": len(transactions),
                "transfer_count": transfer_count,
                "downstream_use_count": material_input_count + studio_input_count,
                "eligible_local": not blockers,
                "blockers": blockers,
                "provider_operation": "package_discontinue",
                "provider_dispatch": "locked_until_sandbox_write_readback_verification",
                "note": "Finish is separate: depleted packages finish at zero; discontinue is only for a package created in error before modification/transfer.",
            }


class MetrcStrictTransferService(MetrcTransferReadinessService):
    """Treat strict transfer creation as the actual physical departure boundary.

    DoobieLogic already has a separate manifest-draft/preflight workflow. The
    inventory transfer ledger mutates only at physical dispatch, so a strict Metrc
    transfer becomes departure-locked immediately rather than creating a false
    pre-departure inventory decrement.
    """

    def dispatch_whole_packages(self, *args: Any, actor: str, **kwargs: Any) -> dict[str, Any]:
        result = super().dispatch_whole_packages(*args, actor=actor, **kwargs)
        organization_id = str(args[0]) if args else str(kwargs.get("organization_id") or "")
        transfer_id = str(result.get("id") or "")
        with self.sessions.begin() as session:
            control = session.scalar(select(MetrcTransferControl).where(
                MetrcTransferControl.organization_id == organization_id,
                MetrcTransferControl.transfer_id == transfer_id,
            ).with_for_update())
            if control:
                control.provider_status = "departed"
                control.departure_confirmed_at = control.departure_confirmed_at or utc_now()
                control.departure_confirmed_by = control.departure_confirmed_by or actor
        return self.detail(organization_id, transfer_id)
