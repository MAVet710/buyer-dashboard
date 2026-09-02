from __future__ import annotations

import json
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select

from modules.coman.models import AuditEvent, InventoryLot, InventoryTransaction, Product, utc_now
from modules.cultivation.batch_models import CultivationPlantGroup
from modules.cultivation.models import CultivationPlant
from modules.inventory_transfers.models import InventoryTransfer, InventoryTransferLine
from modules.inventory_transfers.service import InventoryTransferService
from modules.material_lineage.models import MaterialTransformation, MaterialTransformationLoss, MaterialTransformationOutput
from modules.material_lineage.service import MaterialLineageService
from modules.operational_moats.models import CultivationHarvest

from .metrc_guide_v11_models import MetrcHarvestWasteProjection
from .metrc_process_compliance import MetrcProcessComplianceService, MetrcStrictTransferService
from .metrc_process_models import CultivationWasteRecord, MetrcTransferControl


_FINISH_MOISTURE_REASON = "Remaining harvest weight at Metrc Finish Batch closeout"
_EASTERN = ZoneInfo("America/New_York")


class MetrcGuideV11Service(MetrcProcessComplianceService):
    """Corrections required by the supplied Metrc 2021 Generic User Guide v11.1.

    The generic guide is an operational workflow reference, not a substitute for a
    jurisdiction's rules or the current API contract. Provider-changing operations
    stay provider-confirmed/fail-closed until their exact sandbox write/readback is
    verified.
    """

    def add_plants_to_harvest(self, *args: Any, harvest_date: date, **kwargs: Any) -> dict[str, Any]:
        # The guide says a forgotten plant can join the existing batch by using the
        # exact same harvest name/details only until 12:00 a.m. Eastern. Our route
        # targets the existing durable harvest ID, so enforce the time boundary here
        # in addition to the base service's same-date/detail/downstream guards.
        now_eastern = utc_now().astimezone(_EASTERN)
        if now_eastern.date() != harvest_date:
            raise ValueError(
                "The Metrc same-batch window has closed. Forgotten plants only join the existing harvest until 12:00 a.m. Eastern on the harvest date; create/reconcile the provider harvest as required instead."
            )
        return super().add_plants_to_harvest(*args, harvest_date=harvest_date, **kwargs)

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
            transformation = None
            material_loss = None
            if target_type == "harvest":
                harvest = session.get(CultivationHarvest, target_id)
                if not harvest or harvest.organization_id != organization_id or harvest.facility_id != facility_id:
                    raise ValueError("Waste source harvest was not found in the active facility.")
                if harvest.status not in {"active", "drying"}:
                    raise ValueError("Harvest waste is reported after harvest starts and before the batch is finished. Unfinish a completed batch before correcting harvest waste.")
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
            elif target_type == "plant":
                plant = session.get(CultivationPlant, target_id)
                if not plant or plant.organization_id != organization_id or plant.facility_id != facility_id or plant.phase in {"harvested", "destroyed"}:
                    raise ValueError("Live-plant waste source was not found in the active facility.")
            else:
                group = session.get(CultivationPlantGroup, target_id)
                if not group or group.organization_id != organization_id or group.facility_id != facility_id or group.status != "active":
                    raise ValueError("Live plant-batch waste source was not found in the active facility.")

            waste = CultivationWasteRecord(
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
            session.add(waste)
            session.flush()
            if target_type == "harvest" and weight > 0 and transformation is not None:
                material_loss = MaterialTransformationLoss(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    transformation_id=transformation.id,
                    quantity=weight,
                    unit="g",
                    loss_type="waste",
                    measurement_basis=basis,
                    reason=reason,
                )
                session.add(material_loss)
                session.flush()
                session.add(MetrcHarvestWasteProjection(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    waste_record_id=waste.id,
                    material_loss_id=material_loss.id,
                ))
            waste_id = waste.id
        return {
            "id": waste_id,
            "target_type": target_type,
            "target_id": target_id,
            "weight": weight,
            "unit": "g",
            "measurement_basis": basis if target_type == "harvest" else "",
        }

    def discontinue_harvest_waste(
        self,
        organization_id: str,
        facility_id: str,
        harvest_id: str,
        waste_id: str,
        *,
        actor: str,
        provider_confirmed: bool,
        provider_reference: str = "",
    ) -> dict[str, Any]:
        if not provider_confirmed:
            raise ValueError("Confirm the Metrc Discontinue Waste action before restoring the harvest weight locally.")
        with self.sessions.begin() as session:
            harvest = session.get(CultivationHarvest, harvest_id)
            waste = session.get(CultivationWasteRecord, waste_id)
            if not harvest or harvest.organization_id != organization_id or harvest.facility_id != facility_id:
                raise ValueError("Harvest was not found in the active facility.")
            if harvest.status not in {"active", "drying"}:
                raise ValueError("Unfinish the harvest before discontinuing a harvested waste entry.")
            if not waste or waste.organization_id != organization_id or waste.facility_id != facility_id or waste.target_type != "harvest" or waste.target_id != harvest.id:
                raise ValueError("Harvest waste entry was not found for this batch.")
            projection = session.scalar(select(MetrcHarvestWasteProjection).where(
                MetrcHarvestWasteProjection.organization_id == organization_id,
                MetrcHarvestWasteProjection.facility_id == facility_id,
                MetrcHarvestWasteProjection.waste_record_id == waste.id,
            ).with_for_update())
            if projection is None:
                raise ValueError("This legacy waste entry has no deterministic material-loss link. Reconcile it before discontinuing so the wrong loss is never restored.")
            if projection.discontinued_at is not None:
                raise ValueError("This harvest waste entry is already discontinued.")
            loss = session.get(MaterialTransformationLoss, projection.material_loss_id)
            if loss is None:
                raise ValueError("The harvest waste projection is incomplete; reconcile before continuing.")
            restored = float(loss.quantity or 0.0)
            loss.quantity = 0.0
            loss.reason = f"{loss.reason} [discontinued in Metrc]"[:255]
            projection.discontinued_at = utc_now()
            projection.discontinued_by = actor
            projection.provider_reference = str(provider_reference or "").strip()
            session.add(AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="cultivation_waste",
                entity_id=waste.id,
                action="metrc_harvest_waste_discontinued",
                actor=actor,
                changes_json=json.dumps({
                    "harvest_id": harvest.id,
                    "restored_weight_g": restored,
                    "provider_reference": projection.provider_reference,
                }, sort_keys=True),
            ))
        return {
            "harvest_id": harvest_id,
            "waste_id": waste_id,
            "status": "discontinued",
            "restored_weight_g": restored,
        }

    def harvest_closeout_preview(self, organization_id: str, facility_id: str, harvest_id: str) -> dict[str, Any]:
        preview = super().harvest_closeout_preview(organization_id, facility_id, harvest_id)
        with self.sessions() as session:
            active_waste_count = int(session.scalar(
                select(func.count(CultivationWasteRecord.id))
                .outerjoin(
                    MetrcHarvestWasteProjection,
                    MetrcHarvestWasteProjection.waste_record_id == CultivationWasteRecord.id,
                )
                .where(
                    CultivationWasteRecord.organization_id == organization_id,
                    CultivationWasteRecord.facility_id == facility_id,
                    CultivationWasteRecord.target_type == "harvest",
                    CultivationWasteRecord.target_id == harvest_id,
                    or_(
                        MetrcHarvestWasteProjection.id.is_(None),
                        MetrcHarvestWasteProjection.discontinued_at.is_(None),
                    ),
                )
            ) or 0)
        preview["structured_waste_record_count"] = active_waste_count
        return preview

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
            remainder = float(preview["remaining_for_moisture_loss_g"])
            if remainder > 1e-6:
                session.add(MaterialTransformationLoss(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    transformation_id=transformation.id,
                    quantity=remainder,
                    unit="g",
                    loss_type="moisture_loss",
                    measurement_basis=preview["measurement_basis"],
                    reason=_FINISH_MOISTURE_REASON,
                ))
                # The existing fail-closed completion invariant queries persisted
                # disposition rows in before_flush. Flush the auto moisture entry
                # first so the completion guard sees the exact closed mass balance.
                session.flush()
            transformation.status = "committed"
            harvest.status = "completed"
            harvest.completed_at = harvest.completed_at or utc_now()
            session.flush()
        return self.harvest_closeout_preview(organization_id, facility_id, harvest_id)

    def unfinish_harvest(
        self,
        organization_id: str,
        facility_id: str,
        harvest_id: str,
        *,
        actor: str,
        provider_confirmed: bool,
        provider_reference: str = "",
    ) -> dict[str, Any]:
        if not provider_confirmed:
            raise ValueError("Confirm the Metrc Unfinish action before returning the harvest batch to active locally.")
        with self.sessions.begin() as session:
            harvest = session.scalar(select(CultivationHarvest).where(
                CultivationHarvest.id == harvest_id,
                CultivationHarvest.organization_id == organization_id,
                CultivationHarvest.facility_id == facility_id,
            ).with_for_update())
            if not harvest or harvest.status != "completed":
                raise ValueError("Only a completed harvest can be unfinished.")
            transformation = session.scalar(select(MaterialTransformation).where(
                MaterialTransformation.organization_id == organization_id,
                MaterialTransformation.facility_id == facility_id,
                MaterialTransformation.transformation_type == "harvest_allocation",
                MaterialTransformation.source_entity_type == "harvest",
                MaterialTransformation.source_entity_id == harvest.id,
            ).with_for_update())
            restored_moisture = 0.0
            if transformation is not None:
                moisture_rows = list(session.scalars(select(MaterialTransformationLoss).where(
                    MaterialTransformationLoss.transformation_id == transformation.id,
                    MaterialTransformationLoss.loss_type == "moisture_loss",
                    MaterialTransformationLoss.reason.like(f"{_FINISH_MOISTURE_REASON}%"),
                ).with_for_update()))
                for loss in moisture_rows:
                    restored_moisture += float(loss.quantity or 0.0)
                    loss.quantity = 0.0
                    loss.reason = f"{_FINISH_MOISTURE_REASON} [reversed by Unfinish]"[:255]
                transformation.status = "open"
            harvest.status = "active"
            harvest.completed_at = None
            session.add(AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="cultivation_harvest",
                entity_id=harvest.id,
                action="metrc_harvest_unfinished",
                actor=actor,
                changes_json=json.dumps({
                    "restored_moisture_loss_g": restored_moisture,
                    "provider_reference": str(provider_reference or "").strip(),
                }, sort_keys=True),
            ))
        return {
            "harvest_id": harvest_id,
            "status": "active",
            "restored_moisture_loss_g": restored_moisture,
        }


