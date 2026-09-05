from __future__ import annotations

from functools import wraps
import importlib

_COMPOSED = False
FULL_SYNC_PAGE_SAFETY_CEILING = 10_000


def compose_metrc_runtime() -> None:
    """Attach cross-router METRC behavior after the API module graph is initialized.

    The composition is deliberately late and idempotent. Router package imports stay
    side-effect free, while main.py invokes this once after importing every router and
    before any APIRouter is copied into the FastAPI application.

    Route attachment is revalidated on every call. This matters in test/dev reload
    environments where a parent router module can be reloaded after the one-time
    runtime behavior has already been composed. Missing child projections are safely
    reattached without duplicating routes that are already present.
    """

    global _COMPOSED

    from fastapi import Depends, HTTPException

    from services import metrc_facility_bootstrap as metrc_facility_bootstrap
    from services import metrc_incremental_sync as metrc_incremental_sync_module
    from services import metrc_resilient_bootstrap as metrc_resilient_bootstrap_module
    from services.metrc_expanded_workspace_hydration import (
        MetrcWorkspaceHydrationService as ExpandedMetrcWorkspaceHydrationService,
    )
    from services.metrc_natural_bootstrap import NaturalMetrcFacilityBootstrapService
    from services.metrc_rate_limit_policy import install_metrc_rate_limit_policy

    # Resolve reload-sensitive modules from the import registry on every call instead
    # of through backend.app.routers package attributes. Test/dev isolation can replace
    # a module in sys.modules while the package attribute still points at the previous
    # object; composing against that stale object makes route ownership depend on
    # import order. import_module() returns the current registered module instead.
    alpha_sandbox_connections = importlib.import_module(
        "backend.app.routers.alpha_sandbox_connections"
    )
    inventory_reconciliation = importlib.import_module(
        "backend.app.routers.inventory_reconciliation"
    )
    location_settings = importlib.import_module("backend.app.routers.location_settings")
    plants = importlib.import_module("backend.app.routers.plants")
    retail_insights = importlib.import_module("backend.app.routers.retail_insights")
    sandbox_integrations = importlib.import_module(
        "backend.app.routers.sandbox_integrations"
    )

    metrc_cultivation_snapshot_module = importlib.import_module(
        "backend.app.routers.metrc_cultivation_snapshot"
    )
    metrc_facility_setup_snapshot_module = importlib.import_module(
        "backend.app.routers.metrc_facility_setup_snapshot"
    )
    metrc_incremental_sync_router_module = importlib.import_module(
        "backend.app.routers.metrc_incremental_sync"
    )
    metrc_package_lab_detail_module = importlib.import_module(
        "backend.app.routers.metrc_package_lab_detail"
    )
    metrc_production_snapshot_module = importlib.import_module(
        "backend.app.routers.metrc_production_snapshot"
    )
    metrc_retail_snapshot_module = importlib.import_module(
        "backend.app.routers.metrc_retail_snapshot"
    )
    regulatory_detail_module = importlib.import_module(
        "backend.app.routers.regulatory_detail"
    )
    metrc_natural_sync_module = importlib.import_module(
        "backend.app.services.metrc_natural_sync"
    )

    metrc_cultivation_snapshot_router = metrc_cultivation_snapshot_module.router
    metrc_facility_setup_snapshot_router = metrc_facility_setup_snapshot_module.router
    augment_facility_setup_overview = (
        metrc_facility_setup_snapshot_module.augment_facility_setup_overview
    )
    metrc_incremental_sync_router = metrc_incremental_sync_router_module.router
    metrc_package_lab_detail_router = metrc_package_lab_detail_module.router
    metrc_production_snapshot_router = metrc_production_snapshot_module.router
    metrc_retail_snapshot_router = metrc_retail_snapshot_module.router
    regulatory_detail_router = regulatory_detail_module.router

    from .services.metrc_context import resolve_metrc_context
    from .services.metrc_permission_evidence import MetrcPermissionEvidenceStore
    from .services.metrc_sync_policy import MetrcPolicySyncControlService

    def route_key(route) -> tuple[str, tuple[str, ...]]:
        return (
            str(getattr(route, "path", "") or ""),
            tuple(
                sorted(
                    str(method)
                    for method in (getattr(route, "methods", None) or ())
                )
            ),
        )

    def include_router_once(parent, child) -> None:
        child_keys = {route_key(route) for route in child.routes}
        if not child_keys:
            return
        parent_keys = {route_key(route) for route in parent.routes}
        missing = child_keys - parent_keys
        if not missing:
            return
        if len(missing) != len(child_keys):
            raise RuntimeError(
                "METRC runtime composition found a partially attached child router; "
                "refusing to duplicate routes or hide an inconsistent API graph."
            )
        parent.include_router(child)

    # Revalidate local provider projections on every call. FastAPI copies child
    # routes into the parent at include time, so a dev/test reload of a parent
    # router can otherwise erase projections while the one-time runtime flag stays
    # true. This block is side-effect-safe because already-present route sets are
    # detected and left untouched.
    include_router_once(plants.router, metrc_cultivation_snapshot_router)
    include_router_once(
        inventory_reconciliation.router, metrc_production_snapshot_router
    )
    include_router_once(inventory_reconciliation.router, regulatory_detail_router)
    include_router_once(
        inventory_reconciliation.router, metrc_package_lab_detail_router
    )
    include_router_once(retail_insights.router, metrc_retail_snapshot_router)
    include_router_once(sandbox_integrations.router, metrc_incremental_sync_router)
    include_router_once(location_settings.router, metrc_facility_setup_snapshot_router)

    if _COMPOSED:
        return

    # All shared Metrc reads now honor Retry-After up to a bounded 30 seconds.
    # Installing here avoids any import-time dependency loop through traceability.
    install_metrc_rate_limit_policy()

    # A real full import must not stop at the old 100-page/10k-row bootstrap
    # boundary. Keep a pathological-provider safety ceiling, but allow up to one
    # million rows per collection while preserving page checkpoints and resume.
    metrc_facility_bootstrap.MAX_INITIAL_PAGES = FULL_SYNC_PAGE_SAFETY_CEILING
    metrc_resilient_bootstrap_module.MAX_INITIAL_PAGES = FULL_SYNC_PAGE_SAFETY_CEILING
    metrc_incremental_sync_module.MAX_INITIAL_PAGES = FULL_SYNC_PAGE_SAFETY_CEILING

    # Compose one final authenticated bootstrap at the actual runtime consumers.
    # Do NOT replace services.metrc_facility_bootstrap.MetrcFacilityBootstrapService
    # globally: that class is the stable core/audit primitive used by isolated tests
    # and by incremental persistence. Global rebinding made behavior depend on import
    # order. Consumers that need the natural runtime are explicitly rebound instead.
    sandbox_integrations.MetrcFacilityBootstrapService = (
        NaturalMetrcFacilityBootstrapService
    )
    metrc_natural_sync_module.ResilientSnapshottingMetrcFacilityBootstrapService = (
        NaturalMetrcFacilityBootstrapService
    )

    # Incremental sync keeps its non-destructive delta algorithm but routes newly
    # changed provider objects through the expanded Product/Inventory/Cultivation
    # materializer rather than the earlier Product/Inventory-only implementation.
    metrc_incremental_sync_module.MetrcWorkspaceHydrationService = (
        ExpandedMetrcWorkspaceHydrationService
    )

    original_sandbox_sync = sandbox_integrations.run_sandbox_sync
    original_sandbox_status = sandbox_integrations.sandbox_runtime_status
    original_sandbox_retry = sandbox_integrations.retry_sandbox_sync
    original_discover_metrc_facilities = sandbox_integrations._discover_metrc_facilities

    def natural_metrc_context(*, context, engine, settings):
        try:
            _service, metrc = resolve_metrc_context(engine, settings, context)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        if not metrc.configured:
            raise HTTPException(
                422,
                metrc.message
                or "Configure the Metrc sandbox connection before synchronization.",
            )
        if not metrc.trusted_mapping:
            raise HTTPException(
                409,
                "Verify the exact Metrc sandbox facility/license mapping before synchronization.",
            )
        return metrc

    def discovered_facilities_without_permission_prerequisite(*, service, context, engine, settings):
        result = original_discover_metrc_facilities(
            service=service,
            context=context,
            engine=engine,
            settings=settings,
        )
        public = dict(result)
        public["bootstrap_resources"] = [
            str(resource)
            for resource in result.get("bootstrap_resources", [])
            if str(resource) != "facility_permissions"
        ]
        public["optional_capability_checks"] = [
            {
                "resource": "employee_permissions",
                "endpoint": "GET /employees/v2/permissions",
                "required_for_initial_hydration": False,
                "message": (
                    "Permission introspection is optional and is captured as audit evidence when the connected employee identity and provider access allow it. Metrc still enforces permissions on every resource request."
                ),
            }
        ]
        return public

    @wraps(original_sandbox_sync)
    def natural_sandbox_sync(provider, payload, context, engine, settings):
        if str(provider or "").strip().casefold() != "metrc":
            return original_sandbox_sync(
                provider,
                payload,
                context=context,
                engine=engine,
                settings=settings,
            )
        sandbox_integrations._require_developer_connections(context)
        metrc = natural_metrc_context(
            context=context, engine=engine, settings=settings
        )
        try:
            return MetrcPolicySyncControlService(engine).sync(
                organization_id=context.organization_id,
                facility_id=context.facility_id,
                metrc=metrc,
                actor=context.user_id,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @wraps(original_sandbox_status)
    def natural_sandbox_status(provider, context, engine, settings):
        if str(provider or "").strip().casefold() != "metrc":
            return original_sandbox_status(
                provider,
                context=context,
                engine=engine,
                settings=settings,
            )
        sandbox_integrations._require_developer_connections(context)
        try:
            _service, metrc = resolve_metrc_context(engine, settings, context)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        return MetrcPolicySyncControlService(engine).status(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            metrc=metrc,
        )

    @wraps(original_sandbox_retry)
    def natural_sandbox_retry(provider, context, engine, settings):
        if str(provider or "").strip().casefold() != "metrc":
            return original_sandbox_retry(
                provider,
                context=context,
                engine=engine,
                settings=settings,
            )
        sandbox_integrations._require_developer_connections(context)
        metrc = natural_metrc_context(
            context=context, engine=engine, settings=settings
        )
        try:
            result = MetrcPolicySyncControlService(engine).sync(
                organization_id=context.organization_id,
                facility_id=context.facility_id,
                metrc=metrc,
                actor=context.user_id,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {
            "provider": "metrc",
            "environment": metrc.environment,
            "retried": sum(
                1
                for row in result.get("resources", [])
                if row.get("status") in {"succeeded", "skipped"}
            ),
            "natural_sync": result,
        }

    def replace_route_call(router, suffix: str, replacement) -> None:
        for route in router.routes:
            path = str(getattr(route, "path", "") or "")
            if path.endswith(suffix):
                route.endpoint = replacement
                if getattr(route, "dependant", None) is not None:
                    route.dependant.call = replacement
                return
        raise RuntimeError(
            f"Expected FastAPI route ending in {suffix!r} was not found during METRC composition."
        )

    # Replace captured APIRoute callables as well as module globals. The alpha
    # wrapper imported legacy function objects earlier, so patch those aliases too.
    sandbox_integrations._discover_metrc_facilities = (
        discovered_facilities_without_permission_prerequisite
    )
    sandbox_integrations.run_sandbox_sync = natural_sandbox_sync
    sandbox_integrations.sandbox_runtime_status = natural_sandbox_status
    sandbox_integrations.retry_sandbox_sync = natural_sandbox_retry
    replace_route_call(
        sandbox_integrations.router, "/{provider}/sync", natural_sandbox_sync
    )
    replace_route_call(
        sandbox_integrations.router, "/{provider}/runtime", natural_sandbox_status
    )
    replace_route_call(
        sandbox_integrations.router, "/{provider}/retry", natural_sandbox_retry
    )
    alpha_sandbox_connections.legacy_run_sandbox_sync = natural_sandbox_sync
    alpha_sandbox_connections.legacy_retry_sandbox_sync = natural_sandbox_retry

    original_facility_setup_overview = location_settings.facility_setup_overview
    original_metrc_permissions = location_settings.metrc_permissions

    @wraps(original_facility_setup_overview)
    def synced_facility_setup_overview(
        *,
        context=Depends(location_settings.get_request_context),
        engine=Depends(location_settings.get_engine),
        settings=Depends(location_settings.get_settings),
    ):
        overview = original_facility_setup_overview(
            context=context,
            engine=engine,
            settings=settings,
        )
        return augment_facility_setup_overview(
            overview,
            context=context,
            engine=engine,
        )

    @wraps(original_metrc_permissions)
    def persisted_metrc_permissions(
        *,
        context=Depends(location_settings.get_request_context),
        engine=Depends(location_settings.get_engine),
        settings=Depends(location_settings.get_settings),
    ):
        result = original_metrc_permissions(
            context=context,
            engine=engine,
            settings=settings,
        )
        public = dict(result)
        public["evidence_persisted"] = False
        public["evidence_optional"] = True
        if result.get("status") != "synced" or not result.get("can_introspect"):
            return public
        try:
            _service, metrc = resolve_metrc_context(engine, settings, context)
            evidence = MetrcPermissionEvidenceStore(engine).persist(
                organization_id=context.organization_id,
                facility_id=context.facility_id,
                actor=context.user_id,
                jurisdiction_code=metrc.state,
                environment=metrc.environment,
                license_number=metrc.license_number,
                employee_license_number=str(result.get("employee_license_number") or ""),
                permissions=result.get("permissions") or [],
            )
        except Exception as exc:  # permission evidence must never block normal provider reads
            public["evidence_error"] = f"Permission evidence was not persisted: {exc}"
            return public
        public["evidence_persisted"] = True
        public["evidence"] = evidence
        return public

    location_settings.facility_setup_overview = synced_facility_setup_overview
    replace_route_call(
        location_settings.router, "/facility-setup", synced_facility_setup_overview
    )
    location_settings.metrc_permissions = persisted_metrc_permissions
    replace_route_call(
        location_settings.router, "/metrc-permissions", persisted_metrc_permissions
    )

    _COMPOSED = True
