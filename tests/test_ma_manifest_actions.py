from __future__ import annotations

from datetime import date
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.manifest_drafts import ManifestDraftService
from modules.coman.models import Base, Facility, InventoryLot
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.doobie_actions.service import DoobieActionService
from modules.integrations import IntegrationConfigurationService
from modules.regulatory import RegulatoryMappingService
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.metrc_native import MetrcNativeError, submit_metrc_action, validate_metrc_action
from services.traceability_dispatcher import TraceabilityDispatcher


ENCRYPTION_KEY = "test-only-encryption-key"
INTEGRATOR_KEY = "test-integrator-key"
USER_API_KEY = "test-user-key"
LICENSE = "MP281234"
PACKAGE = "1A406030000MA00001"


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return engine


def _commercial_setup():
    engine = _engine()
    coman = ComanRepository(engine)
    organization = coman.create_organization("MA Manifest QA")
    facility = coman.create_facility(organization.id, "MA Manufacturing + Wholesale", "MA-WHOLESALE")
    with Session(engine) as session, session.begin():
        stored = session.get(Facility, facility.id)
        stored.commercial_enabled = True
        stored.production_enabled = True

    product = coman.create_product(
        organization.id,
        sku="MA-CASE",
        name="Massachusetts Wholesale Case",
        item_type="finished_good",
        base_unit="case",
        unit_cost=25,
        retail_price=70,
        actor="admin",
    )
    lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="MA-LOT-1",
        actor="admin",
        opening_quantity=20,
        unit="case",
    )
    with Session(engine) as session, session.begin():
        stored_lot = session.get(InventoryLot, lot.id)
        stored_lot.compliance_package_id = PACKAGE
        stored_lot.status = "available"

    commercial = CommercialRepository(engine)
    customer = commercial.create_trade_partner(
        organization.id,
        name="Licensed MA Retailer",
        partner_type="customer",
        actor="admin",
        license_or_registration="MR281111",
    )
    order = commercial.create_order(
        organization_id=organization.id,
        facility_id=facility.id,
        partner_id=customer.id,
        order_number="SO-MA-100",
        order_type="sales",
        order_date=date.today(),
        due_date=None,
        lines=[{"product_id": product.id, "quantity": 4, "unit": "case", "unit_price": 60}],
        actor="admin",
    )
    commercial.confirm_order(order.id, organization_id=organization.id, facility_id=facility.id, actor="admin")
    line = commercial.list_order_lines(organization.id, order_id=order.id)[0]
    commercial.allocate_lot(
        organization_id=organization.id,
        facility_id=facility.id,
        order_line_id=line.id,
        lot_id=lot.id,
        quantity=4,
        actor="admin",
    )
    return engine, organization, facility, order


def _trusted_metrc(engine, organization_id: str, facility_id: str, *, actor: str = "admin"):
    integrations = IntegrationConfigurationService(engine, ENCRYPTION_KEY)
    row = integrations.save(
        scope_type="user",
        scope_key=f"{actor}|{facility_id}",
        provider="metrc",
        organization_id=organization_id,
        facility_id=facility_id,
        configuration={"state": "MA", "license_number": LICENSE, "environment": "sandbox"},
        secret=USER_API_KEY,
        actor=actor,
    )
    row = integrations.validation_result(row.id, ok=True)
    RegulatoryMappingService(engine).verify(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        jurisdiction_code="MA",
        license_number=LICENSE,
        provider_facility_id="ma-sandbox-facility",
        environment="sandbox",
        integration_configuration_id=row.id,
        actor=actor,
    )
    return row


def _build_proposal(engine, organization_id: str, facility_id: str, order_id: str):
    return ManifestDraftService(engine).build_proposal(
        organization_id=organization_id,
        facility_id=facility_id,
        order_id=order_id,
        actor="admin",
        license_number=LICENSE,
        jurisdiction_code="MA",
        environment="sandbox",
        estimated_departure="2026-09-01T09:00:00-04:00",
        estimated_arrival="2026-09-01T11:00:00-04:00",
        planned_route="Facility → I-195 → licensed retailer",
        transfer_type_name="Transfer",
        driver_name="Authorized Employee",
        driver_license_number="S12345678",
        vehicle_license_plate_number="MA12345",
        vehicle_make="Ford",
        vehicle_model="Transit",
    )


