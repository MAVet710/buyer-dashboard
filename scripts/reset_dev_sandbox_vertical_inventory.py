from __future__ import annotations

import argparse
import json
import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Facility, InventoryLot, Organization, Product
from modules.coman.vertical_demo_inventory import (
    DEV_FACILITY_CODE,
    DEV_ORGANIZATION_SLUG,
    replace_dev_sandbox_inventory,
)
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService
from modules.extraction import ExtractionRepository
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


def _validate(engine, organization_id: str, facility_id: str, result) -> dict[str, int]:
    final_ids = set(result.final_lots)
    final_product_ids = set(result.final_product_ids)
    wholesale = WholesaleCommerceStorefrontService(engine).wholesale_inventory(organization_id, facility_id)
    eligible = [row for row in wholesale["items"] if row["lot_id"] in final_ids]
    blocked = [row for row in wholesale["blocked_items"] if row["lot_id"] in final_ids]
    if len(eligible) != 100 or blocked:
        raise RuntimeError(f"DEV vertical validation failed wholesale eligibility: eligible={len(eligible)} blocked={len(blocked)}")

    with Session(engine) as session:
        quality_count = sum(session.get(LotQualityEvidence, lot_id) is not None for lot_id in final_ids)
        packaging_count = sum(session.get(ProductPackagingProfile, product_id) is not None for product_id in final_product_ids)
        costed_count = sum(
            bool((product := session.get(Product, product_id)) is not None and float(product.unit_cost or 0.0) > 0)
            for product_id in final_product_ids
        )
    if quality_count != 100 or packaging_count != 100 or costed_count != 100:
        raise RuntimeError(
            "DEV vertical validation failed product detail coverage: "
            f"quality={quality_count} packaging={packaging_count} costed={costed_count}"
        )

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
    if plant_ancestry != 100 or extraction_graphs != 30:
        raise RuntimeError(
            f"DEV vertical validation failed genealogy: plant_ancestry={plant_ancestry} extraction_graphs={extraction_graphs}"
        )

    picker_ids = {row["lot_id"] for row in ExtractionRepository(engine).list_available_lots(organization_id, facility_id)}
    bad_picker = len(final_ids.intersection(picker_ids))
    if bad_picker:
        raise RuntimeError(f"DEV vertical validation failed extraction picker isolation: {bad_picker} finished lot(s) exposed")

    return {
        "finished_lots": len(final_ids),
        "wholesale_eligible": len(eligible),
        "canonical_quality": quality_count,
        "packaging_profiles": packaging_count,
        "positive_cogs": costed_count,
        "plant_ancestry": plant_ancestry,
        "extraction_graphs": extraction_graphs,
        "finished_lots_in_extraction_picker": bad_picker,
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
            "message": "Dry run only. Use --apply to retire current DEV inventory and seed the replacement vertical generation.",
        }

    result = replace_dev_sandbox_inventory(
        engine,
        organization_id,
        facility_id,
        generation=generation,
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
    parser = argparse.ArgumentParser(description="Replace only the DEV Sandbox inventory with the vertical seed-to-sale dataset.")
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
