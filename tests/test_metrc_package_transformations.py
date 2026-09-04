from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

from backend.app.services import metrc_package_transformations as transformations
from backend.app.services.metrc_package_transformations import (
    GovernedMetrcPackageTransformationService,
    MetrcPackageTransformationError,
    package_transformation_confirmation_token,
)
from modules.package_studio.service import (
    PackageStudioInputPlan,
    PackageStudioOutputPlan,
    PackageStudioPlan,
)


class FakeTraceability:
    def __init__(self):
        self.transaction = SimpleNamespace(id="tx-1", status="requested", external_reference="")
        self.attempts = []
        self.reconciliations = []
        self.created = 0

    def create_transaction(self, **kwargs):
        self.created += 1
        return self.transaction

    def claim_transition_logged(self, **kwargs):
        if self.transaction.status != kwargs["expected_status"]:
            return self.transaction, False
        self.transaction.status = kwargs["new_status"]
        return self.transaction, True

    def transition_logged(self, **kwargs):
        self.transaction.status = kwargs["new_status"]
        if kwargs.get("external_reference"):
            self.transaction.external_reference = kwargs["external_reference"]
        return self.transaction

    def record_attempt(self, **kwargs):
        self.attempts.append(kwargs)
        return SimpleNamespace()

    def get_transaction(self, organization_id, facility_id, transaction_id):
        return self.transaction

    def record_reconciliation(self, **kwargs):
        self.reconciliations.append(kwargs)
        return self.transaction


def _plan(*, loss=0.0):
    return PackageStudioPlan(
        action_type="breakdown",
        inputs=(PackageStudioInputPlan(lot_id="source-lot", quantity=10, unit="g"),),
        outputs=(
            PackageStudioOutputPlan(
                product_id="product-1",
                lot_code="OUT-1",
                inventory_quantity=5,
                inventory_unit="g",
                source_equivalent_quantity=10,
                source_equivalent_unit="g",
                compliance_package_id="TAG-1",
            ),
        ),
        loss_quantity=loss,
        source_unit="g",
        reason="tracked transform",
    )


def _prepared(output_count=1):
    rows = []
    for position in range(1, output_count + 1):
        rows.append(
            {
                "position": position,
                "lot_code": f"OUT-{position}",
                "product_id": "product-1",
                "item": "GMO Flower",
                "tag": f"TAG-{position}",
                "inventory_quantity": 5.0,
                "inventory_unit": "g",
                "source_equivalent_quantity": 5.0,
                "provider_payload": {"tag": f"TAG-{position}"},
                "provider_request_body": [{"Tag": f"TAG-{position}"}],
            }
        )
    return {
        "operation_type": "package_studio_transform",
        "entity_type": "inventory_lot",
        "entity_id": "source-lot",
        "actual_date": "2026-09-04",
        "summary": {"title": "Tracked transformation", "outputs": []},
        "provider_outputs": rows,
        "expected_source_quantity": 90.0,
        "fingerprint_context": {
            "source_provider_id": "77",
            "source_provider_label": "SOURCE-TAG",
            "source_local_unit": "g",
            "source_local_balance": 100.0,
            "source_quantity": 10.0,
            "outputs": [{"position": row["position"], "tag": row["tag"]} for row in rows],
        },
    }


def _child_evidence(provider_id, tag, *, status=200):
    if status != 200:
        return {
            "http_status": status,
            "passed": False,
            "provider_id": "",
            "request": {"method": "POST", "path": "packages/v2"},
            "response": {"error": "provider failure"},
            "message": f"Metrc returned HTTP {status}",
        }
    return {
        "http_status": 200,
        "passed": True,
        "provider_id": str(provider_id),
        "request": {"method": "POST", "path": "packages/v2"},
        "response": {"Id": provider_id},
        "message": "accepted",
        "readback": {
            "ok": True,
            "records": [
                {
                    "provider_id": str(provider_id),
                    "label": tag,
                    "quantity": 5.0,
                    "unit_of_measure": "Grams",
                    "source": {
                        "Id": provider_id,
                        "Label": tag,
                        "ItemName": "GMO Flower",
                        "Quantity": 5.0,
                        "UnitOfMeasureName": "Grams",
                        "IsFinished": False,
                    },
                }
            ],
        },
    }


def test_tracked_transform_rejects_unreported_loss_before_provider_work():
    service = GovernedMetrcPackageTransformationService(create_engine("sqlite+pysqlite:///:memory:", future=True))
    with pytest.raises(MetrcPackageTransformationError) as exc:
        service.prepare(
            organization_id="org",
            facility_id="facility",
            plan=_plan(loss=1.0),
            actual_date="2026-09-04",
            state="MA",
            environment="sandbox",
            license_number="LIC-1",
            integrator_api_key="integrator",
            user_api_key="user",
        )
    assert "governed Metrc adjustment/waste reason" in str(exc.value)


