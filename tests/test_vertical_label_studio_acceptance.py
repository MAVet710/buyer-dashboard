from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.label_studio import LabelInventoryService
from modules.coman.models import Base, Facility, Organization
from modules.coman.vertical_demo_inventory import seed_vertical_dev_inventory


def test_all_100_vertical_finished_lots_are_label_studio_ready():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="DEV Sandbox", slug="dev-sandbox")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="DEV Sandbox Vertical Facility",
            code="SANDBOX",
            cultivation_enabled=True,
            production_enabled=True,
            retail_enabled=True,
            commercial_enabled=True,
        )
        session.add(facility)
        session.flush()
        organization_id, facility_id = organization.id, facility.id

    seeded = seed_vertical_dev_inventory(
        engine,
        organization_id,
        facility_id,
        generation="LABEL100",
        actor="label-100-acceptance",
    )
    assert len(seeded.final_lots) == 100

    sources = LabelInventoryService(engine).list_sources(organization_id, facility_id)
    by_lot = {row["lot_id"]: row for row in sources}
    finished = [by_lot[lot_id] for lot_id in seeded.final_lots]

    assert len(finished) == 100
    assert all(row["label"]["net_contents"] for row in finished)
    assert all(row["label"]["package_id"] for row in finished)
    assert all(row["label"]["license_number"] == "DEV-SANDBOX-VERTICAL" for row in finished)
    assert all(row["label"]["brand"] == "DoobieLogic DEV Vertical" for row in finished)
    assert all(row["label"]["strain"] for row in finished)
    assert all(row["label"]["lab_testing_state"] == "Passed" for row in finished)
    assert all(row["label"]["coa_reference"] for row in finished)
    assert all(row["label"]["potency"] for row in finished)
