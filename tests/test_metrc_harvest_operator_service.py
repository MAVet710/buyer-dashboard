from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from backend.app.services import metrc_harvest_operator_service as subject


class FakeTraceability:
    def __init__(self):
        self.reconciliations: list[dict] = []
        self.transitions: list[dict] = []

    def record_reconciliation(self, **kwargs):
        self.reconciliations.append(kwargs)
        return kwargs

    def transition_logged(self, **kwargs):
        self.transitions.append(kwargs)
        return SimpleNamespace(
            id=kwargs["transaction_id"],
            status=kwargs["new_status"],
            external_reference=kwargs.get("external_reference", ""),
        )


def test_verified_harvest_waste_uses_python_date_for_local_persistence(monkeypatch):
    captured: dict = {}

    class FakeCompliance:
        def __init__(self, engine):
            captured["engine"] = engine

        def record_waste(self, organization_id, facility_id, **kwargs):
            captured["organization_id"] = organization_id
            captured["facility_id"] = facility_id
            captured.update(kwargs)
            return {"id": "waste-local"}

    monkeypatch.setattr(subject, "MetrcProcessComplianceService", FakeCompliance)
    service = subject.MetrcHarvestOperatorService.__new__(subject.MetrcHarvestOperatorService)
    service.engine = object()
    prepared = {
        "operation_type": "harvest_waste",
        "entity_id": "harvest-local",
        "provider_payload": {"actual_date": "2026-09-04", "waste_weight": 12.5},
        "fingerprint_context": {
            "waste_method": "Compost",
            "waste_reason": "Trim loss",
            "waste_location": "WASTE-A",
            "measurement_basis": "wet",
        },
    }

    result = service._apply_single_local(
        organization_id="org-1",
        facility_id="facility-1",
        actor="operator-1",
        transaction_id="tx-1",
        prepared=prepared,
        all_waste_reported=False,
    )

    assert result == {"id": "waste-local"}
    assert captured["waste_date"] == date(2026, 9, 4)
    assert isinstance(captured["waste_date"], date)
    assert captured["provider_confirmed"] is True


def test_uncertain_single_write_reconciliation_records_provider_atomic_true():
    service = subject.MetrcHarvestOperatorService.__new__(subject.MetrcHarvestOperatorService)
    service.traceability = FakeTraceability()
    transaction = SimpleNamespace(id="tx-single", status="submitted", external_reference="")
    prepared = {
        "operation_type": "harvest_waste",
        "summary": {"title": "Record harvest waste"},
        "fingerprint_context": {"provider_harvest_id": "71"},
    }

    result = service._composite_reconciliation(
        organization_id="org-1",
        facility_id="facility-1",
        actor="operator-1",
        transaction=transaction,
        prepared=prepared,
        outcomes=[{"status": "unknown", "message": "timeout"}],
        message="Provider outcome is unknown.",
        provider_reference="71",
    )

    evidence = service.traceability.reconciliations[-1]["evidence"]
    assert evidence["provider_atomic"] is True
    assert evidence["blind_retry_allowed"] is False
    assert service.traceability.reconciliations[-1]["retry_eligible"] is False
    assert result["status"] == "reconciliation_required"
