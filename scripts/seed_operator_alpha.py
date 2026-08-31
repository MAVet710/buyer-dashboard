from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine

from modules.coman.demo_data import ensure_coman_demo_dataset
from modules.coman.models import Base
from services.demo_data import build_demo_payload


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///./operator-alpha.db")
    if database_url.startswith("sqlite") and "operator-alpha.db" in database_url:
        Path("operator-alpha.db").unlink(missing_ok=True)
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
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
