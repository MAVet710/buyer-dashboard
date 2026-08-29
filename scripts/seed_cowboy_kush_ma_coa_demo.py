from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent, Facility, InventoryLot, Organization, Product

ORGANIZATION_SLUG = "cbk"
FACILITY_CODE = "CBK COOP"
ACTOR = "codex:cowboy-kush-ma-coa-demo-seed"


@dataclass(frozen=True)
class DemoBatch:
    sku: str
    lot_code: str
    sample_id: str
    tracking_number: str
    lab: str
    tested_at: str
    coa_url: str
    thca_percent: float
    tac_percent: float
    terpenes_percent: float
    quantity: int


# Real Massachusetts COA facts sourced from OpenCOA. Cowboy Kush product identity,
# inventory quantity and pricing remain demo data; the source cultivator/producer is
# intentionally not represented as Cowboy Kush.
BATCHES = (
    DemoBatch(
        sku="CBK-FLR-GMO-35G",
        lot_code="GMO9763700",
        sample_id="NA60723004-004",
        tracking_number="1A40A0300007595000009770",
        lab="Kaycha MA, LLC",
        tested_at="2026-07-27",
        coa_url="https://opencoa.org/coa/019fb7fc-b04e-71e8-a5d5-a8dec420951e/gmo9763700",
        thca_percent=35.01,
        tac_percent=31.40,
        terpenes_percent=1.51,
        quantity=144,
    ),
    DemoBatch(
        sku="CBK-FLR-WEDDING-CAKE-35G",
        lot_code="WECA-F1H4-2026.06.29-B",
        sample_id="NA60717003-021",
        tracking_number="1A40A0300008C3D000035718",
        lab="Kaycha MA, LLC",
        tested_at="2026-07-22",
        coa_url="https://opencoa.org/coa/019f9446-8169-72c3-98de-354d7f760eb0/weca-f1h4-2026-06-29-b",
        thca_percent=31.83,
        tac_percent=28.10,
        terpenes_percent=1.81,
        quantity=120,
    ),
    DemoBatch(
        sku="CBK-FLR-WEDDING-CAKE-35G",
        lot_code="WECA-F5H2-2025.03.31-A",
        sample_id="NA50415005-008",
        tracking_number="1A40A0300008C3D000018413",
        lab="Kaycha MA, LLC",
        tested_at="2025-04-17",
        coa_url="https://opencoa.org/coa/019f4c1b-b75b-71c1-a3e8-703bd0ac111b/weca-f5h2-2025-03-31-a",
        thca_percent=32.93,
        tac_percent=29.16,
        terpenes_percent=2.49,
        quantity=72,
    ),
    DemoBatch(
        sku="CBK-FLR-GARY-PAYTON-35G",
        lot_code="B3.R13.GAPA.06.02.26 (2)",
        sample_id="NA60724002-002",
        tracking_number="1A40A0300009E99000199191",
        lab="Kaycha MA, LLC",
        tested_at="2026-07-28",
        coa_url="https://opencoa.org/coa/019fb802-939b-72dc-98a4-d80dd04a11ba/b3-r13-gapa-06-02-26-2",
        thca_percent=21.23,
        tac_percent=19.11,
        terpenes_percent=1.09,
        quantity=96,
    ),
    DemoBatch(
        sku="CBK-FLR-MOTORBREATH-35G",
        lot_code="MOBR250813-2-6A1",
        sample_id="NA50902001-004",
        tracking_number="1A40A030000012E000101613",
        lab="Kaycha MA, LLC",
        tested_at="2025-09-04",
        coa_url="https://opencoa.org/coa/019f4e7a-ef4d-7056-819a-4ae4461614fb/mobr250813-2-6a1",
        thca_percent=31.44,
        tac_percent=27.73,
        terpenes_percent=3.79,
        quantity=84,
    ),
    DemoBatch(
        sku="CBK-FLR-GELATO-35G",
        lot_code="Gelato-LDF-2025-14.2",
        sample_id="AL51212009-003",
        tracking_number="",
        lab="Kaycha MA, LLC",
        tested_at="2025-12-16",
        coa_url="https://opencoa.org/coa/019eb5a9-2e78-7188-852b-63667ce36699/gelato-ldf-2025-14-2",
        thca_percent=26.43,
        tac_percent=23.67,
        terpenes_percent=2.03,
        quantity=108,
    ),
    DemoBatch(
        sku="CBK-FLR-BLUE-DREAM-35G",
        lot_code="OB5-110625(816)",
        sample_id="NA51229001-003",
        tracking_number="1A40A0300010D89000000821",
        lab="Kaycha MA, LLC",
        tested_at="2025-12-31",
        coa_url="https://opencoa.org/coa/019f42d8-d3be-70e6-ab42-559844f5ef76/ob5-110625-816",
        thca_percent=26.30,
        tac_percent=23.32,
        terpenes_percent=0.92,
        quantity=132,
    ),
)


