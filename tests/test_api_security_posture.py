from pathlib import Path

from fastapi import APIRouter
from fastapi.routing import APIRoute

import backend.app.main as main_module
from backend.app.auth import get_request_context
from backend.app.main import app, settings


# These routes are allowed to be unauthenticated if their implementation needs
# it, but the security gate never requires them to remain public. If a route
# later gains tenant authentication, that is strictly safer and should pass.
PERMITTED_PUBLIC_API_ROUTES = {
    ("POST", f"{settings.api_prefix}/trial/activate"),
}


def _depends_on(dependant, target) -> bool:
    if getattr(dependant, "call", None) is target:
        return True
    return any(_depends_on(child, target) for child in getattr(dependant, "dependencies", ()))


def _api_route_security() -> dict[tuple[str, str], bool]:
    """Collect endpoint auth from imported APIRouters plus direct app routes.

    Inspecting the source routers is intentional. Some tests import the app in
    ways that leave only directly-added routes visible in ``app.routes``, while
    each imported APIRouter still retains FastAPI's complete dependency graph.
    """
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

    # Capture endpoints added directly to the FastAPI app, such as the explicit
    # admin facility update route, without depending on included-router copies.
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(settings.api_prefix):
            continue
        for method in (route.methods or set()) - {"HEAD", "OPTIONS"}:
            security.setdefault((method, route.path), _depends_on(route.dependant, get_request_context))

    return security


def test_every_non_public_api_route_requires_tenant_context():
    security = _api_route_security()
    unexpected = sorted(
        key for key, protected in security.items() if not protected and key not in PERMITTED_PUBLIC_API_ROUTES
    )
    assert not unexpected, "API routes missing organization/facility request context: " + ", ".join(
        f"{method} {path}" for method, path in unexpected
    )


def test_public_api_allowlist_is_a_ceiling_not_a_requirement():
    actual = {key for key, protected in _api_route_security().items() if not protected}
    assert actual <= PERMITTED_PUBLIC_API_ROUTES


def test_permitted_trial_activation_route_is_registered():
    assert ("POST", f"{settings.api_prefix}/trial/activate") in _api_route_security()


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


def test_post_supabase_hardening_new_tables_remain_data_api_locked_down():
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
