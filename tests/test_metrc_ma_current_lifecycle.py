import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.services import metrc_ma_current_lifecycle as lifecycle_module
from backend.app.services.metrc_ma_current_lifecycle import (
    GovernedMetrcMaCurrentLifecycleService,
    MetrcMaCurrentLifecycleError,
    lifecycle_confirmation_token,
)
from modules.coman.models import Base, Facility, Organization
from modules.traceability.backoffice import TraceabilityBackofficeRepository


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.content = b"{}" if payload is not None else b""
        self.text = ""

    def json(self):
        return self._payload


def _fixture(*, retail=True, production=True):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        org = Organization(name="MA Lifecycle Org", slug="ma-lifecycle-org")
        session.add(org)
        session.flush()
        facility = Facility(
            organization_id=org.id,
            name="MA Facility",
            code="MA",
            retail_enabled=retail,
            production_enabled=production,
        )
        session.add(facility)
        session.flush()
        return engine, org.id, facility.id


def _receipt_read(provider_id: int, *, is_final: bool):
    return {
        "ok": True,
        "http_status": 200,
        "records": [{
            "provider_id": str(provider_id),
            "source": {
                "Id": provider_id,
                "IsFinal": is_final,
                "ArchivedDate": None,
                "LastModified": "2026-09-10T10:00:00",
            },
        }],
    }


def _delivery_read(provider_id: int, *, voided_date=None):
    return {
        "ok": True,
        "http_status": 200,
        "records": [{
            "provider_id": str(provider_id),
            "source": {
                "Id": provider_id,
                "VoidedDate": voided_date,
                "SalesDeliveryState": "Active" if not voided_date else "Voided",
                "LastModified": "2026-09-10T10:00:00",
            },
        }],
    }


def _execute_kwargs(org_id, facility_id, operation, payload, token, confirmation="confirm-1"):
    return dict(
        organization_id=org_id,
        facility_id=facility_id,
        actor="user-1",
        operation_type=operation,
        payload=payload,
        confirmation_id=confirmation,
        confirmation_token=token,
        reason="Current MA v2 lifecycle test",
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator",
        user_api_key="user",
    )


def test_receipt_finalize_uses_documented_body_and_requires_isfinal_readback(monkeypatch):
    engine, org_id, facility_id = _fixture()
    service = GovernedMetrcMaCurrentLifecycleService(engine)
    state = {"final": False}

    def fake_fetch(**kwargs):
        assert kwargs["resource"] == "sales_receipts_by_id"
        assert kwargs["path_parameters"] == {"id": 44}
        return _receipt_read(44, is_final=state["final"])

    def fake_request(method, url, **kwargs):
        assert method == "PUT"
        assert url.endswith("/sales/v2/receipts/finalize")
        assert kwargs["params"] == {"licenseNumber": "LIC-1"}
        assert kwargs["json"] == [{"Id": 44}]
        state["final"] = True
        return FakeResponse(200)

    monkeypatch.setattr(lifecycle_module, "fetch_metrc_resource", fake_fetch)
    monkeypatch.setattr(lifecycle_module.requests, "request", fake_request)
    prepared = service.prepare(
        operation_type="sales_receipt_finalize",
        payload={"id": 44},
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator",
        user_api_key="user",
    )
    assert prepared["provider_request_body"] == [{"Id": 44}]
    assert prepared["provider_prestate"]["is_final"] is False
    token = lifecycle_confirmation_token(
        prepared=prepared,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        confirmation_id="confirm-1",
    )
    result = service.execute(**_execute_kwargs(org_id, facility_id, "sales_receipt_finalize", {"id": 44}, token))
    assert result["verified"] is True
    row = TraceabilityBackofficeRepository(engine).list_transactions(org_id, facility_id)[0]
    assert row.status == "verified"
    assert row.external_reference == "44"


def test_receipt_unfinalize_rejects_already_unfinalized_and_missing_semantic_flag(monkeypatch):
    engine, _, _ = _fixture()
    service = GovernedMetrcMaCurrentLifecycleService(engine)

    monkeypatch.setattr(lifecycle_module, "fetch_metrc_resource", lambda **kwargs: _receipt_read(45, is_final=False))
    try:
        service.prepare(
            operation_type="sales_receipt_unfinalize",
            payload={"id": 45},
            state="MA",
            environment="sandbox",
            license_number="LIC-1",
            integrator_api_key="integrator",
            user_api_key="user",
        )
    except MetrcMaCurrentLifecycleError as exc:
        assert "already reports" in str(exc)
    else:
        raise AssertionError("Already-unfinalized receipt was not blocked")

    def no_flag(**kwargs):
        return {"ok": True, "http_status": 200, "records": [{"provider_id": "46", "source": {"Id": 46}}]}

    monkeypatch.setattr(lifecycle_module, "fetch_metrc_resource", no_flag)
    try:
        service.prepare(
            operation_type="sales_receipt_finalize",
            payload={"id": 46},
            state="MA",
            environment="sandbox",
            license_number="LIC-1",
            integrator_api_key="integrator",
            user_api_key="user",
        )
    except MetrcMaCurrentLifecycleError as exc:
        assert "IsFinal" in str(exc)
    else:
        raise AssertionError("Receipt finalization inferred state without IsFinal")


