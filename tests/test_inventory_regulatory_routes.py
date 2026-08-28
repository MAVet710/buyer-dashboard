from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext
from backend.app.routers import inventory as inventory_router
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


def _metrc(
    *,
    configured: bool = True,
    trusted: bool = True,
    status: str = "connected",
    environment: str = "sandbox",
) -> MetrcContext:
    return MetrcContext(
        configured=configured,
        state="MA" if configured else "",
        license_number="MP281281" if configured else "",
        user_api_key="user-key" if configured else "",
        integrator_api_key="integrator-key" if configured else "",
        status=status if configured else "not_configured",
        environment=environment,
        trusted_mapping=trusted if configured else False,
        message="ready" if configured else "Configure Metrc for this facility.",
        row=object() if configured else None,
    )


def test_unconfigured_inventory_read_remains_safe_setup_state(monkeypatch):
    engine = _engine()
    metrc = _metrc(configured=False)
    monkeypatch.setattr(inventory_router, "resolve_metrc_context", lambda *_args, **_kwargs: (None, metrc))

    resolved = inventory_router._metrc_context(
        operation="production",
        context=_context(),
        engine=engine,
        settings=object(),
    )

    assert resolved.configured is False
    assert resolved.trusted_mapping is False


def test_inbound_queue_propagates_exact_saved_environment(monkeypatch):
    engine = _engine()
    captured = {}
    metrc = _metrc(environment="sandbox")
    monkeypatch.setattr(inventory_router, "resolve_metrc_context", lambda *_args, **_kwargs: (None, metrc))

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "transfers": [{"Id": 12, "ManifestNumber": "MAN-12", "PackageCount": 2}],
        }

    monkeypatch.setattr(inventory_router, "fetch_all_incoming_transfers", fake_fetch)
    result = inventory_router.inbound_queue(
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
    monkeypatch.setattr(inventory_router, "resolve_metrc_context", lambda *_args, **_kwargs: (None, metrc))

    with pytest.raises(HTTPException) as exc:
        inventory_router._metrc_context(
            operation="production",
            context=_context(),
            engine=engine,
            settings=object(),
        )
    assert exc.value.status_code == 409
    assert "exact Metrc facility" in str(exc.value.detail)


def test_live_inventory_reads_require_validated_connection(monkeypatch):
    engine = _engine()
    metrc = _metrc(status="error")
    monkeypatch.setattr(inventory_router, "resolve_metrc_context", lambda *_args, **_kwargs: (None, metrc))

    with pytest.raises(HTTPException) as exc:
        inventory_router._metrc_context(
            operation="production",
            context=_context(),
            engine=engine,
            settings=object(),
        )
    assert exc.value.status_code == 409
    assert "Validate the Metrc connection" in str(exc.value.detail)
