from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine

from backend.app.services import metrc_natural_sync
from backend.app.services.metrc_sync_policy import MetrcPolicySyncControlService


def test_full_sync_summary_preserves_zero_accepted_and_counts_restrictions(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    class StubBootstrap:
        def __init__(self, _engine):
            pass

        def sync(self, **_kwargs):
            return {
                "totals": {"failed": 0, "records": 4},
                "resources": [
                    {
                        "resource": "packages",
                        "status": "succeeded",
                        "record_count": 3,
                        "accepted_count": 0,
                        "duplicate_count": 3,
                        "transport": "metrc_authenticated_full",
                        "hydration_checkpoint": {"status": "initial-full"},
                    },
                    {
                        "resource": "sales_receipts",
                        "status": "succeeded",
                        "record_count": 0,
                        "accepted_count": 0,
                        "duplicate_count": 0,
                        "transport": "metrc_authenticated_full",
                        "hydration_checkpoint": {"status": "permission-skipped"},
                    },
                    {
                        "resource": "strains",
                        "status": "succeeded",
                        "record_count": 1,
                        "accepted_count": 1,
                        "duplicate_count": 0,
                        "transport": "metrc_authenticated_full",
                        "hydration_checkpoint": {"status": "initial-full"},
                    },
                ],
            }

    monkeypatch.setattr(
        metrc_natural_sync,
        "ResilientSnapshottingMetrcFacilityBootstrapService",
        StubBootstrap,
    )

    metrc = SimpleNamespace(
        license_number="SF-SBX-MA-4-11701",
        state="MA",
        environment="sandbox",
        integrator_api_key="integrator",
        user_api_key="user",
    )
    result = MetrcPolicySyncControlService(engine)._run_full(
        organization_id="org-summary",
        facility_id="fac-summary",
        metrc=metrc,
        actor="tester",
        reason="baseline_required",
    )

    package = next(row for row in result["resources"] if row["resource"] == "packages")
    assert package["accepted_count"] == 0
    assert result["totals"] == {
        "records": 4,
        "accepted": 1,
        "duplicates": 3,
        "errors": 1,
        "restrictions": 1,
    }


def test_full_sync_summary_counts_legacy_skipped_resource_as_restriction(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    class StubBootstrap:
        def __init__(self, _engine):
            pass

        def sync(self, **_kwargs):
            return {
                "totals": {"failed": 1, "records": 0},
                "resources": [
                    {
                        "resource": "processing_jobs",
                        "status": "skipped",
                        "record_count": 0,
                        "accepted_count": 0,
                        "duplicate_count": 0,
                    },
                    {
                        "resource": "other_resource",
                        "status": "failed",
                        "record_count": 0,
                        "accepted_count": 0,
                        "duplicate_count": 0,
                    },
                ],
            }

    monkeypatch.setattr(
        metrc_natural_sync,
        "ResilientSnapshottingMetrcFacilityBootstrapService",
        StubBootstrap,
    )
    metrc = SimpleNamespace(
        license_number="SF-SBX-MA-4-11701",
        state="MA",
        environment="sandbox",
        integrator_api_key="integrator",
        user_api_key="user",
    )
    result = MetrcPolicySyncControlService(engine)._run_full(
        organization_id="org-summary",
        facility_id="fac-summary",
        metrc=metrc,
        actor="tester",
        reason="baseline_required",
    )

    assert result["totals"]["restrictions"] == 1
    assert result["totals"]["errors"] == 2