def test_delivery_delete_verifies_voideddate_not_merely_http_200(monkeypatch):
    engine, org_id, facility_id = _fixture()
    service = GovernedMetrcMaCurrentLifecycleService(engine)
    state = {"voided": None}

    def fake_fetch(**kwargs):
        return _delivery_read(88, voided_date=state["voided"])

    def fake_request(method, url, **kwargs):
        assert method == "DELETE"
        assert url.endswith("/sales/v2/deliveries/88")
        assert "json" not in kwargs
        state["voided"] = "2026-09-10T10:05:00"
        return FakeResponse(200)

    monkeypatch.setattr(lifecycle_module, "fetch_metrc_resource", fake_fetch)
    monkeypatch.setattr(lifecycle_module.requests, "request", fake_request)
    prepared = service.prepare(
        operation_type="sales_delivery_delete",
        payload={"id": 88},
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator",
        user_api_key="user",
    )
    token = lifecycle_confirmation_token(
        prepared=prepared,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        confirmation_id="confirm-1",
    )
    result = service.execute(**_execute_kwargs(org_id, facility_id, "sales_delivery_delete", {"id": 88}, token))
    assert result["verified"] is True


def test_template_delete_requires_complete_preflight_and_proves_absence_after_archive(monkeypatch):
    engine, org_id, facility_id = _fixture()
    service = GovernedMetrcMaCurrentLifecycleService(engine)
    state = {"present": True}

    def fake_pages(**kwargs):
        assert kwargs["resource"] == "transfer_templates_outgoing"
        records = []
        if state["present"]:
            records = [{
                "provider_id": "77",
                "name": "Wholesale Route",
                "source": {"TransferTemplateId": 77, "Name": "Wholesale Route", "LastModified": "2026-09-10T10:00:00"},
            }]
        return {"passed": True, "page_count": 1, "total_pages": 1, "records": records}

    def fake_request(method, url, **kwargs):
        assert method == "DELETE"
        assert url.endswith("/transfers/v2/templates/outgoing/77")
        assert "json" not in kwargs
        state["present"] = False
        return FakeResponse(200)

    monkeypatch.setattr(lifecycle_module, "fetch_all_metrc_resource_pages", fake_pages)
    monkeypatch.setattr(lifecycle_module.requests, "request", fake_request)
    prepared = service.prepare(
        operation_type="transfer_template_delete",
        payload={"transfer_template_id": 77},
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator",
        user_api_key="user",
    )
    assert prepared["provider_prestate"]["present"] is True
    assert prepared["summary"]["note"]
    token = lifecycle_confirmation_token(
        prepared=prepared,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        confirmation_id="confirm-1",
    )
    result = service.execute(**_execute_kwargs(org_id, facility_id, "transfer_template_delete", {"transfer_template_id": 77}, token))
    assert result["verified"] is True


def test_uncertain_write_is_reconciliation_required_and_never_blindly_retried(monkeypatch):
    engine, org_id, facility_id = _fixture()
    service = GovernedMetrcMaCurrentLifecycleService(engine)
    monkeypatch.setattr(lifecycle_module, "fetch_metrc_resource", lambda **kwargs: _receipt_read(50, is_final=False))

    def timeout(*args, **kwargs):
        raise requests.Timeout("unknown outcome")

    monkeypatch.setattr(lifecycle_module.requests, "request", timeout)
    prepared = service.prepare(
        operation_type="sales_receipt_finalize",
        payload={"id": 50},
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator",
        user_api_key="user",
    )
    token = lifecycle_confirmation_token(
        prepared=prepared,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        confirmation_id="confirm-1",
    )
    result = service.execute(**_execute_kwargs(org_id, facility_id, "sales_receipt_finalize", {"id": 50}, token))
    assert result["status"] == "reconciliation_required"
    row = TraceabilityBackofficeRepository(engine).list_transactions(org_id, facility_id)[0]
    assert row.retry_eligible is False
    assert row.mismatch_reason


def test_current_lifecycle_writes_fail_closed_outside_verified_ma_sandbox(monkeypatch):
    engine, _, _ = _fixture()
    service = GovernedMetrcMaCurrentLifecycleService(engine)
    for state, environment in (("MA", "production"), ("OR", "sandbox")):
        try:
            service.prepare(
                operation_type="sales_receipt_finalize",
                payload={"id": 1},
                state=state,
                environment=environment,
                license_number="LIC-1",
                integrator_api_key="integrator",
                user_api_key="user",
            )
        except MetrcMaCurrentLifecycleError:
            pass
        else:
            raise AssertionError("Current MA lifecycle action crossed jurisdiction/environment boundary")