def test_stale_confirmation_is_rejected_before_traceability_or_provider_dispatch(monkeypatch):
    service = GovernedMetrcPackageTransformationService(create_engine("sqlite+pysqlite:///:memory:", future=True))
    fake = FakeTraceability()
    service.traceability = fake
    prepared = _prepared()
    monkeypatch.setattr(service, "prepare", lambda **kwargs: prepared)

    with pytest.raises(MetrcPackageTransformationError) as exc:
        service.execute(
            organization_id="org",
            facility_id="facility",
            actor="operator",
            plan=_plan(),
            actual_date="2026-09-04",
            confirmation_id="confirm-1",
            confirmation_token="stale-token",
            state="MA",
            environment="sandbox",
            license_number="LIC-1",
            integrator_api_key="integrator",
            user_api_key="user",
        )
    assert "changed after preview" in str(exc.value)
    assert fake.created == 0


def test_partial_provider_creation_enters_reconciliation_and_never_blind_retries(monkeypatch):
    service = GovernedMetrcPackageTransformationService(create_engine("sqlite+pysqlite:///:memory:", future=True))
    fake = FakeTraceability()
    service.traceability = fake
    prepared = _prepared(output_count=2)
    monkeypatch.setattr(service, "prepare", lambda **kwargs: prepared)
    calls = []

    def execute_provider(**kwargs):
        calls.append(kwargs["payload"]["tag"])
        if len(calls) == 1:
            return _child_evidence("101", "TAG-1")
        return _child_evidence("", "TAG-2", status=500)

    monkeypatch.setattr(transformations, "execute_lifecycle_evaluation_action", execute_provider)
    token = package_transformation_confirmation_token(
        prepared=prepared,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        confirmation_id="confirm-1",
    )
    result = service.execute(
        organization_id="org",
        facility_id="facility",
        actor="operator",
        plan=_plan(),
        actual_date="2026-09-04",
        confirmation_id="confirm-1",
        confirmation_token=token,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator",
        user_api_key="user",
    )

    assert result["status"] == "reconciliation_required"
    assert calls == ["TAG-1", "TAG-2"]
    assert result["verified_outputs"][0]["provider_id"] == "101"
    assert fake.reconciliations[-1]["retry_eligible"] is False
    evidence = fake.reconciliations[-1]["evidence"]
    assert evidence["provider_atomic"] is False
    assert evidence["blind_retry_allowed"] is False


def test_provider_verified_but_local_commit_failure_reconciles_without_second_provider_write(monkeypatch):
    service = GovernedMetrcPackageTransformationService(create_engine("sqlite+pysqlite:///:memory:", future=True))
    fake = FakeTraceability()
    service.traceability = fake
    prepared = _prepared()
    monkeypatch.setattr(service, "prepare", lambda **kwargs: prepared)
    provider_calls = []

    def execute_provider(**kwargs):
        provider_calls.append(kwargs["payload"]["tag"])
        return _child_evidence("101", "TAG-1")

    monkeypatch.setattr(transformations, "execute_lifecycle_evaluation_action", execute_provider)
    monkeypatch.setattr(
        service,
        "_fresh_package",
        lambda **kwargs: {
            "readback": {
                "ok": True,
                "records": [
                    {
                        "provider_id": "77",
                        "label": "SOURCE-TAG",
                        "quantity": 90.0,
                        "unit_of_measure": "Grams",
                        "source": {"Id": 77, "Label": "SOURCE-TAG", "Quantity": 90.0, "UnitOfMeasureName": "Grams"},
                    }
                ],
            },
            "snapshot": {},
        },
    )

    class FailingPackageStudio:
        def __init__(self, engine):
            pass

        def commit(self, *args, **kwargs):
            raise ValueError("local ledger race")

    monkeypatch.setattr(transformations, "PackageStudioService", FailingPackageStudio)
    token = package_transformation_confirmation_token(
        prepared=prepared,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        confirmation_id="confirm-2",
    )
    result = service.execute(
        organization_id="org",
        facility_id="facility",
        actor="operator",
        plan=_plan(),
        actual_date="2026-09-04",
        confirmation_id="confirm-2",
        confirmation_token=token,
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator",
        user_api_key="user",
    )

    assert result["status"] == "reconciliation_required"
    assert provider_calls == ["TAG-1"]
    assert fake.reconciliations[-1]["retry_eligible"] is False
    assert fake.reconciliations[-1]["evidence"]["local_commit_failed"] is True