class MetrcGuideV11TransferService(MetrcStrictTransferService):
    """Guide-aligned receipt including the documented quantity/UOM exception."""

    @staticmethod
    def _weight_to_grams(quantity: float, unit: str) -> float:
        normalized = str(unit or "").strip().casefold()
        if normalized in {"g", "gram", "grams"}:
            return quantity
        if normalized in {"lb", "lbs", "pound", "pounds"}:
            # The supplied guide explicitly uses 453.6 g per pound for this workflow.
            return quantity * 453.6
        raise ValueError("UOM conversion is supported here only for grams and pounds, matching the supplied Metrc guide example.")

    def receive_manifested_package(
        self,
        organization_id: str,
        destination_facility_id: str,
        transfer_id: str,
        line_id: str,
        *,
        operation: str,
        actor: str,
        received_quantity: float | None = None,
        received_unit: str = "",
        variance_reason: str = "",
        lot_code: str = "",
        location: str = "RECEIVING",
        notes: str = "",
    ) -> dict[str, Any]:
        self.assert_receivable(organization_id, transfer_id, line_id)
        reason = str(variance_reason or "").strip().casefold()
        if reason not in {"", "scale_variance", "uom_conversion"}:
            raise ValueError("Receiving variance reason must be scale_variance or uom_conversion.")
        operation = str(operation or "").strip().casefold()
        if operation not in {"retail", "production"}:
            raise ValueError("Destination operation must be retail or production.")

        with self.sessions.begin() as session:
            transfer = session.scalar(select(InventoryTransfer).where(
                InventoryTransfer.id == transfer_id,
                InventoryTransfer.organization_id == organization_id,
                InventoryTransfer.destination_facility_id == destination_facility_id,
            ).with_for_update())
            if not transfer or transfer.status in {"cancelled", "received"}:
                raise ValueError("Transfer is not receivable in the active destination facility.")
            control = session.scalar(select(MetrcTransferControl).where(
                MetrcTransferControl.organization_id == organization_id,
                MetrcTransferControl.transfer_id == transfer.id,
            ).with_for_update())
            if not control or control.departure_confirmed_at is None:
                raise ValueError("A strict Metrc package cannot be received before actual departure is confirmed.")
            line = session.scalar(select(InventoryTransferLine).where(
                InventoryTransferLine.id == line_id,
                InventoryTransferLine.transfer_id == transfer.id,
                InventoryTransferLine.organization_id == organization_id,
            ).with_for_update())
            if not line or line.status != "shipped" or line.destination_lot_id:
                raise ValueError("Transfer package has already been received, rejected, or cancelled.")
            source_lot = session.get(InventoryLot, line.source_lot_id)
            product = session.get(Product, line.product_id)
            if not source_lot or source_lot.organization_id != organization_id or source_lot.facility_id != transfer.source_facility_id:
                raise ValueError("Transfer source lineage is no longer valid.")
            if not product or product.organization_id != organization_id or not product.active:
                raise ValueError("Transferred Product Master item is not active in this organization.")
            package_id = str(line.source_package_id or "").strip()
            if not package_id:
                raise ValueError("Manifested package identity is missing.")

            shipped_qty = float(line.quantity)
            shipped_unit = str(line.unit or "").strip()
            input_qty = shipped_qty if received_quantity is None else float(received_quantity)
            input_unit = str(received_unit or shipped_unit).strip()
            if input_qty <= 0:
                raise ValueError("Received quantity must be greater than zero; reject the package if it cannot be accepted.")

            if reason == "uom_conversion":
                shipped_grams = self._weight_to_grams(shipped_qty, shipped_unit)
                received_grams = self._weight_to_grams(input_qty, input_unit)
                if abs(shipped_grams - received_grams) > 0.05:
                    raise ValueError("UOM conversion must represent the same manifested quantity; use scale_variance for a true measured variance or reject the package.")
                canonical_received = shipped_qty
            else:
                if input_unit.casefold() != shipped_unit.casefold():
                    raise ValueError("Changing unit of measure requires variance_reason=uom_conversion.")
                canonical_received = input_qty
                differs = abs(canonical_received - shipped_qty) > 1e-9
                if differs and reason != "scale_variance":
                    raise ValueError("A different received quantity is allowed only for documented scale variance; otherwise reject the package.")
                if not differs and reason == "scale_variance":
                    raise ValueError("Scale variance was selected but the received quantity matches the shipped quantity.")

            destination_lot_code = str(lot_code or package_id or line.source_lot_code).strip()
            duplicate = session.scalar(select(InventoryLot.id).where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == destination_facility_id,
                or_(
                    InventoryLot.lot_code == destination_lot_code,
                    InventoryLot.compliance_package_id == package_id,
                ),
            ))
            if duplicate:
                raise ValueError("That manifested package already exists in the destination facility.")
            metadata = {
                "operation": operation,
                "source_name": transfer.source_facility_name,
                "manifest_reference": transfer.manifest_reference,
                "transfer_id": transfer.id,
                "transfer_line_id": line.id,
                "source_facility_id": transfer.source_facility_id,
                "source_license_number": transfer.source_license_number,
                "source_lot_id": source_lot.id,
                "source_package_id": package_id,
                "shipped_quantity": shipped_qty,
                "shipped_unit": shipped_unit,
                "entered_received_quantity": input_qty,
                "entered_received_unit": input_unit,
                "variance_reason": reason,
                "notes": str(notes or "").strip(),
            }
            lot = InventoryLot(
                organization_id=organization_id,
                facility_id=destination_facility_id,
                product_id=line.product_id,
                lot_code=destination_lot_code,
                compliance_package_id=package_id,
                external_inventory_id=package_id,
                barcode_value=package_id,
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
                quantity_delta=canonical_received,
                unit=shipped_unit,
                reason=f"Cross-license transfer received from {transfer.source_facility_name}",
                reference=transfer.manifest_reference,
                actor=actor,
            )
            session.add(transaction)
            session.flush()
            InventoryTransferService(self.engine)._copy_quality_evidence(session, source_lot.id, lot.id, actor)

            line.destination_lot_id = lot.id
            line.destination_transaction_id = transaction.id
            line.destination_lot_code = lot.lot_code
            line.destination_package_id = package_id
            line.received_quantity = canonical_received
            line.status = "received"
            line.received_at = utc_now()
            remaining = int(session.scalar(select(func.count(InventoryTransferLine.id)).where(
                InventoryTransferLine.transfer_id == transfer.id,
                InventoryTransferLine.status == "shipped",
                InventoryTransferLine.id != line.id,
            )) or 0)
            transfer.status = "received" if remaining == 0 else "partially_received"
            if remaining == 0:
                transfer.received_at = utc_now()
            control.provider_status = "received" if remaining == 0 else "partially_received"
            session.add(AuditEvent(
                organization_id=organization_id,
                facility_id=destination_facility_id,
                entity_type="inventory_transfer",
                entity_id=transfer.id,
                action="metrc_manifested_package_received",
                actor=actor,
                changes_json=json.dumps(metadata | {
                    "destination_lot_id": lot.id,
                    "canonical_received_quantity": canonical_received,
                    "canonical_received_unit": shipped_unit,
                }, sort_keys=True),
            ))
        return self.detail(organization_id, transfer_id)
