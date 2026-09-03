from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.manifest_drafts import ManifestDraftService
from backend.app.services.manifest_lifecycle import ManifestLifecycleError, ManifestLifecycleService
from modules.coman.models import Base, Facility, InventoryLot
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.doobie_actions.service import DoobieActionService
from modules.traceability.backoffice import TraceabilityBackofficeRepository


LICENSE = "MP281234"
PACKAGE = "1A406030000MA00001"
RECIPIENT = "MR281111"


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return engine


def _setup():
    engine = _engine()
    coman = ComanRepository(engine)
    organization = coman.create_organization("Manifest Lifecycle QA")
    facility = coman.create_facility(organization.id, "MA Wholesale", "MA-WHOLESALE-LIFECYCLE")
    with Session(engine) as session, session.begin():
        stored = session.get(Facility, facility.id)
        stored.commercial_enabled = True
        stored.production_enabled = True

    product = coman.create_product(
        organization.id,
        sku="MA-LIFECYCLE",
        name="MA Lifecycle Case",
        item_type="finished_good",
        base_unit="case",
        unit_cost=20,
        retail_price=60,
        actor="admin",
    )
    lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="MA-LIFECYCLE-LOT",
        actor="admin",
        opening_quantity=10,
        unit="case",
    )
    with Session(engine) as session, session.begin():
        stored_lot = session.get(InventoryLot, lot.id)
        stored_lot.compliance_package_id = PACKAGE
        stored_lot.status = "available"

    commercial = CommercialRepository(engine)
    partner = commercial.create_trade_partner(
        organization.id,
        name="Licensed MA Customer",
        partner_type="customer",
        actor="admin",
        license_or_registration=RECIPIENT,
    )
    order = commercial.create_order(
        organization_id=organization.id,
        facility_id=facility.id,
        partner_id=partner.id,
        order_number="SO-MA-LIFE-1",
        order_type="sales",
        order_date=date.today(),
        due_date=None,
        lines=[{"product_id": product.id, "quantity": 2, "unit": "case", "unit_price": 50}],
        actor="admin",
    )
    commercial.confirm_order(order.id, organization_id=organization.id, facility_id=facility.id, actor="admin")
    line = commercial.list_order_lines(organization.id, order_id=order.id)[0]
    commercial.allocate_lot(
        organization_id=organization.id,
        facility_id=facility.id,
        order_line_id=line.id,
        lot_id=lot.id,
        quantity=2,
        actor="admin",
    )

    proposal = ManifestDraftService(engine).build_proposal(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        actor="admin",
        license_number=LICENSE,
        jurisdiction_code="MA",
        environment="sandbox",
        estimated_departure="2026-09-03T09:00:00-04:00",
        estimated_arrival="2026-09-03T11:00:00-04:00",
        planned_route="MA facility to licensed customer",
        transfer_type_name="Transfer",
    )
    actions = DoobieActionService(engine)
    actions.approve(
        organization_id=organization.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="admin",
    )
    execution = actions.execute(
        organization_id=organization.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="admin",
    )
    tx_id = execution["transaction_id"]
    return engine, organization, facility, proposal, tx_id


def _accept(engine, organization_id: str, facility_id: str, tx_id: str, external_reference: str = "654"):
    repo = TraceabilityBackofficeRepository(engine)
    repo.transition_logged(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=tx_id,
        new_status="submitted",
        actor="admin",
        reason="test submit",
        source="provider_worker",
    )
    return repo.transition_logged(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=tx_id,
        new_status="accepted",
        actor="admin",
        reason="test accepted",
        source="provider_worker",
        external_reference=external_reference,
    )


def _credentials():
    return {
        "state": "MA",
        "environment": "sandbox",
        "license_number": LICENSE,
        "user_api_key": "test-user-key",
        "integrator_api_key": "test-integrator-key",
    }


def test_readback_verifies_exact_template_and_matching_manifest(monkeypatch):
    engine, organization, facility, proposal, tx_id = _setup()
    _accept(engine, organization.id, facility.id, tx_id)

    monkeypatch.setattr(
        "backend.app.services.manifest_lifecycle.fetch_all_outgoing_transfer_templates",
        lambda **kwargs: {"ok": True, "rows": [{"Id": 654, "Name": "DL-SO-MA-LIFE-1-202609030900"}]},
    )
    monkeypatch.setattr(
        "backend.app.services.manifest_lifecycle.fetch_all_outgoing_transfers",
        lambda **kwargs: {"ok": True, "rows": [{"Id": 9001, "ManifestNumber": "MA-MANIFEST-9001"}]},
    )
    monkeypatch.setattr(
        "backend.app.services.manifest_lifecycle.fetch_all_transfer_deliveries",
        lambda **kwargs: {"ok": True, "rows": [{"Id": 7001, "RecipientLicenseNumber": RECIPIENT}]},
    )
    monkeypatch.setattr(
        "backend.app.services.manifest_lifecycle.fetch_all_delivery_packages",
        lambda **kwargs: {"ok": True, "rows": [{"PackageLabel": PACKAGE}]},
    )

    result = ManifestLifecycleService(engine).inspect(
        organization_id=organization.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="admin",
        **_credentials(),
    )

    assert result["state"] == "manifest_available"
    assert result["template_verified"] is True
    assert result["template_id"] == "654"
    assert result["manifest_available"] is True
    assert result["manifest_transfer_id"] == "9001"
    assert result["manifest_number"] == "MA-MANIFEST-9001"
    assert result["delivery_id"] == "7001"
    tx = TraceabilityBackofficeRepository(engine).get_transaction(organization.id, facility.id, tx_id)
    assert tx.status == "verified"
    events = TraceabilityBackofficeRepository(engine).list_status_events(organization.id, facility.id, tx_id)
    assert events[-1].to_status == "verified"
    assert events[-1].source == "provider_readback"


