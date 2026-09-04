from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.services import metrc_master_data_actions as subject


class FakeTraceability:
    def __init__(self):
        self.transaction = SimpleNamespace(
            id="tx-1",
            status="requested",
            external_reference="",
        )
        self.transitions: list[str] = []
        self.attempts: list[dict] = []
        self.reconciliations: list[dict] = []
        self.create_payload: dict | None = None

    def create_transaction(self, **kwargs):
        self.create_payload = kwargs
        return self.transaction

    def transition_logged(self, **kwargs):
        self.transaction.status = kwargs["new_status"]
        if kwargs.get("external_reference"):
            self.transaction.external_reference = kwargs["external_reference"]
        self.transitions.append(kwargs["new_status"])
        return self.transaction

    def record_attempt(self, **kwargs):
        self.attempts.append(kwargs)
        return SimpleNamespace(id="attempt-1")

    def record_reconciliation(self, **kwargs):
        self.reconciliations.append(kwargs)
        return self.transaction


def _token(operation: str, payload: dict, confirmation_id: str = "confirm-1") -> str:
    return subject.master_data_confirmation_token(
        operation_type=operation,
        payload=payload,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        confirmation_id=confirmation_id,
    )


def _service() -> tuple[subject.MetrcMasterDataActionService, FakeTraceability]:
    fake = FakeTraceability()
    service = subject.MetrcMasterDataActionService.__new__(subject.MetrcMasterDataActionService)
    service.traceability = fake
    return service, fake


def _execute(service, operation: str, payload: dict, *, token: str | None = None):
    confirmation_id = "confirm-1"
    return service.execute(
        organization_id="org-1",
        facility_id="facility-1",
        actor="user-1",
        operation_type=operation,
        payload=payload,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator",
        user_api_key="user",
        confirmation_id=confirmation_id,
        confirmation_token=token or _token(operation, payload, confirmation_id),
    )


def test_confirmation_token_changes_when_reviewed_payload_changes():
    first = _token("location_create", {"name": "Room A", "location_type_name": "Default"})
    second = _token("location_create", {"name": "Room B", "location_type_name": "Default"})
    assert first != second


def test_confirmation_token_rejects_unpromoted_action():
    with pytest.raises(subject.MetrcMasterDataActionError):
        _token("brand_create", {"name": "Reserve"})


def test_verified_write_records_full_traceability_lifecycle(monkeypatch: pytest.MonkeyPatch):
    service, fake = _service()
    payload = {"name": "Flower Room 2", "location_type_name": "Default"}
    monkeypatch.setattr(
        subject,
        "execute_master_data_evaluation_action",
        lambda **_kwargs: {
            "passed": True,
            "stage": "complete",
            "operation_type": "location_create",
            "http_status": 200,
            "provider_id": "123",
            "last_modified": "2026-09-04T10:15:00Z",
            "request": {"method": "POST", "path": "locations/v2/", "body": [{"Name": "Flower Room 2", "LocationTypeName": "Default"}]},
            "response": {"Id": 123},
            "readback": {"ok": True, "records": [{"provider_id": "123"}]},
            "message": "verified",
        },
    )

    result = _execute(service, "location_create", payload)

    assert result["ok"] is True
    assert result["verified"] is True
    assert result["status"] == "verified"
    assert result["external_reference"] == "123"
    assert fake.transitions == ["validated", "queued", "submitted", "accepted", "verified"]
    assert fake.create_payload["jurisdiction"] == "MA"
    assert fake.create_payload["environment"] == "sandbox"
    assert fake.create_payload["license_number"] == "LIC-1"
    assert fake.attempts[0]["http_status"] == 200
    assert fake.reconciliations[0]["mismatch_reason"] == ""


def test_http_200_without_exact_readback_requires_reconciliation(monkeypatch: pytest.MonkeyPatch):
    service, fake = _service()
    payload = {"name": "GMO"}
    monkeypatch.setattr(
        subject,
        "execute_master_data_evaluation_action",
        lambda **_kwargs: {
            "passed": False,
            "stage": "readback",
            "operation_type": "strain_create",
            "http_status": 200,
            "provider_id": "456",
            "last_modified": "",
            "request": {"method": "POST", "path": "strains/v2/", "body": [{"Name": "GMO"}]},
            "response": {"Id": 456},
            "readback": {"ok": True, "records": []},
            "message": "Exact readback did not verify.",
        },
    )

    result = _execute(service, "strain_create", payload)

    assert result["verified"] is False
    assert result["status"] == "reconciliation_required"
    assert fake.transitions == ["validated", "queued", "submitted", "accepted", "reconciliation_required"]
    assert fake.reconciliations[0]["retry_eligible"] is False


def test_uncertain_transport_error_blocks_blind_retry(monkeypatch: pytest.MonkeyPatch):
    service, fake = _service()
    payload = {"name": "GMO", "item_category": "Buds", "unit_of_measure": "Each"}

    def fail(**_kwargs):
        raise subject.MetrcEvaluationError("Metrc request failed before evaluation evidence could be captured: Timeout.")

    monkeypatch.setattr(subject, "execute_master_data_evaluation_action", fail)
    result = _execute(service, "item_create", payload)

    assert result["status"] == "reconciliation_required"
    assert fake.transitions == ["validated", "queued", "submitted", "reconciliation_required"]
    assert fake.reconciliations[0]["retry_eligible"] is False
    assert fake.reconciliations[0]["evidence"]["blind_retry_allowed"] is False


def test_changed_payload_cannot_reuse_confirmation_token():
    service, fake = _service()
    reviewed = {"name": "Room A", "location_type_name": "Default"}
    changed = {"name": "Room B", "location_type_name": "Default"}
    with pytest.raises(subject.MetrcMasterDataActionError, match="changed after preview"):
        _execute(service, "location_create", changed, token=_token("location_create", reviewed))
    assert fake.create_payload is None
