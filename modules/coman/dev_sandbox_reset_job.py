from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import (
    CommercialOrder,
    CommercialOrderLine,
    Facility,
    InventoryLot,
    InventoryTransaction,
    OrderLotAllocation,
    Organization,
    Product,
)
from modules.coman.vertical_demo_inventory import DEV_FACILITY_CODE, DEV_ORGANIZATION_SLUG
from modules.coman.vertical_demo_inventory_release import (
    EXPECTED_ACTIVE_PLANTS,
    EXPECTED_EXTRACT_SKUS,
    EXPECTED_FINISHED_SKUS,
    EXPECTED_MOCK_FINISHED_COAS,
    replace_scaled_vertical_dev_inventory,
)
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService
from modules.cultivation.service import ACTIVE_PLANT_PHASES, CultivationService
from modules.extraction import ExtractionRepository
from modules.inventory_availability.service import InventoryAvailabilityService
from modules.inventory_quality import LotQualityEvidence
from modules.material_lineage.service import MaterialLineageService
from modules.product_master import ProductPackagingProfile


def _engine(database_url: str):
    return create_engine(database_url.replace("postgresql://", "postgresql+psycopg://", 1), future=True)


def _scope(engine):
    with Session(engine) as session:
        organization = session.scalar(select(Organization).where(Organization.slug == DEV_ORGANIZATION_SLUG))
        if organization is None or not organization.active:
            raise RuntimeError("Active DEV Sandbox organization was not found.")
        facility = session.scalar(
            select(Facility).where(
                Facility.organization_id == organization.id,
                Facility.code == DEV_FACILITY_CODE,
                Facility.active.is_(True),
            )
        )
        if facility is None:
            raise RuntimeError("Active DEV Sandbox SANDBOX facility was not found.")
        return organization.id, facility.id


def _current_inventory(engine, organization_id: str, facility_id: str) -> dict[str, int]:
    with Session(engine) as session:
        lots = list(
            session.scalars(
                select(InventoryLot).where(
                    InventoryLot.organization_id == organization_id,
                    InventoryLot.facility_id == facility_id,
                )
            )
        )
        active_products = list(
            session.scalars(
                select(Product).where(
                    Product.organization_id == organization_id,
                    Product.active.is_(True),
                )
            )
        )
    return {
        "lots": len(lots),
        "released_or_available_lots": sum(str(row.status or "").casefold() in {"available", "released"} for row in lots),
        "active_products": len(active_products),
    }


