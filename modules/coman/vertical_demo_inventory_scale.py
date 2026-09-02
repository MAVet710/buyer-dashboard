"""Scaled vertical inventory generation for the durable DEV Sandbox tenant.

The scaled scenario intentionally exercises the whole operating graph:
80 active plants across cultivation phases + 40 harvested source plants, 10 reconciled
harvests, 350 flower SKUs, 150 extraction-derived SKUs, real Massachusetts flower
COA references plus extraction-only mock retests, and commercial Purchase/Sales
Orders that reserve and fulfill real finished inventory.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
import json

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from modules.coman.models import (
    AuditEvent,
    CommercialOrder,
    CommercialOrderLine,
    InventoryLot,
    Product,
    TradePartner,
)
from modules.coman.vertical_demo_inventory import (
    DEV_FACILITY_CODE,
    DEV_ORGANIZATION_SLUG,
    VERTICAL_SEED_ACTOR,
    VerticalDevInventoryResult,
    _ensure_product,
    _guard,
    _packaging,
    _profile,
    _quality,
    retire_dev_sandbox_inventory,
)
from modules.coman.vertical_demo_ma_coas import (
    MA_FLOWER_REFERENCE_STRAINS,
    annotate_dev_flower_label_metadata,
    seed_dev_ma_flower_reference_coa,
)
from modules.coman import ComanRepository
from modules.commercial.repository import CommercialRepository, OPEN_ORDER_STATUSES
from modules.cultivation.service import ACTIVE_PLANT_PHASES, CultivationService
from modules.extraction import ExtractionRepository
from modules.inventory_quality import LotQualityService
from modules.material_lineage.harvest_guard import GuardedHarvestAllocationService
from modules.package_studio import (
    PackageStudioInputPlan,
    PackageStudioOutputPlan,
    PackageStudioPlan,
    PackageStudioService,
)
from modules.product_master import ProductMasterRepository

STRAINS = (
    "Candy Sparqs",
    "GMO",
    "Strawberry Cough",
    "Blue Dream",
    "Wedding Cake",
    "Super Lemon Haze",
    "Runtz OG",
    "Motorbreath",
    "Permanent Marker",
    "Animal Tsunami",
)

ACTIVE_PHASES = ("clone", "seedling", "vegetative", "flowering")
ACTIVE_PLANTS_PER_PHASE_PER_STRAIN = 2  # 10 strains x 4 phases x 2 = 80 active plants.
HARVEST_SOURCE_PLANTS_PER_STRAIN = 4     # 40 additional plants actually enter harvest genealogy.

FLOWER_TIERS = (
    ("Reserve", 1.25),
    ("Premium", 1.15),
    ("Classic", 1.00),
    ("Value", 0.85),
    ("House", 0.75),
)
# format, net grams, output units, case pack
FLOWER_BASE_FORMATS = (
    ("Flower Jar 1g", 1.0, 4, 24),
    ("Flower Jar 3.5g", 3.5, 4, 24),
    ("Flower Pouch 7g", 7.0, 4, 12),
    ("Flower Pouch 14g", 14.0, 4, 8),
    ("Flower Pouch 28g", 28.0, 4, 4),
    ("Smalls Pouch 3.5g", 3.5, 4, 24),
    ("Ground Flower Pouch 7g", 7.0, 4, 12),
)

# workflow_key, method, family, package specs (format, net grams, units, case pack, price)
EXTRACT_WORKFLOWS = (
    (
        "bho_cured",
        "BHO",
        "Cured Hydrocarbon Concentrate",
        (
            ("Cured Badder 0.5g", 0.5, 12, 24, 24.0),
            ("Cured Badder 1g", 1.0, 6, 12, 40.0),
            ("Cured Sugar 1g", 1.0, 6, 12, 42.0),
            ("Cured Sauce 1g", 1.0, 6, 12, 45.0),
            ("Crumble 2g", 2.0, 3, 6, 70.0),
        ),
    ),
    (
        "ethanol_crude",
        "Ethanol",
        "Refined Distillate",
        (
            ("Distillate Syringe 0.5g", 0.5, 12, 24, 22.0),
            ("Distillate Syringe 1g", 1.0, 6, 12, 36.0),
            ("Distillate Dart 1g", 1.0, 6, 12, 38.0),
            ("Distillate Jar 1g", 1.0, 6, 12, 35.0),
            ("Distillate Applicator 2g", 2.0, 3, 6, 62.0),
        ),
    ),
    (
        "dry_sift",
        "Dry Sift",
        "Solventless Dry Sift",
        (
            ("Dry Sift 0.5g", 0.5, 12, 24, 20.0),
            ("Dry Sift 1g", 1.0, 6, 12, 34.0),
            ("Kief 1g", 1.0, 6, 12, 30.0),
            ("Reserve Kief 1g", 1.0, 6, 12, 38.0),
            ("Pressed Dry Sift 2g", 2.0, 3, 6, 58.0),
        ),
    ),
)

EXPECTED_ACTIVE_PLANTS = len(STRAINS) * len(ACTIVE_PHASES) * ACTIVE_PLANTS_PER_PHASE_PER_STRAIN
EXPECTED_TOTAL_PLANTS = EXPECTED_ACTIVE_PLANTS + len(STRAINS) * HARVEST_SOURCE_PLANTS_PER_STRAIN
EXPECTED_FLOWER_SKUS = len(STRAINS) * len(FLOWER_TIERS) * len(FLOWER_BASE_FORMATS)
EXPECTED_EXTRACT_SKUS = len(STRAINS) * sum(len(row[3]) for row in EXTRACT_WORKFLOWS)
EXPECTED_FINISHED_SKUS = EXPECTED_FLOWER_SKUS + EXPECTED_EXTRACT_SKUS
EXPECTED_MOCK_FINISHED_COAS = EXPECTED_FINISHED_SKUS // 10


def _retire_active_plants(cultivation: CultivationService, organization_id: str, facility_id: str, actor: str) -> int:
    retired = 0
    for plant in cultivation.list_plants(organization_id, facility_id):
        if plant.phase in ACTIVE_PLANT_PHASES:
            cultivation.transition(
                organization_id,
                facility_id,
                plant.id,
                phase="destroyed",
                room_code=plant.room_code,
                actor=actor,
                reason="DEV Sandbox generation reset",
                notes="Retired before replacement vertical demo generation.",
            )
            retired += 1
    return retired


def _cancel_open_orders(engine: Engine, organization_id: str, facility_id: str, actor: str) -> int:
    with Session(engine) as session, session.begin():
        orders = list(
            session.scalars(
                select(CommercialOrder).where(
                    CommercialOrder.organization_id == organization_id,
                    CommercialOrder.facility_id == facility_id,
                    CommercialOrder.status.in_(OPEN_ORDER_STATUSES),
                )
            )
        )
        for order in orders:
            order.status = "cancelled"
            order.updated_by = actor
            order.notes = (order.notes + "\n" if order.notes else "") + "Superseded by DEV vertical inventory generation reset."
        return len(orders)


def _ensure_partner(
    engine: Engine,
    commercial: CommercialRepository,
    organization_id: str,
    *,
    name: str,
    partner_type: str,
    actor: str,
    license_or_registration: str,
) -> TradePartner:
    with Session(engine) as session:
        existing = session.scalar(
            select(TradePartner).where(
                TradePartner.organization_id == organization_id,
                TradePartner.name == name,
            )
        )
    if existing is None:
        return commercial.create_trade_partner(
            organization_id,
            name=name,
            partner_type=partner_type,
            actor=actor,
            license_or_registration=license_or_registration,
            contact_name="DEV Sandbox Buyer",
            contact_email="dev-wholesale@example.invalid",
            payment_terms="Net 30",
        )
    with Session(engine) as session, session.begin():
        row = session.get(TradePartner, existing.id)
        assert row is not None
        row.partner_type = partner_type
        row.license_or_registration = license_or_registration
        row.active = True
    with Session(engine) as session:
        refreshed = session.get(TradePartner, existing.id)
        assert refreshed is not None
        session.expunge(refreshed)
        return refreshed


def _seed_active_cultivation(
    cultivation: CultivationService,
    organization_id: str,
    facility_id: str,
    generation: str,
    actor: str,
) -> int:
    for phase in ACTIVE_PHASES:
        cultivation.upsert_room(
            organization_id,
            facility_id,
            room_code=f"DEV-{phase.upper()}",
            display_name=f"DEV {phase.title()} Room",
            phase=phase,
            plant_capacity=40,
            square_feet=600 if phase in {"vegetative", "flowering"} else 250,
            target_cycle_days={"clone": 14, "seedling": 18, "vegetative": 28, "flowering": 63}[phase],
            notes="Scaled DEV vertical cultivation stage.",
        )
    count = 0
    for strain_index, strain in enumerate(STRAINS, start=1):
        code = f"S{strain_index:02d}"
        for phase in ACTIVE_PHASES:
            for number in range(1, ACTIVE_PLANTS_PER_PHASE_PER_STRAIN + 1):
                cultivation.create_plant(
                    organization_id,
                    facility_id,
                    plant_tag=f"DEVV-{generation}-{code}-{phase[:2].upper()}{number:02d}",
                    strain_name=strain,
                    phase=phase,
                    room_code=f"DEV-{phase.upper()}",
                    actor=actor,
                    mother_plant_tag=f"DEV-MOTHER-{code}" if phase in {"clone", "seedling"} else "",
                    notes="Active plant in the scaled DEV vertical generation.",
                )
                count += 1
    return count


def _finished_mock_coas(engine: Engine, lot_ids: list[str], generation: str, actor: str) -> int:
    """Create exactly 50 direct mock retest scenarios from extraction-derived finished lots."""

    selected = lot_ids[::3][:EXPECTED_MOCK_FINISHED_COAS]
    if len(selected) != EXPECTED_MOCK_FINISHED_COAS:
        raise RuntimeError(
            f"Expected {EXPECTED_MOCK_FINISHED_COAS} extraction mock-COA scenarios, got {len(selected)}."
        )
    with Session(engine) as session, session.begin():
        for index, lot_id in enumerate(selected, start=1):
            LotQualityService.set_evidence(
                session,
                lot_id=lot_id,
                lab_testing_state="Passed",
                coa_reference=f"DEV-MOCK-FINISHED-COA-{generation}-{index:03d}",
                coa_url=f"https://example.invalid/dev-coa/{generation.lower()}/{index:03d}.pdf",
                thca_percent=round(22.0 + (index % 10) * 0.55, 2),
                tac_percent=round(25.0 + (index % 10) * 0.60, 2),
                total_terpenes_percent=round(1.5 + (index % 7) * 0.18, 2),
                evidence_source="mock_finished_lab",
                actor=actor,
            )
    return len(selected)


def _seed_commercial_orders(
    engine: Engine,
    organization_id: str,
    facility_id: str,
    final_lot_ids: list[str],
    generation: str,
    actor: str,
) -> dict[str, int]:
    commercial = CommercialRepository(engine)
    customers = [
        _ensure_partner(engine, commercial, organization_id, name="Harbor Wellness", partner_type="customer", actor=actor, license_or_registration="MR-DEMO-001"),
        _ensure_partner(engine, commercial, organization_id, name="Cape Select", partner_type="customer", actor=actor, license_or_registration="MR-DEMO-002"),
        _ensure_partner(engine, commercial, organization_id, name="Berkshire Brands", partner_type="customer", actor=actor, license_or_registration="MR-DEMO-003"),
        _ensure_partner(engine, commercial, organization_id, name="South Coast Cannabis", partner_type="customer", actor=actor, license_or_registration="MR-DEMO-004"),
    ]
    vendors = [
        _ensure_partner(engine, commercial, organization_id, name="Mass Packaging Supply", partner_type="vendor", actor=actor, license_or_registration="VENDOR-DEMO-001"),
        _ensure_partner(engine, commercial, organization_id, name="New England Labels", partner_type="vendor", actor=actor, license_or_registration="VENDOR-DEMO-002"),
        _ensure_partner(engine, commercial, organization_id, name="Cone & Jar Supply Co", partner_type="vendor", actor=actor, license_or_registration="VENDOR-DEMO-003"),
    ]

    coman = ComanRepository(engine)
    package_products: list[Product] = []
    for idx, (sku, name, cost) in enumerate(
        (
            ("DEV-PACK-JAR", "Compliant glass jar and lid", 0.62),
            ("DEV-PACK-POUCH", "Compliant child-resistant pouch", 0.38),
            ("DEV-PACK-LABEL", "Compliance label roll", 0.08),
            ("DEV-PACK-EXTRACT-JAR", "Concentrate jar and cap", 0.55),
            ("DEV-PACK-SYRINGE", "Distillate syringe and plunger", 0.48),
        ),
        start=1,
    ):
        package_products.append(
            _ensure_product(
                engine,
                coman,
                organization_id,
                sku=sku,
                name=name,
                item_type="packaging",
                base_unit="unit",
                unit_cost=cost,
                actor=actor,
            )
        )

    today = date.today()
    purchase_orders = 0
    for po_index in range(1, 7):
        lines = []
        for offset in range(2):
            product = package_products[(po_index + offset - 1) % len(package_products)]
            lines.append(
                {
                    "product_id": product.id,
                    "quantity": 500 + po_index * 100,
                    "unit": "unit",
                    "unit_price": float(product.unit_cost),
                    "description": product.name,
                }
            )
        order = commercial.create_order(
            organization_id=organization_id,
            facility_id=facility_id,
            partner_id=vendors[(po_index - 1) % len(vendors)].id,
            order_number=f"DEVV-PO-{generation}-{po_index:03d}",
            order_type="purchase",
            order_date=today - timedelta(days=po_index),
            due_date=today + timedelta(days=po_index + 2),
            lines=lines,
            actor=actor,
            notes="Mock DEV purchase order for packaging/material planning.",
        )
        if po_index <= 3:
            commercial.confirm_order(order.id, organization_id=organization_id, facility_id=facility_id, actor=actor)
        purchase_orders += 1

    with Session(engine) as session:
        lots = list(session.scalars(select(InventoryLot).where(InventoryLot.id.in_(final_lot_ids))))
        lots_by_id = {lot.id: lot for lot in lots}
        products = {row.id: row for row in session.scalars(select(Product).where(Product.organization_id == organization_id))}
    sale_lots = [lots_by_id[lot_id] for lot_id in final_lot_ids[:120] if lot_id in lots_by_id]

    sales_orders = 0
    statuses = Counter()
    for so_index in range(1, 13):
        selected = sale_lots[(so_index - 1) * 5 : (so_index - 1) * 5 + 5]
        quantity = 1.0 if so_index == 12 else 2.0
        lines = [
            {
                "product_id": lot.product_id,
                "quantity": quantity,
                "unit": "unit",
                "unit_price": round(float(products[lot.product_id].retail_price or 10.0) * 0.62, 2),
                "description": products[lot.product_id].name,
            }
            for lot in selected
        ]
        order = commercial.create_order(
            organization_id=organization_id,
            facility_id=facility_id,
            partner_id=customers[(so_index - 1) % len(customers)].id,
            order_number=f"DEVV-SO-{generation}-{so_index:03d}",
            order_type="sales",
            order_date=today - timedelta(days=max(0, 12 - so_index)),
            due_date=today + timedelta(days=so_index % 5),
            lines=lines,
            actor=actor,
            notes="Mock DEV wholesale sales order tied to real vertical finished lots.",
        )
        if so_index <= 3:
            statuses["draft"] += 1
            sales_orders += 1
            continue
        commercial.confirm_order(order.id, organization_id=organization_id, facility_id=facility_id, actor=actor)
        order_lines = commercial.list_order_lines(organization_id, order_id=order.id)
        if so_index <= 6:
            statuses["confirmed"] += 1
        else:
            for line, lot in zip(order_lines, selected):
                commercial.allocate_lot(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    order_line_id=line.id,
                    lot_id=lot.id,
                    quantity=1,
                    actor=actor,
                )
            if so_index <= 9:
                statuses["allocated"] += 1
            elif so_index <= 11:
                for line, lot in list(zip(order_lines, selected))[:2]:
                    commercial.post_fulfillment(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        order_line_id=line.id,
                        lot_id=lot.id,
                        quantity=1,
                        actor=actor,
                        reference=f"DEV-SHIP-{generation}-{so_index:03d}",
                    )
                statuses["partially_fulfilled"] += 1
            else:
                for line, lot in zip(order_lines, selected):
                    commercial.post_fulfillment(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        order_line_id=line.id,
                        lot_id=lot.id,
                        quantity=1,
                        actor=actor,
                        reference=f"DEV-SHIP-{generation}-{so_index:03d}",
                    )
                commercial.set_payment_status(order.id, organization_id=organization_id, facility_id=facility_id, payment_status="paid", actor=actor)
                statuses["fulfilled"] += 1
        sales_orders += 1
    return {"purchase_orders": purchase_orders, "sales_orders": sales_orders, **dict(statuses)}


def seed_scaled_vertical_dev_inventory(
    engine: Engine,
    organization_id: str,
    facility_id: str,
    *,
    generation: str,
    actor: str = VERTICAL_SEED_ACTOR,
) -> VerticalDevInventoryResult:
    with Session(engine) as session, session.begin():
        _, facility = _guard(session, organization_id, facility_id)
        facility.cultivation_enabled = True
        facility.production_enabled = True
        facility.retail_enabled = True
        facility.commercial_enabled = True
        facility.license_number = "DEV-SANDBOX-VERTICAL"
        facility.license_type = "cultivation+manufacturing+retail"

    if set(STRAINS) != set(MA_FLOWER_REFERENCE_STRAINS):
        missing = sorted(set(STRAINS) - set(MA_FLOWER_REFERENCE_STRAINS))
        extra = sorted(set(MA_FLOWER_REFERENCE_STRAINS) - set(STRAINS))
        raise RuntimeError(
            f"DEV MA flower reference coverage mismatch: missing={missing} extra={extra}"
        )

    coman = ComanRepository(engine)
    master = ProductMasterRepository(engine)
    cultivation = CultivationService(engine)
    allocator = GuardedHarvestAllocationService(engine)
    extraction = ExtractionRepository(engine)
    studio = PackageStudioService(engine)

    active_count = _seed_active_cultivation(cultivation, organization_id, facility_id, generation, actor)
    flower_final: list[str] = []
    extract_final: list[str] = []
    extraction_bulk: list[str] = []
    product_ids: list[str] = []
    flower_source_lots: list[str] = []
    trim_source_lots: list[str] = []
    total_plants = active_count

    for strain_index, strain in enumerate(STRAINS, start=1):
        code = f"S{strain_index:02d}"
        flower_source = _ensure_product(
            engine, coman, organization_id,
            sku=f"DEVV-{code}-BULK-FLOWER", name=f"{strain} Bulk Flower",
            item_type="cannabis", base_unit="g", unit_cost=2.0, actor=actor,
        )
        trim_source = _ensure_product(
            engine, coman, organization_id,
            sku=f"DEVV-{code}-TRIM", name=f"{strain} Trim",
            item_type="cannabis", base_unit="g", unit_cost=0.75, actor=actor,
        )
        _profile(master, organization_id, flower_source.id, strain=strain, category="Bulk Flower", product_format="Bulk Flower", actor=actor)
        _profile(master, organization_id, trim_source.id, strain=strain, category="Trim", product_format="Trim", actor=actor)

        harvest_plants = [
            cultivation.create_plant(
                organization_id, facility_id,
                plant_tag=f"DEVV-{generation}-{code}-HARV{number:02d}",
                strain_name=strain, phase="flowering", room_code="DEV-FLOWERING",
                actor=actor, notes="Harvest source plant for scaled DEV genealogy.",
            )
            for number in range(1, HARVEST_SOURCE_PLANTS_PER_STRAIN + 1)
        ]
        total_plants += len(harvest_plants)
        harvest = cultivation.create_harvest(
            organization_id, facility_id,
            harvest_code=f"DEVV-{generation}-{code}-H01",
            plant_ids=[row.id for row in harvest_plants], actor=actor,
            notes="Scaled DEV harvest feeding flower and extraction inventory.",
        )
        cultivation.transition_harvest(organization_id, facility_id, harvest["id"], status="active", actor=actor, wet_weight=20000, unit="g")
        cultivation.transition_harvest(organization_id, facility_id, harvest["id"], status="drying", actor=actor, dry_weight=5000, unit="g")
        outputs = [
            {
                "product_id": flower_source.id, "lot_code": f"DEVV-{generation}-{code}-FLOWER",
                "quantity": 3500, "unit": "g", "purpose": "finished_flower", "measurement_basis": "dry",
                "status": "available", "location_code": "BULK-FLOWER-VAULT",
                "compliance_package_id": f"DEV-HARV-{generation}-{code}-FLOWER",
            },
            {
                "product_id": trim_source.id, "lot_code": f"DEVV-{generation}-{code}-TRIM",
                "quantity": 1500, "unit": "g", "purpose": "trim", "measurement_basis": "dry",
                "status": "available", "location_code": "EXTRACTION-STAGING",
                "compliance_package_id": f"DEV-HARV-{generation}-{code}-TRIM",
            },
        ]
        preview = allocator.preview_harvest_allocation(
            organization_id=organization_id, facility_id=facility_id, harvest_id=harvest["id"], outputs=outputs, losses=[]
        )
        if abs(float(preview["reconciliation"]["dry"]["remaining"])) > 1e-9:
            raise RuntimeError("Scaled DEV harvest did not reconcile to measured dry weight.")
        committed = allocator.commit_harvest_allocation(
            organization_id=organization_id, facility_id=facility_id, harvest_id=harvest["id"],
            outputs=outputs, losses=[], preview_key=preview["preview_key"], actor=actor,
        )
        cultivation.transition_harvest(organization_id, facility_id, harvest["id"], status="completed", actor=actor)
        flower_lot_id, trim_lot_id = committed["output_lot_ids"]
        flower_source_lots.append(flower_lot_id)
        trim_source_lots.append(trim_lot_id)
        seed_dev_ma_flower_reference_coa(
            engine,
            organization_id,
            facility_id,
            flower_lot_id,
            strain=strain,
            actor=actor,
        )
        _quality(engine, trim_lot_id, f"DEV-COA-{generation}-{code}-TRIM", thca=16.0 + strain_index * 0.25, tac=19.0 + strain_index * 0.20, terpenes=1.1 + strain_index * 0.07, source="dev_vertical_harvest_lab", actor=actor)

        flower_outputs: list[PackageStudioOutputPlan] = []
        flower_product_batch: list[str] = []
        source_used = 0.0
        variant_index = 0
        for tier_index, (tier, price_multiplier) in enumerate(FLOWER_TIERS, start=1):
            for format_index, (format_name, grams_each, units, case_pack) in enumerate(FLOWER_BASE_FORMATS, start=1):
                variant_index += 1
                product = _ensure_product(
                    engine, coman, organization_id,
                    sku=f"DEVV-{code}-F{variant_index:02d}",
                    name=f"{strain} {tier} {format_name}", item_type="finished_good", base_unit="unit", unit_cost=0.0,
                    retail_price=round(max(10.0, grams_each * 9.0) * price_multiplier, 2),
                    upc=f"85{strain_index:02d}{variant_index:03d}00000", actor=actor,
                )
                _profile(master, organization_id, product.id, strain=strain, category="Flower", product_format=f"{tier} {format_name}", actor=actor)
                _packaging(engine, organization_id, product.id, net_content=grams_each, case_pack=case_pack)
                product_ids.append(product.id)
                flower_product_batch.append(product.id)
                source_equivalent = grams_each * units
                source_used += source_equivalent
                flower_outputs.append(
                    PackageStudioOutputPlan(
                        product_id=product.id, lot_code=f"DEVV-{generation}-{code}-F{variant_index:02d}",
                        inventory_quantity=units, inventory_unit="unit",
                        source_equivalent_quantity=source_equivalent, source_equivalent_unit="g",
                        compliance_package_id=f"DEV-PKG-{generation}-{code}-F{variant_index:02d}",
                        purpose="standard", location_code="FINISHED-GOODS",
                    )
                )
        packaged = studio.commit(
            PackageStudioPlan(
                action_type="multi_build",
                inputs=(PackageStudioInputPlan(lot_id=flower_lot_id, quantity=source_used, unit="g"),),
                outputs=tuple(flower_outputs), source_unit="g",
                run_number=f"DEV-PKG-{generation}-{code}-FLOWER",
                reason="Scaled DEV flower packaging across 35 finished SKUs.",
            ),
            organization_id=organization_id, facility_id=facility_id, actor=actor,
        )
        annotate_dev_flower_label_metadata(
            engine,
            organization_id,
            facility_id,
            flower_lot_id,
            packaged.output_lot_ids,
        )
        flower_final.extend(packaged.output_lot_ids)

        extract_variant = 0
        for workflow_index, (workflow_key, method, family, package_specs) in enumerate(EXTRACT_WORKFLOWS, start=1):
            bulk = _ensure_product(
                engine, coman, organization_id,
                sku=f"DEVV-{code}-X{workflow_index:02d}-BULK", name=f"{strain} {family} Bulk",
                item_type="cannabis", base_unit="g", unit_cost=0.0, actor=actor,
            )
            _profile(master, organization_id, bulk.id, strain=strain, category="Bulk Extract", product_format=family, actor=actor)
            run = extraction.create_run(
                organization_id=organization_id, facility_id=facility_id,
                batch_number=f"DEV-EXT-{generation}-{code}-{workflow_index:02d}",
                method=method, workflow_key=workflow_key, product_family=family, strain=strain, actor=actor,
            )
            run_input = extraction.reserve_input(
                organization_id=organization_id, facility_id=facility_id, run_id=run.id,
                lot_id=trim_lot_id, quantity=150, unit="g", actor=actor,
            )
            extraction.consume_input(
                organization_id=organization_id, facility_id=facility_id,
                run_input_id=run_input.id, quantity=150, actor=actor,
            )
            extraction.add_cost_event(
                organization_id=organization_id, facility_id=facility_id, run_id=run.id,
                category="labor", amount_usd=75, quantity=3, unit="hour", actor=actor,
            )
            output = extraction.create_output(
                organization_id=organization_id, facility_id=facility_id, run_id=run.id,
                product_id=bulk.id, lot_code=f"DEV-EXT-{generation}-{code}-{workflow_index:02d}-BULK",
                quantity=30, unit="g", compliance_package_id=f"DEV-EXT-PKG-{generation}-{code}-{workflow_index:02d}",
                location_code="EXTRACTION-QA", actor=actor,
            )
            extraction_bulk.append(output.lot_id)
            extraction.record_qa_event(
                organization_id=organization_id, facility_id=facility_id, run_id=run.id, output_id=output.id,
                event_type="coa_attached", result="passed",
                coa_reference=f"DEV-COA-EXT-{generation}-{code}-{workflow_index:02d}", actor=actor,
            )
            extraction.record_qa_event(
                organization_id=organization_id, facility_id=facility_id, run_id=run.id,
                event_type="release", result="passed", actor=actor,
            )
            package_outputs: list[PackageStudioOutputPlan] = []
            for spec_index, (format_name, grams_each, units, case_pack, price) in enumerate(package_specs, start=1):
                extract_variant += 1
                product = _ensure_product(
                    engine, coman, organization_id,
                    sku=f"DEVV-{code}-X{extract_variant:02d}", name=f"{strain} {format_name}",
                    item_type="finished_good", base_unit="unit", unit_cost=0.0, retail_price=price,
                    upc=f"86{strain_index:02d}{extract_variant:03d}00000", actor=actor,
                )
                _profile(master, organization_id, product.id, strain=strain, category="Concentrates", product_format=format_name, actor=actor)
                _packaging(engine, organization_id, product.id, net_content=grams_each, case_pack=case_pack)
                product_ids.append(product.id)
                package_outputs.append(
                    PackageStudioOutputPlan(
                        product_id=product.id, lot_code=f"DEVV-{generation}-{code}-X{extract_variant:02d}",
                        inventory_quantity=units, inventory_unit="unit",
                        source_equivalent_quantity=grams_each * units, source_equivalent_unit="g",
                        compliance_package_id=f"DEV-PKG-{generation}-{code}-X{extract_variant:02d}",
                        purpose="standard", location_code="FINISHED-GOODS",
                    )
                )
            if abs(sum(row.source_equivalent_quantity for row in package_outputs) - 30.0) > 1e-9:
                raise RuntimeError("Scaled DEV extraction package outputs must consume the full 30 g bulk output.")
            extract_packaged = studio.commit(
                PackageStudioPlan(
                    action_type="build_run",
                    inputs=(PackageStudioInputPlan(lot_id=output.lot_id, quantity=30, unit="g"),),
                    outputs=tuple(package_outputs), source_unit="g",
                    run_number=f"DEV-PKG-{generation}-{code}-X{workflow_index:02d}",
                    reason="Scaled DEV released extract packaging.",
                ),
                organization_id=organization_id, facility_id=facility_id, actor=actor,
            )
            extract_final.extend(extract_packaged.output_lot_ids)

    final_lots = flower_final + extract_final
    if len(final_lots) != EXPECTED_FINISHED_SKUS or len(product_ids) != EXPECTED_FINISHED_SKUS:
        raise RuntimeError(
            f"Scaled DEV seed expected {EXPECTED_FINISHED_SKUS} finished SKUs, got lots={len(final_lots)} products={len(product_ids)}."
        )
    mock_coas = _finished_mock_coas(engine, extract_final, generation, actor)
    commercial_summary = _seed_commercial_orders(engine, organization_id, facility_id, final_lots, generation, actor)

    with Session(engine) as session:
        phase_counts = Counter(
            row.phase for row in cultivation.list_plants(organization_id, facility_id) if row.phase in ACTIVE_PLANT_PHASES
        )
    if sum(phase_counts.values()) < 60 or any(phase_counts.get(phase, 0) <= 0 for phase in ACTIVE_PHASES):
        raise RuntimeError(f"Scaled DEV seed did not leave at least 60 active plants across all stages: {dict(phase_counts)}")

    result = VerticalDevInventoryResult(
        generation=generation, retired_lots=0, retired_quantity=0.0,
        plants=total_plants, harvests=len(STRAINS),
        flower_source_lots=len(flower_source_lots), trim_source_lots=len(trim_source_lots),
        flower_final_lots=tuple(flower_final), extraction_bulk_lots=tuple(extraction_bulk),
        extract_final_lots=tuple(extract_final), final_product_ids=tuple(product_ids),
    )
    with Session(engine) as session, session.begin():
        session.add(
            AuditEvent(
                organization_id=organization_id, facility_id=facility_id,
                entity_type="inventory", entity_id=facility_id,
                action="dev_vertical_inventory_seeded", actor=actor,
                changes_json=json.dumps(
                    result.summary()
                    | {
                        "active_plants": sum(phase_counts.values()),
                        "active_plant_phases": dict(phase_counts),
                        "mock_finished_coas": mock_coas,
                        **commercial_summary,
                        "scaled_version": "500-sku-v1",
                    },
                    sort_keys=True,
                ),
            )
        )
    return result


def replace_scaled_vertical_dev_inventory(
    engine: Engine,
    organization_id: str,
    facility_id: str,
    *,
    generation: str,
    actor: str = VERTICAL_SEED_ACTOR,
) -> VerticalDevInventoryResult:
    cultivation = CultivationService(engine)
    _retire_active_plants(cultivation, organization_id, facility_id, actor)
    _cancel_open_orders(engine, organization_id, facility_id, actor)
    retired = retire_dev_sandbox_inventory(engine, organization_id, facility_id, actor=actor)
    seeded = seed_scaled_vertical_dev_inventory(
        engine, organization_id, facility_id, generation=generation, actor=actor,
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


def scaled_vertical_inventory_present(engine: Engine, organization_id: str, facility_id: str) -> bool:
    with Session(engine) as session:
        active_products = list(
            session.scalars(
                select(Product).where(
                    Product.organization_id == organization_id,
                    Product.active.is_(True),
                    Product.sku.like("DEVV-%"),
                    Product.item_type == "finished_good",
                )
            )
        )
        active_plants = len(
            [row for row in CultivationService(engine).list_plants(organization_id, facility_id) if row.phase in ACTIVE_PLANT_PHASES]
        )
        seed_event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.organization_id == organization_id,
                AuditEvent.facility_id == facility_id,
                AuditEvent.action == "dev_vertical_inventory_seeded",
                AuditEvent.changes_json.like('%"scaled_version": "500-sku-v1"%'),
            ).order_by(AuditEvent.occurred_at.desc())
        )
    return len(active_products) == EXPECTED_FINISHED_SKUS and active_plants >= 60 and seed_event is not None
