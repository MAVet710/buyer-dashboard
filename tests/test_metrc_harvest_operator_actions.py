from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.services import metrc_harvest_execution as subject
from backend.app.services.metrc_harvest_actions import harvest_confirmation_token


class FakeTraceability:
    def __init__(self):
        self.transaction = SimpleNamespace(id="tx-harvest", status="requested", external_reference="")
        self.transitions: list[str] = []
        self.attempts: list[dict] = []
        self.reconciliations: list[dict] = []
        self.claim_allowed = True

    def create_transaction(self, **_kwargs):
        return self.transaction

    def claim_transition_logged(self, **kwargs):
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
        return SimpleNamespace(id=f"attempt-{len(self.attempts)}")

    def record_reconciliation(self, **kwargs):
        self.reconciliations.append(kwargs)
        return self.transaction


def _prepared_start() -> dict:
    payloads = [
        {"plant": "TAG-1", "weight": 100.0, "unit_of_weight": "Grams", "drying_location": "DRY-A", "harvest_name": "HARV-1", "actual_date": "2026-09-04"},
        {"plant": "TAG-2", "weight": 50.0, "unit_of_weight": "Grams", "drying_location": "DRY-A", "harvest_name": "HARV-1", "actual_date": "2026-09-04"},
    ]
    return {
        "operation_type": "harvest_start",
        "evaluator_operation": "plant_harvest",
        "entity_type": "cultivation_harvest",
        "entity_id": "harvest-local",
        "provider_payloads": payloads,
        "provider_request_body": [{"Plant": row["plant"]} for row in payloads],
        "summary": {"title": "Start harvest in Metrc", "harvest": "HARV-1", "plant_count": 2, "provider_atomic": False},
        "fingerprint_context": {
            "plant_provider_context": [
                {"local_plant_id": "plant-1", "provider_plant_id": "901", "provider_label": "TAG-1", "wet_weight_g": 100.0},
                {"local_plant_id": "plant-2", "provider_plant_id": "902", "provider_label": "TAG-2", "wet_weight_g": 50.0},
            ],
            "drying_room_id": "room-1",
            "drying_room_code": "DRY-A",
            "reason": "Harvest",
        },
    }


def _evidence(provider_id: str, weight: float) -> dict:
    return {
        "passed": True,
        "http_status": 200,
        "provider_id": provider_id,
        "stage": "complete",
        "request": {"method": "PUT"},
        "response": {"Ids": [int(provider_id)]},
        "readback": {
            "ok": True,
            "http_status": 200,
            "records": [{"provider_id": provider_id, "source": {"Id": int(provider_id), "Name": "HARV-1", "DryingLocationName": "DRY-A", "CurrentWeight": weight}}],
        },
    }


def _plant_read(provider_id: str, harvest_id: str = "71") -> dict:
    return {
        "ok": True,
        "http_status": 200,
        "records": [{"provider_id": provider_id, "source": {"Id": int(provider_id), "HarvestId": int(harvest_id), "HarvestName": "HARV-1", "GrowthPhase": "Harvested"}}],
    }


def _service(monkeypatch: pytest.MonkeyPatch, prepared: dict):
    service = subject.GovernedMetrcHarvestActionService.__new__(subject.GovernedMetrcHarvestActionService)
    fake = FakeTraceability()
    service.traceability = fake
    monkeypatch.setattr(service, "prepare", lambda **_kwargs: prepared)
    return service, fake


def _execute(service, prepared: dict):
    confirmation_id = "confirm-1"
    token = harvest_confirmation_token(prepared=prepared, state="MA", environment="sandbox", license_number="LIC-1", confirmation_id=confirmation_id)
    return service.execute(
        organization_id="org-1", facility_id="fac-1", actor="user-1",
        operation_type="harvest_start", harvest_id="harvest-local", actual_date="2026-09-04",
        state="MA", environment="sandbox", license_number="LIC-1",
        integrator_api_key="integrator", user_api_key="user",
        confirmation_id=confirmation_id, confirmation_token=token,
    )


