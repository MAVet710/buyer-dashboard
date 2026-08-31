"""Seed-to-sale material transformation, harvest allocation and genealogy services."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import (
    InventoryLot,
    InventoryTransaction,
    Product,
    ProductionOrder,
    utc_now,
)
from modules.cultivation.models import CultivationHarvestPlant, CultivationPlant
from modules.operational_moats.models import CultivationHarvest
from modules.package_studio.models import PackageStudioInput, PackageStudioOutput, PackageStudioRun
from modules.production_erp.models import ProductionRunOutput

from .models import (
    MaterialTransformation,
    MaterialTransformationInput,
    MaterialTransformationLoss,
    MaterialTransformationOutput,
)


HARVEST_OUTPUT_PURPOSES = {
    "finished_flower",
    "smalls",
    "trim",
    "biomass",
    "fresh_frozen",
    "recoverable_material",
    "other",
}
MEASUREMENT_BASES = {"dry", "wet"}
LOT_STATUSES = {"available", "released", "quarantine", "hold"}


class MaterialLineageService:
    """Use the canonical inventory ledger for quantity and durable edges for genealogy."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @staticmethod
    def balance(session: Session, lot_id: str) -> float:
        return float(
            session.scalar(
                select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                    InventoryTransaction.lot_id == lot_id
                )
            )
            or 0.0
        )

    @staticmethod
    def transformation(
        session: Session,
        *,
        organization_id: str,
        facility_id: str,
        transformation_type: str,
        source_entity_type: str,
        source_entity_id: str,
        actor: str,
        notes: str = "",
    ) -> MaterialTransformation:
        row = session.scalar(
            select(MaterialTransformation).where(
                MaterialTransformation.organization_id == organization_id,
                MaterialTransformation.facility_id == facility_id,
                MaterialTransformation.transformation_type == transformation_type,
                MaterialTransformation.source_entity_type == source_entity_type,
                MaterialTransformation.source_entity_id == source_entity_id,
            )
        )
        if row is None:
            row = MaterialTransformation(
                organization_id=organization_id,
                facility_id=facility_id,
                transformation_type=transformation_type,
                source_entity_type=source_entity_type,
                source_entity_id=source_entity_id,
                status="open",
                actor=actor,
                notes=notes.strip(),
            )
            session.add(row)
            session.flush()
        return row

    @staticmethod
    def add_input(
        session: Session,
        transformation: MaterialTransformation,
        *,
        entity_type: str,
        entity_id: str,
        lot_id: str | None = None,
        product_id: str | None = None,
        quantity: float = 0.0,
        unit: str = "",
        purpose: str = "source",
        measurement_basis: str = "",
        accumulate: bool = True,
    ) -> MaterialTransformationInput:
        row = session.scalar(
            select(MaterialTransformationInput).where(
                MaterialTransformationInput.transformation_id == transformation.id,
                MaterialTransformationInput.entity_type == entity_type,
                MaterialTransformationInput.entity_id == entity_id,
                MaterialTransformationInput.purpose == purpose,
            )
        )
        if row is None:
            row = MaterialTransformationInput(
                organization_id=transformation.organization_id,
                facility_id=transformation.facility_id,
                transformation_id=transformation.id,
                entity_type=entity_type,
                entity_id=entity_id,
                lot_id=lot_id,
                product_id=product_id,
                quantity=float(quantity or 0),
                unit=str(unit or ""),
                purpose=purpose,
                measurement_basis=measurement_basis,
            )
            session.add(row)
        elif accumulate:
            row.quantity = float(row.quantity or 0) + float(quantity or 0)
            if lot_id:
                row.lot_id = lot_id
            if product_id:
                row.product_id = product_id
            if unit:
                row.unit = unit
            if measurement_basis:
                row.measurement_basis = measurement_basis
        session.flush()
        return row

    @staticmethod
    def add_output(
        session: Session,
        transformation: MaterialTransformation,
        *,
        lot_id: str,
        product_id: str,
        quantity: float,
        unit: str,
        purpose: str = "standard",
        measurement_basis: str = "",
    ) -> MaterialTransformationOutput:
        row = session.scalar(
            select(MaterialTransformationOutput).where(
                MaterialTransformationOutput.transformation_id == transformation.id,
                MaterialTransformationOutput.lot_id == lot_id,
            )
        )
        if row is None:
            row = MaterialTransformationOutput(
                organization_id=transformation.organization_id,
                facility_id=transformation.facility_id,
                transformation_id=transformation.id,
                lot_id=lot_id,
                product_id=product_id,
                quantity=float(quantity),
                unit=unit,
                purpose=purpose,
                measurement_basis=measurement_basis,
            )
            session.add(row)
        else:
            row.product_id = product_id
            row.quantity = float(quantity)
            row.unit = unit
            row.purpose = purpose
            row.measurement_basis = measurement_basis
        session.flush()
        return row

    def preview_harvest_allocation(
        self,
        *,
        organization_id: str,
        facility_id: str,
        harvest_id: str,
        outputs: list[dict[str, Any]],
        losses: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self.sessions() as session:
            return self._preview_harvest_allocation(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                harvest_id=harvest_id,
                outputs=outputs,
                losses=losses or [],
                lock=False,
            )

    def _preview_harvest_allocation(
        self,
        session: Session,
        *,
        organization_id: str,
        facility_id: str,
        harvest_id: str,
        outputs: list[dict[str, Any]],
        losses: list[dict[str, Any]],
        lock: bool,
    ) -> dict[str, Any]:
        query = select(CultivationHarvest).where(
            CultivationHarvest.id == harvest_id,
            CultivationHarvest.organization_id == organization_id,
            CultivationHarvest.facility_id == facility_id,
        )
        if lock:
            query = query.with_for_update()
        harvest = session.scalar(query)
        if harvest is None:
            raise ValueError("Harvest was not found in the active cultivation facility.")
        if harvest.status not in {"active", "drying", "completed"}:
            raise ValueError("Start the harvest before allocating physical output.")
        if not outputs:
            raise ValueError("Add at least one harvest output lot.")

        transformation = session.scalar(
            select(MaterialTransformation).where(
                MaterialTransformation.organization_id == organization_id,
                MaterialTransformation.facility_id == facility_id,
                MaterialTransformation.transformation_type == "harvest_allocation",
                MaterialTransformation.source_entity_type == "harvest",
                MaterialTransformation.source_entity_id == harvest.id,
            )
        )
        existing_by_basis: dict[str, float] = defaultdict(float)
        if transformation:
            for row in session.scalars(
                select(MaterialTransformationOutput).where(
                    MaterialTransformationOutput.transformation_id == transformation.id
                )
            ):
                existing_by_basis[row.measurement_basis or "dry"] += float(row.quantity or 0)
            for row in session.scalars(
                select(MaterialTransformationLoss).where(
                    MaterialTransformationLoss.transformation_id == transformation.id
                )
            ):
                existing_by_basis[row.measurement_basis or "dry"] += float(row.quantity or 0)

        requested_by_basis: dict[str, float] = defaultdict(float)
        normalized_outputs: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        for raw in outputs:
            product_id = str(raw.get("product_id") or "").strip()
            lot_code = str(raw.get("lot_code") or "").strip()
            purpose = str(raw.get("purpose") or "other").strip().casefold()
            basis = str(raw.get("measurement_basis") or "dry").strip().casefold()
            unit = str(raw.get("unit") or "g").strip().casefold()
            quantity = float(raw.get("quantity") or 0)
            status = str(raw.get("status") or "quarantine").strip().casefold()
            location = str(raw.get("location_code") or "HARVEST-OUTPUT").strip()
            compliance_package_id = str(raw.get("compliance_package_id") or "").strip()
            if not product_id or not lot_code:
                raise ValueError("Every harvest output requires a Product Master item and lot code.")
            if quantity <= 0:
                raise ValueError("Harvest output quantities must be greater than zero.")
            if purpose not in HARVEST_OUTPUT_PURPOSES:
                raise ValueError(f"Unsupported harvest output purpose: {purpose}.")
            if basis not in MEASUREMENT_BASES:
                raise ValueError("Harvest output measurement basis must be dry or wet.")
            if unit not in {"g", "gram", "grams"}:
                raise ValueError("Harvest allocation currently uses canonical gram measurements.")
            if status not in LOT_STATUSES:
                raise ValueError("Harvest output status must be available, released, quarantine or hold.")
            if lot_code.casefold() in seen_codes:
                raise ValueError("Harvest output lot codes must be unique within the allocation.")
            seen_codes.add(lot_code.casefold())
            product = session.get(Product, product_id)
            if not product or product.organization_id != organization_id or not product.active:
                raise ValueError("A harvest output product is not active in this organization.")
            duplicate = session.scalar(
                select(InventoryLot.id).where(
                    InventoryLot.facility_id == facility_id,
                    func.lower(InventoryLot.lot_code) == lot_code.casefold(),
                )
            )
            if duplicate:
                raise ValueError(f"Harvest output lot {lot_code} already exists in this facility.")
            requested_by_basis[basis] += quantity
            normalized_outputs.append(
                {
                    "product_id": product.id,
                    "product_name": product.name,
                    "lot_code": lot_code,
                    "quantity": quantity,
                    "unit": "g",
                    "purpose": purpose,
                    "measurement_basis": basis,
                    "status": status,
                    "location_code": location or "HARVEST-OUTPUT",
                    "compliance_package_id": compliance_package_id,
                }
            )

        normalized_losses: list[dict[str, Any]] = []
        for raw in losses:
            quantity = float(raw.get("quantity") or 0)
            if quantity <= 0:
                raise ValueError("Harvest loss quantities must be greater than zero.")
            basis = str(raw.get("measurement_basis") or "dry").strip().casefold()
            if basis not in MEASUREMENT_BASES:
                raise ValueError("Harvest loss measurement basis must be dry or wet.")
            unit = str(raw.get("unit") or "g").strip().casefold()
            if unit not in {"g", "gram", "grams"}:
                raise ValueError("Harvest loss allocation currently uses canonical grams.")
            requested_by_basis[basis] += quantity
            normalized_losses.append(
                {
                    "quantity": quantity,
                    "unit": "g",
                    "loss_type": str(raw.get("loss_type") or "process_loss").strip().casefold(),
                    "measurement_basis": basis,
                    "reason": str(raw.get("reason") or "").strip(),
                }
            )

        measured = {"wet": float(harvest.wet_weight_g or 0), "dry": float(harvest.dry_weight_g or 0)}
        reconciliation: dict[str, dict[str, float]] = {}
        warnings: list[dict[str, str]] = []
        for basis in MEASUREMENT_BASES:
            after = existing_by_basis[basis] + requested_by_basis[basis]
            measured_total = measured[basis]
            if after > measured_total + 1e-6:
                raise ValueError(
                    f"{basis.title()}-basis harvest allocation would exceed measured {basis} weight by "
                    f"{after - measured_total:,.4f} g."
                )
            reconciliation[basis] = {
                "measured": measured_total,
                "already_allocated": existing_by_basis[basis],
                "requested": requested_by_basis[basis],
                "allocated_after": after,
                "remaining": max(0.0, measured_total - after),
            }
            if requested_by_basis[basis] and measured_total <= 0:
                warnings.append({"severity": "blocker", "message": f"Record measured {basis} weight before allocating {basis}-basis output."})

        return {
            "harvest_id": harvest.id,
            "harvest_code": harvest.harvest_code,
            "status": harvest.status,
            "outputs": normalized_outputs,
            "losses": normalized_losses,
            "reconciliation": reconciliation,
            "warnings": warnings,
            "blocker_count": sum(row["severity"] == "blocker" for row in warnings),
            "state": {
                "harvest_updated_at": harvest.updated_at,
                "wet_weight_g": measured["wet"],
                "dry_weight_g": measured["dry"],
                "existing_by_basis": dict(existing_by_basis),
            },
        }

    def commit_harvest_allocation(
        self,
        *,
        organization_id: str,
        facility_id: str,
        harvest_id: str,
        outputs: list[dict[str, Any]],
        losses: list[dict[str, Any]] | None,
        actor: str,
    ) -> dict[str, Any]:
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
            if preview["blocker_count"]:
                raise ValueError("Resolve harvest allocation blockers before posting inventory.")
            harvest = session.get(CultivationHarvest, harvest_id)
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
            }

    @staticmethod
    def production_transformation(
        session: Session,
        *,
        organization_id: str,
        facility_id: str,
        order: ProductionOrder,
        actor: str,
    ) -> MaterialTransformation:
        return MaterialLineageService.transformation(
            session,
            organization_id=organization_id,
            facility_id=facility_id,
            transformation_type="production_run",
            source_entity_type="production_order",
            source_entity_id=order.id,
            actor=actor,
            notes=f"Production material genealogy for {order.order_number}",
        )

    @staticmethod
    def attach_production_outputs(
        session: Session,
        transformation: MaterialTransformation,
        order: ProductionOrder,
    ) -> list[str]:
        attached: list[str] = []
        for output in session.scalars(
            select(ProductionRunOutput).where(
                ProductionRunOutput.production_order_id == order.id,
                ProductionRunOutput.lot_id.is_not(None),
            )
        ):
            if not output.lot_id or float(output.actual_quantity or 0) <= 0:
                continue
            lot = session.get(InventoryLot, output.lot_id)
            if not lot or lot.organization_id != transformation.organization_id or lot.facility_id != transformation.facility_id:
                continue
            MaterialLineageService.add_output(
                session,
                transformation,
                lot_id=lot.id,
                product_id=output.product_id,
                quantity=float(output.actual_quantity or 0),
                unit=output.unit,
                purpose="production_output",
            )
            attached.append(lot.id)
        return attached

    def lot_graph(
        self,
        *,
        organization_id: str,
        facility_id: str,
        lot_id: str,
        max_depth: int = 12,
    ) -> dict[str, Any]:
        with self.sessions() as session:
            lot = session.scalar(
                select(InventoryLot).where(
                    InventoryLot.id == lot_id,
                    InventoryLot.organization_id == organization_id,
                    InventoryLot.facility_id == facility_id,
                )
            )
            if lot is None:
                raise ValueError("Package or lot was not found in the active facility.")
            nodes: dict[str, dict[str, Any]] = {}
            edges: list[dict[str, Any]] = []
            visited: set[tuple[str, str]] = set()

            def add_node(key: str, payload: dict[str, Any]) -> None:
                nodes.setdefault(key, payload | {"key": key})

            def walk_lot(current_lot_id: str, depth: int) -> None:
                marker = ("lot", current_lot_id)
                if marker in visited or depth > max_depth:
                    return
                visited.add(marker)
                current = session.get(InventoryLot, current_lot_id)
                if not current or current.organization_id != organization_id or current.facility_id != facility_id:
                    return
                product = session.get(Product, current.product_id)
                lot_key = f"lot:{current.id}"
                add_node(lot_key, {
                    "type": "lot",
                    "id": current.id,
                    "lot_code": current.lot_code,
                    "package_id": current.compliance_package_id,
                    "product_id": current.product_id,
                    "product_name": product.name if product else "",
                    "status": current.status,
                    "balance": self.balance(session, current.id),
                    "unit": product.base_unit if product else "",
                })

                created = list(
                    session.execute(
                        select(MaterialTransformationOutput, MaterialTransformation)
                        .join(MaterialTransformation, MaterialTransformation.id == MaterialTransformationOutput.transformation_id)
                        .where(
                            MaterialTransformationOutput.lot_id == current.id,
                            MaterialTransformation.organization_id == organization_id,
                            MaterialTransformation.facility_id == facility_id,
                        )
                    )
                )
                for output_row, transformation in created:
                    transform_key = f"transformation:{transformation.id}"
                    add_node(transform_key, {
                        "type": "transformation",
                        "id": transformation.id,
                        "transformation_type": transformation.transformation_type,
                        "source_entity_type": transformation.source_entity_type,
                        "source_entity_id": transformation.source_entity_id,
                        "status": transformation.status,
                    })
                    edges.append({"from": transform_key, "to": lot_key, "relationship": "produced", "quantity": output_row.quantity, "unit": output_row.unit, "purpose": output_row.purpose})
                    if transformation.source_entity_type == "harvest":
                        harvest = session.get(CultivationHarvest, transformation.source_entity_id)
                        if harvest:
                            harvest_key = f"harvest:{harvest.id}"
                            add_node(harvest_key, {"type": "harvest", "id": harvest.id, "harvest_code": harvest.harvest_code, "strain": harvest.strain, "status": harvest.status})
                            edges.append({"from": harvest_key, "to": transform_key, "relationship": "transformed_by"})
                    elif transformation.source_entity_type == "production_order":
                        order = session.get(ProductionOrder, transformation.source_entity_id)
                        if order:
                            order_key = f"production_order:{order.id}"
                            add_node(order_key, {"type": "production_order", "id": order.id, "order_number": order.order_number, "product_name": order.product_name, "status": order.status})
                            edges.append({"from": order_key, "to": transform_key, "relationship": "executed_as"})
                    for input_row in session.scalars(
                        select(MaterialTransformationInput).where(
                            MaterialTransformationInput.transformation_id == transformation.id
                        )
                    ):
                        if input_row.lot_id:
                            parent_key = f"lot:{input_row.lot_id}"
                            edges.append({"from": parent_key, "to": transform_key, "relationship": "consumed", "quantity": input_row.quantity, "unit": input_row.unit, "purpose": input_row.purpose})
                            walk_lot(input_row.lot_id, depth + 1)
                        elif input_row.entity_type == "plant":
                            plant = session.get(CultivationPlant, input_row.entity_id)
                            if plant and plant.organization_id == organization_id and plant.facility_id == facility_id:
                                plant_key = f"plant:{plant.id}"
                                add_node(plant_key, {"type": "plant", "id": plant.id, "plant_tag": plant.plant_tag, "strain_name": plant.strain_name, "phase": plant.phase, "mother_plant_tag": plant.mother_plant_tag})
                                edges.append({"from": plant_key, "to": transform_key, "relationship": "source_plant"})

                # Package Studio is already a durable transformation ledger. Fold it into
                # the same graph instead of duplicating its rows into new tables.
                studio_output = session.scalar(select(PackageStudioOutput).where(PackageStudioOutput.lot_id == current.id))
                if studio_output:
                    run = session.get(PackageStudioRun, studio_output.run_id)
                    if run and run.organization_id == organization_id and run.facility_id == facility_id:
                        run_key = f"package_studio:{run.id}"
                        add_node(run_key, {"type": "transformation", "id": run.id, "transformation_type": f"package_studio:{run.action_type}", "source_entity_type": "package_studio_run", "source_entity_id": run.id, "status": run.status})
                        edges.append({"from": run_key, "to": lot_key, "relationship": "produced", "quantity": studio_output.inventory_quantity, "unit": studio_output.inventory_unit, "purpose": studio_output.purpose})
                        for source in session.scalars(select(PackageStudioInput).where(PackageStudioInput.run_id == run.id)):
                            parent_key = f"lot:{source.lot_id}"
                            edges.append({"from": parent_key, "to": run_key, "relationship": "consumed", "quantity": source.quantity, "unit": source.unit, "purpose": source.purpose})
                            walk_lot(source.lot_id, depth + 1)

                for input_row, transformation in session.execute(
                    select(MaterialTransformationInput, MaterialTransformation)
                    .join(MaterialTransformation, MaterialTransformation.id == MaterialTransformationInput.transformation_id)
                    .where(
                        MaterialTransformationInput.lot_id == current.id,
                        MaterialTransformation.organization_id == organization_id,
                        MaterialTransformation.facility_id == facility_id,
                    )
                ):
                    transform_key = f"transformation:{transformation.id}"
                    add_node(transform_key, {"type": "transformation", "id": transformation.id, "transformation_type": transformation.transformation_type, "source_entity_type": transformation.source_entity_type, "source_entity_id": transformation.source_entity_id, "status": transformation.status})
                    edges.append({"from": lot_key, "to": transform_key, "relationship": "consumed", "quantity": input_row.quantity, "unit": input_row.unit, "purpose": input_row.purpose})
                    for child in session.scalars(select(MaterialTransformationOutput).where(MaterialTransformationOutput.transformation_id == transformation.id)):
                        child_key = f"lot:{child.lot_id}"
                        edges.append({"from": transform_key, "to": child_key, "relationship": "produced", "quantity": child.quantity, "unit": child.unit, "purpose": child.purpose})
                        walk_lot(child.lot_id, depth + 1)

                for source in session.scalars(select(PackageStudioInput).where(PackageStudioInput.lot_id == current.id)):
                    run = session.get(PackageStudioRun, source.run_id)
                    if not run or run.organization_id != organization_id or run.facility_id != facility_id:
                        continue
                    run_key = f"package_studio:{run.id}"
                    add_node(run_key, {"type": "transformation", "id": run.id, "transformation_type": f"package_studio:{run.action_type}", "source_entity_type": "package_studio_run", "source_entity_id": run.id, "status": run.status})
                    edges.append({"from": lot_key, "to": run_key, "relationship": "consumed", "quantity": source.quantity, "unit": source.unit, "purpose": source.purpose})
                    for child in session.scalars(select(PackageStudioOutput).where(PackageStudioOutput.run_id == run.id)):
                        if child.lot_id:
                            child_key = f"lot:{child.lot_id}"
                            edges.append({"from": run_key, "to": child_key, "relationship": "produced", "quantity": child.inventory_quantity, "unit": child.inventory_unit, "purpose": child.purpose})
                            walk_lot(child.lot_id, depth + 1)

            walk_lot(lot.id, 0)
            # De-duplicate identical edges produced while traversing both directions.
            unique: dict[tuple, dict[str, Any]] = {}
            for edge in edges:
                key = (edge.get("from"), edge.get("to"), edge.get("relationship"), edge.get("quantity"), edge.get("unit"), edge.get("purpose"))
                unique[key] = edge
            return {
                "root_lot_id": lot.id,
                "nodes": list(nodes.values()),
                "edges": list(unique.values()),
                "node_count": len(nodes),
                "edge_count": len(unique),
                "max_depth": max_depth,
            }
