from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.services.metrc_cultivation_tags import MetrcCultivationTagMirror
from modules.coman.models import Facility, Organization
from modules.regulatory.metrc_process_models import MetrcTagInventory


def _engine():
    engine=create_engine("sqlite+pysqlite:///:memory:",future=True)
    Organization.__table__.create(engine)
    Facility.__table__.create(engine)
    MetrcTagInventory.__table__.create(engine)
    sessions=sessionmaker(bind=engine,expire_on_commit=False,future=True)
    with sessions.begin() as session:
        session.add(Organization(id="org-1",name="Grower",slug="grower"))
        session.add(Facility(id="fac-1",organization_id="org-1",name="Grow",code="GROW",active=True,cultivation_enabled=True))
        session.add(MetrcTagInventory(organization_id="org-1",facility_id="fac-1",jurisdiction_code="MA",license_number="LIC-1",environment="sandbox",tag_type="plant",label="OLD-AVAILABLE",provider_id="1",status="available"))
        session.add(MetrcTagInventory(organization_id="org-1",facility_id="fac-1",jurisdiction_code="MA",license_number="LIC-1",environment="sandbox",tag_type="plant",label="USED-TAG",provider_id="2",status="used"))
        session.add(MetrcTagInventory(organization_id="org-1",facility_id="fac-1",jurisdiction_code="MA",license_number="LIC-1",environment="sandbox",tag_type="plant",label="BACK-AGAIN",provider_id="3",status="unavailable"))
    return engine


def test_fresh_snapshot_marks_missing_available_tags_unavailable_and_restores_provider_available():
    engine=_engine()
    result=MetrcCultivationTagMirror(engine).replace_available_plant_snapshot(
        organization_id="org-1",facility_id="fac-1",jurisdiction_code="MA",license_number="LIC-1",environment="sandbox",
        records=[{"provider_id":"3","label":"BACK-AGAIN","source":{"Id":3,"Label":"BACK-AGAIN"}},{"provider_id":"4","label":"NEW-TAG","source":{"Id":4,"Label":"NEW-TAG"}}],
    )
    assert result["available_count"]==2
    with Session(engine) as session:
        rows={row.label:row for row in session.query(MetrcTagInventory).all()}
        assert rows["OLD-AVAILABLE"].status=="unavailable"
        assert rows["BACK-AGAIN"].status=="available"
        assert rows["NEW-TAG"].status=="available"
        assert rows["USED-TAG"].status=="used"


def test_fresh_snapshot_never_resurrects_used_tag_even_if_provider_lists_it_available():
    engine=_engine()
    MetrcCultivationTagMirror(engine).replace_available_plant_snapshot(
        organization_id="org-1",facility_id="fac-1",jurisdiction_code="MA",license_number="LIC-1",environment="sandbox",
        records=[{"provider_id":"2","label":"USED-TAG","source":{"Id":2,"Label":"USED-TAG"}}],
    )
    with Session(engine) as session:
        row=session.query(MetrcTagInventory).filter_by(label="USED-TAG").one()
        assert row.status=="used"
