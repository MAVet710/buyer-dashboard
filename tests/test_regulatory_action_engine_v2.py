from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.regulatory_actions import RegulatoryActionProposalService, action_recommendations
from modules.coman.models import Base, Facility
from modules.coman.repository import ComanRepository
from modules.doobie_actions.service import DoobieActionService
from modules.regulatory import (
    CapabilityStatus,
    DOCUMENTATION_PENDING_JURISDICTIONS,
    capability_evidence,
    capability_status,
    get_metrc_write_contract,
    require_metrc_write_contract,
)
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from scripts.validate_ma_metrc_sandbox import live_read, readiness
from scripts.verify_metrc_capabilities import _endpoint_present
from services.metrc_native import MetrcNativeError, submit_metrc_action


PACKAGE = "1A406030000MA00999"
LICENSE = "MP281234"


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return engine


def _production_setup(*, opening_quantity: float = 0):
    engine = _engine()
    coman = ComanRepository(engine)
    organization = coman.create_organization("Regulatory Action QA")
    facility = coman.create_facility(organization.id, "MA Production", "MA-PROD")
    with Session(engine) as session, session.begin():
        stored = session.get(Facility, facility.id)
        stored.production_enabled = True
        stored.commercial_enabled = True
    product = coman.create_product(
        organization.id,
        sku="REG-ACT-1",
        name="Finished Cannabis Package",
        item_type="finished_good",
        base_unit="Each",
        actor="admin",
    )
    lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="REG-LOT-1",
        compliance_package_id=PACKAGE,
        opening_quantity=opening_quantity,
        unit="Each",
        actor="admin",
    )
    return engine, organization, facility, lot


def test_endpoint_evidence_requires_exact_method_path_pair():
    text = "POST /something/else GET /packages/v2/active"
    assert _endpoint_present(text, "GET /packages/v2/active") is True
    assert _endpoint_present(text, "POST /packages/v2/active") is False
    assert _endpoint_present("POST   /processing/v2/start", "POST /processing/v2/start") is True


def test_pending_jurisdictions_stay_explicitly_fail_closed():
    assert DOCUMENTATION_PENDING_JURISDICTIONS == frozenset({"AL", "GU", "VI", "VA", "WV"})
    for code in DOCUMENTATION_PENDING_JURISDICTIONS:
        assert capability_status(code, "transfers") == CapabilityStatus.UNKNOWN


def test_ma_package_waste_is_resolved_as_unsupported_not_guessed():
    assert capability_status("MA", "package_waste") == CapabilityStatus.UNSUPPORTED
    evidence = capability_evidence("MA", "package_waste")
    assert evidence is not None
    assert "NO DEDICATED" in evidence.endpoint
    assert "plant" in evidence.note.casefold()


def test_write_registry_enables_only_verified_payload_contracts():
    package_finish = require_metrc_write_contract(
        operation_type="package_finish",
        jurisdiction="MA",
        environment="sandbox",
    )
    assert package_finish.dispatch_enabled is True
    assert package_finish.path == "packages/v2/finish"

    receiving = get_metrc_write_contract("inbound_transfer_accept")
    processing = get_metrc_write_contract("processing_start")
    cultivation = get_metrc_write_contract("plant_location_update")
    assert receiving is not None and receiving.dispatch_enabled is False
    assert processing is not None and processing.dispatch_enabled is False
    assert cultivation is not None and cultivation.dispatch_enabled is False

    with pytest.raises(ValueError, match="automatic execution is locked"):
        require_metrc_write_contract(
            operation_type="processing_start",
            jurisdiction="MA",
            environment="sandbox",
        )


def test_transfer_template_scope_stays_ma_sandbox_only_before_network(monkeypatch):
    monkeypatch.setattr(
        "services.metrc_native.requests.request",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("blocked operation must not call Metrc")),
    )
    payload = {
        "template": {
            "Name": "DL-SCOPE-GUARD",
            "Destinations": [{
                "RecipientLicenseNumber": "MR281111",
                "TransferTypeName": "Transfer",
                "PlannedRoute": "Licensed route",
                "EstimatedDepartureDateTime": "2026-09-01T09:00:00-04:00",
                "EstimatedArrivalDateTime": "2026-09-01T11:00:00-04:00",
                "Packages": [{"PackageLabel": PACKAGE}],
            }],
        }
    }
    with pytest.raises(MetrcNativeError, match="only for the Massachusetts Metrc sandbox"):
        submit_metrc_action(
            state="MA",
            environment="production",
            license_number=LICENSE,
            integrator_api_key="integrator",
            user_api_key="user",
            operation_type="transfer_template_create",
            entity_id="SO-SCOPE",
            payload=payload,
        )
    with pytest.raises(MetrcNativeError, match="only for the Massachusetts Metrc sandbox"):
        submit_metrc_action(
            state="OR",
            environment="sandbox",
            license_number=LICENSE,
            integrator_api_key="integrator",
            user_api_key="user",
            operation_type="transfer_template_create",
            entity_id="SO-SCOPE",
            payload=payload,
        )