def seed(database_url: str, *, apply: bool) -> dict[str, int]:
    engine = create_engine(database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    stats = {"batches": len(BATCHES), "lots_created": 0, "lots_updated": 0, "missing_products": 0}
    with Session(engine) as session, session.begin():
        organization = session.scalar(select(Organization).where(Organization.slug == ORGANIZATION_SLUG))
        if not organization or not organization.active:
            raise RuntimeError("Active Cowboy Kush organization was not found.")
        facility = session.scalar(select(Facility).where(Facility.organization_id == organization.id, Facility.code == FACILITY_CODE, Facility.active.is_(True)))
        if not facility:
            raise RuntimeError("Active Cowboy Kush wholesale facility was not found.")

        products = {row.sku: row for row in session.scalars(select(Product).where(Product.organization_id == organization.id))}
        for batch in BATCHES:
            product = products.get(batch.sku)
            if product is None:
                stats["missing_products"] += 1
                continue
            lot = session.scalar(select(InventoryLot).where(InventoryLot.facility_id == facility.id, InventoryLot.lot_code == batch.lot_code))
            metadata = {
                "demo_data": True,
                "demo_source": "OpenCOA Massachusetts",
                "source_attribution": "Laboratory facts sourced from the linked OpenCOA record; Cowboy Kush product/inventory context is demo-only.",
                "lab_testing_state": "Passed",
                "coa_reference": batch.sample_id or batch.lot_code,
                "coa_url": batch.coa_url,
                "batch_name": batch.lot_code,
                "sample_id": batch.sample_id,
                "source_tracking_number": batch.tracking_number,
                "laboratory": batch.lab,
                "analysis_date": batch.tested_at,
                "thca_percent": batch.thca_percent,
                "tac_percent": batch.tac_percent,
                "total_terpenes_percent": batch.terpenes_percent,
                "inventory_quantity": batch.quantity,
                "release_status": "released",
            }
            if lot is None:
                lot = InventoryLot(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    product_id=product.id,
                    lot_code=batch.lot_code,
                    compliance_package_id=batch.tracking_number,
                    external_inventory_id=f"OPENCOA:{batch.sample_id}",
                    barcode_value=batch.sample_id or batch.lot_code,
                    location_code="DEMO-WHOLESALE",
                    status="available",
                    notes=json.dumps(metadata, sort_keys=True),
                )
                session.add(lot)
                stats["lots_created"] += 1
            else:
                lot.product_id = product.id
                lot.compliance_package_id = batch.tracking_number
                lot.external_inventory_id = f"OPENCOA:{batch.sample_id}"
                lot.location_code = "DEMO-WHOLESALE"
                lot.status = "available"
                lot.notes = json.dumps(metadata, sort_keys=True)
                stats["lots_updated"] += 1
            session.add(AuditEvent(
                organization_id=organization.id,
                facility_id=facility.id,
                entity_type="inventory_lot",
                entity_id=lot.id or batch.lot_code,
                action="demo_ma_coa_attached",
                actor=ACTOR,
                changes_json=json.dumps({"sku": batch.sku, "lot_code": batch.lot_code, "coa_url": batch.coa_url, "quantity": batch.quantity}, sort_keys=True),
            ))
        if not apply:
            session.rollback()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Cowboy Kush demo inventory with real Massachusetts OpenCOA lab facts.")
    parser.add_argument("--apply", action="store_true", help="Commit changes; default is a rolled-back dry run.")
    args = parser.parse_args()
    result = seed(os.environ["DL_PROD_DB_URL"], apply=args.apply)
    print(json.dumps({**result, "applied": args.apply}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
