from __future__ import annotations

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

    from fastapi import HTTPException

    from services import metrc_facility_bootstrap as metrc_facility_bootstrap
    from services import metrc_incremental_sync as metrc_incremental_sync_module
    from services import metrc_resilient_bootstrap as metrc_resilient_bootstrap_module
    from services.metrc_expanded_workspace_hydration import (
        MetrcWorkspaceHydrationService as ExpandedMetrcWorkspaceHydrationService,
    )
    from services.metrc_natural_bootstrap import NaturalMetrcFacilityBootstrapService
    from services.metrc_rate_limit_policy import install_metrc_rate_limit_policy

    from .routers import alpha_sandbox_connections
    from .routers import inventory_reconciliation
    from .routers import location_settings
    from .routers import plants
    from .routers import retail_insights
    from .routers import sandbox_integrations
    from .routers.metrc_cultivation_snapshot import router as metrc_cultivation_snapshot_router
    from .routers.metrc_facility_setup_snapshot import (
        augment_facility_setup_overview,
        router as metrc_facility_setup_snapshot_router,
    )
    from .routers.metrc_incremental_sync import router as metrc_incremental_sync_router
    from .routers.metrc_package_lab_detail import router as metrc_package_lab_detail_router
    from .routers.metrc_production_snapshot import router as metrc_production_snapshot_router
    from .routers.metrc_retail_snapshot import router as metrc_retail_snapshot_router
    from .routers.regulatory_detail import router as regulatory_detail_router
    from .services import metrc_natural_sync as metrc_natural_sync_module
    from .services.metrc_context import resolve_metrc_context
    from .services.metrc_sync_policy import MetrcPolicySyncControlService

    def route_key(route) -> tuple[str, tuple[str, ...]]:
        return (
            str(getattr(route, "path", "") or ""),
            tuple(sorted(str(method) for method in (getattr(route, "methods", None) or ()))),
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
    include_router_once(inventory_reconciliation.router, metrc_production_snapshot_router)
    include_router_once(inventory_reconciliation.router, regulatory_detail_router)
    include_router_once(inventory_reconciliation.router, metrc_package_lab_detail_router)
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
    sandbox_integrations.MetrcFacilityBootstrapService = NaturalMetrcFacilityBootstrapService
    metrc_natural_sync_module.ResilientSnapshottingMetrcFacilityBootstrapService = NaturalMetrcFacilityBootstrapService

    # Incremental sync keeps its non-destructive delta algorithm but routes newly
    # changed provider objects through the expanded Product/Inventory/Cultivation
    # materializer rather than the earlier Product/Inventory-only implementation.
    metrc_incremental_sync_module.MetrcWorkspaceHydrationService = ExpandedMetrcWorkspaceHydrationService

    original_sandbox_sync = sandbox_integrations.run_sandbox_sync
    original_sandbox_status = sandbox_integrations.sandbox_runtime_status
    original_sandbox_retry = sandbox_integrations.retry_sandbox_sync

    def natural_metrc_context(*, context, engine, settings):
        try:
            _service, metrc = resolve_metrc_context(engine, settings, context)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        if not metrc.configured:
            raise HTTPException(
                422,
                metrc.message or "Configure the Metrc sandbox connection before synchronization.",
            )
        if not metrc.trusted_mapping:
            raise HTTPException(
                409,
                "Verify the exact Metrc sandbox facility/license mapping before synchronization.",
            )
        return metrc

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
        metrc = natural_metrc_context(context=context, engine=engine, settings=settings)
        try:
            return MetrcPolicySyncControlService(engine).sync(
                organization_id=context.organization_id,
                facility_id=context.facility_id,
                metrc=metrc,
                actor=context.user_id,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

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

    def natural_sandbox_retry(provider, context, engine, settings):
        if str(provider or "").strip().casefold() != "metrc":
            return original_sandbox_retry(
                provider,
                context=context,
                engine=engine,
                settings=settings,
            )
        sandbox_integrations._require_developer_connections(context)
        metrc = natural_metrc_context(context=context, engine=engine, settings=settings)
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
        raise RuntimeError(f"Expected FastAPI route ending in {suffix!r} was not found during METRC composition.")

    # Replace captured APIRoute callables as well as module globals. The alpha
    # wrapper imported legacy function objects earlier, so patch those aliases too.
    sandbox_integrations.run_sandbox_sync = natural_sandbox_sync
    sandbox_integrations.sandbox_runtime_status = natural_sandbox_status
    sandbox_integrations.retry_sandbox_sync = natural_sandbox_retry
    replace_route_call(sandbox_integrations.router, "/{provider}/sync", natural_sandbox_sync)
    replace_route_call(sandbox_integrations.router, "/{provider}/runtime", natural_sandbox_status)
    replace_route_call(sandbox_integrations.router, "/{provider}/retry", natural_sandbox_retry)
    alpha_sandbox_connections.legacy_run_sandbox_sync = natural_sandbox_sync
    alpha_sandbox_connections.legacy_retry_sandbox_sync = natural_sandbox_retry

    original_facility_setup_overview = location_settings.facility_setup_overview

    def synced_facility_setup_overview(*, context, engine, settings):
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

    location_settings.facility_setup_overview = synced_facility_setup_overview
    replace_route_call(location_settings.router, "/facility-setup", synced_facility_setup_overview)

    _COMPOSED = True
