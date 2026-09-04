from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.auth import RequestContext
from backend.app.routers import package_studio


def _plan():
    return package_studio.Plan(
        action_type="breakdown",
        inputs=[package_studio.InputPlan(lot_id="lot-1", quantity=10, unit="g")],
        outputs=[
            package_studio.OutputPlan(
                product_id="product-1",
                lot_code="out-1",
                inventory_quantity=10,
                inventory_unit="g",
                source_equivalent_quantity=10,
                source_equivalent_unit="g",
            )
        ],
        source_unit="g",
        reason="alpha mode regression",
    )


def _context():
    return RequestContext(
        user_id="operator-1",
        organization_id="org-1",
        facility_id="facility-1",
        role="operator",
    )


def test_doobielogic_sandbox_allows_local_package_studio_even_with_historical_metrc_link(monkeypatch):
    committed = SimpleNamespace(__dict__={"run_id": "run-1", "output_lot_ids": ["out-1"]})

    class FakePackageStudioService:
        def __init__(self, engine):
            self.engine = engine

        def commit(self, plan, *, organization_id, facility_id, actor):
            assert organization_id == "org-1"
            assert facility_id == "facility-1"
            assert actor == "operator-1"
            return committed

    monkeypatch.setattr(package_studio, "PackageStudioService", FakePackageStudioService)
    monkeypatch.setattr(package_studio, "_alpha_mode", lambda engine, context: SimpleNamespace(metrc_enabled=False))

    def should_not_scan_links(*args, **kwargs):
        raise AssertionError("Historical Metrc links must not gate local Package Studio in DoobieLogic Sandbox.")

    monkeypatch.setattr(package_studio, "_tracked_source_ids", should_not_scan_links)
    result = package_studio.commit(_plan(), context=_context(), engine=object())
    assert result["run_id"] == "run-1"


def test_metrc_sandbox_blocks_local_commit_for_tracked_source(monkeypatch):
    monkeypatch.setattr(package_studio, "_alpha_mode", lambda engine, context: SimpleNamespace(metrc_enabled=True))
    monkeypatch.setattr(package_studio, "_tracked_source_ids", lambda engine, context, payload: ["lot-1"])

    with pytest.raises(HTTPException) as exc:
        package_studio.commit(_plan(), context=_context(), engine=object())

    assert exc.value.status_code == 409
    assert "Metrc-tracked source package" in str(exc.value.detail)
