from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, inspect

from modules.coman.demo_data import ensure_coman_demo_dataset
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
    "inventory_lot_quality_evidence",
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
    print(f"ALPHA_ORGANIZATION_ID={seeded['organization_id']}")
    print(f"ALPHA_FACILITY_ID={seeded['facility_id']}")


if __name__ == "__main__":
    main()
