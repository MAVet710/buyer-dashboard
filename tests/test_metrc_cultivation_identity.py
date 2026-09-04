from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services import metrc_cultivation_identity as subject
from modules.coman.models import Facility, Organization
from modules.cultivation.models import CultivationRoom
from modules.traceability.models import TraceabilityTransaction
from modules.traceability.object_links import TraceabilityObjectLink


def _service() -> tuple[subject.MetrcCultivationIdentityService, object]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Organization.__table__.create(engine)
    Facility.__table__.create(engine)
    CultivationRoom.__table__.create(engine)
    TraceabilityTransaction.__table__.create(engine)
    TraceabilityObjectLink.__table__.create(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        session.add(Organization(id="org-1", name="Grower", slug="grower"))
        session.add(Facility(id="fac-1", organization_id="org-1", name="Grow", code="GROW", cultivation_enabled=True))
        session.add(CultivationRoom(id="room-1", organization_id="org-1", facility_id="fac-1", room_code="VEG-A", display_name="Veg A", active=True))
        session.add(CultivationRoom(id="room-2", organization_id="org-1", facility_id="fac-1", room_code="FLOWER-A", display_name="Flower A", active=True))
        session.add(CultivationRoom(id="room-off", organization_id="org-1", facility_id="fac-1", room_code="OLD", display_name="Old", active=False))
    return subject.MetrcCultivationIdentityService(engine), engine


def _link(service: subject.MetrcCultivationIdentityService, room_id: str = "room-1", provider_id: str = "11"):
    return service.link_room(
        organization_id="org-1",
        facility_id="fac-1",
        room_id=room_id,
        provider_location_id=provider_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator-runtime",
        user_api_key="user-runtime",
    )


def test_room_link_requires_exact_selected_provider_identity(monkeypatch: pytest.MonkeyPatch):
    service, _engine = _service()
    monkeypatch.setattr(
        subject,
        "fetch_metrc_resource",
        lambda **_kwargs: {"ok": True, "records": [{"provider_id": "12", "name": "Veg A", "source": {"Id": 12, "Name": "Veg A", "IsActive": True}}]},
    )
    with pytest.raises(subject.MetrcCultivationIdentityError, match="different location identity"):
        _link(service, provider_id="11")


def test_inactive_provider_location_cannot_back_active_room(monkeypatch: pytest.MonkeyPatch):
    service, _engine = _service()
    monkeypatch.setattr(
        subject,
        "fetch_metrc_resource",
        lambda **_kwargs: {"ok": True, "records": [{"provider_id": "11", "name": "Veg A", "source": {"Id": 11, "Name": "Veg A", "IsActive": False}}]},
    )
    with pytest.raises(subject.MetrcCultivationIdentityError, match="inactive"):
        _link(service)


def test_local_inactive_room_cannot_be_newly_linked(monkeypatch: pytest.MonkeyPatch):
    service, _engine = _service()
    called = False

    def should_not_read(**_kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(subject, "fetch_metrc_resource", should_not_read)
    with pytest.raises(subject.MetrcCultivationIdentityError, match="Inactive cultivation rooms"):
        _link(service, room_id="room-off")
    assert called is False


def test_verified_room_link_persists_provider_id_and_label(monkeypatch: pytest.MonkeyPatch):
    service, _engine = _service()
    monkeypatch.setattr(
        subject,
        "fetch_metrc_resource",
        lambda **_kwargs: {
            "ok": True,
            "records": [{
                "provider_id": "11",
                "name": "METRC VEG NORTH",
                "last_modified": "2026-09-04T11:00:00Z",
                "source": {"Id": 11, "Name": "METRC VEG NORTH", "IsActive": True},
            }],
        },
    )
    result = _link(service)
    assert result["link"]["entity_type"] == "cultivation_room"
    assert result["link"]["entity_id"] == "room-1"
    assert result["link"]["provider_resource"] == "locations"
    assert result["link"]["provider_id"] == "11"
    assert result["link"]["provider_label"] == "METRC VEG NORTH"
    assert result["readback"]["provider_id"] == "11"


def test_one_metrc_location_cannot_be_bound_to_two_local_rooms(monkeypatch: pytest.MonkeyPatch):
    service, _engine = _service()
    monkeypatch.setattr(
        subject,
        "fetch_metrc_resource",
        lambda **_kwargs: {"ok": True, "records": [{"provider_id": "11", "name": "METRC VEG NORTH", "source": {"Id": 11, "Name": "METRC VEG NORTH", "IsActive": True}}]},
    )
    _link(service, room_id="room-1")
    with pytest.raises(ValueError, match="already linked to a different DoobieLogic object"):
        _link(service, room_id="room-2")


def test_room_linking_is_ma_sandbox_only():
    service, _engine = _service()
    with pytest.raises(subject.MetrcCultivationIdentityError, match="Massachusetts Metrc sandbox"):
        service.link_room(
            organization_id="org-1",
            facility_id="fac-1",
            room_id="room-1",
            provider_location_id="11",
            state="MA",
            environment="production",
            license_number="LIC-1",
            integrator_api_key="integrator-runtime",
            user_api_key="user-runtime",
        )
