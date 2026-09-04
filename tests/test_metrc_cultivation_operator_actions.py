from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.services import metrc_cultivation_actions as subject


class FakeTraceability:
    def __init__(self):
        self.transaction = SimpleNamespace(id="tx-1", status="requested", external_reference="")
        self.transitions: list[str] = []
        self.attempts: list[dict] = []
        self.reconciliations: list[dict] = []
        self.create_payload: dict | None = None
        self.claim_allowed = True

    def create_transaction(self, **kwargs):
        self.create_payload = kwargs
        return self.transaction

    def claim_transition_logged(self, **kwargs):
        assert kwargs["expected_status"] == "requested"
        if not self.claim_allowed:
            self.transaction.status = "validated"
            return self.transaction, False
        self.transaction.status = kwargs["new_status"]
        self.transitions.append(kwargs["new_status"])
        return self.transaction, True

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


class FakeLinks:
    pass


def _prepared(operation: str = "plant_move", *, destination: str = "FLOWER B") -> dict:
    if operation == "plant_move":
        return {
            "operation_type": "plant_move",
            "evaluator_operation": "plant_location",
            "entity_type": "cultivation_plant",
            "entity_id": "plant-1",
            "provider_payload": {"id": 91, "label": "1A4PLANT1", "location": destination, "actual_date": "2026-09-04"},
            "provider_request_body": [{"Id": 91, "Label": "1A4PLANT1", "Location": destination, "ActualDate": "2026-09-04"}],
            "summary": {"title": "Move plant", "plant": "1A4PLANT1", "to_room": destination, "metrc_location": destination},
            "fingerprint_context": {"provider_plant_id": "91", "destination_room_id": "room-2", "destination_room_code": "FLOWER-B", "provider_room_id": "22", "provider_current_location": "FLOWER A"},
        }
    return {
        "operation_type": "plant_batch_vegetative",
        "evaluator_operation": "plant_batch_growthphase",
        "entity_type": "cultivation_group",
        "entity_id": "group-1",
        "provider_payload": {"name": "GMO-CLONES", "count": 2, "starting_tag": "1A4TAG001", "growth_phase": "Vegetative", "new_location": "VEG A", "growth_date": "2026-09-04"},
        "provider_request_body": [{"Name": "GMO-CLONES", "Count": 2, "StartingTag": "1A4TAG001", "GrowthPhase": "Vegetative", "NewLocation": "VEG A", "GrowthDate": "2026-09-04"}],
        "summary": {"title": "Move plant batch to vegetative", "group": "GMO-CLONES", "count": 2, "strain": "GMO", "metrc_location": "VEG A"},
        "fingerprint_context": {"group_provider_id": "41", "destination_room_id": "room-1", "destination_room_code": "VEG-A", "plant_ids": ["plant-1", "plant-2"]},
    }


def _service(prepared: dict) -> tuple[subject.MetrcCultivationActionService, FakeTraceability]:
    service = subject.MetrcCultivationActionService.__new__(subject.MetrcCultivationActionService)
    fake = FakeTraceability()
    service.engine = None
    service.traceability = fake
    service.links = FakeLinks()
    service.prepare = lambda **_kwargs: prepared
    return service, fake


def _token(prepared: dict, confirmation_id: str = "confirm-1") -> str:
    return subject.cultivation_confirmation_token(
        prepared=prepared,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        confirmation_id=confirmation_id,
    )


def _execute(service, prepared: dict, *, token: str | None = None):
    return service.execute(
        organization_id="org-1",
        facility_id="fac-1",
        actor="user-1",
        operation_type=prepared["operation_type"],
        entity_id=prepared["entity_id"],
        actual_date="2026-09-04",
        destination_room_id=str(prepared.get("fingerprint_context", {}).get("destination_room_id") or ""),
        starting_tag=str(prepared.get("provider_payload", {}).get("starting_tag") or ""),
        reason="Operator confirmed cultivation action",
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator-runtime",
        user_api_key="user-runtime",
        confirmation_id="confirm-1",
        confirmation_token=token or _token(prepared),
    )


def test_confirmation_binds_current_provider_and_local_fingerprint():
    reviewed = _prepared(destination="FLOWER B")
    changed = _prepared(destination="FLOWER C")
    assert _token(reviewed) != _token(changed)