def test_composite_start_verifies_every_plant_before_local_apply(monkeypatch: pytest.MonkeyPatch):
    prepared = _prepared_start()
    service, fake = _service(monkeypatch, prepared)
    evidences = iter([_evidence("71", 100.0), _evidence("71", 150.0)])
    monkeypatch.setattr(subject, "execute_lifecycle_evaluation_action", lambda **_kwargs: next(evidences))
    monkeypatch.setattr(subject, "fetch_metrc_resource", lambda **kwargs: _plant_read(str(kwargs["path_parameters"]["id"])))
    monkeypatch.setattr(service, "_apply_start_local", lambda **_kwargs: {"local": "reconciled"})

    result = _execute(service, prepared)

    assert result["verified"] is True
    assert fake.transitions == ["validated", "queued", "submitted", "accepted", "verified"]
    assert len(fake.attempts) == 2
    assert fake.reconciliations[-1]["evidence"]["local_reconciled"] is True


def test_second_plant_different_harvest_id_stops_in_reconciliation(monkeypatch: pytest.MonkeyPatch):
    prepared = _prepared_start()
    service, fake = _service(monkeypatch, prepared)
    evidences = iter([_evidence("71", 100.0), _evidence("72", 50.0)])
    monkeypatch.setattr(subject, "execute_lifecycle_evaluation_action", lambda **_kwargs: next(evidences))
    monkeypatch.setattr(subject, "fetch_metrc_resource", lambda **kwargs: _plant_read(str(kwargs["path_parameters"]["id"])))
    local_called = False
    def local(**_kwargs):
        nonlocal local_called
        local_called = True
        return {}
    monkeypatch.setattr(service, "_apply_start_local", local)

    result = _execute(service, prepared)

    assert result["status"] == "reconciliation_required"
    assert local_called is False
    assert fake.transitions[-1] == "reconciliation_required"
    assert fake.reconciliations[-1]["evidence"]["provider_atomic"] is False


def test_unknown_second_plant_after_first_success_blocks_blind_retry(monkeypatch: pytest.MonkeyPatch):
    prepared = _prepared_start()
    service, fake = _service(monkeypatch, prepared)
    calls = 0
    def execute(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _evidence("71", 100.0)
        raise subject.MetrcLifecycleEvaluationError("timeout")
    monkeypatch.setattr(subject, "execute_lifecycle_evaluation_action", execute)
    monkeypatch.setattr(subject, "fetch_metrc_resource", lambda **kwargs: _plant_read(str(kwargs["path_parameters"]["id"])))
    monkeypatch.setattr(service, "_apply_start_local", lambda **_kwargs: pytest.fail("local apply must not run"))

    result = _execute(service, prepared)

    assert result["status"] == "reconciliation_required"
    assert fake.reconciliations[-1]["retry_eligible"] is False
    assert fake.reconciliations[-1]["evidence"]["blind_retry_allowed"] is False


def test_same_harvest_id_but_wrong_aggregate_weight_requires_reconciliation(monkeypatch: pytest.MonkeyPatch):
    prepared = _prepared_start()
    service, _fake = _service(monkeypatch, prepared)
    evidences = iter([_evidence("71", 99.0), _evidence("71", 150.0)])
    monkeypatch.setattr(subject, "execute_lifecycle_evaluation_action", lambda **_kwargs: next(evidences))
    monkeypatch.setattr(subject, "fetch_metrc_resource", lambda **kwargs: _plant_read(str(kwargs["path_parameters"]["id"])))
    monkeypatch.setattr(service, "_apply_start_local", lambda **_kwargs: pytest.fail("local apply must not run"))

    result = _execute(service, prepared)

    assert result["status"] == "reconciliation_required"


def test_concurrent_confirmation_loser_never_dispatches(monkeypatch: pytest.MonkeyPatch):
    prepared = _prepared_start()
    service, fake = _service(monkeypatch, prepared)
    fake.claim_allowed = False
    called = False
    def provider(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("provider dispatch must not run")
    monkeypatch.setattr(subject, "execute_lifecycle_evaluation_action", provider)

    result = _execute(service, prepared)

    assert called is False
    assert result["already_submitted"] is True
    assert result["status"] == "validated"