def _validate(engine, organization_id: str, facility_id: str, result) -> dict[str, object]:
    final_ids = set(result.final_lots)
    final_product_ids = set(result.final_product_ids)
    if len(final_ids) != EXPECTED_FINISHED_SKUS or len(final_product_ids) != EXPECTED_FINISHED_SKUS:
        raise RuntimeError(
            f"DEV vertical validation expected {EXPECTED_FINISHED_SKUS} unique finished lots/products; "
            f"got lots={len(final_ids)} products={len(final_product_ids)}"
        )

    wholesale = WholesaleCommerceStorefrontService(engine).wholesale_inventory(organization_id, facility_id)
    eligible = [row for row in wholesale["items"] if row["lot_id"] in final_ids]
    blocked = [row for row in wholesale["blocked_items"] if row["lot_id"] in final_ids]
    if len(eligible) != EXPECTED_FINISHED_SKUS or blocked:
        raise RuntimeError(
            f"DEV vertical validation failed wholesale eligibility: eligible={len(eligible)} blocked={len(blocked)}"
        )
    wholesale_by_lot = {row["lot_id"]: row for row in eligible}

    with Session(engine) as session:
        quality_rows = [session.get(LotQualityEvidence, lot_id) for lot_id in final_ids]
        quality_count = sum(row is not None for row in quality_rows)
        packaging_count = sum(session.get(ProductPackagingProfile, product_id) is not None for product_id in final_product_ids)
        costed_count = sum(
            bool((product := session.get(Product, product_id)) is not None and float(product.unit_cost or 0.0) > 0)
            for product_id in final_product_ids
        )
        mock_rows = [
            row for row in quality_rows
            if row is not None and row.evidence_source == "mock_finished_lab"
        ]
        po_rows = list(
            session.scalars(
                select(CommercialOrder).where(
                    CommercialOrder.organization_id == organization_id,
                    CommercialOrder.facility_id == facility_id,
                    CommercialOrder.order_number.like(f"DEVV-PO-{result.generation}-%"),
                )
            )
        )
        so_rows = list(
            session.scalars(
                select(CommercialOrder).where(
                    CommercialOrder.organization_id == organization_id,
                    CommercialOrder.facility_id == facility_id,
                    CommercialOrder.order_number.like(f"DEVV-SO-{result.generation}-%"),
                )
            )
        )
        po_ids = [row.id for row in po_rows]
        so_ids = [row.id for row in so_rows]
        po_line_count = len(list(session.scalars(select(CommercialOrderLine).where(CommercialOrderLine.commercial_order_id.in_(po_ids or ["__none__"])))))
        so_line_count = len(list(session.scalars(select(CommercialOrderLine).where(CommercialOrderLine.commercial_order_id.in_(so_ids or ["__none__"])))))
        allocations = list(
            session.scalars(
                select(OrderLotAllocation).where(
                    OrderLotAllocation.organization_id == organization_id,
                    OrderLotAllocation.facility_id == facility_id,
                    OrderLotAllocation.commercial_order_id.in_(so_ids or ["__none__"]),
                )
            )
        )
        shipment_count = len(
            list(
                session.scalars(
                    select(InventoryTransaction).where(
                        InventoryTransaction.organization_id == organization_id,
                        InventoryTransaction.facility_id == facility_id,
                        InventoryTransaction.commercial_order_id.in_(so_ids or ["__none__"]),
                        InventoryTransaction.transaction_type == "shipment",
                    )
                )
            )
        )

    if quality_count != EXPECTED_FINISHED_SKUS or packaging_count != EXPECTED_FINISHED_SKUS or costed_count != EXPECTED_FINISHED_SKUS:
        raise RuntimeError(
            "DEV vertical validation failed product detail coverage: "
            f"quality={quality_count} packaging={packaging_count} costed={costed_count}"
        )
    if len(mock_rows) != EXPECTED_MOCK_FINISHED_COAS:
        raise RuntimeError(f"Expected {EXPECTED_MOCK_FINISHED_COAS} explicit finished mock COAs, got {len(mock_rows)}")
    for evidence in mock_rows:
        wholesale_row = wholesale_by_lot.get(evidence.lot_id)
        if wholesale_row is None:
            raise RuntimeError(f"Mock-COA lot {evidence.lot_id} is missing from Wholesale.")
        if wholesale_row["coa_reference"] != evidence.coa_reference or wholesale_row["coa_url"] != evidence.coa_url:
            raise RuntimeError(f"Mock COA did not propagate intact to Wholesale for lot {evidence.lot_id}.")

    plants = CultivationService(engine).list_plants(organization_id, facility_id)
    active_phase_counts = Counter(row.phase for row in plants if row.phase in ACTIVE_PLANT_PHASES)
    if sum(active_phase_counts.values()) != EXPECTED_ACTIVE_PLANTS:
        raise RuntimeError(f"Expected {EXPECTED_ACTIVE_PLANTS} active plants, got {dict(active_phase_counts)}")
    if set(active_phase_counts) != {"clone", "seedling", "vegetative", "flowering"} or any(active_phase_counts[phase] != 20 for phase in active_phase_counts):
        raise RuntimeError(f"DEV active plant stages are not evenly populated: {dict(active_phase_counts)}")

    lineage = MaterialLineageService(engine)
    plant_ancestry = 0
    extraction_graphs = 0
    extract_ids = set(result.extract_final_lots)
    for lot_id in final_ids:
        graph = lineage.lot_graph(organization_id=organization_id, facility_id=facility_id, lot_id=lot_id)
        if any(node["type"] == "plant" for node in graph["nodes"]):
            plant_ancestry += 1
        if lot_id in extract_ids and any(node.get("transformation_type") == "extraction_run" for node in graph["nodes"]):
            extraction_graphs += 1
    if plant_ancestry != EXPECTED_FINISHED_SKUS or extraction_graphs != EXPECTED_EXTRACT_SKUS:
        raise RuntimeError(
            f"DEV vertical validation failed genealogy: plant_ancestry={plant_ancestry} extraction_graphs={extraction_graphs}"
        )

    picker_ids = {row["lot_id"] for row in ExtractionRepository(engine).list_available_lots(organization_id, facility_id)}
    bad_picker = len(final_ids.intersection(picker_ids))
    if bad_picker:
        raise RuntimeError(f"DEV vertical validation failed extraction picker isolation: {bad_picker} finished lot(s) exposed")

    po_statuses = Counter(row.status for row in po_rows)
    so_statuses = Counter(row.status for row in so_rows)
    if len(po_rows) != 6 or po_line_count != 12 or po_statuses != Counter({"draft": 3, "confirmed": 3}):
        raise RuntimeError(f"DEV PO scenario mismatch: orders={len(po_rows)} lines={po_line_count} statuses={dict(po_statuses)}")
    expected_so_statuses = Counter({"draft": 3, "confirmed": 3, "allocated": 3, "partially_fulfilled": 2, "fulfilled": 1})
    if len(so_rows) != 12 or so_line_count != 60 or so_statuses != expected_so_statuses:
        raise RuntimeError(f"DEV SO scenario mismatch: orders={len(so_rows)} lines={so_line_count} statuses={dict(so_statuses)}")
    if len(allocations) != 30 or shipment_count != 9:
        raise RuntimeError(f"DEV Wholesale commitment/fulfillment mismatch: allocations={len(allocations)} shipments={shipment_count}")

    with Session(engine) as availability_session:
        availability = InventoryAvailabilityService.build(availability_session, organization_id, facility_id)
    wholesale_reserved_lots = sum(float(row.get("wholesale_reserved") or 0) > 0 for row in availability["by_lot"].values())
    if wholesale_reserved_lots <= 0:
        raise RuntimeError("DEV SO allocations did not affect organization-wide inventory availability.")

    return {
        "finished_lots": len(final_ids),
        "wholesale_eligible": len(eligible),
        "canonical_quality": quality_count,
        "mock_finished_coas": len(mock_rows),
        "packaging_profiles": packaging_count,
        "positive_cogs": costed_count,
        "active_plants": sum(active_phase_counts.values()),
        "active_plant_phases": dict(active_phase_counts),
        "plant_ancestry": plant_ancestry,
        "extraction_graphs": extraction_graphs,
        "finished_lots_in_extraction_picker": bad_picker,
        "purchase_orders": len(po_rows),
        "purchase_order_statuses": dict(po_statuses),
        "sales_orders": len(so_rows),
        "sales_order_statuses": dict(so_statuses),
        "sales_order_allocations": len(allocations),
        "sales_order_shipments": shipment_count,
        "lots_with_wholesale_reservations": wholesale_reserved_lots,
    }


