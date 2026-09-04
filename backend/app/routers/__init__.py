"""API routers and runtime service composition."""

# The authenticated Metrc facility bootstrap is imported by the sandbox router
# from its long-lived service module. Compose the current-snapshot + reliability
# behavior here before any router module imports that class, avoiding duplicate
# provider reads while keeping the base bootstrap independently testable.
from services import metrc_facility_bootstrap as _metrc_facility_bootstrap
from services.metrc_resilient_bootstrap import ResilientSnapshottingMetrcFacilityBootstrapService

_metrc_facility_bootstrap.MetrcFacilityBootstrapService = ResilientSnapshottingMetrcFacilityBootstrapService

# Cultivation keeps its explicit live verification endpoint, but normal page-load
# regulatory state comes from the locally synchronized provider snapshot. Attach
# the projection before main.py captures the plants router object.
from . import plants as _plants
from .metrc_cultivation_snapshot import router as _metrc_cultivation_snapshot_router

_plants.router.include_router(_metrc_cultivation_snapshot_router)

# Production follows the same pattern: the existing manufacturing regulatory
# endpoint stays available for an explicit provider verification, while the normal
# Production workspace consumes the last synchronized current snapshot locally.
from . import inventory_reconciliation as _inventory_reconciliation
from .metrc_production_snapshot import router as _metrc_production_snapshot_router
from .regulatory_detail import router as _regulatory_detail_router

_inventory_reconciliation.router.include_router(_metrc_production_snapshot_router)
# Keep one tenant-scoped, provider-neutral detail contract underneath the already
# authenticated inventory/regulatory router. Package 360, Product 360 and other
# operator surfaces can consume the same local snapshot API without calling Metrc.
_inventory_reconciliation.router.include_router(_regulatory_detail_router)

# Retail Insights receives provider-owned Metrc sales receipt/delivery shadows.
# These do not become local POS ledger rows simply because they already exist at
# the provider; normal retail analytics continue to use DoobieLogic's durable
# local sales ledger while the regulatory panel shows synchronized provider state.
from . import retail_insights as _retail_insights
from .metrc_retail_snapshot import router as _metrc_retail_snapshot_router

_retail_insights.router.include_router(_metrc_retail_snapshot_router)

# The sandbox control plane owns explicit provider synchronization. The incremental
# child route resolves the active trusted facility mapping and uses LastModified
# deltas without accepting a caller-supplied license override.
from . import sandbox_integrations as _sandbox_integrations
from .metrc_incremental_sync import router as _metrc_incremental_sync_router

_sandbox_integrations.router.include_router(_metrc_incremental_sync_router)

# Facility Setup already loads one overview request on page entry. Enrich that
# existing response with locally synchronized Metrc master-data counts/freshness,
# and expose the detailed local snapshot on a separate read-only child endpoint.
# The existing explicit live Metrc endpoints remain unchanged for operator-driven
# verification and governed edit flows.
from . import location_settings as _location_settings
from .metrc_facility_setup_snapshot import (
    augment_facility_setup_overview as _augment_facility_setup_overview,
    router as _metrc_facility_setup_snapshot_router,
)

_location_settings.router.include_router(_metrc_facility_setup_snapshot_router)
_original_facility_setup_overview = _location_settings.facility_setup_overview


def _synced_facility_setup_overview(*, context, engine, settings):
    overview = _original_facility_setup_overview(context=context, engine=engine, settings=settings)
    return _augment_facility_setup_overview(overview, context=context, engine=engine)


_location_settings.facility_setup_overview = _synced_facility_setup_overview
for _route in _location_settings.router.routes:
    if getattr(_route, "path", "") == "/facility-setup":
        _route.endpoint = _synced_facility_setup_overview
        if getattr(_route, "dependant", None) is not None:
            _route.dependant.call = _synced_facility_setup_overview
        break

__all__ = ["ResilientSnapshottingMetrcFacilityBootstrapService"]
