from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent, Facility, InventoryLot, Organization, Product
from modules.product_master.models import ProductMasterProfile


ORGANIZATION_SLUG = "cbk"
FACILITY_CODE = "CBK COOP"
ACTOR = "codex:cowboy-kush-wholesale-catalog-seed"
FLOWER_IMAGE = "/products/cowboy-kush/prepacked-flower.png"
PREROLL_IMAGE = "/products/cowboy-kush/pre-roll.png"


@dataclass(frozen=True)
class CatalogItem:
    sku: str
    name: str
    strain: str
    category: str
    product_format: str
    image_url: str


def flower(code: str, strain: str, size: str = "3.5g") -> CatalogItem:
    return CatalogItem(
        sku=f"CBK-FLR-{code}-{size.upper().replace('.', '')}",
        name=f"{strain} Pre-Packed Flower {size}",
        strain=strain,
        category="Flower",
        product_format=f"{size} pre-packed flower pouch",
        image_url=FLOWER_IMAGE,
    )


def preroll(code: str, strain: str) -> CatalogItem:
    return CatalogItem(
        sku=f"CBK-PR-{code}-1G",
        name=f"{strain} Pre-Roll 1g",
        strain=strain,
        category="Pre-Rolls",
        product_format="1g single pre-roll tube",
        image_url=PREROLL_IMAGE,
    )


CATALOG = (
    flower("SIMPLE-JACK", "Simple Jack", "7g"),
    flower("GELATO", "Gelato"),
    flower("CHERRY-PIE", "Cherry Pie"),
    flower("DURBAN-MARGY", "Durban Margy"),
    flower("GAZZURPLE", "Gazzurple"),
    flower("SUMMER-LEMON", "Summer Lemon"),
    flower("BLUE-DREAM", "Blue Dream"),
    flower("GMO", "GMO"),
    flower("WEDDING-CAKE", "Wedding Cake"),
    flower("GARY-PAYTON", "Gary Payton"),
    flower("JEALOUSY", "Jealousy"),
    flower("MOTORBREATH", "Motorbreath"),
    flower("TROP-COOKIES", "Tropicana Cookies"),
    flower("NORTHERN-LIGHTS", "Northern Lights"),
    flower("SOUR-DIESEL", "Sour Diesel"),
    preroll("CHERRY-PIE", "Cherry Pie"),
    preroll("DURBAN-MARGY", "Durban Margy"),
    preroll("GAZZURPLE", "Gazzurple"),
    preroll("SUMMER-LEMON", "Summer Lemon"),
    preroll("SIMPLE-JACK", "Simple Jack"),
    preroll("GELATO", "Gelato"),
    preroll("BLUE-DREAM", "Blue Dream"),
    preroll("GMO", "GMO"),
    preroll("WEDDING-CAKE", "Wedding Cake"),
    preroll("SOUR-DIESEL", "Sour Diesel"),
)


def seed(database_url: str, *, apply: bool) -> dict[str, int]:
    engine = create_engine(database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    stats = {"catalog_items": len(CATALOG), "products_created": 0, "products_updated": 0, "lots_created": 0}
    with Session(engine) as session, session.begin():
        organization = session.scalar(select(Organization).where(Organization.slug == ORGANIZATION_SLUG))
        if not organization or not organization.active:
            raise RuntimeError("Active Cowboy Kush organization was not found.")
        facility = session.scalar(
            select(Facility).where(
                Facility.organization_id == organization.id,
                Facility.code == FACILITY_CODE,
                Facility.active.is_(True),
            )
        )
        if not facility:
            raise RuntimeError("Active Cowboy Kush wholesale facility was not found.")
        if facility.retail_enabled or not facility.production_enabled:
            raise RuntimeError("Cowboy Kush facility is not configured as production-only wholesale.")

        existing = {
            row.sku: row
            for row in session.scalars(select(Product).where(Product.organization_id == organization.id))
        }
        for item in CATALOG:
            product = existing.get(item.sku)
            if product is None:
                product = Product(
                    organization_id=organization.id,
                    sku=item.sku,
                    name=item.name,
                    item_type="finished_good",
                    base_unit="unit",
                    unit_cost=0,
                    retail_price=0,
                    upc="",
                    external_product_id=item.sku,
                    active=True,
                )
                session.add(product)
                session.flush()
                stats["products_created"] += 1
            else:
                product.name = item.name
                product.item_type = "finished_good"
                product.base_unit = "unit"
                product.external_product_id = item.sku
                product.active = True
                stats["products_updated"] += 1

            profile = session.get(ProductMasterProfile, product.id)
            if profile is None:
                profile = ProductMasterProfile(organization_id=organization.id, product_id=product.id)
                session.add(profile)
            profile.brand = "Cowboy Kush"
            profile.category = item.category
            profile.subcategory = "Wholesale retail-ready finished good"
            profile.strain = item.strain
            profile.manufacturer = "Cowboy Kush"
            profile.product_format = item.product_format
            profile.image_url = item.image_url
            profile.description = (
                f"Cowboy Kush {item.product_format}. Wholesale retail-ready finished good. "
                "Potency, compliance identifiers, sellable quantity, and pricing must be supplied from the released batch record."
            )
            profile.retail_enabled = False
            profile.production_enabled = True

            lot_code = f"CATALOG-HOLD-{item.sku}"
            lot = session.scalar(
                select(InventoryLot).where(
                    InventoryLot.facility_id == facility.id,
                    InventoryLot.lot_code == lot_code,
                )
            )
            if lot is None:
                lot = InventoryLot(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    product_id=product.id,
                    lot_code=lot_code,
                    compliance_package_id="",
                    external_inventory_id="",
                    barcode_value=item.sku,
                    location_code="CATALOG-HOLD",
                    status="hold",
                    notes=json.dumps(
                        {
                            "catalog_seed": True,
                            "inventory_quantity": 0,
                            "release_status": "awaiting real batch and compliance data",
                            "source_assets": ["CBK PPF.png" if item.category == "Flower" else "CBK PRJ.png"],
                        },
                        sort_keys=True,
                    ),
                )
                session.add(lot)
                stats["lots_created"] += 1

            session.add(
                AuditEvent(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    entity_type="product",
                    entity_id=product.id,
                    action="wholesale_catalog_seeded",
                    actor=ACTOR,
                    changes_json=json.dumps(
                        {
                            "sku": item.sku,
                            "product_format": item.product_format,
                            "image_url": item.image_url,
                            "sellable_quantity": 0,
                            "status": "hold",
                        },
                        sort_keys=True,
                    ),
                )
            )

        if not apply:
            session.rollback()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Cowboy Kush wholesale retail-ready catalog.")
    parser.add_argument("--apply", action="store_true", help="Commit changes; default is a rolled-back dry run.")
    args = parser.parse_args()
    result = seed(os.environ["DL_PROD_DB_URL"], apply=args.apply)
    print(json.dumps({**result, "applied": args.apply}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
