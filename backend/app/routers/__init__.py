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

__all__ = ["SnapshottingMetrcFacilityBootstrapService"]
