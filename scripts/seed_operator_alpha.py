from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from modules.coman.demo_data import ensure_coman_demo_dataset
from modules.coman.models import Facility
from modules.cultivation.service import CultivationService
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
    "coa_documents",
    "coa_analyte_results",
}


def _verify_migrated_schema(engine) -> None:
    tables = set(inspect(engine).get_table_names())
    missing = sorted(_REQUIRED_MIGRATED_TABLES - tables)
    if missing:
        raise RuntimeError(
            "Operator alpha requires an Alembic-migrated application database. "
            f"Missing tables: {', '.join(missing)}. Run `alembic upgrade head` before seeding."
        )


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
    # This integrated acceptance facility deliberately exercises every operating
    # context. Capability isolation is covered separately; the browser alpha
    # needs all three contexts to be reachable against one stable facility.
    with Session(engine) as session, session.begin():
        facility = session.get(Facility, seeded["facility_id"])
        if facility is None:
            raise RuntimeError("Operator alpha facility was not created by the demo seed.")
        facility.retail_enabled = True
        facility.production_enabled = True
        facility.cultivation_enabled = True
        facility.commercial_enabled = True

    # The real-browser cultivation journey needs physical plants, not only a
    # cultivation capability flag. Seed them through the same durable service
    # operators use so the alpha fixture also exercises room/plant persistence.
    cultivation = CultivationService(engine)
    cultivation.upsert_room(
        seeded["organization_id"],
        seeded["facility_id"],
        room_code="OA-VEG",
        display_name="Operator Alpha Vegetative",
        phase="vegetative",
        plant_capacity=24,
        square_feet=180,
        target_cycle_days=21,
        active=True,
    )
    cultivation.upsert_room(
        seeded["organization_id"],
        seeded["facility_id"],
        room_code="OA-FLOWER",
        display_name="Operator Alpha Flower",
        phase="flowering",
        plant_capacity=24,
        square_feet=260,
        target_cycle_days=63,
        active=True,
    )
    for plant_tag, strain_name in (
        ("OA-PLANT-BROWSER-0001", "Operator Kush"),
        ("OA-PLANT-BROWSER-0002", "Operator Haze"),
    ):
        cultivation.create_plant(
            seeded["organization_id"],
            seeded["facility_id"],
            plant_tag=plant_tag,
            strain_name=strain_name,
            phase="vegetative",
            room_code="OA-VEG",
            actor="operator-alpha-browser",
            planted_at=date(2026, 8, 1),
            estimated_harvest_date=date(2026, 11, 1),
            notes="Integrated real-browser cultivation acceptance fixture",
        )

    print(f"ALPHA_ORGANIZATION_ID={seeded['organization_id']}")
    print(f"ALPHA_FACILITY_ID={seeded['facility_id']}")


if __name__ == "__main__":
    main()
