"""Seed the DEV Sandbox with a true vertical seed-to-sale inventory graph.

This module is deliberately restricted to the durable ``dev-sandbox`` tenant.  A reset
retires old on-hand inventory through append-only ledger adjustments instead of deleting
history, releases old inventory claims, deactivates the superseded catalog, and then
builds the replacement inventory through the same cultivation, extraction, QA, Package
Studio, Product Master, and material-lineage services used by operators.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from modules.coman import ComanRepository
from modules.coman.models import (
    AuditEvent,
    Facility,
    InventoryLot,
    InventoryTransaction,
    MaterialReservation,
    OrderLotAllocation,
    Organization,
    Product,
)
from modules.cultivation.service import CultivationService
from modules.extraction import ExtractionRepository
from modules.inventory_quality import LotQualityService
from modules.material_lineage.harvest_guard import GuardedHarvestAllocationService
from modules.package_studio import (
    PackageStudioInputPlan,
    PackageStudioOutputPlan,
    PackageStudioPlan,
    PackageStudioService,
)
from modules.product_master import ProductMasterRepository, ProductPackagingService

DEV_ORGANIZATION_SLUG = "dev-sandbox"
DEV_FACILITY_CODE = "SANDBOX"
VERTICAL_SEED_ACTOR = "demo-seeder:vertical-inventory-v1"

STRAINS = (
    "Gastro Pop",
    "GMO",
    "Strawberry Cough",
    "Blue Dream",
    "Wedding Cake",
    "Super Lemon Haze",
    "Gelato 41",
    "Motorbreath",
    "Permanent Marker",
    "Animal Face",
)

# format name, net grams, package count, case pack
FLOWER_FORMATS = (
    ("Flower Jar 1g", 1.0, 10, 24),
    ("Flower Jar 3.5g", 3.5, 10, 24),
    ("Flower Pouch 7g", 7.0, 5, 12),
    ("Flower Pouch 14g", 14.0, 2, 8),
    ("Flower Pouch 28g", 28.0, 1, 4),
    ("Smalls Pouch 3.5g", 3.5, 10, 24),
    ("Ground Flower Pouch 7g", 7.0, 5, 12),
)

# workflow key, method, finished format
EXTRACT_FORMATS = (
    ("bho_cured", "BHO", "Cured Badder 1g"),
    ("ethanol_crude", "Ethanol", "Distillate 1g"),
    ("dry_sift", "Dry Sift", "Dry Sift 1g"),
)


@dataclass(frozen=True)
class VerticalDevInventoryResult:
    generation: str
    retired_lots: int
    retired_quantity: float
    plants: int
    harvests: int
    flower_source_lots: int
    trim_source_lots: int
    flower_final_lots: tuple[str, ...]
    extraction_bulk_lots: tuple[str, ...]
    extract_final_lots: tuple[str, ...]
    final_product_ids: tuple[str, ...]

    @property
    def final_lots(self) -> tuple[str, ...]:
        return self.flower_final_lots + self.extract_final_lots

    def summary(self) -> dict[str, object]:
        return {
            "generation": self.generation,
            "retired_lots": self.retired_lots,
            "retired_quantity": round(self.retired_quantity, 4),
            "plants": self.plants,
            "harvests": self.harvests,
            "flower_source_lots": self.flower_source_lots,
            "trim_source_lots": self.trim_source_lots,
            "flower_final_lots": len(self.flower_final_lots),
            "extraction_bulk_lots": len(self.extraction_bulk_lots),
            "extract_final_lots": len(self.extract_final_lots),
            "final_lots": len(self.final_lots),
            "final_products": len(self.final_product_ids),
        }


def _generation(value: str | None = None) -> str:
    raw = value or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    cleaned = "".join(ch for ch in str(raw).upper() if ch.isalnum())
    if not cleaned:
        raise ValueError("A non-empty DEV inventory generation is required.")
    return cleaned[:24]


def _guard(session: Session, organization_id: str, facility_id: str) -> tuple[Organization, Facility]:
    organization = session.get(Organization, organization_id)
    facility = session.get(Facility, facility_id)
    if organization is None or organization.slug != DEV_ORGANIZATION_SLUG:
        raise RuntimeError("DEV inventory replacement is restricted to the dev-sandbox organization.")
    if (
        facility is None
        or facility.organization_id != organization.id
        or facility.code != DEV_FACILITY_CODE
    ):
        raise RuntimeError("DEV inventory replacement is restricted to the dev-sandbox SANDBOX facility.")
    return organization, facility


def retire_dev_sandbox_inventory(
    engine: Engine,
    organization_id: str,
    facility_id: str,
    *,
    actor: str = VERTICAL_SEED_ACTOR,
) -> dict[str, float | int]:
    """Take every old DEV lot to zero without destroying ledger or genealogy history."""

    with Session(engine) as session, session.begin():
        _guard(session, organization_id, facility_id)
        lots = list(
            session.scalars(
                select(InventoryLot).where(
                    InventoryLot.organization_id == organization_id,
                    InventoryLot.facility_id == facility_id,
                )
            )
        )
        balances = {
            lot_id: float(quantity or 0.0)
            for lot_id, quantity in session.execute(
                select(
                    InventoryTransaction.lot_id,
                    func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0),
                )
                .where(
                    InventoryTransaction.organization_id == organization_id,
                    InventoryTransaction.facility_id == facility_id,
                )
                .group_by(InventoryTransaction.lot_id)
            )
        }
        products = {
            row.id: row
            for row in session.scalars(select(Product).where(Product.organization_id == organization_id))
        }

        retired_quantity = 0.0
        for lot in lots:
            balance = float(balances.get(lot.id, 0.0))
            product = products.get(lot.product_id)
            if abs(balance) > 1e-9:
                session.add(
                    InventoryTransaction(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        lot_id=lot.id,
                        transaction_type="adjustment",
                        quantity_delta=-balance,
                        unit=(product.base_unit if product else "unit"),
                        actor=actor,
                        reason="DEV Sandbox vertical inventory reset; retire superseded on-hand inventory",
                        reference="vertical-dev-reset",
                    )
                )
                retired_quantity += abs(balance)
            lot.status = "depleted"
            lot.location_code = "ARCHIVED-DEV-RESET"

        # Old Production and Wholesale promises must not reserve the replacement stock.
        for reservation in session.scalars(
            select(MaterialReservation).where(
                MaterialReservation.organization_id == organization_id,
                MaterialReservation.facility_id == facility_id,
                MaterialReservation.status == "reserved",
            )
        ):
            reservation.quantity = 0.0
            reservation.status = "released"
        for allocation in session.scalars(
            select(OrderLotAllocation).where(
                OrderLotAllocation.organization_id == organization_id,
                OrderLotAllocation.facility_id == facility_id,
                OrderLotAllocation.status.in_(("reserved", "partial")),
            )
        ):
            allocation.status = "released"

        # Keep historical product references intact but remove superseded products from
        # active Product Master / picker surfaces.  The vertical products are reactivated
        # below when they are reused by deterministic SKU.
        for product in products.values():
            product.active = False

        session.add(
            AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="inventory",
                entity_id=facility_id,
                action="dev_vertical_inventory_retired",
                actor=actor,
                changes_json=json.dumps(
                    {"lots": len(lots), "retired_quantity": round(retired_quantity, 4)},
                    sort_keys=True,
                ),
            )
        )
        return {"retired_lots": len(lots), "retired_quantity": retired_quantity}


def _ensure_product(
    engine: Engine,
    coman: ComanRepository,
    organization_id: str,
    *,
    sku: str,
    name: str,
    item_type: str,
    base_unit: str,
    unit_cost: float,
    retail_price: float = 0.0,
    upc: str = "",
    actor: str,
) -> Product:
    with Session(engine) as session:
        existing = session.scalar(
            select(Product).where(Product.organization_id == organization_id, Product.sku == sku)
        )
    if existing is None:
        return coman.create_product(
            organization_id,
            sku=sku,
            name=name,
            item_type=item_type,
            base_unit=base_unit,
            unit_cost=unit_cost,
            retail_price=retail_price,
            upc=upc,
            actor=actor,
        )
    with Session(engine) as session, session.begin():
        row = session.get(Product, existing.id)
        assert row is not None
        row.name = name
        row.item_type = item_type
        row.base_unit = base_unit
        row.unit_cost = float(unit_cost)
        row.retail_price = float(retail_price)
        row.upc = upc
        row.active = True
    with Session(engine) as session:
        refreshed = session.get(Product, existing.id)
        assert refreshed is not None
        session.expunge(refreshed)
        return refreshed


def _profile(
    master: ProductMasterRepository,
    organization_id: str,
    product_id: str,
    *,
    strain: str,
    category: str,
    product_format: str,
    actor: str,
) -> None:
    master.update_profile(
        organization_id,
        product_id,
        actor=actor,
        brand="DoobieLogic DEV Vertical",
        category=category,
        subcategory=product_format,
        strain=strain,
        manufacturer="DEV Sandbox Vertical Facility",
        product_format=product_format,
        description=f"{strain} {product_format} generated through the DEV seed-to-sale operator workflow.",
        retail_enabled=True,
        production_enabled=True,
    )


def _packaging(
    engine: Engine,
    organization_id: str,
    product_id: str,
    *,
    net_content: float,
    case_pack: float,
) -> None:
    with Session(engine) as session, session.begin():
        ProductPackagingService.upsert(
            session,
            organization_id=organization_id,
            product_id=product_id,
            net_content=net_content,
            net_content_unit="g",
            units_per_package=1,
            sellable_unit="each",
            case_pack=case_pack,
        )


def _quality(
    engine: Engine,
    lot_id: str,
    reference: str,
    *,
    thca: float,
    tac: float,
    terpenes: float,
    source: str,
    actor: str,
) -> None:
    with Session(engine) as session, session.begin():
        LotQualityService.set_evidence(
            session,
            lot_id=lot_id,
            lab_testing_state="Passed",
            coa_reference=reference,
            thca_percent=thca,
            tac_percent=tac,
            total_terpenes_percent=terpenes,
            evidence_source=source,
            actor=actor,
        )


def seed_vertical_dev_inventory(
    engine: Engine,
    organization_id: str,
    facility_id: str,
    *,
    generation: str | None = None,
    actor: str = VERTICAL_SEED_ACTOR,
) -> VerticalDevInventoryResult:
    generation_code = _generation(generation)
    with Session(engine) as session, session.begin():
        _, facility = _guard(session, organization_id, facility_id)
        facility.cultivation_enabled = True
        facility.production_enabled = True
        facility.retail_enabled = True
        facility.commercial_enabled = True
        facility.license_number = "DEV-SANDBOX-VERTICAL"
        facility.license_type = "cultivation+manufacturing+retail"

    coman = ComanRepository(engine)
    master = ProductMasterRepository(engine)
    cultivation = CultivationService(engine)
    harvest_allocator = GuardedHarvestAllocationService(engine)
    extraction = ExtractionRepository(engine)
    studio = PackageStudioService(engine)

    flower_final_lot_ids: list[str] = []
    extract_final_lot_ids: list[str] = []
    extraction_bulk_lot_ids: list[str] = []
    final_product_ids: list[str] = []
    flower_source_lot_ids: list[str] = []
    trim_source_lot_ids: list[str] = []
    plant_count = 0
    harvest_count = 0

    for strain_index, strain in enumerate(STRAINS, start=1):
        code = f"S{strain_index:02d}"
        flower_source = _ensure_product(
            engine,
            coman,
            organization_id,
            sku=f"DEVV-{code}-BULK-FLOWER",
            name=f"{strain} Bulk Flower",
            item_type="cannabis",
            base_unit="g",
            unit_cost=2.0,
            actor=actor,
        )
        trim_source = _ensure_product(
            engine,
            coman,
            organization_id,
            sku=f"DEVV-{code}-TRIM",
            name=f"{strain} Trim",
            item_type="cannabis",
            base_unit="g",
            unit_cost=0.75,
            actor=actor,
        )
        _profile(master, organization_id, flower_source.id, strain=strain, category="Bulk Flower", product_format="Bulk Flower", actor=actor)
        _profile(master, organization_id, trim_source.id, strain=strain, category="Trim", product_format="Trim", actor=actor)

        plants = [
            cultivation.create_plant(
                organization_id,
                facility_id,
                plant_tag=f"DEVV-{generation_code}-{code}-P{plant_index:02d}",
                strain_name=strain,
                phase="flowering",
                room_code=f"FLOWER-{strain_index:02d}",
                actor=actor,
            )
            for plant_index in (1, 2)
        ]
        plant_count += len(plants)
        harvest = cultivation.create_harvest(
            organization_id,
            facility_id,
            harvest_code=f"DEVV-{generation_code}-{code}-H01",
            plant_ids=[plant.id for plant in plants],
            actor=actor,
        )
        harvest_count += 1
        cultivation.transition_harvest(
            organization_id,
            facility_id,
            harvest["id"],
            status="active",
            actor=actor,
            wet_weight=4000,
            unit="g",
        )
        cultivation.transition_harvest(
            organization_id,
            facility_id,
            harvest["id"],
            status="drying",
            actor=actor,
            dry_weight=1000,
            unit="g",
        )
        harvest_outputs = [
            {
                "product_id": flower_source.id,
                "lot_code": f"DEVV-{generation_code}-{code}-FLOWER",
                "quantity": 700,
                "unit": "g",
                "purpose": "finished_flower",
                "measurement_basis": "dry",
                "status": "available",
                "location_code": "BULK-FLOWER-VAULT",
                "compliance_package_id": f"DEV-HARV-{generation_code}-{code}-FLOWER",
            },
            {
                "product_id": trim_source.id,
                "lot_code": f"DEVV-{generation_code}-{code}-TRIM",
                "quantity": 300,
                "unit": "g",
                "purpose": "trim",
                "measurement_basis": "dry",
                "status": "available",
                "location_code": "EXTRACTION-STAGING",
                "compliance_package_id": f"DEV-HARV-{generation_code}-{code}-TRIM",
            },
        ]
        preview = harvest_allocator.preview_harvest_allocation(
            organization_id=organization_id,
            facility_id=facility_id,
            harvest_id=harvest["id"],
            outputs=harvest_outputs,
            losses=[],
        )
        if abs(float(preview["reconciliation"]["dry"]["remaining"])) > 1e-9:
            raise RuntimeError("DEV harvest allocation did not fully reconcile the measured dry weight.")
        committed = harvest_allocator.commit_harvest_allocation(
            organization_id=organization_id,
            facility_id=facility_id,
            harvest_id=harvest["id"],
            outputs=harvest_outputs,
            losses=[],
            preview_key=preview["preview_key"],
            actor=actor,
        )
        cultivation.transition_harvest(
            organization_id,
            facility_id,
            harvest["id"],
            status="completed",
            actor=actor,
        )
        flower_lot_id, trim_lot_id = committed["output_lot_ids"]
        flower_source_lot_ids.append(flower_lot_id)
        trim_source_lot_ids.append(trim_lot_id)
        _quality(engine, flower_lot_id, f"DEV-COA-{generation_code}-{code}-FLOWER", thca=25.0 + strain_index * 0.35, tac=28.0 + strain_index * 0.3, terpenes=1.7 + strain_index * 0.11, source="dev_vertical_lab", actor=actor)
        _quality(engine, trim_lot_id, f"DEV-COA-{generation_code}-{code}-TRIM", thca=16.0 + strain_index * 0.25, tac=19.0 + strain_index * 0.2, terpenes=1.1 + strain_index * 0.07, source="dev_vertical_lab", actor=actor)

        flower_outputs: list[PackageStudioOutputPlan] = []
        flower_source_used = 0.0
        for format_index, (format_name, grams_each, units, case_pack) in enumerate(FLOWER_FORMATS, start=1):
            product = _ensure_product(
                engine,
                coman,
                organization_id,
                sku=f"DEVV-{code}-F{format_index:02d}",
                name=f"{strain} {format_name}",
                item_type="finished_good",
                base_unit="unit",
                unit_cost=0.0,
                retail_price=round(max(10.0, grams_each * 9.0), 2),
                upc=f"851{strain_index:02d}{format_index:02d}00000",
                actor=actor,
            )
            _profile(master, organization_id, product.id, strain=strain, category="Flower", product_format=format_name, actor=actor)
            _packaging(engine, organization_id, product.id, net_content=grams_each, case_pack=case_pack)
            final_product_ids.append(product.id)
            source_equivalent = grams_each * units
            flower_source_used += source_equivalent
            flower_outputs.append(
                PackageStudioOutputPlan(
                    product_id=product.id,
                    lot_code=f"DEVV-{generation_code}-{code}-F{format_index:02d}",
                    inventory_quantity=units,
                    inventory_unit="unit",
                    source_equivalent_quantity=source_equivalent,
                    source_equivalent_unit="g",
                    compliance_package_id=f"DEV-PKG-{generation_code}-{code}-F{format_index:02d}",
                    purpose="standard",
                    location_code="FINISHED-GOODS",
                )
            )
        packaged_flower = studio.commit(
            PackageStudioPlan(
                action_type="multi_build",
                inputs=(PackageStudioInputPlan(lot_id=flower_lot_id, quantity=flower_source_used, unit="g"),),
                outputs=tuple(flower_outputs),
                source_unit="g",
                run_number=f"DEV-PKG-{generation_code}-{code}-FLOWER",
                reason="DEV vertical saleable flower packaging",
            ),
            organization_id=organization_id,
            facility_id=facility_id,
            actor=actor,
        )
        flower_final_lot_ids.extend(packaged_flower.output_lot_ids)

        for extract_index, (workflow_key, method, format_name) in enumerate(EXTRACT_FORMATS, start=1):
            bulk = _ensure_product(
                engine,
                coman,
                organization_id,
                sku=f"DEVV-{code}-X{extract_index:02d}-BULK",
                name=f"{strain} {format_name} Bulk",
                item_type="cannabis",
                base_unit="g",
                unit_cost=0.0,
                actor=actor,
            )
            _profile(master, organization_id, bulk.id, strain=strain, category="Bulk Extract", product_format=format_name, actor=actor)
            finished = _ensure_product(
                engine,
                coman,
                organization_id,
                sku=f"DEVV-{code}-X{extract_index:02d}",
                name=f"{strain} {format_name}",
                item_type="finished_good",
                base_unit="unit",
                unit_cost=0.0,
                retail_price=35.0,
                upc=f"861{strain_index:02d}{extract_index:02d}00000",
                actor=actor,
            )
            _profile(master, organization_id, finished.id, strain=strain, category="Concentrates", product_format=format_name, actor=actor)
            _packaging(engine, organization_id, finished.id, net_content=1.0, case_pack=12)
            final_product_ids.append(finished.id)

            run = extraction.create_run(
                organization_id=organization_id,
                facility_id=facility_id,
                batch_number=f"DEV-EXT-{generation_code}-{code}-{extract_index:02d}",
                method=method,
                workflow_key=workflow_key,
                product_family=format_name,
                strain=strain,
                actor=actor,
            )
            run_input = extraction.reserve_input(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run.id,
                lot_id=trim_lot_id,
                quantity=50,
                unit="g",
                actor=actor,
            )
            extraction.consume_input(
                organization_id=organization_id,
                facility_id=facility_id,
                run_input_id=run_input.id,
                quantity=50,
                actor=actor,
            )
            extraction.add_cost_event(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run.id,
                category="labor",
                amount_usd=25,
                quantity=1,
                unit="hour",
                actor=actor,
            )
            output = extraction.create_output(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run.id,
                product_id=bulk.id,
                lot_code=f"DEV-EXT-{generation_code}-{code}-{extract_index:02d}-BULK",
                quantity=10,
                unit="g",
                compliance_package_id=f"DEV-EXT-PKG-{generation_code}-{code}-{extract_index:02d}",
                location_code="EXTRACTION-QA",
                actor=actor,
            )
            extraction_bulk_lot_ids.append(output.lot_id)
            extraction.record_qa_event(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run.id,
                output_id=output.id,
                event_type="coa_attached",
                result="passed",
                coa_reference=f"DEV-COA-EXT-{generation_code}-{code}-{extract_index:02d}",
                actor=actor,
            )
            extraction.record_qa_event(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run.id,
                event_type="release",
                result="passed",
                actor=actor,
            )
            packaged_extract = studio.commit(
                PackageStudioPlan(
                    action_type="build_run",
                    inputs=(PackageStudioInputPlan(lot_id=output.lot_id, quantity=10, unit="g"),),
                    outputs=(
                        PackageStudioOutputPlan(
                            product_id=finished.id,
                            lot_code=f"DEVV-{generation_code}-{code}-X{extract_index:02d}",
                            inventory_quantity=10,
                            inventory_unit="unit",
                            source_equivalent_quantity=10,
                            source_equivalent_unit="g",
                            compliance_package_id=f"DEV-PKG-{generation_code}-{code}-X{extract_index:02d}",
                            purpose="standard",
                            location_code="FINISHED-GOODS",
                        ),
                    ),
                    source_unit="g",
                    run_number=f"DEV-PKG-{generation_code}-{code}-X{extract_index:02d}",
                    reason="DEV vertical released extract packaging",
                ),
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
            )
            extract_final_lot_ids.extend(packaged_extract.output_lot_ids)

    result = VerticalDevInventoryResult(
        generation=generation_code,
        retired_lots=0,
        retired_quantity=0.0,
        plants=plant_count,
        harvests=harvest_count,
        flower_source_lots=len(flower_source_lot_ids),
        trim_source_lots=len(trim_source_lot_ids),
        flower_final_lots=tuple(flower_final_lot_ids),
        extraction_bulk_lots=tuple(extraction_bulk_lot_ids),
        extract_final_lots=tuple(extract_final_lot_ids),
        final_product_ids=tuple(final_product_ids),
    )
    if len(result.final_lots) != 100 or len(result.final_product_ids) != 100:
        raise RuntimeError("DEV vertical seed did not create exactly 100 finished inventory lots/products.")

    with Session(engine) as session, session.begin():
        session.add(
            AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="inventory",
                entity_id=facility_id,
                action="dev_vertical_inventory_seeded",
                actor=actor,
                changes_json=json.dumps(result.summary(), sort_keys=True),
            )
        )
    return result


def replace_dev_sandbox_inventory(
    engine: Engine,
    organization_id: str,
    facility_id: str,
    *,
    generation: str | None = None,
    actor: str = VERTICAL_SEED_ACTOR,
) -> VerticalDevInventoryResult:
    retired = retire_dev_sandbox_inventory(
        engine,
        organization_id,
        facility_id,
        actor=actor,
    )
    seeded = seed_vertical_dev_inventory(
        engine,
        organization_id,
        facility_id,
        generation=generation,
        actor=actor,
    )
    return VerticalDevInventoryResult(
        generation=seeded.generation,
        retired_lots=int(retired["retired_lots"]),
        retired_quantity=float(retired["retired_quantity"]),
        plants=seeded.plants,
        harvests=seeded.harvests,
        flower_source_lots=seeded.flower_source_lots,
        trim_source_lots=seeded.trim_source_lots,
        flower_final_lots=seeded.flower_final_lots,
        extraction_bulk_lots=seeded.extraction_bulk_lots,
        extract_final_lots=seeded.extract_final_lots,
        final_product_ids=seeded.final_product_ids,
    )
