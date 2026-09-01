from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import backend.app.main as main_module
from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.main import app, settings
from modules.coman.demo_data import ensure_coman_demo_dataset
from modules.coman.models import Base
from services.demo_data import build_demo_payload


ROOT = Path(__file__).resolve().parents[1]

# These are the operator-facing workspaces that must remain wired through the
# current flat navigation. Alias labels are intentionally included because an
# operator can still reach them through route restoration/deep links.
EXPECTED_OPERATOR_WORKSPACES = {
    "Home",
    "Operations Control Tower",
    "Enterprise Control Tower",
    "Buyer Operations",
    "Purchasing",
    "Buying Recommendations",
    "Delivery Performance",
    "Purchase Orders",
    "Buying Budget",
    "Replenishment Policies",
    "Inventory",
    "Retail Inventory Transfers",
    "Inventory Audits",
    "Retail Product 360",
    "Retail Product Master",
    "Package 360",
    "Retail Catalog Admin",
    "Slow Movers",
    "Production Inventory",
    "Production Inventory Transfers",
    "Production Product Master",
    "Production",
    "Production Calendar",
    "Production Run 360",
    "Extraction",
    "White Label / Repack",
    "Package Studio",
    "Wholesale Ops",
    "Orders",
    "Warehouse Pick Pack",
    "Compliance",
    "Traceability Actions",
    "Compliance Q&A",
    "Label Studio",
    "MA Flower Equivalency",
    "Product Name Mapper",
    "Nomenclature Mapper",
    "Reports",
    "Sales & Category Trends",
    "Executive Reports",
    "Data & Settings",
    "Location Settings",
    "Admin",
    "Admin Tools",
    "Integrations",
    "AI & METRC Integrations",
    "METRC Integrations",
    "Doobie",
}

# Durable reads that the integrated Co-Man demo facility is explicitly expected
# to support. Capability- or upload-dependent reads are validated separately so
# a correct 403/422 readiness response is not mislabeled as an app defect.
CORE_OPERATOR_READS = (
    "/api/v1/account/context",
    "/api/v1/account/access-options",
    "/api/v1/inventory/retail/packages",
    "/api/v1/inventory/production/packages",
    "/api/v1/inventory/transfers",
    "/api/v1/product-master?operation=retail&status=active",
    "/api/v1/product-master?operation=production&status=active",
    "/api/v1/inventory/retail/audits",
    "/api/v1/inventory/production/audits",
    "/api/v1/retail-insights/trends?days=30",
    "/api/v1/production/orders",
    "/api/v1/extraction/workflows",
    "/api/v1/extraction/lots",
    "/api/v1/extraction/runs",
    "/api/v1/package-studio/workspace",
    "/api/v1/label-printing/inventory-sources",
    "/api/v1/label-printing/coas?limit=250",
    "/api/v1/commercial/orders?open_only=false",
    "/api/v1/commercial/workspace",
    "/api/v1/storefronts/wholesale-inventory",
    "/api/v1/storefronts",
    "/api/v1/data-hub/datasets",
)


