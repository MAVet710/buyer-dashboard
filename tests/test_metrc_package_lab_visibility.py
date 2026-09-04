from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_package_360_surfaces_cached_metrc_lab_results_with_explicit_live_verification():
    package_360 = (ROOT / "frontend/src/components/Package360Window.tsx").read_text(encoding="utf-8")
    lab_panel = (ROOT / "frontend/src/components/MetrcPackageLabResults.tsx").read_text(encoding="utf-8")

    assert 'import { MetrcPackageLabResults } from "./MetrcPackageLabResults";' in package_360
    assert '<MetrcPackageLabResults lotId={data.package.id}' in package_360
    assert "/api/v1/inventory/regulatory-detail/local/inventory_lot/" in lab_panel
    assert "/lab-results/live" in lab_panel
    assert "Verify live" in lab_panel
    assert "Cached package-specific regulatory evidence loads from DoobieLogic" in lab_panel
    assert "network_request_made" in lab_panel


def test_package_lab_routes_are_statically_owned_by_inventory_reconciliation():
    inventory_reconciliation = (ROOT / "backend/app/routers/inventory_reconciliation.py").read_text(encoding="utf-8")
    assert "from .metrc_package_lab_detail import router as metrc_package_lab_detail_router" in inventory_reconciliation
    assert "router.include_router(metrc_package_lab_detail_router)" in inventory_reconciliation