def test_manifest_draft_uses_durable_customer_license_and_allocated_package():
    engine, organization, facility, order = _commercial_setup()
    candidates = ManifestDraftService(engine).candidates(organization.id, facility.id)
    assert candidates == [{
        "order_id": order.id,
        "order_number": "SO-MA-100",
        "status": "allocated",
        "customer": "Licensed MA Retailer",
        "customer_license": "MR281111",
        "package_count": 1,
        "package_labels": [PACKAGE],
        "ready": True,
    }]

    proposal = _build_proposal(engine, organization.id, facility.id, order.id)
    preview = json.loads(proposal.preview_json)
    payload = json.loads(proposal.payload_json)
    destination = payload["request_payload"]["template"]["Destinations"][0]
    assert proposal.action_type == "prepare_transfer_manifest"
    assert proposal.source_type == "doobie_agent"
    assert proposal.risk_level == "compliance"
    assert preview["customer"]["license"] == "MR281111"
    assert preview["packages"][0]["package_label"] == PACKAGE
    assert destination["RecipientLicenseNumber"] == "MR281111"
    assert destination["Packages"] == [{"PackageLabel": PACKAGE, "WholesalePrice": 240.0}]
    assert preview["environment"] == "sandbox"


def test_manifest_action_requires_employee_approval_and_execution_only_queues_traceability(monkeypatch):
    engine, organization, facility, order = _commercial_setup()
    proposal = _build_proposal(engine, organization.id, facility.id, order.id)
    service = DoobieActionService(engine)

    with pytest.raises(ValueError, match="Approve the preview"):
        service.execute(
            organization_id=organization.id,
            facility_id=facility.id,
            proposal_id=proposal.id,
            actor="admin",
        )

    monkeypatch.setattr("services.metrc_native.requests.request", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("approval/execution must not call Metrc")))
    service.approve(
        organization_id=organization.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="admin",
    )
    result = service.execute(
        organization_id=organization.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="admin",
    )
    transaction = TraceabilityBackofficeRepository(engine).get_transaction(
        organization.id,
        facility.id,
        result["transaction_id"],
    )
    assert result["status"] == "queued"
    assert transaction.status == "queued"
    assert transaction.operation_type == "transfer_template_create"
    assert transaction.license_number == LICENSE


def test_transfer_template_validation_allowlists_payload_and_rejects_missing_fields():
    valid = {
        "template": {
            "Name": "DL-SO-MA-100",
            "UnexpectedTopLevel": "drop-me",
            "Destinations": [{
                "RecipientLicenseNumber": "MR281111",
                "TransferTypeName": "Transfer",
                "PlannedRoute": "Licensed route",
                "EstimatedDepartureDateTime": "2026-09-01T09:00:00-04:00",
                "EstimatedArrivalDateTime": "2026-09-01T11:00:00-04:00",
                "UnexpectedDestination": "drop-me",
                "Packages": [{"PackageLabel": PACKAGE, "WholesalePrice": 240, "UnexpectedPackage": "drop-me"}],
            }],
        }
    }
    body = validate_metrc_action(operation_type="transfer_template_create", entity_id="SO-MA-100", payload=valid)["body"][0]
    assert "UnexpectedTopLevel" not in body
    assert "UnexpectedDestination" not in body["Destinations"][0]
    assert "UnexpectedPackage" not in body["Destinations"][0]["Packages"][0]

    invalid = {"template": {"Name": "DL-BAD", "Destinations": [{"Packages": [{"PackageLabel": PACKAGE}]}]}}
    with pytest.raises(MetrcNativeError, match="missing RecipientLicenseNumber"):
        validate_metrc_action(operation_type="transfer_template_create", entity_id="SO-BAD", payload=invalid)


def test_ma_sandbox_transfer_template_uses_exact_provider_endpoint_and_environment(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        ok = True
        content = b'[{"Id":321}]'
        text = '[{"Id":321}]'
        def json(self):
            return [{"Id": 321}]

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return Response()

    monkeypatch.setattr("services.metrc_native.requests.request", fake_request)
    result = submit_metrc_action(
        state="MA",
        environment="sandbox",
        license_number=LICENSE,
        integrator_api_key=INTEGRATOR_KEY,
        user_api_key=USER_API_KEY,
        operation_type="transfer_template_create",
        entity_id="SO-MA-100",
        payload={"template": {
            "Name": "DL-SO-MA-100",
            "Destinations": [{
                "RecipientLicenseNumber": "MR281111",
                "TransferTypeName": "Transfer",
                "PlannedRoute": "Licensed route",
                "EstimatedDepartureDateTime": "2026-09-01T09:00:00-04:00",
                "EstimatedArrivalDateTime": "2026-09-01T11:00:00-04:00",
                "Packages": [{"PackageLabel": PACKAGE}],
            }],
        }},
    )
    assert result["environment"] == "sandbox"
    assert result["state"] == "MA"
    assert result["external_reference"] == "321"
    assert calls[0][0] == "POST"
    assert calls[0][1] == f"https://sandbox-api-ma.metrc.com/transfers/v2/templates/outgoing?licenseNumber={LICENSE}"
    assert calls[0][2]["auth"] == (INTEGRATOR_KEY, USER_API_KEY)


@pytest.mark.parametrize("state,environment", [("MA", "production"), ("OR", "sandbox")])
def test_transfer_template_write_stays_blocked_outside_ma_sandbox(monkeypatch, state, environment):
    monkeypatch.setattr("services.metrc_native.requests.request", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("blocked write must not call provider")))
    with pytest.raises(MetrcNativeError, match="only for the Massachusetts Metrc sandbox"):
        submit_metrc_action(
            state=state,
            environment=environment,
            license_number=LICENSE,
            integrator_api_key=INTEGRATOR_KEY,
            user_api_key=USER_API_KEY,
            operation_type="transfer_template_create",
            entity_id="SO-MA-100",
            payload={"template": {
                "Name": "DL-SO-MA-100",
                "Destinations": [{
                    "RecipientLicenseNumber": "MR281111",
                    "TransferTypeName": "Transfer",
                    "PlannedRoute": "Licensed route",
                    "EstimatedDepartureDateTime": "2026-09-01T09:00:00-04:00",
                    "EstimatedArrivalDateTime": "2026-09-01T11:00:00-04:00",
                    "Packages": [{"PackageLabel": PACKAGE}],
                }],
            }},
        )