def _seeded_client() -> tuple[TestClient, dict[str, str]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    seeded = ensure_coman_demo_dataset(
        state={},
        actor="strict-alpha-operator",
        payload=build_demo_payload(date(2026, 8, 31), scale="small"),
        engine=engine,
    )
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    headers = {
        "X-Organization-Id": seeded["organization_id"],
        "X-Facility-Id": seeded["facility_id"],
        "X-User-Id": "strict-alpha-operator",
        "X-User-Role": "dev",
    }
    return TestClient(app, raise_server_exceptions=False), headers


def _static_get_routes() -> list[tuple[str, APIRoute]]:
    routes: dict[str, APIRoute] = {}
    seen_routers: set[int] = set()
    for name, router in vars(main_module).items():
        if not name.endswith("_router") or not isinstance(router, APIRouter) or id(router) in seen_routers:
            continue
        seen_routers.add(id(router))
        for route in router.routes:
            if not isinstance(route, APIRoute) or "GET" not in (route.methods or set()):
                continue
            path = f"{settings.api_prefix}{route.path}"
            routes.setdefault(path, route)
    for route in app.routes:
        if not isinstance(route, APIRoute) or "GET" not in (route.methods or set()):
            continue
        if route.path.startswith(settings.api_prefix):
            routes.setdefault(route.path, route)
    return sorted(routes.items())


def test_every_operator_workspace_is_routed_and_rendered():
    routes_source = (ROOT / "frontend" / "src" / "lib" / "workspaceRoutes.ts").read_text(encoding="utf-8")
    shell_source = (ROOT / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    app_source = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

    routed_pages = set(re.findall(r'page:\s*"([^"]+)"', routes_source))
    navigation_pages = set(re.findall(r'page:\s*"([^"]+)"', shell_source))

    missing_expected_routes = EXPECTED_OPERATOR_WORKSPACES - routed_pages
    assert not missing_expected_routes, f"Operator workspaces missing routes: {sorted(missing_expected_routes)}"

    missing_navigation_routes = navigation_pages - routed_pages
    assert not missing_navigation_routes, f"Navigation points at unrouted workspaces: {sorted(missing_navigation_routes)}"

    missing_dispatch = {
        page
        for page in routed_pages
        if f'page === "{page}"' not in app_source and f'|| page === "{page}"' not in app_source
    }
    assert not missing_dispatch, f"Routed workspaces missing App dispatch: {sorted(missing_dispatch)}"


def test_core_operator_reads_return_200_on_integrated_demo_facility():
    client, headers = _seeded_client()
    try:
        failures: list[tuple[str, int, str]] = []
        for path in CORE_OPERATOR_READS:
            response = client.get(path, headers=headers)
            if response.status_code != 200:
                failures.append((path, response.status_code, response.text[:400]))
        assert not failures, "Core operator reads failed: " + repr(failures)
    finally:
        app.dependency_overrides.clear()


def test_upload_and_capability_dependent_workspaces_fail_closed_with_operator_guidance():
    client, headers = _seeded_client()
    try:
        buyer = client.get("/api/v1/buyer-parity/dashboard", headers=headers)
        assert buyer.status_code in {200, 422}
        if buyer.status_code == 422:
            assert "Inventory and Product Sales data" in buyer.text
            assert "Data & Settings" in buyer.text

        context = client.get("/api/v1/account/context", headers=headers)
        assert context.status_code == 200
        cultivation_enabled = bool(context.json()["capabilities"]["cultivation"])
        plants = client.get("/api/v1/inventory/production/plants", headers=headers)
        if cultivation_enabled:
            assert plants.status_code == 200, plants.text
        else:
            assert plants.status_code == 403
            assert "does not enable cultivation operations" in plants.text
    finally:
        app.dependency_overrides.clear()


def test_all_static_get_api_routes_avoid_internal_server_errors_on_seeded_facility():
    """Broad alpha crash sweep across safe, parameter-free GET endpoints.

    A 4xx can be a valid permission/configuration/business-state response and is
    evaluated by focused tests elsewhere. A 500/501 on a static GET is always an
    alpha defect because simply opening or refreshing a workspace must not crash
    the server.
    """

    client, headers = _seeded_client()
    try:
        failures: list[tuple[str, int, str]] = []
        exercised: list[str] = []
        for path, route in _static_get_routes():
            if "{" in path:
                continue
            required_queries = [field for field in route.dependant.query_params if getattr(field, "required", False)]
            if required_queries:
                continue

            response = client.get(path, headers=headers)
            exercised.append(path)
            if response.status_code in {500, 501}:
                failures.append((path, response.status_code, response.text[:500]))

        assert len(exercised) >= 35, f"Alpha crash sweep unexpectedly exercised only {len(exercised)} routes."
        assert not failures, "Static GET operator crash defects: " + repr(failures)
    finally:
        app.dependency_overrides.clear()
