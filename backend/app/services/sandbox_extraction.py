"""Realistic, deterministic extraction data for the canonical DEV Sandbox.

This seed exists to make the React/FastAPI Extraction workspace feel like a live
manufacturing operation without ever touching a customer tenant. It creates
synthetic bulk inputs, linked extraction/refinement runs, WIP/released outputs,
QA states, COGS, resource usage, traceability lifecycle records, and one toll job.

The records intentionally contain no extraction recipes, machine setpoints,
solvent ratios, temperatures, pressures, or other process instructions. Those
belong in approved facility SOPs and manufacturer documentation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any

from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.orm import Session

from modules.coman.models import (
    Customer,
    Facility,
    InventoryLot,
    InventoryTransaction,
    Organization,
    Product,
)
from modules.extraction.models import (
    ExtractionCostEvent,
    ExtractionQAEvent,
    ExtractionRun,
    ExtractionRunInput,
    ExtractionRunOutput,
    ExtractionStageEvent,
    ExtractionTollJob,
)
from modules.extraction.performance_models import ExtractionResourceEvent
from modules.extraction.workflows import get_extraction_workflow
from modules.traceability.models import TraceabilityTransaction

SANDBOX_ORGANIZATION_SLUG = "dev-sandbox"
SANDBOX_FACILITY_CODE = "SANDBOX"
SANDBOX_EXTRACTION_VERSION = "extraction-realism-v1"
SANDBOX_EXTRACTION_ACTOR = "DEV Sandbox"
SANDBOX_EXTRACTION_LICENSE = "MP-SBX-0001"
SANDBOX_EXTRACTION_FACILITY = "DEV Sandbox Extraction Facility"

_REQUIRED_TABLES = {
    "coman_organizations",
    "coman_facilities",
    "coman_customers",
    "coman_products",
    "coman_inventory_lots",
    "coman_inventory_transactions",
    "extraction_runs",
    "extraction_run_inputs",
    "extraction_run_outputs",
    "extraction_stage_events",
    "extraction_cost_events",
    "extraction_qa_events",
    "extraction_toll_jobs",
    "extraction_resource_events",
    "traceability_transactions",
}

_INPUT_CATALOG = (
    {
        "key": "gmo_ff",
        "sku": "SBX-EXT-FF-GMO",
        "name": "GMO Fresh Frozen",
        "item_type": "cannabis",
        "unit_cost": 1.55,
        "lot_code": "FF-GMO-0826-A",
        "package": "1A406030000SBXFFGMO001",
        "location": "FREEZER-A1",
        "quantity": 12500.0,
    },
    {
        "key": "trop_ff",
        "sku": "SBX-EXT-FF-TROP",
        "name": "Trop Cherry Fresh Frozen",
        "item_type": "cannabis",
        "unit_cost": 1.75,
        "lot_code": "FF-TROP-0826-B",
        "package": "1A406030000SBXFFTROP002",
        "location": "FREEZER-A2",
        "quantity": 9600.0,
    },
    {
        "key": "superboof_cured",
        "sku": "SBX-EXT-CURED-SB",
        "name": "Super Boof Cured Biomass",
        "item_type": "cannabis",
        "unit_cost": 0.95,
        "lot_code": "CB-SB-0826-03",
        "package": "1A406030000SBXCURSB003",
        "location": "VAULT-BULK-01",
        "quantity": 14200.0,
    },
    {
        "key": "trim",
        "sku": "SBX-EXT-TRIM",
        "name": "Mixed Premium Trim",
        "item_type": "cannabis",
        "unit_cost": 0.65,
        "lot_code": "TRIM-MIX-0826-04",
        "package": "1A406030000SBXTRIM004",
        "location": "VAULT-BULK-02",
        "quantity": 22000.0,
    },
    {
        "key": "blue_dream",
        "sku": "SBX-EXT-CURED-BD",
        "name": "Blue Dream Cured Biomass",
        "item_type": "cannabis",
        "unit_cost": 1.10,
        "lot_code": "CB-BD-0826-05",
        "package": "1A406030000SBXCURBD005",
        "location": "VAULT-BULK-03",
        "quantity": 13000.0,
    },
    {
        "key": "aged_rosin",
        "sku": "SBX-EXT-ROSIN-INPUT",
        "name": "Released Bulk Hash Rosin",
        "item_type": "wip",
        "unit_cost": 24.00,
        "lot_code": "ROSIN-REL-0826-06",
        "package": "1A406030000SBXROSIN006",
        "location": "COLD-STORAGE-2",
        "quantity": 700.0,
    },
)

_OUTPUT_CATALOG = {
    "live_resin": ("SBX-EXT-LIVE", "Bulk Live Resin", 16.0),
    "cured_resin": ("SBX-EXT-CURED", "Bulk Cured Resin", 13.0),
    "crude": ("SBX-EXT-CRUDE", "Winterized Crude Oil", 5.4),
    "distillate": ("SBX-EXT-DIST", "Bulk Distillate", 7.8),
    "bubble_hash": ("SBX-EXT-HASH", "90u Bubble Hash", 14.0),
    "hash_rosin": ("SBX-EXT-HRO", "Bulk Hash Rosin", 24.0),
    "dry_sift": ("SBX-EXT-SIFT", "Bulk Dry Sift", 9.0),
    "co2_oil": ("SBX-EXT-CO2O", "Bulk CO2 Oil", 7.0),
    "rosin_vape": ("SBX-EXT-RVAPE", "Rosin Vape Oil", 28.0),
}

_RUN_SPECS = (
    {
        "batch": "SANDBOX-EXT-001",
        "workflow": "bho_live_resin",
        "stage": "recovery",
        "status": "active",
        "strain": "GMO",
        "input_key": "gmo_ff",
        "input_type": "Fresh Frozen",
        "input_g": 500.0,
        "output_key": "live_resin",
        "output_g": 78.0,
        "intermediate_g": 86.0,
        "output_type": "Live Resin",
        "operator": "Maya Chen",
        "machine": "Hydrocarbon Suite A",
        "client": "In House",
        "coa": "not_submitted",
        "revenue": 1638.0,
        "cogs": 812.0,
        "age_hours": 9,
    },
    {
        "batch": "SANDBOX-EXT-002",
        "workflow": "bho_cured",
        "stage": "qa",
        "status": "hold",
        "strain": "Super Boof",
        "input_key": "superboof_cured",
        "input_type": "Cured Biomass",
        "input_g": 650.0,
        "output_key": "cured_resin",
        "output_g": 81.0,
        "intermediate_g": 89.0,
        "output_type": "Badder",
        "operator": "Jordan Reyes",
        "machine": "Hydrocarbon Suite B",
        "client": "In House",
        "coa": "failed",
        "revenue": 1458.0,
        "cogs": 744.0,
        "age_hours": 31,
    },
    {
        "batch": "SANDBOX-EXT-003",
        "workflow": "ethanol_crude",
        "stage": "release",
        "status": "complete",
        "strain": "Mixed Cultivars",
        "input_key": "trim",
        "input_type": "Trim / Biomass",
        "input_g": 1200.0,
        "output_key": "crude",
        "output_g": 150.0,
        "intermediate_g": 164.0,
        "output_type": "Crude Oil",
        "operator": "Sam Patel",
        "machine": "Ethanol Line 1",
        "client": "In House",
        "coa": "passed",
        "revenue": 1200.0,
        "cogs": 688.0,
        "age_hours": 74,
    },
    {
        "batch": "SANDBOX-EXT-004",
        "workflow": "crude_distillate",
        "stage": "distillation",
        "status": "active",
        "strain": "Mixed Cultivars",
        "input_key": "output:SANDBOX-EXT-003",
        "input_type": "Winterized Crude Oil",
        "input_g": 140.0,
        "output_key": "distillate",
        "output_g": 108.0,
        "intermediate_g": 118.0,
        "output_type": "Distillate",
        "operator": "Sam Patel",
        "machine": "Refinement Line 1",
        "client": "In House",
        "coa": "not_submitted",
        "revenue": 1080.0,
        "cogs": 512.0,
        "age_hours": 7,
    },
    {
        "batch": "SANDBOX-EXT-005",
        "workflow": "ice_water_hash",
        "stage": "release",
        "status": "complete",
        "strain": "Trop Cherry",
        "input_key": "trop_ff",
        "input_type": "Fresh Frozen",
        "input_g": 900.0,
        "output_key": "bubble_hash",
        "output_g": 54.0,
        "intermediate_g": 61.0,
        "output_type": "Bubble Hash / Ice Water Hash",
        "operator": "Avery Brooks",
        "machine": "Solventless Room 1",
        "client": "In House",
        "coa": "passed",
        "revenue": 1512.0,
        "cogs": 906.0,
        "age_hours": 49,
    },
    {
        "batch": "SANDBOX-EXT-006",
        "workflow": "hash_rosin",
        "stage": "qa",
        "status": "qa",
        "strain": "Trop Cherry",
        "input_key": "output:SANDBOX-EXT-005",
        "input_type": "Bubble Hash",
        "input_g": 50.0,
        "output_key": "hash_rosin",
        "output_g": 37.0,
        "intermediate_g": 40.0,
        "output_type": "Hash Rosin",
        "operator": "Avery Brooks",
        "machine": "Rosin Room 1",
        "client": "In House",
        "coa": "pending",
        "revenue": 1332.0,
        "cogs": 702.0,
        "age_hours": 22,
    },
    {
        "batch": "SANDBOX-EXT-007",
        "workflow": "dry_sift",
        "stage": "release",
        "status": "complete",
        "strain": "Wedding Cake",
        "input_key": "superboof_cured",
        "input_type": "Cured Flower / Trim",
        "input_g": 800.0,
        "output_key": "dry_sift",
        "output_g": 90.0,
        "intermediate_g": 97.0,
        "output_type": "Dry Sift / Kief",
        "operator": "Jordan Reyes",
        "machine": "Sift Room 1",
        "client": "In House",
        "coa": "passed",
        "revenue": 1080.0,
        "cogs": 590.0,
        "age_hours": 96,
    },
    {
        "batch": "SANDBOX-EXT-008",
        "workflow": "co2_extract",
        "stage": "qa",
        "status": "hold",
        "strain": "Blue Dream",
        "input_key": "blue_dream",
        "input_type": "Cured Biomass",
        "input_g": 1300.0,
        "output_key": "co2_oil",
        "output_g": 142.0,
        "intermediate_g": 154.0,
        "output_type": "CO2 Oil",
        "operator": "Maya Chen",
        "machine": "CO2 Suite 1",
        "client": "In House",
        "coa": "pending",
        "revenue": 1420.0,
        "cogs": 940.0,
        "age_hours": 38,
    },
    {
        "batch": "SANDBOX-EXT-009",
        "workflow": "rosin_vape",
        "stage": "intake",
        "status": "queued",
        "strain": "GMO",
        "input_key": "aged_rosin",
        "input_type": "Released Hash Rosin",
        "input_g": 80.0,
        "output_key": "rosin_vape",
        "output_g": 0.0,
        "intermediate_g": 0.0,
        "output_type": "Vape Oil",
        "operator": "Avery Brooks",
        "machine": "Formulation Bench 1",
        "client": "In House",
        "coa": "not_submitted",
        "revenue": 0.0,
        "cogs": 50.0,
        "age_hours": 0,
    },
    {
        "batch": "SANDBOX-EXT-010",
        "workflow": "bho_live_resin",
        "stage": "post_process",
        "status": "active",
        "strain": "Trop Cherry",
        "input_key": "trop_ff",
        "input_type": "Fresh Frozen",
        "input_g": 700.0,
        "output_key": "live_resin",
        "output_g": 72.0,
        "intermediate_g": 84.0,
        "output_type": "Live Resin",
        "operator": "Maya Chen",
        "machine": "Hydrocarbon Suite A",
        "client": "Atlantic Wellness Labs",
        "coa": "not_submitted",
        "revenue": 2200.0,
        "cogs": 1040.0,
        "age_hours": 13,
        "toll": True,
        "processing_fee": 2200.0,
    },
)


def _upsert_product(
    session: Session,
    organization_id: str,
    *,
    sku: str,
    name: str,
    item_type: str,
    unit_cost: float,
) -> Product:
    product = session.scalar(
        select(Product).where(
            Product.organization_id == organization_id,
            Product.sku == sku,
        )
    )
    if product is None:
        product = Product(
            organization_id=organization_id,
            sku=sku,
            name=name,
            item_type=item_type,
            base_unit="g",
            unit_cost=unit_cost,
            retail_price=0.0,
            external_product_id=f"SBX-{sku}",
            active=True,
        )
        session.add(product)
        session.flush()
    else:
        product.name = name
        product.item_type = item_type
        product.base_unit = "g"
        product.unit_cost = unit_cost
        product.active = True
    return product


def _upsert_inventory_lot(
    session: Session,
    organization_id: str,
    facility_id: str,
    *,
    product: Product,
    lot_code: str,
    package_id: str,
    location: str,
    quantity: float,
    status: str = "available",
    reference: str,
) -> InventoryLot:
    lot = session.scalar(
        select(InventoryLot).where(
            InventoryLot.facility_id == facility_id,
            InventoryLot.lot_code == lot_code,
        )
    )
    if lot is None:
        lot = InventoryLot(
            organization_id=organization_id,
            facility_id=facility_id,
            product_id=product.id,
            lot_code=lot_code,
            compliance_package_id=package_id,
            external_inventory_id=package_id,
            barcode_value=package_id,
            location_code=location,
            status=status,
            received_at=datetime.now(timezone.utc) - timedelta(days=5),
            notes=f"Synthetic DEV Sandbox extraction inventory · {SANDBOX_EXTRACTION_VERSION}",
        )
        session.add(lot)
        session.flush()
    else:
        lot.product_id = product.id
        lot.compliance_package_id = package_id
        lot.external_inventory_id = package_id
        lot.barcode_value = package_id
        lot.location_code = location
        lot.status = status
        lot.notes = f"Synthetic DEV Sandbox extraction inventory · {SANDBOX_EXTRACTION_VERSION}"

    receipt = session.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.organization_id == organization_id,
            InventoryTransaction.facility_id == facility_id,
            InventoryTransaction.reference == reference,
        )
    )
    if receipt is None:
        session.add(
            InventoryTransaction(
                organization_id=organization_id,
                facility_id=facility_id,
                lot_id=lot.id,
                transaction_type="receipt",
                quantity_delta=quantity,
                unit="g",
                reason="Synthetic DEV Sandbox extraction inventory receipt",
                reference=reference,
                actor=SANDBOX_EXTRACTION_ACTOR,
                occurred_at=datetime.now(timezone.utc) - timedelta(days=5),
            )
        )
    return lot


def _release_status(status: str) -> str:
    if status == "complete":
        return "approved"
    if status == "qa":
        return "pending"
    if status == "hold":
        return "blocked"
    return "blocked"


def _trace_status(status: str) -> str:
    return {
        "complete": "verified",
        "qa": "submitted",
        "hold": "reconciliation_required",
        "active": "validated",
        "queued": "requested",
        "planned": "requested",
    }.get(status, "requested")


def _output_status(status: str) -> str:
    return "released" if status == "complete" else "quarantine" if status in {"hold", "qa"} else "wip"


def _output_lot_status(status: str) -> str:
    return "available" if status == "complete" else "quarantine"


def _coa_status(value: str) -> str:
    return value if value in {"not_submitted", "pending", "passed", "failed"} else "pending"


def _apply_stage_outputs(run: ExtractionRun, workflow_key: str, output_g: float, intermediate_g: float) -> None:
    for field in (
        "extraction_output_g",
        "purge_output_g",
        "crystallization_output_g",
        "sauce_fraction_g",
        "diamond_fraction_g",
        "crude_output_g",
        "winterized_output_g",
        "filtered_output_g",
        "decarbed_output_g",
        "distillate_output_g",
        "wash_output_g",
        "dried_hash_output_g",
        "sift_output_g",
        "rosin_output_g",
    ):
        setattr(run, field, 0.0)

    if workflow_key in {"bho_live_resin", "bho_cured"}:
        run.extraction_output_g = max(output_g, intermediate_g)
        run.purge_output_g = output_g
    elif workflow_key == "ethanol_crude":
        run.crude_output_g = max(output_g, intermediate_g)
        run.winterized_output_g = output_g
        run.filtered_output_g = output_g
    elif workflow_key == "crude_distillate":
        run.distillate_output_g = output_g
    elif workflow_key == "ice_water_hash":
        run.wash_output_g = max(output_g, intermediate_g)
        run.dried_hash_output_g = output_g
    elif workflow_key == "hash_rosin":
        run.rosin_output_g = output_g
    elif workflow_key == "dry_sift":
        run.sift_output_g = output_g
    elif workflow_key == "co2_extract":
        run.crude_output_g = max(output_g, intermediate_g)
        run.filtered_output_g = output_g
    run.final_output_g = output_g


def _ensure_customer(session: Session, organization_id: str) -> Customer:
    name = "Atlantic Wellness Labs"
    customer = session.scalar(
        select(Customer).where(
            Customer.organization_id == organization_id,
            Customer.name == name,
        )
    )
    if customer is None:
        customer = Customer(
            organization_id=organization_id,
            name=name,
            license_or_registration="MC-SBX-71001",
            contact_name="Sandbox Operations",
            contact_email="sandbox-extraction@example.invalid",
            active=True,
        )
        session.add(customer)
        session.flush()
    return customer


def _ensure_costs(
    session: Session,
    organization_id: str,
    facility_id: str,
    run: ExtractionRun,
    total_cogs: float,
) -> None:
    source_id = f"{SANDBOX_EXTRACTION_VERSION}:{run.batch_number}"
    shares = (
        ("material", 0.54),
        ("labor", 0.19),
        ("processing", 0.14),
        ("overhead", 0.09),
        ("packaging", 0.04),
    )
    for category, share in shares:
        existing = session.scalar(
            select(ExtractionCostEvent.id).where(
                ExtractionCostEvent.run_id == run.id,
                ExtractionCostEvent.category == category,
                ExtractionCostEvent.source_id == source_id,
            )
        )
        if existing is None:
            session.add(
                ExtractionCostEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    run_id=run.id,
                    category=category,
                    amount_usd=round(total_cogs * share, 2),
                    source_type="sandbox",
                    source_id=source_id,
                    notes="Synthetic DEV Sandbox COGS component.",
                    actor=SANDBOX_EXTRACTION_ACTOR,
                )
            )


def _ensure_resources(
    session: Session,
    organization_id: str,
    facility_id: str,
    run: ExtractionRun,
    index: int,
) -> None:
    source = f"{SANDBOX_EXTRACTION_VERSION}:{run.batch_number}"
    if session.scalar(
        select(ExtractionResourceEvent.id).where(
            ExtractionResourceEvent.run_id == run.id,
            ExtractionResourceEvent.source_reference == source,
        )
    ) is not None:
        return
    session.add_all(
        [
            ExtractionResourceEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run.id,
                stage_key=run.current_stage_key,
                resource_type="utility",
                resource_name="Extraction suite energy",
                quantity=28.0 + index * 2.5,
                unit="kWh",
                recovered_quantity=None,
                cost_usd=8.0 + index * 1.2,
                source_reference=source,
                notes="Synthetic facility resource usage; no operating setpoints.",
                actor=SANDBOX_EXTRACTION_ACTOR,
            ),
            ExtractionResourceEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run.id,
                stage_key=run.current_stage_key,
                resource_type="consumable",
                resource_name="Process consumable kit",
                quantity=1.0,
                unit="kit",
                recovered_quantity=None,
                cost_usd=12.0 + index,
                source_reference=source,
                notes="Synthetic consumable usage for costing only.",
                actor=SANDBOX_EXTRACTION_ACTOR,
            ),
        ]
    )


def _ensure_qa(
    session: Session,
    organization_id: str,
    facility_id: str,
    run: ExtractionRun,
    output: ExtractionRunOutput | None,
    coa: str,
) -> None:
    if coa == "not_submitted":
        return
    reference = f"SBX-COA-{run.batch_number[-3:]}-{SANDBOX_EXTRACTION_VERSION}"
    if session.scalar(
        select(ExtractionQAEvent.id).where(
            ExtractionQAEvent.run_id == run.id,
            ExtractionQAEvent.coa_reference == reference,
        )
    ) is not None:
        return
    if coa == "passed":
        event_type, result = "release", "passed"
        notes = "Synthetic COA passed; sandbox output released."
    elif coa == "failed":
        event_type, result = "hold", "failed"
        notes = "Synthetic QA exception on hold for review."
    else:
        event_type, result = "sample_submitted", "pending"
        notes = "Synthetic sample submitted; results pending."
    session.add(
        ExtractionQAEvent(
            organization_id=organization_id,
            facility_id=facility_id,
            run_id=run.id,
            output_id=output.id if output else None,
            event_type=event_type,
            result=result,
            coa_reference=reference,
            deviation_code="SBX-QA-002" if coa == "failed" else "",
            notes=notes,
            actor=SANDBOX_EXTRACTION_ACTOR,
        )
    )


def _ensure_traceability(
    session: Session,
    organization_id: str,
    facility_id: str,
    run: ExtractionRun,
    output_lot: InventoryLot | None,
) -> None:
    key = f"sandbox:extraction-realism:{run.batch_number}"
    if session.scalar(
        select(TraceabilityTransaction.id).where(
            TraceabilityTransaction.organization_id == organization_id,
            TraceabilityTransaction.facility_id == facility_id,
            TraceabilityTransaction.idempotency_key == key,
        )
    ) is not None:
        return
    status = _trace_status(run.status)
    now = datetime.now(timezone.utc)
    completed = status in {"verified", "reconciliation_required"}
    submitted = status in {"submitted", "accepted", "verified", "reconciliation_required"}
    session.add(
        TraceabilityTransaction(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            license_number=SANDBOX_EXTRACTION_LICENSE,
            operation_type="package_create" if output_lot else "run_validation",
            entity_type="extraction_run",
            entity_id=run.id,
            idempotency_key=key,
            status=status,
            request_payload_json=json.dumps(
                {"synthetic": True, "dataset": SANDBOX_EXTRACTION_VERSION, "batch": run.batch_number},
                sort_keys=True,
            ),
            response_payload_json=json.dumps(
                {"synthetic": True, "status": status},
                sort_keys=True,
            ),
            external_reference=output_lot.compliance_package_id if output_lot else "",
            attempt_count=1 if submitted else 0,
            reason="Synthetic DEV Sandbox traceability lifecycle.",
            requested_by=SANDBOX_EXTRACTION_ACTOR,
            approved_by=SANDBOX_EXTRACTION_ACTOR if status == "verified" else "",
            requested_at=run.started_at or now,
            submitted_at=now - timedelta(minutes=30) if submitted else None,
            completed_at=now - timedelta(minutes=10) if completed else None,
        )
    )


def ensure_rich_extraction_sandbox(engine: Engine) -> dict[str, Any]:
    """Idempotently make the canonical DEV Sandbox Extraction workspace realistic."""
    tables = set(inspect(engine).get_table_names())
    missing_tables = sorted(_REQUIRED_TABLES - tables)
    if missing_tables:
        return {
            "seeded": False,
            "reason": "schema_unavailable",
            "missing_tables": missing_tables,
            "version": SANDBOX_EXTRACTION_VERSION,
        }

    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        organization = session.scalar(
            select(Organization).where(Organization.slug == SANDBOX_ORGANIZATION_SLUG)
        )
        if organization is None:
            return {"seeded": False, "reason": "sandbox_organization_missing", "version": SANDBOX_EXTRACTION_VERSION}
        facility = session.scalar(
            select(Facility).where(
                Facility.organization_id == organization.id,
                Facility.code == SANDBOX_FACILITY_CODE,
            )
        )
        if facility is None:
            return {"seeded": False, "reason": "sandbox_facility_missing", "version": SANDBOX_EXTRACTION_VERSION}

        organization_id = organization.id
        facility_id = facility.id
        customer = _ensure_customer(session, organization_id)

        input_lots: dict[str, InventoryLot] = {}
        for row in _INPUT_CATALOG:
            product = _upsert_product(
                session,
                organization_id,
                sku=row["sku"],
                name=row["name"],
                item_type=row["item_type"],
                unit_cost=float(row["unit_cost"]),
            )
            lot = _upsert_inventory_lot(
                session,
                organization_id,
                facility_id,
                product=product,
                lot_code=row["lot_code"],
                package_id=row["package"],
                location=row["location"],
                quantity=float(row["quantity"]),
                reference=f"{SANDBOX_EXTRACTION_VERSION}:receipt:{row['key']}",
            )
            input_lots[row["key"]] = lot

        output_products: dict[str, Product] = {}
        for key, (sku, name, unit_cost) in _OUTPUT_CATALOG.items():
            output_products[key] = _upsert_product(
                session,
                organization_id,
                sku=sku,
                name=name,
                item_type="wip",
                unit_cost=unit_cost,
            )

        linked_lots = dict(input_lots)
        for index, spec in enumerate(_RUN_SPECS, start=1):
            workflow = get_extraction_workflow(spec["workflow"])
            input_lot = linked_lots.get(spec["input_key"])
            if input_lot is None:
                raise RuntimeError(f"Sandbox extraction input dependency is missing: {spec['input_key']}")
            input_product = session.get(Product, input_lot.product_id)
            if input_product is None:
                raise RuntimeError("Sandbox extraction input product is missing.")

            run = session.scalar(
                select(ExtractionRun).where(
                    ExtractionRun.organization_id == organization_id,
                    ExtractionRun.facility_id == facility_id,
                    ExtractionRun.batch_number == spec["batch"],
                )
            )
            started_at = None if spec["status"] == "queued" else now - timedelta(hours=int(spec["age_hours"]))
            completed_at = now - timedelta(hours=max(1, int(spec["age_hours"]) - 2)) if spec["status"] == "complete" else None
            if run is None:
                run = ExtractionRun(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    customer_id=customer.id if spec.get("toll") else None,
                    batch_number=spec["batch"],
                    method=workflow.method,
                    workflow_key=workflow.key,
                    current_stage_key=spec["stage"],
                    status=spec["status"],
                    release_status=_release_status(spec["status"]),
                    product_family=spec["output_type"],
                    strain=spec["strain"],
                    toll_processing=bool(spec.get("toll")),
                    compliance_provider="metrc",
                    license_number=SANDBOX_EXTRACTION_LICENSE,
                    operator=spec["operator"],
                    notes=(
                        f"Synthetic DEV Sandbox run · {SANDBOX_EXTRACTION_VERSION}. "
                        "Business-state demo only; no operating recipe or process setpoints are stored."
                    ),
                    run_date=(started_at or now).date(),
                    jurisdiction="MA",
                    facility_license_name=SANDBOX_EXTRACTION_FACILITY,
                    client_name_snapshot=spec["client"],
                    manual_batch_id_internal=spec["batch"],
                    input_material_type=spec["input_type"],
                    manual_input_weight_g=float(spec["input_g"]),
                    intermediate_output_g=float(spec["intermediate_g"]),
                    manual_finished_output_g=float(spec["output_g"]),
                    residual_loss_g=max(0.0, float(spec["input_g"]) - float(spec["output_g"])),
                    machine_line=spec["machine"],
                    metrc_package_id_input=input_lot.compliance_package_id,
                    metrc_manifest_or_transfer_id=f"SBX-XFER-{index:04d}",
                    manual_coa_status=_coa_status(spec["coa"]),
                    manual_qa_hold=spec["status"] == "hold",
                    processing_fee_usd=float(spec.get("processing_fee", 0.0)),
                    estimated_revenue_usd=float(spec["revenue"]),
                    manual_cogs_usd=float(spec["cogs"]),
                    intermediate_product_type=spec["output_type"],
                    final_product_type=spec["output_type"],
                    formulation_used=False,
                    formulation_base_g=0.0,
                    terpene_handling_mode="Native / No Add-Back",
                    terpene_percentage=0.0,
                    terpene_weight_g=0.0,
                    started_at=started_at,
                    completed_at=completed_at,
                    created_by=SANDBOX_EXTRACTION_ACTOR,
                    updated_by=SANDBOX_EXTRACTION_ACTOR,
                )
                session.add(run)
                session.flush()
            else:
                run.customer_id = customer.id if spec.get("toll") else None
                run.method = workflow.method
                run.workflow_key = workflow.key
                run.current_stage_key = spec["stage"]
                run.status = spec["status"]
                run.release_status = _release_status(spec["status"])
                run.product_family = spec["output_type"]
                run.strain = spec["strain"]
                run.toll_processing = bool(spec.get("toll"))
                run.compliance_provider = "metrc"
                run.license_number = SANDBOX_EXTRACTION_LICENSE
                run.operator = spec["operator"]
                run.notes = (
                    f"Synthetic DEV Sandbox run · {SANDBOX_EXTRACTION_VERSION}. "
                    "Business-state demo only; no operating recipe or process setpoints are stored."
                )
                run.run_date = (started_at or now).date()
                run.jurisdiction = "MA"
                run.facility_license_name = SANDBOX_EXTRACTION_FACILITY
                run.client_name_snapshot = spec["client"]
                run.manual_batch_id_internal = spec["batch"]
                run.input_material_type = spec["input_type"]
                run.manual_input_weight_g = float(spec["input_g"])
                run.intermediate_output_g = float(spec["intermediate_g"])
                run.manual_finished_output_g = float(spec["output_g"])
                run.residual_loss_g = max(0.0, float(spec["input_g"]) - float(spec["output_g"]))
                run.machine_line = spec["machine"]
                run.metrc_package_id_input = input_lot.compliance_package_id
                run.metrc_manifest_or_transfer_id = f"SBX-XFER-{index:04d}"
                run.manual_coa_status = _coa_status(spec["coa"])
                run.manual_qa_hold = spec["status"] == "hold"
                run.processing_fee_usd = float(spec.get("processing_fee", 0.0))
                run.estimated_revenue_usd = float(spec["revenue"])
                run.manual_cogs_usd = float(spec["cogs"])
                run.intermediate_product_type = spec["output_type"]
                run.final_product_type = spec["output_type"]
                run.formulation_used = False
                run.formulation_base_g = 0.0
                run.terpene_handling_mode = "Native / No Add-Back"
                run.terpene_percentage = 0.0
                run.terpene_weight_g = 0.0
                run.started_at = started_at
                run.completed_at = completed_at
                run.updated_by = SANDBOX_EXTRACTION_ACTOR

            _apply_stage_outputs(run, workflow.key, float(spec["output_g"]), float(spec["intermediate_g"]))
            run.metrc_input_package_id = input_lot.compliance_package_id
            session.flush()

            run_input = session.scalar(select(ExtractionRunInput).where(ExtractionRunInput.run_id == run.id).limit(1))
            is_queued = spec["status"] == "queued"
            input_cost = float(spec["input_g"]) * float(input_product.unit_cost or 0.0)
            if run_input is None:
                run_input = ExtractionRunInput(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    run_id=run.id,
                    lot_id=input_lot.id,
                    role="primary_input",
                    planned_quantity=float(spec["input_g"]),
                    reserved_quantity=float(spec["input_g"]),
                    consumed_quantity=0.0 if is_queued else float(spec["input_g"]),
                    unit="g",
                    unit_cost_snapshot=float(input_product.unit_cost or 0.0),
                    input_cost_usd=0.0 if is_queued else input_cost,
                    source_reference=SANDBOX_EXTRACTION_VERSION,
                    status="reserved" if is_queued else "consumed",
                    reserved_by=SANDBOX_EXTRACTION_ACTOR,
                )
                session.add(run_input)
            else:
                run_input.lot_id = input_lot.id
                run_input.role = "primary_input"
                run_input.planned_quantity = float(spec["input_g"])
                run_input.reserved_quantity = float(spec["input_g"])
                run_input.consumed_quantity = 0.0 if is_queued else float(spec["input_g"])
                run_input.unit = "g"
                run_input.unit_cost_snapshot = float(input_product.unit_cost or 0.0)
                run_input.input_cost_usd = 0.0 if is_queued else input_cost
                run_input.source_reference = SANDBOX_EXTRACTION_VERSION
                run_input.status = "reserved" if is_queued else "consumed"
                run_input.reserved_by = SANDBOX_EXTRACTION_ACTOR

            consume_reference = f"{SANDBOX_EXTRACTION_VERSION}:consume:{spec['batch']}"
            if not is_queued and session.scalar(
                select(InventoryTransaction.id).where(
                    InventoryTransaction.organization_id == organization_id,
                    InventoryTransaction.facility_id == facility_id,
                    InventoryTransaction.reference == consume_reference,
                )
            ) is None:
                session.add(
                    InventoryTransaction(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        lot_id=input_lot.id,
                        transaction_type="consume",
                        quantity_delta=-float(spec["input_g"]),
                        unit="g",
                        reason=f"Synthetic extraction input · {spec['batch']}",
                        reference=consume_reference,
                        actor=SANDBOX_EXTRACTION_ACTOR,
                        occurred_at=started_at or now,
                    )
                )

            output: ExtractionRunOutput | None = None
            output_lot: InventoryLot | None = None
            if float(spec["output_g"]) > 0:
                output_product = output_products[spec["output_key"]]
                output_package = f"1A406030000SBXOUT{index:03d}"
                output_lot_code = f"OUT-{spec['batch'][-3:]}-{spec['output_key'].upper()[:8]}"
                output_location = "RELEASED-BULK" if spec["status"] == "complete" else "QA-HOLD" if spec["status"] in {"hold", "qa"} else "WIP-EXTRACTION"
                output_lot = _upsert_inventory_lot(
                    session,
                    organization_id,
                    facility_id,
                    product=output_product,
                    lot_code=output_lot_code,
                    package_id=output_package,
                    location=output_location,
                    quantity=float(spec["output_g"]),
                    status=_output_lot_status(spec["status"]),
                    reference=f"{SANDBOX_EXTRACTION_VERSION}:output:{spec['batch']}",
                )
                linked_lots[f"output:{spec['batch']}"] = output_lot
                output = session.scalar(select(ExtractionRunOutput).where(ExtractionRunOutput.run_id == run.id).limit(1))
                if output is None:
                    output = ExtractionRunOutput(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        run_id=run.id,
                        product_id=output_product.id,
                        lot_id=output_lot.id,
                        position=1,
                        output_label=f"{spec['strain']} {spec['output_type']}",
                        quantity=float(spec["output_g"]),
                        unit="g",
                        status=_output_status(spec["status"]),
                        coa_status=_coa_status(spec["coa"]),
                        compliance_package_id=output_package,
                        output_cost_usd=float(spec["cogs"]),
                        notes=f"Synthetic extraction output · {SANDBOX_EXTRACTION_VERSION}",
                        created_by=SANDBOX_EXTRACTION_ACTOR,
                    )
                    session.add(output)
                    session.flush()
                else:
                    output.product_id = output_product.id
                    output.lot_id = output_lot.id
                    output.output_label = f"{spec['strain']} {spec['output_type']}"
                    output.quantity = float(spec["output_g"])
                    output.unit = "g"
                    output.status = _output_status(spec["status"])
                    output.coa_status = _coa_status(spec["coa"])
                    output.compliance_package_id = output_package
                    output.output_cost_usd = float(spec["cogs"])
                    output.notes = f"Synthetic extraction output · {SANDBOX_EXTRACTION_VERSION}"
                run.metrc_package_id_output = output_package
                run.metrc_final_package_id = output_package
            else:
                run.metrc_package_id_output = ""
                run.metrc_final_package_id = ""

            stage_marker = f"{SANDBOX_EXTRACTION_VERSION}:{spec['batch']}:timeline"
            if session.scalar(
                select(ExtractionStageEvent.id).where(
                    ExtractionStageEvent.run_id == run.id,
                    ExtractionStageEvent.notes == stage_marker,
                )
            ) is None:
                session.add(
                    ExtractionStageEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        run_id=run.id,
                        stage_key=workflow.first_stage,
                        event_type="started",
                        input_weight_g=float(spec["input_g"]),
                        output_weight_g=None,
                        loss_weight_g=None,
                        operator=spec["operator"],
                        notes=stage_marker,
                        occurred_at=started_at or now,
                    )
                )
                if float(spec["output_g"]) > 0:
                    measurement_stage = next(
                        (stage for stage in workflow.stages if stage.output_fields),
                        workflow.stages[0],
                    )
                    session.add(
                        ExtractionStageEvent(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            run_id=run.id,
                            stage_key=measurement_stage.key,
                            event_type="measurement",
                            input_weight_g=float(spec["input_g"]),
                            output_weight_g=float(spec["output_g"]),
                            loss_weight_g=max(0.0, min(12.0, float(spec["input_g"]) * 0.01)),
                            loss_reason="Recorded sandbox process variance",
                            stage_output_field=measurement_stage.output_fields[0] if measurement_stage.output_fields else "",
                            metrc_stage_input_id=input_lot.compliance_package_id,
                            metrc_stage_output_id=output_lot.compliance_package_id if output_lot else "",
                            operator=spec["operator"],
                            notes=f"{stage_marker}:measurement",
                            occurred_at=(started_at or now) + timedelta(hours=2),
                        )
                    )

            _ensure_costs(session, organization_id, facility_id, run, float(spec["cogs"]))
            _ensure_resources(session, organization_id, facility_id, run, index)
            _ensure_qa(session, organization_id, facility_id, run, output, _coa_status(spec["coa"]))
            _ensure_traceability(session, organization_id, facility_id, run, output_lot)

            if spec.get("toll"):
                toll = session.scalar(select(ExtractionTollJob).where(ExtractionTollJob.run_id == run.id))
                if toll is None:
                    toll = ExtractionTollJob(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        run_id=run.id,
                        customer_id=customer.id,
                        promised_completion_at=now + timedelta(days=1),
                        processing_fee_usd=float(spec["processing_fee"]),
                        invoice_status="sent",
                        payment_status="pending",
                        external_reference=f"SBX-TOLL-{spec['batch'][-3:]}",
                        notes="Synthetic toll-processing job with SLA and billing state.",
                        jurisdiction="MA",
                        client_license_snapshot=customer.license_or_registration,
                        material_received_at=started_at,
                        input_weight_g=float(spec["input_g"]),
                        expected_output_g=105.0,
                        actual_output_g=float(spec["output_g"]),
                        coa_status=_coa_status(spec["coa"]),
                        job_status="processing",
                        created_by=SANDBOX_EXTRACTION_ACTOR,
                    )
                    session.add(toll)
                else:
                    toll.customer_id = customer.id
                    toll.promised_completion_at = now + timedelta(days=1)
                    toll.processing_fee_usd = float(spec["processing_fee"])
                    toll.invoice_status = "sent"
                    toll.payment_status = "pending"
                    toll.external_reference = f"SBX-TOLL-{spec['batch'][-3:]}"
                    toll.notes = "Synthetic toll-processing job with SLA and billing state."
                    toll.jurisdiction = "MA"
                    toll.client_license_snapshot = customer.license_or_registration
                    toll.material_received_at = started_at
                    toll.input_weight_g = float(spec["input_g"])
                    toll.expected_output_g = 105.0
                    toll.actual_output_g = float(spec["output_g"])
                    toll.coa_status = _coa_status(spec["coa"])
                    toll.job_status = "processing"

        run_count = int(
            session.scalar(
                select(func.count(ExtractionRun.id)).where(
                    ExtractionRun.organization_id == organization_id,
                    ExtractionRun.facility_id == facility_id,
                    ExtractionRun.batch_number.like("SANDBOX-EXT-%"),
                )
            )
            or 0
        )
        lot_count = int(
            session.scalar(
                select(func.count(InventoryLot.id)).where(
                    InventoryLot.organization_id == organization_id,
                    InventoryLot.facility_id == facility_id,
                    InventoryLot.notes.like(f"%{SANDBOX_EXTRACTION_VERSION}%"),
                )
            )
            or 0
        )
        qa_count = int(
            session.scalar(
                select(func.count(ExtractionQAEvent.id)).where(
                    ExtractionQAEvent.organization_id == organization_id,
                    ExtractionQAEvent.facility_id == facility_id,
                    ExtractionQAEvent.coa_reference.like("SBX-COA-%"),
                )
            )
            or 0
        )
        method_count = int(
            session.scalar(
                select(func.count(func.distinct(ExtractionRun.method))).where(
                    ExtractionRun.organization_id == organization_id,
                    ExtractionRun.facility_id == facility_id,
                    ExtractionRun.batch_number.like("SANDBOX-EXT-%"),
                )
            )
            or 0
        )

    return {
        "seeded": True,
        "version": SANDBOX_EXTRACTION_VERSION,
        "organization_id": organization_id,
        "facility_id": facility_id,
        "runs": run_count,
        "inventory_lots": lot_count,
        "qa_events": qa_count,
        "methods": method_count,
        "production_writes_enabled": False,
    }