def test_provider_acceptance_does_not_equal_readback_verification(monkeypatch):
    engine, organization, facility, proposal, tx_id = _setup()
    _accept(engine, organization.id, facility.id, tx_id)
    monkeypatch.setattr(
        "backend.app.services.manifest_lifecycle.fetch_all_outgoing_transfer_templates",
        lambda **kwargs: {"ok": True, "rows": [{"Id": 999, "Name": "Some Other Template"}]},
    )

    result = ManifestLifecycleService(engine).inspect(
        organization_id=organization.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="admin",
        **_credentials(),
    )

    assert result["state"] == "accepted"
    assert result["template_verified"] is False
    tx = TraceabilityBackofficeRepository(engine).get_transaction(organization.id, facility.id, tx_id)
    assert tx.status == "accepted"


def test_manifest_requires_exact_recipient_and_package_evidence(monkeypatch):
    engine, organization, facility, proposal, tx_id = _setup()
    _accept(engine, organization.id, facility.id, tx_id)
    monkeypatch.setattr(
        "backend.app.services.manifest_lifecycle.fetch_all_outgoing_transfer_templates",
        lambda **kwargs: {"ok": True, "rows": [{"Id": 654, "Name": "DL-SO-MA-LIFE-1-202609030900"}]},
    )
    monkeypatch.setattr(
        "backend.app.services.manifest_lifecycle.fetch_all_outgoing_transfers",
        lambda **kwargs: {"ok": True, "rows": [{"Id": 9001, "ManifestNumber": "WRONG-SHIPMENT"}]},
    )
    monkeypatch.setattr(
        "backend.app.services.manifest_lifecycle.fetch_all_transfer_deliveries",
        lambda **kwargs: {"ok": True, "rows": [{"Id": 7001, "RecipientLicenseNumber": "MR-DIFFERENT"}]},
    )
    monkeypatch.setattr(
        "backend.app.services.manifest_lifecycle.fetch_all_delivery_packages",
        lambda **kwargs: {"ok": True, "rows": [{"PackageLabel": "1A406030000MA99999"}]},
    )

    result = ManifestLifecycleService(engine).inspect(
        organization_id=organization.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="admin",
        **_credentials(),
    )
    assert result["state"] == "template_verified"
    assert result["template_verified"] is True
    assert result["manifest_available"] is False
    assert result["manifest_download_available"] is False


def test_manifest_pdf_is_only_retrieved_after_exact_manifest_match(monkeypatch):
    engine, organization, facility, proposal, tx_id = _setup()
    _accept(engine, organization.id, facility.id, tx_id)
    monkeypatch.setattr(
        "backend.app.services.manifest_lifecycle.fetch_all_outgoing_transfer_templates",
        lambda **kwargs: {"ok": True, "rows": [{"Id": 654, "Name": "DL-SO-MA-LIFE-1-202609030900"}]},
    )
    monkeypatch.setattr(
        "backend.app.services.manifest_lifecycle.fetch_all_outgoing_transfers",
        lambda **kwargs: {"ok": True, "rows": [{"Id": 9001, "ManifestNumber": "MA-MANIFEST-9001"}]},
    )
    monkeypatch.setattr(
        "backend.app.services.manifest_lifecycle.fetch_all_transfer_deliveries",
        lambda **kwargs: {"ok": True, "rows": [{"Id": 7001, "RecipientFacilityLicenseNumber": RECIPIENT}]},
    )
    monkeypatch.setattr(
        "backend.app.services.manifest_lifecycle.fetch_all_delivery_packages",
        lambda **kwargs: {"ok": True, "rows": [{"Label": PACKAGE}]},
    )
    calls = []

    class PdfResponse:
        status_code = 200
        ok = True
        content = b"%PDF-1.7 test manifest"
        headers = {"Content-Type": "application/pdf"}

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return PdfResponse()

    monkeypatch.setattr("backend.app.services.manifest_lifecycle.requests.get", fake_get)
    content, name = ManifestLifecycleService(engine).manifest_pdf(
        organization_id=organization.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="admin",
        **_credentials(),
    )
    assert content.startswith(b"%PDF")
    assert name == "MA-MANIFEST-9001"
    assert calls == [(
        "https://sandbox-api-ma.metrc.com/transfers/v2/manifest/9001/pdf",
        {"auth": ("test-integrator-key", "test-user-key"), "headers": {"Accept": "application/pdf"}, "timeout": 20},
    )]


def test_manifest_lifecycle_is_tenant_and_environment_fail_closed(monkeypatch):
    engine, organization, facility, proposal, _ = _setup()
    monkeypatch.setattr(
        "backend.app.services.manifest_lifecycle.fetch_all_outgoing_transfer_templates",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("blocked scope must not call Metrc")),
    )
    with pytest.raises(ManifestLifecycleError, match="Massachusetts Metrc sandbox"):
        ManifestLifecycleService(engine).inspect(
            organization_id=organization.id,
            facility_id=facility.id,
            proposal_id=proposal.id,
            actor="admin",
            state="MA",
            environment="production",
            license_number=LICENSE,
            user_api_key="test-user-key",
            integrator_api_key="test-integrator-key",
        )
    with pytest.raises(ManifestLifecycleError, match="active facility"):
        ManifestLifecycleService(engine).inspect(
            organization_id="different-org",
            facility_id=facility.id,
            proposal_id=proposal.id,
            actor="admin",
            **_credentials(),
        )
