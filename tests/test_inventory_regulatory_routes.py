from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext
from backend.app.main import app
from backend.app.routers import inventory_reconciliation as regulatory_router
from backend.app.services.metrc_context import MetrcContext
from modules.coman.models import Base, Facility, Organization


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Organization(id="org-1", name="One", slug="one"))
        session.add(Facility(
            id="fac-1",
            organization_id="org-1",
            name="Production",
            code="PROD",
            production_enabled=True,
        ))
        session.commit()
    return engine


def _context() -> RequestContext:
    return RequestContext("user-1", "org-1", "fac-1", "operator")


def _metrc(*, trusted: bool = True, status: str = "connected", environment: str = "sandbox") -> MetrcContext:
    return MetrcContext(
        configured=True,
        state="MA",
        license_number="MP281281",
        user_api_key="user-key",
        integrator_api_key="integrator-key",
        status=status,
        environment=environment,
        trusted_mapping=trusted,
        message="ready",
        row=object(),
    )


def test_trusted_inventory_router_precedes_legacy_live_inbound_route():
    # API_PREFIX may be overridden by the runtime environment. Assert ordering
    # by the registered endpoint identities instead of hardcoding /api/v1.
    candidates = [
        (index, route.endpoint)
        for index, route in enumerate(app.routes)
        if "GET" in getattr(route, "methods", set())
        and getattr(getattr(route, "endpoint", None), "__name__", "")
        in {"trusted_inbound_queue", "inbound_queue"}
    ]
    trusted = next((item for item in candidates if item[1].__name__ == "trusted_inbound_queue"), None)
    legacy = next((item for item in candidates if item[1].__name__ == "inbound_queue"), None)
    assert trusted is not None
    assert legacy is not None
    assert trusted[0] < legacy[0]
    assert trusted[1].__module__ == "backend.app.routers.inventory_reconciliation"


def test_trusted_inbound_propagates_exact_mapping_environment(monkeypatch):
    engine = _engine()
    captured = {}
    metrc = _metrc(environment="sandbox")
    monkeypatch.setattr(regulatory_router, "resolve_metrc_context", lambda *_args, **_kwargs: (None, metrc))

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "transfers": [{"Id": 12, "ManifestNumber": "MAN-12", "PackageCount": 2}],
        }

    monkeypatch.setattr(regulatory_router, "fetch_all_incoming_transfers", fake_fetch)
    result = regulatory_router.trusted_inbound_queue(
        "production",
        context=_context(),
        engine=engine,
        settings=object(),
    )

    assert result["configured"] is True
    assert result["environment"] == "sandbox"
    assert result["transfers"][0]["transfer_id"] == "12"
    assert captured["state"] == "MA"
    assert captured["license_number"] == "MP281281"
    assert captured["environment"] == "sandbox"


def test_live_inventory_reads_fail_closed_without_exact_trusted_mapping(monkeypatch):
    engine = _engine()
    metrc = _metrc(trusted=False)
    monkeypatch.setattr(regulatory_router, "resolve_metrc_context", lambda *_args, **_kwargs: (None, metrc))

    with pytest.raises(HTTPException) as exc:
        regulatory_router._ready_metrc(
            operation="production",
            context=_context(),
            engine=engine,
            settings=object(),
            receiving=True,
        )
    assert exc.value.status_code == 409
    assert "exact Metrc facility" in str(exc.value.detail)


def test_live_inventory_reads_require_validated_connection(monkeypatch):
    engine = _engine()
    metrc = _metrc(status="error")
    monkeypatch.setattr(regulatory_router, "resolve_metrc_context", lambda *_args, **_kwargs: (None, metrc))

    with pytest.raises(HTTPException) as exc:
        regulatory_router._ready_metrc(
            operation="production",
            context=_context(),
            engine=engine,
            settings=object(),
            receiving=True,
        )
    assert exc.value.status_code == 409
    assert "Validate the Metrc connection" in str(exc.value.detail)