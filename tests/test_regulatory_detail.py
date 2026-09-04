from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext
from backend.app.routers.regulatory_detail import local_regulatory_detail, provider_regulatory_detail
from modules.coman.models import Base, Facility, Organization, utc_now
from modules.integrations.models import IntegrationProviderSnapshot, IntegrationSyncState
from modules.traceability.object_links import TraceabilityObjectLink


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org-reg", name="Regulatory Detail", slug="regulatory-detail"))
        session.add(Organization(id="org-other", name="Other", slug="other-regulatory-detail"))
        session.add(Facility(id="fac-reg", organization_id="org-reg", name="Mapped", code="REG"))
        session.add(Facility(id="fac-other", organization_id="org-other", name="Other", code="OTHER"))
        now = utc_now()
        session.add(
            TraceabilityObjectLink(
                id="link-1",
                organization_id="org-reg",
                facility_id="fac-reg",
                provider="metrc",
                jurisdiction="MA",
                environment="sandbox",
                license_number="MP281234",
                entity_type="inventory_lot",
                entity_id="lot-1",
                provider_resource="packages",
                provider_id="PKG-1",
                provider_label="1A4000000000000000000001",
                status="verified",
                verified_at=now,
                last_seen_at=now,
            )
        )
        session.add(
            IntegrationProviderSnapshot(
                id="snapshot-1",
                organization_id="org-reg",
                facility_id="fac-reg",
                provider="metrc",
                environment="sandbox",
                resource="packages",
                external_id="PKG-1",
                provider_label="1A4000000000000000000001",
                fingerprint="a" * 64,
                raw_payload_json=json.dumps({"Id": "PKG-1", "Label": "1A4000000000000000000001", "Quantity": 42}),
                normalized_payload_json=json.dumps({"provider": "metrc", "resource": "packages", "quantity": 42}),
                present=True,
                snapshot_run_id="run-1",
                last_seen_at=now,
            )
        )
        session.add(
            IntegrationSyncState(
                organization_id="org-reg",
                facility_id="fac-reg",
                provider="metrc",
                resource="packages",
                environment="sandbox",
                cursor="initial-full",
                status="succeeded",
                last_started_at=now,
                last_completed_at=now,
                last_success_at=now,
                records_seen=1,
                records_written=1,
                updated_by="tester",
            )
        )
    return engine


def _context(org="org-reg", facility="fac-reg"):
    return RequestContext("user-1", org, facility, "operator")


def test_local_regulatory_detail_returns_exact_identity_current_snapshot_raw_record_and_sync_evidence():
    engine = _engine()
    result = local_regulatory_detail(
        "inventory_lot",
        "lot-1",
        provider="metrc",
        environment="sandbox",
        context=_context(),
        engine=engine,
    )

    assert result["network_request_made"] is False
    assert result["linked"] is True
    assert len(result["entries"]) == 1
    entry = result["entries"][0]
    assert entry["current_in_provider"] is True
    assert entry["reconciliation_required"] is False
    assert entry["identity"]["provider_id"] == "PKG-1"
    assert entry["identity"]["license_number"] == "MP281234"
    assert entry["current_snapshot"]["raw_provider_record"]["Quantity"] == 42
    assert entry["current_snapshot"]["normalized_provider_record"]["resource"] == "packages"
    assert entry["current_snapshot"]["age_seconds"] is not None
    assert entry["sync"]["status"] == "succeeded"
    assert entry["sync"]["cursor"] == "initial-full"


def test_provider_regulatory_detail_resolves_same_snapshot_and_local_link():
    engine = _engine()
    result = provider_regulatory_detail(
        "packages",
        "PKG-1",
        provider="metrc",
        environment="sandbox",
        context=_context(),
        engine=engine,
    )

    assert result["network_request_made"] is False
    assert result["current_in_provider"] is True
    assert result["identity"]["entity_type"] == "inventory_lot"
    assert result["identity"]["entity_id"] == "lot-1"
    assert result["current_snapshot"]["raw_provider_record"]["Label"].startswith("1A4")


def test_provider_regulatory_detail_is_tenant_scoped():
    engine = _engine()
    with pytest.raises(HTTPException) as exc:
        provider_regulatory_detail(
            "packages",
            "PKG-1",
            provider="metrc",
            environment="sandbox",
            context=_context("org-other", "fac-other"),
            engine=engine,
        )
    assert exc.value.status_code == 404
