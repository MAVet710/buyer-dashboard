from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.services import metrc_transfer_actions as actions_module
from backend.app.services.metrc_transfer_actions import (
    GovernedMetrcTransferActionService,
    MetrcTransferActionError,
    transfer_confirmation_token,
)
from modules.coman.models import Base, Facility, Organization
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.metrc_evaluation_transfers import MetrcTransferEvaluationError


def _fixture():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        org = Organization(name="Transfer Org", slug="transfer-org")
        session.add(org)
        session.flush()
        facility = Facility(
            organization_id=org.id,
            name="Wholesale",
            code="WHOLE",
            retail_enabled=False,
            production_enabled=True,
            commercial_enabled=True,
        )
        session.add(facility)
        session.flush()
        return engine, org.id, facility.id


def _create_payload():
    return {
        "entity_id": "SO-MA-100",
        "last_modified_start": "2026-09-01T00:00:00-04:00",
        "last_modified_end": "2026-09-02T23:59:59-04:00",
        "template": {
            "Name": "DL-SO-MA-100",
            "Destinations": [
                {
                    "RecipientLicenseNumber": "MR281111",
                    "TransferTypeName": "Transfer",
                    "PlannedRoute": "Licensed route",
                    "EstimatedDepartureDateTime": "2026-09-01T09:00:00-04:00",
                    "EstimatedArrivalDateTime": "2026-09-01T11:00:00-04:00",
                    "Packages": [
                        {
                            "PackageLabel": "1A406030000MA00001",
                            "WholesalePrice": 240.0,
                        }
                    ],
                }
            ],
        },
    }


def test_prepare_matches_current_ma_outgoing_template_contract():
    engine, _, _ = _fixture()
    prepared = GovernedMetrcTransferActionService(engine).prepare(
        operation_type="transfer_template_create",
        payload=_create_payload(),
        state="MA",
        environment="sandbox",
        license_number="MP281234",
    )
    assert prepared["provider_method"] == "POST"
    assert prepared["provider_path"] == "transfers/v2/templates/outgoing"
    assert prepared["summary"]["destination_count"] == 1
    assert prepared["summary"]["package_count"] == 1
    assert "not itself proof" in prepared["summary"]["note"]


def test_transfer_confirmation_binds_provider_payload():
    engine, _, _ = _fixture()
    service = GovernedMetrcTransferActionService(engine)
    prepared = service.prepare(
        operation_type="transfer_template_create",
        payload=_create_payload(),
        state="MA",
        environment="sandbox",
        license_number="MP281234",
    )
    token = transfer_confirmation_token(
        prepared=prepared,
        state="MA",
        environment="sandbox",
        license_number="MP281234",
        confirmation_id="confirm-1",
    )
    changed = _create_payload()
    changed["template"]["Destinations"][0]["Packages"][0]["WholesalePrice"] = 250.0
    changed_prepared = service.prepare(
        operation_type="transfer_template_create",
        payload=changed,
        state="MA",
        environment="sandbox",
        license_number="MP281234",
    )
    assert token != transfer_confirmation_token(
        prepared=changed_prepared,
        state="MA",
        environment="sandbox",
        license_number="MP281234",
        confirmation_id="confirm-1",
    )


def test_verified_template_write_is_idempotent_in_global_ledger(monkeypatch):
    engine, org_id, facility_id = _fixture()
    service = GovernedMetrcTransferActionService(engine)
    payload = _create_payload()
    prepared = service.prepare(
        operation_type="transfer_template_create",
        payload=payload,
        state="MA",
        environment="sandbox",
        license_number="MP281234",
    )
    token = transfer_confirmation_token(
        prepared=prepared,
        state="MA",
        environment="sandbox",
        license_number="MP281234",
        confirmation_id="confirm-1",
    )
    calls = []

    def fake_execute(**kwargs):
        calls.append(kwargs)
        return {
            "passed": True,
            "stage": "complete",
            "operation_type": "transfer_template_create",
            "http_status": 200,
            "provider_id": "91",
            "last_modified": "2026-09-01T09:05:00-04:00",
            "request": {"method": "POST", "path": "transfers/v2/templates/outgoing"},
            "response": {"Ids": [91]},
            "readback": {"passed": True, "records": [{"provider_id": "91"}]},
            "message": "verified",
        }

    monkeypatch.setattr(actions_module, "execute_transfer_template_write", fake_execute)
    kwargs = dict(
        organization_id=org_id,
        facility_id=facility_id,
        actor="user-1",
        operation_type="transfer_template_create",
        payload=payload,
        confirmation_id="confirm-1",
        confirmation_token=token,
        reason="Prepare outgoing transfer template",
        state="MA",
        environment="sandbox",
        license_number="MP281234",
        integrator_api_key="integrator",
        user_api_key="user",
    )
    first = service.execute(**kwargs)
    second = service.execute(**kwargs)
    assert first["verified"] is True
    assert second["already_submitted"] is True
    assert len(calls) == 1
    row = TraceabilityBackofficeRepository(engine).list_transactions(org_id, facility_id)[0]
    assert row.status == "verified"
    assert row.entity_type == "transfer_template"
    assert row.external_reference == "91"


def test_unknown_template_write_requires_reconciliation(monkeypatch):
    engine, org_id, facility_id = _fixture()
    service = GovernedMetrcTransferActionService(engine)
    payload = _create_payload()
    prepared = service.prepare(
        operation_type="transfer_template_create",
        payload=payload,
        state="MA",
        environment="sandbox",
        license_number="MP281234",
    )
    token = transfer_confirmation_token(
        prepared=prepared,
        state="MA",
        environment="sandbox",
        license_number="MP281234",
        confirmation_id="confirm-2",
    )

    def fail(**kwargs):
        raise MetrcTransferEvaluationError("Metrc request timed out before a reliable response was received.")

    monkeypatch.setattr(actions_module, "execute_transfer_template_write", fail)
    result = service.execute(
        organization_id=org_id,
        facility_id=facility_id,
        actor="user-1",
        operation_type="transfer_template_create",
        payload=payload,
        confirmation_id="confirm-2",
        confirmation_token=token,
        reason="Prepare outgoing transfer template",
        state="MA",
        environment="sandbox",
        license_number="MP281234",
        integrator_api_key="integrator",
        user_api_key="user",
    )
    assert result["status"] == "reconciliation_required"
    row = TraceabilityBackofficeRepository(engine).list_transactions(org_id, facility_id)[0]
    assert row.retry_eligible is False
    assert row.mismatch_reason


def test_transfer_template_actions_fail_closed_outside_ma_sandbox():
    engine, _, _ = _fixture()
    service = GovernedMetrcTransferActionService(engine)
    for state, environment in (("MA", "production"), ("OR", "sandbox")):
        try:
            service.prepare(
                operation_type="transfer_template_create",
                payload=_create_payload(),
                state=state,
                environment=environment,
                license_number="MP281234",
            )
        except MetrcTransferActionError:
            pass
        else:
            raise AssertionError("Promoted transfer-template action crossed its MA sandbox boundary")