def test_stale_confirmation_is_rejected_before_traceability_or_provider_call(monkeypatch: pytest.MonkeyPatch):
    reviewed = _prepared(destination="FLOWER B")
    current = _prepared(destination="FLOWER C")
    service, fake = _service(current)
    called = False

    def should_not_run(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("provider must not be called for a stale preview")

    monkeypatch.setattr(subject, "execute_lifecycle_evaluation_action", should_not_run)
    with pytest.raises(subject.MetrcCultivationActionError, match="changed after preview"):
        _execute(service, current, token=_token(reviewed))
    assert called is False
    assert fake.create_payload is None


def test_concurrent_confirmation_loser_never_dispatches(monkeypatch: pytest.MonkeyPatch):
    prepared = _prepared()
    service, fake = _service(prepared)
    fake.claim_allowed = False
    called = False

    def should_not_run(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("provider must not be called after losing the execution lease")

    monkeypatch.setattr(subject, "execute_lifecycle_evaluation_action", should_not_run)
    result = _execute(service, prepared)
    assert called is False
    assert result["already_submitted"] is True
    assert result["status"] == "validated"
    assert fake.transitions == []


def test_http_200_with_wrong_business_readback_never_applies_local_state(monkeypatch: pytest.MonkeyPatch):
    prepared = _prepared()
    service, fake = _service(prepared)
    local_called = False

    monkeypatch.setattr(
        subject,
        "execute_lifecycle_evaluation_action",
        lambda **_kwargs: {
            "passed": True,
            "stage": "complete",
            "http_status": 200,
            "provider_id": "91",
            "request": {"method": "PUT", "path": "plants/v2/location"},
            "response": {},
            "readback": {"ok": True, "records": [{"provider_id": "91", "source": {"Id": 91, "Label": "1A4PLANT1", "LocationName": "FLOWER A"}}]},
        },
    )
    service._verify_provider_state = lambda **_kwargs: {"matched": False, "differences": [{"field": "Location"}]}

    def should_not_apply(**_kwargs):
        nonlocal local_called
        local_called = True
        raise AssertionError("local state must wait for verified provider state")

    service._apply_local_verified_state = should_not_apply
    result = _execute(service, prepared)

    assert local_called is False
    assert result["verified"] is False
    assert result["status"] == "reconciliation_required"
    assert fake.transitions == ["validated", "queued", "submitted", "accepted", "reconciliation_required"]
    assert fake.reconciliations[-1]["retry_eligible"] is False


def test_provider_verified_local_failure_is_reconciliation_not_retry(monkeypatch: pytest.MonkeyPatch):
    prepared = _prepared()
    service, fake = _service(prepared)
    monkeypatch.setattr(
        subject,
        "execute_lifecycle_evaluation_action",
        lambda **_kwargs: {
            "passed": True,
            "stage": "complete",
            "http_status": 200,
            "provider_id": "91",
            "request": {"method": "PUT", "path": "plants/v2/location"},
            "response": {},
            "readback": {"ok": True, "records": [{"provider_id": "91"}]},
        },
    )
    service._verify_provider_state = lambda **_kwargs: {"matched": True, "record": {"provider_id": "91"}}

    def fail_local(**_kwargs):
        raise ValueError("database write failed")

    service._apply_local_verified_state = fail_local
    result = _execute(service, prepared)

    assert result["verified"] is False
    assert result["status"] == "reconciliation_required"
    assert fake.transitions == ["validated", "queued", "submitted", "accepted", "reconciliation_required"]
    reconciliation = fake.reconciliations[-1]
    assert reconciliation["retry_eligible"] is False
    assert reconciliation["evidence"]["provider_verified"] is True
    assert reconciliation["evidence"]["local_apply_failed"] is True
    assert reconciliation["evidence"]["blind_retry_allowed"] is False


def test_fully_verified_provider_and_local_state_reaches_verified(monkeypatch: pytest.MonkeyPatch):
    prepared = _prepared()
    service, fake = _service(prepared)
    monkeypatch.setattr(
        subject,
        "execute_lifecycle_evaluation_action",
        lambda **_kwargs: {
            "passed": True,
            "stage": "complete",
            "http_status": 200,
            "provider_id": "91",
            "request": {"method": "PUT", "path": "plants/v2/location"},
            "response": {},
            "readback": {"ok": True, "records": [{"provider_id": "91"}]},
        },
    )
    service._verify_provider_state = lambda **_kwargs: {"matched": True, "record": {"provider_id": "91"}}
    service._apply_local_verified_state = lambda **_kwargs: {"plant_id": "plant-1", "room_code": "FLOWER-B"}

    result = _execute(service, prepared)

    assert result["verified"] is True
    assert result["status"] == "verified"
    assert result["local_result"]["room_code"] == "FLOWER-B"
    assert fake.transitions == ["validated", "queued", "submitted", "accepted", "verified"]
    assert fake.reconciliations[-1]["mismatch_reason"] == ""


def test_vegetative_verification_reads_every_returned_provider_plant(monkeypatch: pytest.MonkeyPatch):
    prepared = _prepared("plant_batch_vegetative")
    service = subject.MetrcCultivationActionService.__new__(subject.MetrcCultivationActionService)
    calls: list[str] = []

    def read(**kwargs):
        provider_id = str(kwargs["path_parameters"]["id"])
        calls.append(provider_id)
        label = "1A4TAG001" if provider_id == "101" else "1A4TAG002"
        return {
            "ok": True,
            "records": [{
                "provider_id": provider_id,
                "label": label,
                "source": {
                    "Id": int(provider_id),
                    "Label": label,
                    "GrowthPhase": "Vegetative",
                    "LocationName": "VEG A",
                    "StrainName": "GMO",
                },
            }],
        }

    monkeypatch.setattr(subject, "fetch_metrc_resource", read)
    verification = service._verify_provider_state(
        prepared=prepared,
        evidence={"passed": True, "response": {"Ids": [101, 102]}},
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator-runtime",
        user_api_key="user-runtime",
    )

    assert verification["matched"] is True
    assert calls == ["101", "102"]
    assert [row["label"] for row in verification["plants"]] == ["1A4TAG001", "1A4TAG002"]


def test_vegetative_partial_id_response_fails_without_reading_partial_set(monkeypatch: pytest.MonkeyPatch):
    prepared = _prepared("plant_batch_vegetative")
    service = subject.MetrcCultivationActionService.__new__(subject.MetrcCultivationActionService)
    called = False

    def should_not_read(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("partial provider ID set must fail before per-ID reads")

    monkeypatch.setattr(subject, "fetch_metrc_resource", should_not_read)
    verification = service._verify_provider_state(
        prepared=prepared,
        evidence={"passed": True, "response": {"Ids": [101]}},
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator-runtime",
        user_api_key="user-runtime",
    )

    assert called is False
    assert verification["matched"] is False
    assert any(row["reason"] == "mutation_response_id_count_mismatch" for row in verification["differences"])
