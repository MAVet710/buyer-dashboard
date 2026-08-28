from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext
from backend.app.routers import inventory_reconciliation, plants
from backend.app.services import regulatory_metrc
from backend.app.services.metrc_context import MetrcContext
from modules.coman.models import Base, Facility, Organization


def _engine(*, production: bool = False, cultivation: bool = False):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Organization(id="org-1", name="Operator", slug="operator"))
        session.add(Facility(
            id="fac-1",
            organization_id="org-1",
            name="Licensed Facility",
            code="FAC",
            production_enabled=production,
            cultivation_enabled=cultivation,
        ))
        session.commit()
    return engine


def _context() -> RequestContext:
    return RequestContext("user-1", "org-1", "fac-1", "operator")


def _metrc(*, environment: str = "sandbox", trusted: bool = True, configured: bool = True) -> MetrcContext:
    return MetrcContext(
        configured=configured,
        state="MA" if configured else "",
        license_number="LIC-281281" if configured else "",
        user_api_key="user-key" if configured else "",
        integrator_api_key="integrator-key" if configured else "",
        status="connected" if configured else "not_configured",
        environment=environment,
        trusted_mapping=trusted if configured else False,
        message="ready" if configured else "Configure Metrc for this facility.",
        row=object() if configured else None,
    )


def _resource(resource: str, records: list[dict] | None = None):
    return {
        "ok": True,
        "resource": resource,
        "capability": resource,
        "records": records or [],
        "page_count": 1,
        "truncated": False,
        "read_plan": {"evidence": {"source_url": "https://api-ma.metrc.com/Documentation"}},
    }


def test_trusted_regulatory_context_keeps_cultivation_and_manufacturing_licenses_separate(monkeypatch):
    engine = _engine(cultivation=True)
    monkeypatch.setattr(regulatory_metrc, "resolve_metrc_context", lambda *_args, **_kwargs: (None, _metrc()))

    cultivation = regulatory_metrc.resolve_trusted_regulatory_metrc(
        context=_context(), engine=engine, settings=object(), facility_capability="cultivation"
    )
    assert cultivation.environment == "sandbox"

    with pytest.raises(HTTPException) as exc:
        regulatory_metrc.resolve_trusted_regulatory_metrc(
            context=_context(), engine=engine, settings=object(), facility_capability="production"
        )
    assert exc.value.status_code == 403


def test_trusted_regulatory_context_fails_closed_without_verified_mapping(monkeypatch):
    engine = _engine(production=True)
    monkeypatch.setattr(
        regulatory_metrc,
        "resolve_metrc_context",
        lambda *_args, **_kwargs: (None, _metrc(trusted=False)),
    )
    with pytest.raises(HTTPException) as exc:
        regulatory_metrc.resolve_trusted_regulatory_metrc(
            context=_context(), engine=engine, settings=object(), facility_capability="production"
        )
    assert exc.value.status_code == 409
    assert "exact Metrc facility" in str(exc.value.detail)


def test_manufacturing_snapshot_propagates_saved_environment(monkeypatch):
    engine = _engine(production=True)
    captured: list[dict] = []
    monkeypatch.setattr(
        inventory_reconciliation,
        "resolve_trusted_regulatory_metrc",
        lambda **_kwargs: _metrc(environment="sandbox"),
    )

    def packages(**kwargs):
        captured.append(dict(kwargs))
        return _resource("packages_active", [{"label": "PKG-1", "name": "Bulk", "quantity": 100, "unit_of_measure": "g"}])

    def processing(**kwargs):
        captured.append(dict(kwargs))
        return _resource("processing_active", [{"provider_id": "PROC-1", "name": "Extraction", "status": "Active"}])

    monkeypatch.setattr(inventory_reconciliation, "fetch_all_active_metrc_packages", packages)
    monkeypatch.setattr(inventory_reconciliation, "fetch_all_active_processing_jobs", processing)

    result = inventory_reconciliation.manufacturing_regulatory_snapshot(
        context=_context(), engine=engine, settings=object()
    )

    assert result["ready"] is True
    assert result["environment"] == "sandbox"
    assert result["summary"]["active_package_count"] == 1
    assert result["summary"]["active_processing_job_count"] == 1
    assert all(call["environment"] == "sandbox" for call in captured)
    assert all(call["license_number"] == "LIC-281281" for call in captured)


def test_cultivation_snapshot_reads_each_cultivation_resource_in_exact_environment(monkeypatch):
    engine = _engine(cultivation=True)
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(
        plants,
        "resolve_trusted_regulatory_metrc",
        lambda **_kwargs: _metrc(environment="sandbox"),
    )

    def fake(resource: str, records: list[dict] | None = None):
        def run(**kwargs):
            captured.append((resource, kwargs["environment"]))
            return _resource(resource, records)
        return run

    monkeypatch.setattr(plants, "fetch_all_active_plant_batches", fake("plant_batches_active"))
    monkeypatch.setattr(plants, "fetch_all_vegetative_plants", fake("plants_vegetative"))
    monkeypatch.setattr(plants, "fetch_all_flowering_plants", fake("plants_flowering"))
    monkeypatch.setattr(plants, "fetch_all_active_harvests", fake("harvests_active"))

    result = plants.cultivation_regulatory_snapshot(
        context=_context(), engine=engine, settings=object()
    )

    assert result["ready"] is True
    assert result["environment"] == "sandbox"
    assert {name for name, _environment in captured} == {
        "plant_batches_active",
        "plants_vegetative",
        "plants_flowering",
        "harvests_active",
    }
    assert all(environment == "sandbox" for _name, environment in captured)
    assert result["reconciliation"]["read_only"] is True