def run(database_url: str, *, apply: bool, generation: str | None = None) -> dict[str, object]:
    engine = _engine(database_url)
    organization_id, facility_id = _scope(engine)
    before = _current_inventory(engine, organization_id, facility_id)
    if not apply:
        return {
            "applied": False,
            "organization_slug": DEV_ORGANIZATION_SLUG,
            "facility_code": DEV_FACILITY_CODE,
            "before": before,
            "message": "Dry run only. Use --apply to retire current DEV inventory and seed the scaled vertical generation.",
        }

    generation_code = generation or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    result = replace_scaled_vertical_dev_inventory(
        engine,
        organization_id,
        facility_id,
        generation=generation_code,
        actor="cloud-run:dev-vertical-inventory-reset",
    )
    validation = _validate(engine, organization_id, facility_id, result)
    return {
        "applied": True,
        "organization_slug": DEV_ORGANIZATION_SLUG,
        "facility_code": DEV_FACILITY_CODE,
        "before": before,
        "seed": result.summary(),
        "validation": validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replace only the DEV Sandbox inventory with the scaled vertical seed-to-sale dataset.")
    parser.add_argument("--apply", action="store_true", help="Apply the destructive DEV inventory replacement. Default is a read-only dry run.")
    parser.add_argument("--generation", default="", help="Optional generation suffix for deterministic test runs.")
    args = parser.parse_args()
    output = run(
        os.environ["DL_PROD_DB_URL"],
        apply=args.apply,
        generation=args.generation or None,
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