def test_depleted_package_finish_is_deterministic_and_requires_approval(monkeypatch):
    engine, organization, facility, lot = _production_setup(opening_quantity=0)
    service = RegulatoryActionProposalService(engine)
    candidates = service.package_finish_candidates(organization.id, facility.id)
    assert candidates == [{
        "lot_id": lot.id,
        "package_label": PACKAGE,
        "lot_code": "REG-LOT-1",
        "product_name": "Finished Cannabis Package",
        "product_sku": "REG-ACT-1",
        "local_balance": 0.0,
        "location": "UNASSIGNED",
        "status": "available",
        "ready": True,
    }]

    proposal = service.package_finish_proposal(
        organization_id=organization.id,
        facility_id=facility.id,
        lot_id=lot.id,
        actor="admin",
        jurisdiction_code="MA",
        environment="sandbox",
        license_number=LICENSE,
        actual_date="2026-09-03",
    )
    proposal_again = service.package_finish_proposal(
        organization_id=organization.id,
        facility_id=facility.id,
        lot_id=lot.id,
        actor="admin",
        jurisdiction_code="MA",
        environment="sandbox",
        license_number=LICENSE,
        actual_date="2026-09-03",
    )
    assert proposal_again.id == proposal.id
    assert proposal.action_type == "prepare_regulatory_action"
    assert proposal.source_type == "doobie_agent"
    assert proposal.risk_level == "compliance"
    assert json.loads(proposal.payload_json)["operation_type"] == "package_finish"

    actions = DoobieActionService(engine)
    with pytest.raises(ValueError, match="Approve the preview"):
        actions.execute(
            organization_id=organization.id,
            facility_id=facility.id,
            proposal_id=proposal.id,
            actor="admin",
        )

    monkeypatch.setattr(
        "services.metrc_native.requests.request",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("approval/queueing must not call Metrc")),
    )
    actions.approve(
        organization_id=organization.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="admin",
    )
    queued = actions.execute(
        organization_id=organization.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="admin",
    )
    tx = TraceabilityBackofficeRepository(engine).get_transaction(
        organization.id,
        facility.id,
        queued["transaction_id"],
    )
    assert tx.status == "queued"
    assert tx.operation_type == "package_finish"
    assert tx.entity_id == PACKAGE


def test_non_depleted_package_cannot_be_prepared_for_finish():
    engine, organization, facility, lot = _production_setup(opening_quantity=3)
    service = RegulatoryActionProposalService(engine)
    assert service.package_finish_candidates(organization.id, facility.id) == []
    with pytest.raises(ValueError, match="still has 3 local units"):
        service.package_finish_proposal(
            organization_id=organization.id,
            facility_id=facility.id,
            lot_id=lot.id,
            actor="admin",
            jurisdiction_code="MA",
            environment="sandbox",
            license_number=LICENSE,
            actual_date="2026-09-03",
        )


def test_regulatory_recommendations_never_claim_locked_writes_are_enabled():
    intelligence = {
        "findings": [
            {"domain": "manufacturing", "code": "processing_job_exception", "entity_id": "55", "severity": "high", "title": "Processing issue"},
            {"domain": "cultivation", "code": "plant_room_mismatch", "entity_id": "1A-PLANT", "severity": "medium", "title": "Plant mismatch"},
        ]
    }
    catalog = RegulatoryActionProposalService.catalog(jurisdiction_code="MA", environment="sandbox")
    rows = action_recommendations(intelligence=intelligence, catalog=catalog)
    assert {row["operation_type"] for row in rows} == {"processing_adjust", "plant_location_update"}
    assert all(row["provider_dispatch_enabled"] is False for row in rows)
    assert all(row["human_approval_required"] is True for row in rows)


def test_ma_sandbox_readiness_never_calls_network_without_credentials(monkeypatch):
    monkeypatch.setattr(
        "scripts.validate_ma_metrc_sandbox.requests.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("missing credentials must not call Metrc")),
    )
    report = readiness({})
    assert report["ready"] is False
    assert report["status"] == "credentials_missing"
    assert report["write_performed"] is False
    assert set(report["missing"]) == {
        "METRC_INTEGRATOR_API_KEY",
        "METRC_MA_SANDBOX_USER_API_KEY",
        "METRC_MA_SANDBOX_LICENSE_NUMBER",
    }
    assert live_read({})["status"] == "credentials_missing"


def test_marketing_surfaces_current_product_pillars():
    from pathlib import Path

    marketing = Path("frontend/src/pages/MarketingHome.tsx").read_text(encoding="utf-8")
    beta = Path("frontend/src/pages/BetaPartnerPage.tsx").read_text(encoding="utf-8")
    home = Path("frontend/src/pages/HomePage.tsx").read_text(encoding="utf-8")
    for content in (marketing, beta, home):
        assert "Doobie Agent" in content
        assert "Wholesale" in content
    assert "Customer Portal" in marketing
    assert "Customer Portal" in beta
    assert "Customer Portal" in home
