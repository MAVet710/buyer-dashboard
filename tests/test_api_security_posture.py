from pathlib import Path

from fastapi import APIRouter
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.auth import get_request_context
from backend.app.main import app, settings


PERMITTED_PUBLIC_API_ROUTES = {
    ("POST", f"{settings.api_prefix}/trial/activate"),
    ("POST", f"{settings.api_prefix}/beta/apply"),
    ("POST", f"{settings.api_prefix}/account/username-login"),
    ("GET", f"{settings.api_prefix}/commerce-portal/{{token}}"),
    ("POST", f"{settings.api_prefix}/commerce-portal/{{token}}/orders"),
    ("GET", f"{settings.api_prefix}/commerce-storefronts/{{slug}}"),
    ("POST", f"{settings.api_prefix}/commerce-storefronts/{{slug}}/orders"),
}
SERVICE_ACCOUNT_PREFIX = f"{settings.api_prefix}/external/v1/"


def _depends_on(dependant, target) -> bool:
    if getattr(dependant, "call", None) is target:
        return True
    return any(_depends_on(child, target) for child in getattr(dependant, "dependencies", ()))


def _api_route_security() -> dict[tuple[str, str], bool]:
    security: dict[tuple[str, str], bool] = {}
    seen_routers: set[int] = set()
    for name, router in vars(main_module).items():
        if not name.endswith("_router") or not isinstance(router, APIRouter) or id(router) in seen_routers:
            continue
        seen_routers.add(id(router))
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            path = f"{settings.api_prefix}{route.path}"
            for method in (route.methods or set()) - {"HEAD", "OPTIONS"}:
                security[(method, path)] = _depends_on(route.dependant, get_request_context)
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(settings.api_prefix):
            continue
        for method in (route.methods or set()) - {"HEAD", "OPTIONS"}:
            security.setdefault((method, route.path), _depends_on(route.dependant, get_request_context))
    return security


def test_every_non_public_employee_api_route_requires_tenant_context():
    security = _api_route_security()
    unexpected = sorted(
        key
        for key, protected in security.items()
        if not protected
        and key not in PERMITTED_PUBLIC_API_ROUTES
        and not key[1].startswith(SERVICE_ACCOUNT_PREFIX)
    )
    assert not unexpected, "API routes missing organization/facility request context: " + ", ".join(
        f"{method} {path}" for method, path in unexpected
    )


def test_public_api_allowlist_is_explicit_and_bounded():
    security = _api_route_security()
    unauthenticated_non_service = {
        key for key, protected in security.items() if not protected and not key[1].startswith(SERVICE_ACCOUNT_PREFIX)
    }
    assert unauthenticated_non_service <= PERMITTED_PUBLIC_API_ROUTES
    assert ("POST", f"{settings.api_prefix}/trial/activate") in security
    assert ("POST", f"{settings.api_prefix}/beta/apply") in security
    assert ("POST", f"{settings.api_prefix}/account/username-login") in security
    assert ("GET", f"{settings.api_prefix}/commerce-storefronts/{{slug}}") in security
    assert ("POST", f"{settings.api_prefix}/commerce-storefronts/{{slug}}/orders") in security


def test_hosted_storefront_subdomain_cors_is_exact_and_bounded():
    client = TestClient(app)
    preflight_path = f"{settings.api_prefix}/commerce-storefronts/cowboykush"

    allowed = client.options(
        preflight_path,
        headers={
            "Origin": "https://cowboykush.doobielogic.io",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://cowboykush.doobielogic.io"

    malicious_suffix = client.options(
        preflight_path,
        headers={
            "Origin": "https://cowboykush.doobielogic.io.evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in malicious_suffix.headers

    insecure_scheme = client.options(
        preflight_path,
        headers={
            "Origin": "http://cowboykush.doobielogic.io",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in insecure_scheme.headers

    assert main_module.DOOBIELOGIC_SUBDOMAIN_ORIGIN_REGEX == r"^https://[a-z0-9-]+\.doobielogic\.io$"


def test_external_api_uses_scoped_bearer_service_account_authentication():
    source = Path("backend/app/routers/external_api.py").read_text(encoding="utf-8")
    assert 'scheme.casefold() != "bearer"' in source
    assert "authenticate_service_account" in source
    assert "_service_context(engine, authorization" in source
    assert '"inventory:read"' in source
    assert '"orders:read"' in source
    assert '"finance:read"' in source
    assert '"telemetry:write"' in source


def test_production_api_discovery_is_conditionally_disabled():
    source = Path("backend/app/main.py").read_text(encoding="utf-8")
    assert 'docs_url="/docs" if settings.is_development else None' in source
    assert 'redoc_url="/redoc" if settings.is_development else None' in source
    assert 'openapi_url="/openapi.json" if settings.is_development else None' in source


def test_api_and_operational_frontend_are_noindex():
    api_source = Path("backend/app/main.py").read_text(encoding="utf-8")
    nginx_source = Path("frontend/nginx.conf").read_text(encoding="utf-8")
    assert "X-Robots-Tag" in api_source
    assert "noindex, nofollow, noarchive, nosnippet" in api_source
    assert "doobielogic.io 1;" in nginx_source
    assert "www.doobielogic.io 1;" in nginx_source
    assert "noindex, nofollow, noarchive, nosnippet" in nginx_source
    assert "Sitemap: https://doobielogic.io/sitemap.xml" in nginx_source


def test_sitemap_contains_only_public_marketing_urls():
    sitemap = Path("frontend/public/sitemap.xml").read_text(encoding="utf-8")
    assert "https://doobielogic.io/" in sitemap
    forbidden = ("ops.doobielogic.io", "/api/", "/admin", "/inventory", "/buyer", "/production")
    assert not any(value in sitemap for value in forbidden)


def test_post_supabase_hardening_ai_tables_remain_data_api_locked_down():
    migration = Path("migrations/versions/0040_ai_runtime.py").read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "REVOKE ALL PRIVILEGES ON TABLE" in migration
    for table in (
        "ai_knowledge_documents",
        "ai_knowledge_chunks",
        "ai_mapping_memory",
        "ai_telemetry",
        "ai_agent_feedback",
        "ai_agent_eval_cases",
    ):
        assert table in migration
