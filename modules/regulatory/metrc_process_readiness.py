from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import AuditEvent, Facility, InventoryLot, InventoryTransaction, Product, utc_now
from modules.cultivation.batch_models import CultivationPlantGroup, CultivationPlantGroupMember
from modules.cultivation.batches import CultivationBatchService
from modules.cultivation.models import CultivationHarvestPlant, CultivationPlant, CultivationPlantEvent
from modules.inventory_availability.service import InventoryAvailabilityService
from modules.inventory_transfers.models import InventoryTransfer, InventoryTransferLine
from modules.inventory_transfers.service import InventoryTransferService
from modules.operational_moats.models import CultivationHarvest

from .metrc_process_models import (
    CultivationAdditiveApplication,
    CultivationHarvestPlantWeight,
    CultivationManicureBatch,
    CultivationManicurePlantWeight,
    CultivationRegulatoryIdentity,
    CultivationTestSample,
    CultivationWasteRecord,
    MetrcTagInventory,
    MetrcTransferControl,
    MetrcTransferLineReturn,
)


ORIGIN_TYPES = {"mother", "source_package", "transfer", "beginning_inventory", "state_authorized", "legacy_demo"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MetrcProcessReadinessService:
    """Durable process layer that mirrors the Metrc lifecycle without bypassing provider truth.

    Provider-changing operations require an explicit provider confirmation flag until
    the corresponding deterministic Metrc write contract has passed sandbox
    write/readback promotion. This lets credentials be connected without another
    schema/process rewrite while keeping regulatory writes fail closed.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @staticmethod
    def _facility(session: Session, organization_id: str, facility_id: str) -> Facility:
        facility = session.get(Facility, facility_id)
        if not facility or facility.organization_id != organization_id or not facility.active:
            raise ValueError("The active facility was not found in the organization.")
        return facility

    @staticmethod
    def _provider_label(record: dict[str, Any]) -> str:
        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        return str(record.get("label") or source.get("Label") or source.get("Tag") or "").strip()

    @staticmethod
    def _provider_id(record: dict[str, Any]) -> str:
        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        return str(record.get("provider_id") or source.get("Id") or source.get("id") or "").strip()

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
        env = str(environment or "").strip().casefold()
        if env not in {"sandbox", "production"}:
            raise ValueError("Metrc tag sync requires sandbox or production environment.")
        jurisdiction = str(jurisdiction_code or "").strip().upper()
        license_no = str(license_number or "").strip()
        if not jurisdiction or not license_no:
            raise ValueError("Metrc tag sync requires an exact jurisdiction and facility license.")
        now = _now()
        seen: dict[str, set[str]] = {"plant": set(), "package": set()}
        with self.sessions.begin() as session:
            self._facility(session, organization_id, facility_id)
            for tag_type, records in (("plant", plant_records), ("package", package_records)):
                for record in records:
                    label = self._provider_label(record)
                    if not label:
                        continue
                    seen[tag_type].add(label)
                    row = session.scalar(
                        select(MetrcTagInventory).where(
                            MetrcTagInventory.facility_id == facility_id,
                            MetrcTagInventory.environment == env,
                            MetrcTagInventory.tag_type == tag_type,
                            MetrcTagInventory.label == label,
                        )
                    )
                    if row is None:
                        row = MetrcTagInventory(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            jurisdiction_code=jurisdiction,
                            license_number=license_no,
                            environment=env,
                            tag_type=tag_type,
                            label=label,
                            provider_id=self._provider_id(record),
                            status="available",
                            synced_at=now,
                        )
                        session.add(row)
                    else:
                        row.jurisdiction_code = jurisdiction
                        row.license_number = license_no
                        row.provider_id = self._provider_id(record) or row.provider_id
                        row.synced_at = now
                        # A locally used/reserved/voided tag is never resurrected merely
                        # because a stale provider response includes it.
                        if row.status == "available":
                            row.status = "available"
            session.flush()
        return {
            "plant_available": len(seen["plant"]),
            "package_available": len(seen["package"]),
            "synced_at": now.isoformat(),
            "environment": env,
            "license_number": license_no,
        }

    def list_tags(
        self,
        organization_id: str,
        facility_id: str,
        *,
        environment: str,
        tag_type: str = "",
        status: str = "available",
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        with self.sessions() as session:
            self._facility(session, organization_id, facility_id)
            statement = select(MetrcTagInventory).where(
                MetrcTagInventory.organization_id == organization_id,
                MetrcTagInventory.facility_id == facility_id,
                MetrcTagInventory.environment == str(environment).strip().casefold(),
            )
            if tag_type:
                statement = statement.where(MetrcTagInventory.tag_type == tag_type)
            if status:
                statement = statement.where(MetrcTagInventory.status == status)
            rows = list(session.scalars(statement.order_by(MetrcTagInventory.label).limit(max(1, min(limit, 5000)))))
        return [self._tag_payload(row) for row in rows]

    @staticmethod
    def _tag_payload(row: MetrcTagInventory) -> dict[str, Any]:
        return {
            "id": row.id,
            "tag_type": row.tag_type,
            "label": row.label,
            "status": row.status,
            "jurisdiction_code": row.jurisdiction_code,
            "license_number": row.license_number,
            "environment": row.environment,
            "reserved_for_type": row.reserved_for_type,
            "reserved_for_id": row.reserved_for_id,
            "synced_at": row.synced_at.isoformat() if row.synced_at else None,
        }

    def create_immature_group(
        self,
        organization_id: str,
        facility_id: str,
        *,
        group_code: str,
        group_type: str,
        strain_name: str,
        quantity: int,
        origin_type: str,
        origin_reference: str,
        actor: str,
        room_code: str = "UNASSIGNED",
        mother_plant_id: str | None = None,
        source_lot_id: str | None = None,
        planted_at: date | None = None,
        estimated_harvest_date: date | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        origin = str(origin_type or "").strip().casefold()
        reference = str(origin_reference or "").strip()
        if origin not in ORIGIN_TYPES:
            raise ValueError("Select a supported plant origin before creating an immature batch.")
        if origin != "legacy_demo" and not reference:
            raise ValueError("Metrc-aligned immature batches require a durable origin reference; unexplained 'thin air' creation is blocked.")
        if origin == "mother" and not mother_plant_id:
            raise ValueError("Mother-origin plantings require the source mother plant.")
        if origin == "source_package" and not source_lot_id:
            raise ValueError("Source-package plantings require the source package/lot.")
        kind = str(group_type or "").strip().casefold()
        if kind not in {"clone_batch", "seed_batch", "nursery"}:
            raise ValueError("Metrc-aligned immature creation must begin as a clone, seed, or nursery batch.")

        group = CultivationBatchService(self.engine).create_group(
            organization_id,
            facility_id,
            group_code=group_code,
            group_type=kind,
            strain_name=strain_name,
            quantity=quantity,
            actor=actor,
            room_code=room_code,
            mother_plant_id=mother_plant_id,
            source_lot_id=source_lot_id,
            # Existing plant_tag remains DoobieLogic's durable internal identity.
            # Regulatory RFID identity is deliberately separate and blank here.
            tag_prefix=f"DL-{str(group_code).strip()}",
            planted_at=planted_at,
            estimated_harvest_date=estimated_harvest_date,
            notes=notes,
        )
        plant_ids = [str(row.get("id") or "") for row in group.get("plants") or []]
        with self.sessions.begin() as session:
            self._facility(session, organization_id, facility_id)
            for plant_id in plant_ids:
                if not plant_id:
                    continue
                existing = session.scalar(select(CultivationRegulatoryIdentity).where(CultivationRegulatoryIdentity.plant_id == plant_id))
                if existing is None:
                    session.add(
                        CultivationRegulatoryIdentity(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            plant_id=plant_id,
                            origin_type=origin,
                            origin_reference=reference,
                            metrc_plant_tag=None,
                        )
                    )
        return self.group_regulatory_detail(organization_id, facility_id, group["id"])

    def group_regulatory_detail(self, organization_id: str, facility_id: str, group_id: str) -> dict[str, Any]:
        group = CultivationBatchService(self.engine).group_detail(organization_id, facility_id, group_id)
        plant_ids = [str(row.get("id") or "") for row in group.get("plants") or []]
        with self.sessions() as session:
            identities = list(
                session.scalars(select(CultivationRegulatoryIdentity).where(CultivationRegulatoryIdentity.plant_id.in_(plant_ids or ["__none__"])))
            )
        by_plant = {row.plant_id: row for row in identities}
        enriched = []
        for plant in group.get("plants") or []:
            identity = by_plant.get(str(plant.get("id") or ""))
            enriched.append({
                **plant,
                "metrc_plant_tag": identity.metrc_plant_tag if identity else None,
                "origin_type": identity.origin_type if identity else "",
                "origin_reference": identity.origin_reference if identity else "",
            })
        return {**group, "plants": enriched}

    def assign_vegetative_tags(
        self,
        organization_id: str,
        facility_id: str,
        group_id: str,
        *,
        environment: str,
        actor: str,
        provider_confirmed: bool,
        tag_labels: list[str] | None = None,
        provider_reference: str = "",
    ) -> dict[str, Any]:
        if not provider_confirmed:
            raise ValueError("Confirm the Metrc growth-phase/tag assignment before DoobieLogic marks the regulatory tags used.")
        env = str(environment or "").strip().casefold()
        with self.sessions.begin() as session:
            self._facility(session, organization_id, facility_id)
            group = session.get(CultivationPlantGroup, group_id)
            if not group or group.organization_id != organization_id or group.facility_id != facility_id or group.status != "active":
                raise ValueError("The active immature group was not found in this facility.")
            members = list(
                session.scalars(
                    select(CultivationPlant)
                    .join(CultivationPlantGroupMember, CultivationPlantGroupMember.plant_id == CultivationPlant.id)
                    .where(CultivationPlantGroupMember.group_id == group.id)
                    .order_by(CultivationPlant.plant_tag)
                    .with_for_update()
                )
            )
            immature = [row for row in members if row.phase in {"clone", "seedling"}]
            if not immature:
                raise ValueError("This group has no immature plants awaiting vegetative tagging.")
            identities = list(
                session.scalars(select(CultivationRegulatoryIdentity).where(CultivationRegulatoryIdentity.plant_id.in_([row.id for row in immature])).with_for_update())
            )
            identity_by_plant = {row.plant_id: row for row in identities}
            if len(identity_by_plant) != len(immature):
                raise ValueError("Every immature plant must have a recorded regulatory origin before vegetative tagging.")
            if any(row.metrc_plant_tag for row in identities):
                raise ValueError("One or more selected plants already has a Metrc plant tag.")

            requested = [str(value).strip() for value in (tag_labels or []) if str(value).strip()]
            if requested and len(requested) != len(immature):
                raise ValueError("Provide exactly one available Metrc plant tag per plant, or omit tags for automatic allocation.")
            tag_statement = select(MetrcTagInventory).where(
                MetrcTagInventory.organization_id == organization_id,
                MetrcTagInventory.facility_id == facility_id,
                MetrcTagInventory.environment == env,
                MetrcTagInventory.tag_type == "plant",
                MetrcTagInventory.status == "available",
            )
            if requested:
                tag_statement = tag_statement.where(MetrcTagInventory.label.in_(requested))
            tags = list(session.scalars(tag_statement.order_by(MetrcTagInventory.label).with_for_update()))
            if requested:
                tags = sorted(tags, key=lambda row: requested.index(row.label) if row.label in requested else 999999)
            else:
                tags = tags[: len(immature)]
            if len(tags) < len(immature):
                raise ValueError("Not enough freshly synced available Metrc plant tags exist for this facility/environment.")

            now = _now()
            for plant, tag in zip(immature, tags, strict=True):
                identity = identity_by_plant[plant.id]
                tag.status = "used"
                tag.reserved_for_type = "plant"
                tag.reserved_for_id = plant.id
                tag.used_at = now
                identity.metrc_plant_tag = tag.label
                identity.tag_assigned_at = now
                before = plant.phase
                plant.phase = "vegetative"
                session.add(CultivationPlantEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    plant_id=plant.id,
                    event_type="metrc_tag_assigned_vegetative",
                    from_value=before,
                    to_value="vegetative",
                    reason=f"Metrc tag {tag.label} assigned",
                    notes=str(provider_reference or ""),
                    actor=actor,
                ))
            group.group_type = "vegetative"
        return self.group_regulatory_detail(organization_id, facility_id, group_id)

    def replace_plant_tag(
        self,
        organization_id: str,
        facility_id: str,
        plant_id: str,
        *,
        environment: str,
        new_tag_label: str,
        actor: str,
        provider_confirmed: bool,
        replace_date: date | None = None,
    ) -> dict[str, Any]:
        if not provider_confirmed:
            raise ValueError("Confirm the Metrc replace-tag action before replacing regulatory identity in DoobieLogic.")
        label = str(new_tag_label or "").strip()
        with self.sessions.begin() as session:
            plant = session.get(CultivationPlant, plant_id)
            if not plant or plant.organization_id != organization_id or plant.facility_id != facility_id:
                raise ValueError("Plant was not found in the active facility.")
            identity = session.scalar(select(CultivationRegulatoryIdentity).where(CultivationRegulatoryIdentity.plant_id == plant.id).with_for_update())
            if not identity or not identity.metrc_plant_tag:
                raise ValueError("Plant does not currently have a Metrc regulatory tag to replace.")
            tag = session.scalar(
                select(MetrcTagInventory).where(
                    MetrcTagInventory.facility_id == facility_id,
                    MetrcTagInventory.environment == str(environment).strip().casefold(),
                    MetrcTagInventory.tag_type == "plant",
                    MetrcTagInventory.label == label,
                    MetrcTagInventory.status == "available",
                ).with_for_update()
            )
            if tag is None:
                raise ValueError("The replacement plant tag is not available in the synced Metrc tag inventory.")
            old = identity.metrc_plant_tag
            identity.previous_metrc_plant_tag = old
            identity.metrc_plant_tag = tag.label
            identity.tag_replaced_at = _now()
            tag.status = "used"
            tag.reserved_for_type = "plant"
            tag.reserved_for_id = plant.id
            tag.used_at = _now()
            session.add(CultivationPlantEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                plant_id=plant.id,
                event_type="metrc_tag_replaced",
                from_value=old,
                to_value=tag.label,
                reason=f"Replace date {(replace_date or date.today()).isoformat()}",
                actor=actor,
            ))
        return {"plant_id": plant_id, "previous_metrc_plant_tag": old, "metrc_plant_tag": label}

    def correct_plant_strain(
        self,
        organization_id: str,
        facility_id: str,
        plant_id: str,
        *,
        strain_name: str,
        actor: str,
        provider_confirmed: bool,
        reason: str,
    ) -> dict[str, Any]:
        if not provider_confirmed:
            raise ValueError("Confirm the Metrc strain correction before changing the local regulatory projection.")
        strain = str(strain_name or "").strip()
        if not strain:
            raise ValueError("Corrected strain name is required.")
        with self.sessions.begin() as session:
            plant = session.get(CultivationPlant, plant_id)
            if not plant or plant.organization_id != organization_id or plant.facility_id != facility_id:
                raise ValueError("Plant was not found in the active facility.")
            old = plant.strain_name
            plant.strain_name = strain
            session.add(CultivationPlantEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                plant_id=plant.id,
                event_type="strain_corrected",
                from_value=old,
                to_value=strain,
                reason=str(reason or "").strip(),
                actor=actor,
            ))
        return {"plant_id": plant_id, "previous_strain": old, "strain_name": strain}

    def record_harvest_wet_weights(
        self,
        organization_id: str,
        facility_id: str,
        harvest_id: str,
        *,
        plant_weights: list[dict[str, Any]],
        actor: str,
        provider_confirmed: bool,
    ) -> dict[str, Any]:
        if not provider_confirmed:
            raise ValueError("Confirm the Metrc harvest action before closing plant-level wet weights in DoobieLogic.")
        supplied = {str(row.get("plant_id") or "").strip(): float(row.get("wet_weight_g") or 0.0) for row in plant_weights}
        if not supplied or any(weight < 0 for weight in supplied.values()):
            raise ValueError("Provide a non-negative wet weight for every harvested plant.")
        with self.sessions.begin() as session:
            harvest = session.get(CultivationHarvest, harvest_id)
            if not harvest or harvest.organization_id != organization_id or harvest.facility_id != facility_id:
                raise ValueError("Harvest was not found in the active facility.")
            links = list(session.scalars(select(CultivationHarvestPlant).where(CultivationHarvestPlant.harvest_id == harvest.id)))
            expected = {row.plant_id for row in links}
            if set(supplied) != expected:
                raise ValueError("Wet-weight submission must contain exactly every plant assigned to this harvest.")
            plants = list(session.scalars(select(CultivationPlant).where(CultivationPlant.id.in_(expected)).with_for_update()))
            if any(row.phase != "flowering" for row in plants):
                raise ValueError("Only flowering plants can be harvested into this batch.")
            for plant in plants:
                row = session.scalar(
                    select(CultivationHarvestPlantWeight).where(
                        CultivationHarvestPlantWeight.harvest_id == harvest.id,
                        CultivationHarvestPlantWeight.plant_id == plant.id,
                    )
                )
                if row is None:
                    row = CultivationHarvestPlantWeight(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        harvest_id=harvest.id,
                        plant_id=plant.id,
                        wet_weight_g=supplied[plant.id],
                        actor=actor,
                    )
                    session.add(row)
                else:
                    row.wet_weight_g = supplied[plant.id]
                    row.actor = actor
                    row.recorded_at = _now()
                plant.phase = "harvested"
                plant.retired_at = plant.retired_at or utc_now()
                session.add(CultivationPlantEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    plant_id=plant.id,
                    event_type="harvested_with_wet_weight",
                    from_value="flowering",
                    to_value="harvested",
                    reason=f"Wet weight {supplied[plant.id]:.4f} g",
                    actor=actor,
                ))
            harvest.wet_weight_g = sum(supplied.values())
            if harvest.status == "planned":
                harvest.status = "active"
            harvest.harvested_at = harvest.harvested_at or utc_now()
        return {"harvest_id": harvest_id, "plant_count": len(supplied), "wet_weight_g": sum(supplied.values())}

    def record_waste(self, organization_id: str, facility_id: str, *, actor: str, provider_confirmed: bool, **payload: Any) -> dict[str, Any]:
        if not provider_confirmed:
            raise ValueError("Confirm the required Metrc waste record before marking the regulatory event confirmed locally.")
        target_type = str(payload.get("target_type") or "").strip().casefold()
        target_id = str(payload.get("target_id") or "").strip()
        method = str(payload.get("method") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        location = str(payload.get("location") or "").strip()
        weight = float(payload.get("weight") or 0.0)
        unit = str(payload.get("unit") or "").strip()
        if target_type not in {"plant", "plant_group", "harvest"} or not target_id or not method or not reason or not location or not unit or weight < 0:
            raise ValueError("Waste requires source, method, weight/UOM, reason, date, and location.")
        with self.sessions.begin() as session:
            self._facility(session, organization_id, facility_id)
            row = CultivationWasteRecord(
                organization_id=organization_id,
                facility_id=facility_id,
                target_type=target_type,
                target_id=target_id,
                method=method,
                material_mixed=str(payload.get("material_mixed") or "").strip(),
                weight=weight,
                unit=unit,
                reason=reason,
                waste_date=payload.get("waste_date") or date.today(),
                location=location,
                notes=str(payload.get("notes") or "").strip(),
                actor=actor,
            )
            session.add(row)
            session.flush()
            row_id = row.id
        return {"id": row_id, "target_type": target_type, "target_id": target_id, "weight": weight, "unit": unit}

    def create_manicure_batch(
        self,
        organization_id: str,
        facility_id: str,
        *,
        batch_code: str,
        source_phase: str,
        location: str,
        manicure_date: date,
        plant_weights: list[dict[str, Any]],
        notes: str,
        actor: str,
        provider_confirmed: bool,
    ) -> dict[str, Any]:
        if not provider_confirmed:
            raise ValueError("Confirm the Metrc manicure action before creating the regulatory manicure batch locally.")
        phase = str(source_phase or "").strip().casefold()
        if phase not in {"vegetative", "flowering"}:
            raise ValueError("Manicure source plants must be vegetative or flowering.")
        weights = {str(row.get("plant_id") or "").strip(): float(row.get("weight_g") or 0.0) for row in plant_weights}
        if not weights or any(value <= 0 for value in weights.values()):
            raise ValueError("Manicure requires a positive removed weight for every selected plant.")
        with self.sessions.begin() as session:
            plants = list(session.scalars(select(CultivationPlant).where(
                CultivationPlant.organization_id == organization_id,
                CultivationPlant.facility_id == facility_id,
                CultivationPlant.id.in_(weights),
            )))
            if len(plants) != len(weights) or any(row.phase != phase for row in plants):
                raise ValueError("Every manicure source plant must exist in the active facility and match the selected growth phase.")
            batch = CultivationManicureBatch(
                organization_id=organization_id,
                facility_id=facility_id,
                batch_code=str(batch_code or "").strip(),
                source_phase=phase,
                location=str(location or "").strip(),
                manicure_date=manicure_date,
                total_weight_g=sum(weights.values()),
                notes=str(notes or "").strip(),
                actor=actor,
            )
            if not batch.batch_code or not batch.location:
                raise ValueError("Manicure batch code and location are required.")
            session.add(batch)
            session.flush()
            for plant_id, weight in weights.items():
                session.add(CultivationManicurePlantWeight(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    manicure_batch_id=batch.id,
                    plant_id=plant_id,
                    weight_g=weight,
                ))
            batch_id = batch.id
        return {"id": batch_id, "batch_code": batch_code, "source_phase": phase, "total_weight_g": sum(weights.values())}

    def record_additive(self, organization_id: str, facility_id: str, *, actor: str, **payload: Any) -> dict[str, Any]:
        target_type = str(payload.get("target_type") or "").strip().casefold()
        amount = float(payload.get("amount") or 0.0)
        if target_type not in {"plant", "plant_group", "location"} or amount < 0:
            raise ValueError("Additive application target and non-negative amount are required.")
        with self.sessions.begin() as session:
            self._facility(session, organization_id, facility_id)
            row = CultivationAdditiveApplication(
                organization_id=organization_id,
                facility_id=facility_id,
                target_type=target_type,
                target_id=str(payload.get("target_id") or "").strip(),
                product_name=str(payload.get("product_name") or "").strip(),
                epa_number=str(payload.get("epa_number") or "").strip(),
                supplier=str(payload.get("supplier") or "").strip(),
                amount=amount,
                unit=str(payload.get("unit") or "").strip(),
                active_ingredients=str(payload.get("active_ingredients") or "").strip(),
                application_date=payload.get("application_date") or date.today(),
                notes=str(payload.get("notes") or "").strip(),
                actor=actor,
            )
            if not row.target_id or not row.product_name or not row.unit:
                raise ValueError("Additive applications require target, product name, amount/UOM, and application date.")
            session.add(row)
            session.flush()
            row_id = row.id
        return {"id": row_id, "target_type": target_type, "target_id": row.target_id, "product_name": row.product_name}

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
        source_kind = str(source_type or "").strip().casefold()
        if source_kind not in {"harvest", "package"} or quantity <= 0:
            raise ValueError("Testing sample requires a harvest/package source and positive quantity.")
        with self.sessions.begin() as session:
            tag = session.scalar(select(MetrcTagInventory).where(
                MetrcTagInventory.organization_id == organization_id,
                MetrcTagInventory.facility_id == facility_id,
                MetrcTagInventory.environment == str(environment).strip().casefold(),
                MetrcTagInventory.tag_type == "package",
                MetrcTagInventory.label == str(package_tag or "").strip(),
                MetrcTagInventory.status == "available",
            ).with_for_update())
            if tag is None:
                raise ValueError("Testing requires an available package tag from the synced Metrc facility inventory.")
            sample = CultivationTestSample(
                organization_id=organization_id,
                facility_id=facility_id,
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
            tag.reserved_at = _now()
            if provider_confirmed:
                tag.used_at = _now()
            sample_id = sample.id
        return {"id": sample_id, "package_tag": package_tag, "status": "provider_confirmed" if provider_confirmed else "planned"}

    def confirm_test_sample(self, organization_id: str, facility_id: str, sample_id: str, *, provider_reference: str, actor: str) -> dict[str, Any]:
        with self.sessions.begin() as session:
            sample = session.get(CultivationTestSample, sample_id)
            if not sample or sample.organization_id != organization_id or sample.facility_id != facility_id:
                raise ValueError("Testing sample was not found in the active facility.")
            if sample.status == "cancelled":
                raise ValueError("Cancelled testing samples cannot be confirmed.")
            sample.status = "provider_confirmed"
            sample.provider_reference = str(provider_reference or "").strip()
            sample.actor = actor
            tag = session.scalar(select(MetrcTagInventory).where(
                MetrcTagInventory.facility_id == facility_id,
                MetrcTagInventory.environment.in_(("sandbox", "production")),
                MetrcTagInventory.tag_type == "package",
                MetrcTagInventory.label == sample.package_tag,
            ).with_for_update())
            if tag:
                tag.status = "used"
                tag.used_at = _now()
        return {"id": sample_id, "status": "provider_confirmed", "provider_reference": sample.provider_reference}

    def readiness_summary(self, organization_id: str, facility_id: str, *, environment: str) -> dict[str, Any]:
        env = str(environment or "").strip().casefold()
        with self.sessions() as session:
            self._facility(session, organization_id, facility_id)
            tag_counts = {
                kind: int(session.scalar(select(func.count(MetrcTagInventory.id)).where(
                    MetrcTagInventory.organization_id == organization_id,
                    MetrcTagInventory.facility_id == facility_id,
                    MetrcTagInventory.environment == env,
                    MetrcTagInventory.tag_type == kind,
                    MetrcTagInventory.status == "available",
                )) or 0)
                for kind in ("plant", "package")
            }
            untagged_veg = int(session.scalar(
                select(func.count(CultivationPlant.id))
                .outerjoin(CultivationRegulatoryIdentity, CultivationRegulatoryIdentity.plant_id == CultivationPlant.id)
                .where(
                    CultivationPlant.organization_id == organization_id,
                    CultivationPlant.facility_id == facility_id,
                    CultivationPlant.phase.in_(("vegetative", "flowering")),
                    CultivationRegulatoryIdentity.metrc_plant_tag.is_(None),
                )
            ) or 0)
            planned_samples = int(session.scalar(select(func.count(CultivationTestSample.id)).where(
                CultivationTestSample.organization_id == organization_id,
                CultivationTestSample.facility_id == facility_id,
                CultivationTestSample.status == "planned",
            )) or 0)
        return {
            "environment": env,
            "available_plant_tags": tag_counts["plant"],
            "available_package_tags": tag_counts["package"],
            "vegetative_or_flowering_without_regulatory_tag": untagged_veg,
            "testing_samples_waiting_provider_confirmation": planned_samples,
            "write_policy": "provider-confirmed until sandbox write/readback contract is promoted",
        }


class MetrcTransferReadinessService:
    """Strict transfer overlay that preserves complete manifested package identity."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def _balance(self, session: Session, lot_id: str) -> float:
        return float(session.scalar(select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(InventoryTransaction.lot_id == lot_id)) or 0.0)

    def dispatch_whole_packages(
        self,
        organization_id: str,
        source_facility_id: str,
        *,
        destination_facility_id: str,
        manifest_reference: str,
        lines: list[dict[str, Any]],
        actor: str,
        provider_transfer_id: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        if not lines:
            raise ValueError("Select at least one complete Metrc package for transfer.")
        with self.sessions() as session:
            availability = InventoryAvailabilityService.build(session, organization_id, source_facility_id)
            for line in lines:
                lot_id = str(line.get("source_lot_id") or "").strip()
                requested = float(line.get("quantity") or 0.0)
                lot = session.get(InventoryLot, lot_id)
                if not lot or lot.organization_id != organization_id or lot.facility_id != source_facility_id:
                    raise ValueError("Every Metrc transfer source must be an existing package in the active source facility.")
                if not str(lot.compliance_package_id or "").strip():
                    raise ValueError("Metrc transfer source is missing a package tag. Package the material before manifesting it.")
                physical = self._balance(session, lot.id)
                claim = availability.get("by_lot", {}).get(lot.id) or {}
                available = float(claim.get("available") or 0.0)
                if abs(requested - physical) > 1e-9:
                    raise ValueError(
                        f"Metrc transfers move complete packages. {lot.lot_code} contains {physical:g}; split/repackage first instead of transferring {requested:g}."
                    )
                if available + 1e-9 < physical:
                    raise ValueError("Resolve package reservations/commitments before transferring the complete Metrc package.")
        transfer = InventoryTransferService(self.engine).dispatch(
            organization_id,
            source_facility_id,
            destination_facility_id=destination_facility_id,
            manifest_reference=manifest_reference,
            lines=lines,
            actor=actor,
            external_transfer_id=provider_transfer_id,
            notes=notes,
        )
        with self.sessions.begin() as session:
            control = MetrcTransferControl(
                organization_id=organization_id,
                transfer_id=transfer["id"],
                provider_transfer_id=str(provider_transfer_id or "").strip(),
                provider_status="prepared",
                notes=str(notes or "").strip(),
            )
            session.add(control)
        return self.detail(organization_id, transfer["id"])

    def confirm_departure(self, organization_id: str, source_facility_id: str, transfer_id: str, *, actor: str) -> dict[str, Any]:
        with self.sessions.begin() as session:
            transfer = session.get(InventoryTransfer, transfer_id)
            if not transfer or transfer.organization_id != organization_id or transfer.source_facility_id != source_facility_id:
                raise ValueError("Transfer was not found in the active source facility.")
            control = session.scalar(select(MetrcTransferControl).where(MetrcTransferControl.transfer_id == transfer.id).with_for_update())
            if not control:
                raise ValueError("Transfer is not registered for strict Metrc lifecycle control.")
            if control.departure_confirmed_at is None:
                control.departure_confirmed_at = _now()
                control.departure_confirmed_by = actor
                control.provider_status = "departed"
        return self.detail(organization_id, transfer_id)

    def assert_cancellable(self, organization_id: str, transfer_id: str) -> None:
        with self.sessions() as session:
            control = session.scalar(select(MetrcTransferControl).where(
                MetrcTransferControl.organization_id == organization_id,
                MetrcTransferControl.transfer_id == transfer_id,
            ))
            if control and control.departure_confirmed_at is not None:
                raise ValueError("A Metrc-controlled transfer cannot be cancelled after actual departure; use rejection/return handling.")

    def assert_receivable(self, organization_id: str, transfer_id: str, line_id: str) -> None:
        with self.sessions() as session:
            return_row = session.scalar(select(MetrcTransferLineReturn).where(
                MetrcTransferLineReturn.organization_id == organization_id,
                MetrcTransferLineReturn.transfer_id == transfer_id,
                MetrcTransferLineReturn.transfer_line_id == line_id,
            ))
            if return_row:
                raise ValueError("This manifested package was rejected and cannot also be received into destination inventory.")

    def receive_whole_package(
        self,
        organization_id: str,
        destination_facility_id: str,
        transfer_id: str,
        line_id: str,
        *,
        operation: str,
        actor: str,
        lot_code: str = "",
        location: str = "RECEIVING",
        notes: str = "",
    ) -> dict[str, Any]:
        self.assert_receivable(organization_id, transfer_id, line_id)
        with self.sessions() as session:
            line = session.get(InventoryTransferLine, line_id)
            if not line or line.organization_id != organization_id or line.transfer_id != transfer_id:
                raise ValueError("Transfer package was not found.")
            package_id = str(line.source_package_id or "").strip()
            if not package_id:
                raise ValueError("Manifested package identity is missing.")
        InventoryTransferService(self.engine).receive_line(
            organization_id,
            destination_facility_id,
            transfer_id,
            line_id,
            operation=operation,
            actor=actor,
            lot_code=lot_code or package_id,
            package_id=package_id,
            location=location,
            notes=notes,
        )
        with self.sessions.begin() as session:
            control = session.scalar(select(MetrcTransferControl).where(MetrcTransferControl.transfer_id == transfer_id).with_for_update())
            if control:
                base = session.get(InventoryTransfer, transfer_id)
                control.provider_status = "received" if base and base.status == "received" else "partially_received"
        return self.detail(organization_id, transfer_id)

    def reject_package(
        self,
        organization_id: str,
        destination_facility_id: str,
        transfer_id: str,
        line_id: str,
        *,
        actor: str,
        reason: str,
        notes: str = "",
        return_manifest_reference: str = "",
    ) -> dict[str, Any]:
        with self.sessions.begin() as session:
            transfer = session.get(InventoryTransfer, transfer_id)
            line = session.get(InventoryTransferLine, line_id)
            control = session.scalar(select(MetrcTransferControl).where(MetrcTransferControl.transfer_id == transfer_id).with_for_update())
            if not transfer or transfer.organization_id != organization_id or transfer.destination_facility_id != destination_facility_id:
                raise ValueError("Transfer was not found for the active destination facility.")
            if not line or line.transfer_id != transfer.id or line.destination_lot_id:
                raise ValueError("Only an unreceived manifested package can be rejected.")
            if not control or control.departure_confirmed_at is None:
                raise ValueError("Package rejection requires a Metrc-controlled transfer with confirmed departure.")
            if session.scalar(select(MetrcTransferLineReturn.id).where(MetrcTransferLineReturn.transfer_line_id == line.id)):
                raise ValueError("This manifested package already has a rejection/return record.")
            rejection = MetrcTransferLineReturn(
                organization_id=organization_id,
                transfer_id=transfer.id,
                transfer_line_id=line.id,
                status="returning" if return_manifest_reference else "rejected",
                reason=str(reason or "").strip(),
                notes=str(notes or "").strip(),
                rejected_by=actor,
                return_manifest_reference=str(return_manifest_reference or "").strip(),
            )
            if not rejection.reason:
                raise ValueError("Rejected packages require a reason.")
            session.add(rejection)
            control.provider_status = "rejected"
        return self.detail(organization_id, transfer_id)

    def receive_rejected_return(
        self,
        organization_id: str,
        source_facility_id: str,
        transfer_id: str,
        line_id: str,
        *,
        actor: str,
        state_return_confirmed: bool,
    ) -> dict[str, Any]:
        if not state_return_confirmed:
            raise ValueError("Confirm the rejected package returned in Metrc before restoring source inventory.")
        with self.sessions.begin() as session:
            transfer = session.get(InventoryTransfer, transfer_id)
            line = session.get(InventoryTransferLine, line_id)
            if not transfer or transfer.organization_id != organization_id or transfer.source_facility_id != source_facility_id:
                raise ValueError("Transfer was not found for the active source facility.")
            if not line or line.transfer_id != transfer.id:
                raise ValueError("Transfer package was not found.")
            rejection = session.scalar(select(MetrcTransferLineReturn).where(MetrcTransferLineReturn.transfer_line_id == line.id).with_for_update())
            if not rejection or rejection.status == "returned":
                raise ValueError("A pending rejected-package return was not found.")
            product = session.get(Product, line.product_id)
            if not product:
                raise ValueError("Transferred Product Master item is missing.")
            session.add(InventoryTransaction(
                organization_id=organization_id,
                facility_id=source_facility_id,
                lot_id=line.source_lot_id,
                transaction_type="transfer_rejected_return",
                quantity_delta=float(line.quantity),
                unit=line.unit,
                reason="Rejected Metrc package returned to source custody",
                reference=rejection.return_manifest_reference or transfer.manifest_reference,
                actor=actor,
            ))
            rejection.status = "returned"
            rejection.returned_at = _now()
            rejection.returned_by = actor
            control = session.scalar(select(MetrcTransferControl).where(MetrcTransferControl.transfer_id == transfer.id).with_for_update())
            if control:
                control.provider_status = "returned"
            session.add(AuditEvent(
                organization_id=organization_id,
                facility_id=source_facility_id,
                entity_type="inventory_transfer",
                entity_id=transfer.id,
                action="metrc_rejected_package_returned",
                actor=actor,
                changes_json=f'{{"line_id":"{line.id}","package":"{line.source_package_id}"}}',
            ))
        return self.detail(organization_id, transfer_id)

    def detail(self, organization_id: str, transfer_id: str) -> dict[str, Any]:
        base = InventoryTransferService(self.engine).detail(organization_id, transfer_id)
        with self.sessions() as session:
            control = session.scalar(select(MetrcTransferControl).where(MetrcTransferControl.organization_id == organization_id, MetrcTransferControl.transfer_id == transfer_id))
            returns = list(session.scalars(select(MetrcTransferLineReturn).where(MetrcTransferLineReturn.organization_id == organization_id, MetrcTransferLineReturn.transfer_id == transfer_id)))
        return {
            **base,
            "metrc_control": None if not control else {
                "provider_transfer_id": control.provider_transfer_id,
                "provider_status": control.provider_status,
                "departure_confirmed_at": control.departure_confirmed_at.isoformat() if control.departure_confirmed_at else None,
                "departure_confirmed_by": control.departure_confirmed_by,
            },
            "metrc_rejections": [{
                "transfer_line_id": row.transfer_line_id,
                "status": row.status,
                "reason": row.reason,
                "return_manifest_reference": row.return_manifest_reference,
                "rejected_at": row.rejected_at.isoformat() if row.rejected_at else None,
                "returned_at": row.returned_at.isoformat() if row.returned_at else None,
            } for row in returns],
        }