def test_dispatcher_requires_exact_trusted_mapping_and_submits_only_after_it_exists(monkeypatch):
    engine, organization, facility, order = _commercial_setup()
    proposal = _build_proposal(engine, organization.id, facility.id, order.id)
    actions = DoobieActionService(engine)
    actions.approve(organization_id=organization.id, facility_id=facility.id, proposal_id=proposal.id, actor="admin")
    queued = actions.execute(organization_id=organization.id, facility_id=facility.id, proposal_id=proposal.id, actor="admin")
    transaction_id = queued["transaction_id"]

    integrations = IntegrationConfigurationService(engine, ENCRYPTION_KEY)
    credential = integrations.save(
        scope_type="user",
        scope_key=f"admin|{facility.id}",
        provider="metrc",
        organization_id=organization.id,
        facility_id=facility.id,
        configuration={"state": "MA", "license_number": LICENSE, "environment": "sandbox"},
        secret=USER_API_KEY,
        actor="admin",
    )
    integrations.validation_result(credential.id, ok=True)

    monkeypatch.setattr("services.metrc_native.requests.request", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("untrusted mapping must not call provider")))
    blocked = TraceabilityDispatcher(engine, encryption_key=ENCRYPTION_KEY, metrc_integrator_api_key=INTEGRATOR_KEY).dispatch(
        organization_id=organization.id,
        facility_id=facility.id,
        transaction_id=transaction_id,
        actor="admin",
    )
    assert blocked["status"] == "reconciliation_required"
    assert blocked["outbound_request_sent"] is False

    proposal2 = ManifestDraftService(engine).build_proposal(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        actor="admin",
        license_number=LICENSE,
        jurisdiction_code="MA",
        environment="sandbox",
        estimated_departure="2026-09-02T09:00:00-04:00",
        estimated_arrival="2026-09-02T11:00:00-04:00",
        planned_route="Facility → licensed retailer",
        transfer_type_name="Transfer",
    )
    actions.approve(organization_id=organization.id, facility_id=facility.id, proposal_id=proposal2.id, actor="admin")
    queued2 = actions.execute(organization_id=organization.id, facility_id=facility.id, proposal_id=proposal2.id, actor="admin")
    _trusted_metrc(engine, organization.id, facility.id)

    calls = []
    class Response:
        status_code = 200
        ok = True
        content = b'[{"Id":654}]'
        text = '[{"Id":654}]'
        def json(self):
            return [{"Id": 654}]
    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return Response()
    monkeypatch.setattr("services.metrc_native.requests.request", fake_request)

    submitted = TraceabilityDispatcher(engine, encryption_key=ENCRYPTION_KEY, metrc_integrator_api_key=INTEGRATOR_KEY).dispatch(
        organization_id=organization.id,
        facility_id=facility.id,
        transaction_id=queued2["transaction_id"],
        actor="admin",
    )
    assert submitted["ok"] is True
    assert submitted["status"] == "accepted"
    assert submitted["environment"] == "sandbox"
    assert submitted["external_reference"] == "654"
    assert len(calls) == 1


def test_environment_is_mandatory_for_every_metrc_write(monkeypatch):
    monkeypatch.setattr("services.metrc_native.requests.request", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("missing environment must fail before provider")))
    with pytest.raises(MetrcNativeError, match="explicit sandbox or production environment"):
        submit_metrc_action(
            state="MA",
            environment="",
            license_number=LICENSE,
            integrator_api_key=INTEGRATOR_KEY,
            user_api_key=USER_API_KEY,
            operation_type="package_finish",
            entity_id=PACKAGE,
            payload={},
        )
