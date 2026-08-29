from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import (
    AuditEvent,
    Facility,
    InventoryLot,
    InventoryTransaction,
    Organization,
    Product,
)
from modules.product_master.models import ProductMasterProfile

ORGANIZATION_SLUG = "cbk"
FACILITY_CODE = "CBK COOP"
ACTOR = "codex:cowboy-kush-ma-coa-demo-seed"
BULK_IMAGE = "/products/cowboy-kush/prepacked-flower.png"


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
    quantity: float
    name: str = ""
    strain: str = ""
    category: str = "Flower"
    product_format: str = ""
    base_unit: str = "unit"
    bulk: bool = False


# Real Massachusetts COA facts sourced from OpenCOA. Cowboy Kush product identity,
# inventory quantity and pricing remain demo data; source cultivators/producers are
# intentionally not represented as Cowboy Kush.
BATCHES = (
    DemoBatch("CBK-FLR-GMO-35G", "GMO9763700", "NA60723004-004", "1A40A0300007595000009770", "Kaycha MA, LLC", "2026-07-27", "https://opencoa.org/coa/019fb7fc-b04e-71e8-a5d5-a8dec420951e/gmo9763700", 35.01, 31.40, 1.51, 144),
    DemoBatch("CBK-FLR-WEDDING-CAKE-35G", "WECA-F1H4-2026.06.29-B", "NA60717003-021", "1A40A0300008C3D000035718", "Kaycha MA, LLC", "2026-07-22", "https://opencoa.org/coa/019f9446-8169-72c3-98de-354d7f760eb0/weca-f1h4-2026-06-29-b", 31.83, 28.10, 1.81, 120),
    DemoBatch("CBK-FLR-WEDDING-CAKE-35G", "WECA-F5H2-2025.03.31-A", "NA50415005-008", "1A40A0300008C3D000018413", "Kaycha MA, LLC", "2025-04-17", "https://opencoa.org/coa/019f4c1b-b75b-71c1-a3e8-703bd0ac111b/weca-f5h2-2025-03-31-a", 32.93, 29.16, 2.49, 72),
    DemoBatch("CBK-FLR-GARY-PAYTON-35G", "B3.R13.GAPA.06.02.26 (2)", "NA60724002-002", "1A40A0300009E99000199191", "Kaycha MA, LLC", "2026-07-28", "https://opencoa.org/coa/019fb802-939b-72dc-98a4-d80dd04a11ba/b3-r13-gapa-06-02-26-2", 21.23, 19.11, 1.09, 96),
    DemoBatch("CBK-FLR-MOTORBREATH-35G", "MOBR250813-2-6A1", "NA50902001-004", "1A40A030000012E000101613", "Kaycha MA, LLC", "2025-09-04", "https://opencoa.org/coa/019f4e7a-ef4d-7056-819a-4ae4461614fb/mobr250813-2-6a1", 31.44, 27.73, 3.79, 84),
    DemoBatch("CBK-FLR-GELATO-35G", "Gelato-LDF-2025-14.2", "AL51212009-003", "", "Kaycha MA, LLC", "2025-12-16", "https://opencoa.org/coa/019eb5a9-2e78-7188-852b-63667ce36699/gelato-ldf-2025-14-2", 26.43, 23.67, 2.03, 108),
    DemoBatch("CBK-FLR-BLUE-DREAM-35G", "OB5-110625(816)", "NA51229001-003", "1A40A0300010D89000000821", "Kaycha MA, LLC", "2025-12-31", "https://opencoa.org/coa/019f42d8-d3be-70e6-ab42-559844f5ef76/ob5-110625-816", 26.30, 23.32, 0.92, 132),

    # Bulk wholesale flower. Quantities are demo grams; lab facts and COA URLs are real.
    DemoBatch(
        sku="CBK-BULK-GELATO-SUNRISE",
        lot_code="H36-GSR-20251023-A1",
        sample_id="NA51028009-016",
        tracking_number="",
        lab="Kaycha MA, LLC",
        tested_at="2025-11-03",
        coa_url="https://opencoa.org/coa/019f4f5a-f4c8-71bf-ae1d-4d03648c2cca/h36-gsr-20251023-a1",
        thca_percent=26.93,
        tac_percent=24.08,
        terpenes_percent=3.40,
        quantity=4535.92,
        name="Gelato Sunrise Bulk Flower",
        strain="Gelato Sunrise",
        category="Bulk Flower",
        product_format="Bulk whole flower",
        base_unit="g",
        bulk=True,
    ),
    DemoBatch(
        sku="CBK-BULK-PERMANENT-MARKER",
        lot_code="PRM-F3-08062025-CD",
        sample_id="NA50903005-010",
        tracking_number="",
        lab="Kaycha MA, LLC",
        tested_at="2025-09-06",
        coa_url="https://opencoa.org/coa/019f4e80-f041-73e0-8ce5-bfc5c72ae4c2/prm-f3-08062025-cd",
        thca_percent=26.73,
        tac_percent=24.23,
        terpenes_percent=4.20,
        quantity=3628.74,
        name="Permanent Marker Bulk Flower",
        strain="Permanent Marker",
        category="Bulk Flower",
        product_format="Bulk whole flower",
        base_unit="g",
        bulk=True,
    ),
    DemoBatch(
        sku="CBK-BULK-WEDDING-CAKE",
        lot_code="WECA-F1H4-2026.06.29-B-BULK",
        sample_id="NA60717003-021",
        tracking_number="1A40A0300008C3D000035718",
        lab="Kaycha MA, LLC",
        tested_at="2026-07-22",
        coa_url="https://opencoa.org/coa/019f9446-8169-72c3-98de-354d7f760eb0/weca-f1h4-2026-06-29-b",
        thca_percent=31.83,
        tac_percent=28.10,
        terpenes_percent=1.81,
        quantity=2267.96,
        name="Wedding Cake Bulk Flower",
        strain="Wedding Cake",
        category="Bulk Flower",
        product_format="Bulk whole flower",
        base_unit="g",
        bulk=True,
    ),
    DemoBatch(
        sku="CBK-BULK-MOTORBREATH",
        lot_code="MOBR250813-2-6A1-BULK",
        sample_id="NA50902001-004",
        tracking_number="1A40A030000012E000101613",
        lab="Kaycha MA, LLC",
        tested_at="2025-09-04",
        coa_url="https://opencoa.org/coa/019f4e7a-ef4d-7056-819a-4ae4461614fb/mobr250813-2-6a1",
        thca_percent=31.44,
        tac_percent=27.73,
        terpenes_percent=3.79,
        quantity=2721.55,
        name="Motorbreath Bulk Flower",
        strain="Motorbreath",
        category="Bulk Flower",
        product_format="Bulk whole flower",
        base_unit="g",
        bulk=True,
    ),
)


