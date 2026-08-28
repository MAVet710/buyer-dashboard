from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.cultivation_reconciliation import CultivationMetrcReconciliationService
from modules.coman.models import Base, Facility, Organization
from modules.cultivation.models import CultivationPlant


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Organization(id="org-1", name="Cultivator", slug="cultivator"))
        session.add(Facility(
            id="fac-1",
            organization_id="org-1",
            name="Cultivation",
            code="CULT",
            cultivation_enabled=True,
        ))
        session.add_all([
            CultivationPlant(
                id="plant-v",
                organization_id="org-1",
                facility_id="fac-1",
                plant_tag="1A4FF0100000022000000001",
                strain_name="GMO",
                phase="vegetative",
                room_code="Veg 1",
            ),
            CultivationPlant(
                id="plant-f",
                organization_id="org-1",
                facility_id="fac-1",
                plant_tag="1A4FF0100000022000000002",
                strain_name="Gastro Pop",
                phase="flowering",
                room_code="Flower 2",
            ),
            CultivationPlant(
                id="plant-clone",
                organization_id="org-1",
                facility_id="fac-1",
                plant_tag="CLONE-1",
                strain_name="GMO",
                phase="clone",
                room_code="Clone",
            ),
            CultivationPlant(
                id="plant-retired",
                organization_id="org-1",
                facility_id="fac-1",
                plant_tag="OLD-1",
                strain_name="GMO",
                phase="harvested",
                room_code="Flower 1",
            ),
        ])
        session.commit()
    return engine


def _record(tag: str, strain: str, room: str):
    return {
        "label": tag,
        "name": strain,
        "source": {"Label": tag, "StrainName": strain, "LocationName": room},
    }


def test_cultivation_reconciliation_matches_tagged_active_plants_only():
    report = CultivationMetrcReconciliationService(_engine()).reconcile(
        "org-1",
        "fac-1",
        jurisdiction_code="MA",
        license_number="MC281281",
        environment="sandbox",
        vegetative_records=[_record("1A4FF0100000022000000001", "GMO", "Veg 1")],
        flowering_records=[_record("1A4FF0100000022000000002", "Gastro Pop", "Flower 2")],
    )

    assert report["summary"]["status"] == "clean"
    assert report["summary"]["matched_plant_count"] == 2
    assert report["summary"]["local_immature_unreconciled_count"] == 1
    assert report["summary"]["local_retired_count"] == 1
    assert report["discrepancies"] == []


def test_cultivation_reconciliation_detects_phase_room_and_missing_tags():
    report = CultivationMetrcReconciliationService(_engine()).reconcile(
        "org-1",
        "fac-1",
        jurisdiction_code="MA",
        license_number="MC281281",
        environment="production",
        vegetative_records=[
            _record("1A4FF0100000022000000002", "Gastro Pop", "Veg 9"),
            _record("1A4FF0100000022000000999", "GMO", "Veg 1"),
        ],
        flowering_records=[],
    )

    codes = {row["code"] for row in report["discrepancies"]}
    assert "missing_in_metrc" in codes
    assert "missing_in_doobielogic" in codes
    assert "phase_mismatch" in codes
    assert "room_mismatch" in codes
    assert report["summary"]["high_count"] >= 3
