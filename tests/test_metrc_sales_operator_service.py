from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.services import metrc_sales_actions as actions_module
from backend.app.services.metrc_sales_actions import (
    GovernedMetrcSalesActionService,
    MetrcSalesActionError,
    sales_confirmation_token,
)
from modules.coman.models import Base, Facility, Organization
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.metrc_evaluation_sales import MetrcSalesEvaluationError


def _fixture():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        org = Organization(name="Retail Org", slug="retail-org")
        session.add(org)
        session.flush()
        facility = Facility(
            organization_id=org.id,
            name="Retail",
            code="RET",
            retail_enabled=True,
            production_enabled=False,
        )
        session.add(facility)
        session.flush()
        return engine, org.id, facility.id


def _receipt_payload():
    return {
        "sales_customer_type": "Consumer",
        "sales_date_time": "2026-09-10T09:30:00",
        "external_receipt_number": "DL-1001",
        "transactions": [
            {
                "package_label": "1A4000000000000000000001",
                "quantity": 1,
                "unit_of_measure": "Each",
                "total_amount": 25.0,
            }
        ],
    }


def test_prepare_uses_current_ma_v2_sales_contract_and_local_wall_clock_time():
    engine, _, _ = _fixture()
    service = GovernedMetrcSalesActionService(engine)
    prepared = service.prepare(
        operation_type="sales_receipt_create",
        payload=_receipt_payload(),
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
    )
    assert prepared["provider_method"] == "POST"
    assert prepared["provider_path"] == "sales/v2/receipts"
    assert prepared["provider_request_body"][0]["SalesDateTime"] == "2026-09-10T09:30:00"
    assert prepared["provider_request_body"][0]["ExternalReceiptNumber"] == "DL-1001"

    bad = _receipt_payload()
    bad["sales_date_time"] = "2026-09-10T13:30:00Z"
    try:
        service.prepare(
            operation_type="sales_receipt_create",
            payload=bad,
            state="MA",
            environment="sandbox",
            license_number="LIC-1",
        )
    except MetrcSalesActionError as exc:
        assert "without Z or a UTC offset" in str(exc)
    else:
        raise AssertionError("Metrc facility-local timestamp requirement was not enforced")


def test_confirmation_fingerprint_binds_payload_and_license():
    engine, _, _ = _fixture()
    service = GovernedMetrcSalesActionService(engine)
    prepared = service.prepare(
        operation_type="sales_receipt_create",
        payload=_receipt_payload(),
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
    )
    token = sales_confirmation_token(
        prepared=prepared,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        confirmation_id="confirm-1",
    )
    changed = _receipt_payload()
    changed["transactions"][0]["total_amount"] = 30.0
    changed_prepared = service.prepare(
        operation_type="sales_receipt_create",
        payload=changed,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
    )
    assert token != sales_confirmation_token(
        prepared=changed_prepared,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        confirmation_id="confirm-1",
    )


def test_verified_sales_write_runs_once_through_global_ledger(monkeypatch):
    engine, org_id, facility_id = _fixture()
    service = GovernedMetrcSalesActionService(engine)
    payload = _receipt_payload()
    prepared = service.prepare(
        operation_type="sales_receipt_create",
        payload=payload,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
    )
    token = sales_confirmation_token(
        prepared=prepared,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        confirmation_id="confirm-1",
    )
    calls = []

    def fake_execute(**kwargs):
        calls.append(kwargs)
        return {
            "passed": True,
            "stage": "complete",
            "operation_type": "sales_receipt_create",
            "http_status": 200,
            "provider_id": "44",
            "last_modified": "2026-09-10T09:31:00",
            "request": {"method": "POST", "path": "sales/v2/receipts"},
            "response": {"Ids": [44]},
            "readback": {"ok": True, "records": [{"provider_id": "44"}]},
            "message": "verified",
        }

    monkeypatch.setattr(actions_module, "execute_sales_evaluation_action", fake_execute)
    kwargs = dict(
        organization_id=org_id,
        facility_id=facility_id,
        actor="user-1",
        operation_type="sales_receipt_create",
        payload=payload,
        confirmation_id="confirm-1",
        confirmation_token=token,
        reason="Post verified receipt",
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator",
        user_api_key="user",
    )
    first = service.execute(**kwargs)
    second = service.execute(**kwargs)
    assert first["verified"] is True
    assert second["verified"] is True
    assert second["already_submitted"] is True
    assert len(calls) == 1

    rows = TraceabilityBackofficeRepository(engine).list_transactions(org_id, facility_id)
    assert len(rows) == 1
    assert rows[0].status == "verified"
    assert rows[0].external_reference == "44"


def test_uncertain_provider_result_requires_reconciliation_and_blocks_blind_retry(monkeypatch):
    engine, org_id, facility_id = _fixture()
    service = GovernedMetrcSalesActionService(engine)
    payload = _receipt_payload()
    prepared = service.prepare(
        operation_type="sales_receipt_create",
        payload=payload,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
    )
    token = sales_confirmation_token(
        prepared=prepared,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        confirmation_id="confirm-2",
    )

    def fail(**kwargs):
        raise MetrcSalesEvaluationError("Metrc request timed out before a reliable response was received.")

    monkeypatch.setattr(actions_module, "execute_sales_evaluation_action", fail)
    result = service.execute(
        organization_id=org_id,
        facility_id=facility_id,
        actor="user-1",
        operation_type="sales_receipt_create",
        payload=payload,
        confirmation_id="confirm-2",
        confirmation_token=token,
        reason="Post receipt",
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator",
        user_api_key="user",
    )
    assert result["status"] == "reconciliation_required"
    row = TraceabilityBackofficeRepository(engine).list_transactions(org_id, facility_id)[0]
    assert row.retry_eligible is False
    assert row.mismatch_reason


def test_promoted_sales_write_fails_closed_outside_ma_sandbox():
    engine, _, _ = _fixture()
    service = GovernedMetrcSalesActionService(engine)
    for state, environment in (("MA", "production"), ("OR", "sandbox")):
        try:
            service.prepare(
                operation_type="sales_receipt_create",
                payload=_receipt_payload(),
                state=state,
                environment=environment,
                license_number="LIC-1",
            )
        except MetrcSalesActionError:
            pass
        else:
            raise AssertionError("Promoted MA sandbox sales action crossed its jurisdiction/environment boundary")