def _ensure_bulk_product(session: Session, organization: Organization, batch: DemoBatch) -> Product:
    product = session.scalar(select(Product).where(Product.organization_id == organization.id, Product.sku == batch.sku))
    if product is None:
        product = Product(
            organization_id=organization.id,
            sku=batch.sku,
            name=batch.name,
            item_type="cannabis",
            base_unit=batch.base_unit,
            unit_cost=0,
            retail_price=0,
            upc="",
            external_product_id=batch.sku,
            active=True,
        )
        session.add(product)
        session.flush()
    else:
        product.name = batch.name
        product.item_type = "cannabis"
        product.base_unit = batch.base_unit
        product.active = True

    profile = session.get(ProductMasterProfile, product.id)
    if profile is None:
        profile = ProductMasterProfile(organization_id=organization.id, product_id=product.id)
        session.add(profile)
    profile.brand = "Cowboy Kush"
    profile.category = batch.category
    profile.subcategory = "Wholesale bulk cannabis"
    profile.strain = batch.strain
    profile.manufacturer = "Cowboy Kush"
    profile.product_format = batch.product_format
    profile.image_url = BULK_IMAGE
    profile.description = f"Cowboy Kush demo wholesale {batch.strain} bulk flower backed by linked Massachusetts OpenCOA lab facts."
    profile.retail_enabled = False
    profile.production_enabled = True
    return product


