"""API routers and runtime service composition."""

# The authenticated Metrc facility bootstrap is imported by the sandbox router
# from its long-lived service module. Compose the current-snapshot behavior here
# before any router module imports that class, avoiding duplicate provider reads
# while keeping the base bootstrap independently testable.
from services import metrc_facility_bootstrap as _metrc_facility_bootstrap
from services.metrc_facility_snapshot_bootstrap import SnapshottingMetrcFacilityBootstrapService

_metrc_facility_bootstrap.MetrcFacilityBootstrapService = SnapshottingMetrcFacilityBootstrapService

# Cultivation keeps its explicit live verification endpoint, but normal page-load
# regulatory state comes from the locally synchronized provider snapshot. Attach
# the projection before main.py captures the plants router object.
from . import plants as _plants
from .metrc_cultivation_snapshot import router as _metrc_cultivation_snapshot_router

_plants.router.include_router(_metrc_cultivation_snapshot_router)

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

__all__ = ["SnapshottingMetrcFacilityBootstrapService"]
