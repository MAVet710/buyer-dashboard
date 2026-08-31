from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from modules.coman.demo_data import ensure_coman_demo_dataset
from modules.coman.models import Facility, Product
from services.demo_data import build_demo_payload

# Tables outside the Co-Man model module are deliberate sentinels: if any are
# absent, the alpha database was built with partial SQLAlchemy metadata instead
# of the production Alembic migration chain.
_REQUIRED_MIGRATED_TABLES = {
    "alembic_version",
    "coman_organizations",
    "coman_facilities",
    "coman_products",
    "coman_inventory_lots",
    "integration_configurations",
    "action_proposals",
    "traceability_transactions",
    "material_transformations",
    "lot_quality_evidence",
}

_ZERO_TRAINING_PRODUCTS = (
    {
        "sku": "ZT-BD-HARVEST",
        "name": "Blue Dream Harvest Material",
        "item_type": "cannabis",
        "base_unit": "g",
        "unit_cost": 1.25,
        "retail_price": 0.0,
    },
    {
        "sku": "ZT-BD-EXTRACT",
        "name": "Blue Dream Extract",
        "item_type": "wip",
        "base_unit": "g",
        "unit_cost": 8.0,
        "retail_price": 0.0,
    },
    {
        "sku": "ZT-BD-VAPE-1G",
        "name": "Blue Dream Vape 1g",
        "item_type": "finished_good",
        "base_unit": "unit",
        "unit_cost": 11.0,
        "retail_price": 32.0,
    },
)


def _verify_migrated_schema(engine) -> None:
    tables = set(inspect(engine).get_table_names())
    missing = sorted(_REQUIRED_MIGRATED_TABLES - tables)
    if missing:
        raise RuntimeError(
            "Operator alpha requires an Alembic-migrated application database. "
            f"Missing tables: {', '.join(missing)}. Run `alembic upgrade head` before seeding."
        )


def _ensure_zero_training_prerequisites(engine, organization_id: str, facility_id: str) -> str:
    """Keep catalog/facility setup outside the operator journey itself.

    The acceptance test is testing daily execution, not whether a brand-new tenant
    can configure its licenses and Product Master.  It therefore starts with a
    realistic vertically licensed source facility, a second destination license,
    and three canonical Blue Dream product-master records already available.
    """

    with Session(engine) as session, session.begin():
        source = session.get(Facility, facility_id)
        if source is None or source.organization_id != organization_id:
            raise RuntimeError("Seeded operator-alpha source facility was not found.")
        source.name = "Zero Training Vertical Facility"
        source.license_number = "MC281000"
        source.license_type = "Cultivator / Product Manufacturer"
        source.retail_enabled = True
        source.production_enabled = True
        source.cultivation_enabled = True
        source.commercial_enabled = True

        destination = session.scalar(
            select(Facility).where(
                Facility.organization_id == organization_id,
                Facility.code == "ZT-DEST",
            )
        )
        if destination is None:
            destination = Facility(
                organization_id=organization_id,
                name="Zero Training Destination Dispensary",
                code="ZT-DEST",
                timezone_name="America/New_York",
                license_number="MR281999",
                license_type="Marijuana Retailer",
                retail_enabled=True,
                production_enabled=False,
                cultivation_enabled=False,
                commercial_enabled=True,
                active=True,
            )
            session.add(destination)
            session.flush()
        else:
            destination.name = "Zero Training Destination Dispensary"
            destination.license_number = "MR281999"
            destination.license_type = "Marijuana Retailer"
            destination.retail_enabled = True
            destination.production_enabled = False
            destination.cultivation_enabled = False
            destination.commercial_enabled = True
            destination.active = True

        existing = {
            row.sku: row
            for row in session.scalars(
                select(Product).where(Product.organization_id == organization_id)
            )
        }
        for spec in _ZERO_TRAINING_PRODUCTS:
            product = existing.get(spec["sku"])
            if product is None:
                session.add(Product(organization_id=organization_id, active=True, **spec))
            else:
                for key, value in spec.items():
                    setattr(product, key, value)
                product.active = True

        return destination.id


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///./operator-alpha.db")
    engine = create_engine(database_url, future=True)
    _verify_migrated_schema(engine)
    seeded = ensure_coman_demo_dataset(
        state={},
        actor="operator-alpha-browser",
        payload=build_demo_payload(date(2026, 8, 31), scale="small"),
        engine=engine,
        force=True,
    )
    destination_facility_id = _ensure_zero_training_prerequisites(
        engine,
        seeded["organization_id"],
        seeded["facility_id"],
    )
    print(f"ALPHA_ORGANIZATION_ID={seeded['organization_id']}")
    print(f"ALPHA_FACILITY_ID={seeded['facility_id']}")
    print(f"ALPHA_DESTINATION_FACILITY_ID={destination_facility_id}")


if __name__ == "__main__":
    main()