def _set_opening_balance(session: Session, organization_id: str, facility_id: str, lot: InventoryLot, target: float, unit: str) -> None:
    current = float(session.scalar(select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(InventoryTransaction.lot_id == lot.id)) or 0.0)
    delta = round(float(target) - current, 4)
    if abs(delta) < 0.0001:
        return
    session.add(InventoryTransaction(
        organization_id=organization_id,
        facility_id=facility_id,
        lot_id=lot.id,
        transaction_type="receipt" if delta > 0 else "adjustment",
        quantity_delta=delta,
        unit=unit,
        actor=ACTOR,
        reason="Cowboy Kush OpenCOA demo inventory balance",
    ))


def seed(database_url: str, *, apply: bool) -> dict[str, int]:
    engine = create_engine(database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    stats = {"batches": len(BATCHES), "bulk_batches": sum(batch.bulk for batch in BATCHES), "products_created_or_updated": 0, "lots_created": 0, "lots_updated": 0, "missing_products": 0}
    with Session(engine) as session, session.begin():
        organization = session.scalar(select(Organization).where(Organization.slug == ORGANIZATION_SLUG))
        if not organization or not organization.active:
            raise RuntimeError("Active Cowboy Kush organization was not found.")
        facility = session.scalar(select(Facility).where(Facility.organization_id == organization.id, Facility.code == FACILITY_CODE, Facility.active.is_(True)))
        if not facility:
            raise RuntimeError("Active Cowboy Kush wholesale facility was not found.")

        products = {row.sku: row for row in session.scalars(select(Product).where(Product.organization_id == organization.id))}
        for batch in BATCHES:
            if batch.bulk:
                product = _ensure_bulk_product(session, organization, batch)
                products[batch.sku] = product
                stats["products_created_or_updated"] += 1
            else:
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
                "inventory_type": "bulk" if batch.bulk else "retail_ready",
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
                    location_code="DEMO-BULK-WHOLESALE" if batch.bulk else "DEMO-WHOLESALE",
                    status="available",
                    notes=json.dumps(metadata, sort_keys=True),
                )
                session.add(lot)
                session.flush()
                stats["lots_created"] += 1
            else:
                lot.product_id = product.id
                lot.compliance_package_id = batch.tracking_number
                lot.external_inventory_id = f"OPENCOA:{batch.sample_id}"
                lot.location_code = "DEMO-BULK-WHOLESALE" if batch.bulk else "DEMO-WHOLESALE"
                lot.status = "available"
                lot.notes = json.dumps(metadata, sort_keys=True)
                stats["lots_updated"] += 1

            _set_opening_balance(session, organization.id, facility.id, lot, batch.quantity, batch.base_unit or product.base_unit)
            session.add(AuditEvent(
                organization_id=organization.id,
                facility_id=facility.id,
                entity_type="inventory_lot",
                entity_id=lot.id,
                action="demo_ma_coa_attached",
                actor=ACTOR,
                changes_json=json.dumps({"sku": batch.sku, "lot_code": batch.lot_code, "coa_url": batch.coa_url, "quantity": batch.quantity, "bulk": batch.bulk}, sort_keys=True),
            ))
        if not apply:
            session.rollback()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Cowboy Kush demo inventory with real Massachusetts OpenCOA lab facts, including bulk flower.")
    parser.add_argument("--apply", action="store_true", help="Commit changes; default is a rolled-back dry run.")
    args = parser.parse_args()
    result = seed(os.environ["DL_PROD_DB_URL"], apply=args.apply)
    print(json.dumps({**result, "applied": args.apply}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
