"""API routers and runtime service composition."""

# The authenticated Metrc facility bootstrap is imported by the sandbox router
# from its long-lived service module. Compose the current-snapshot behavior here
# before any router module imports that class, avoiding duplicate provider reads
# while keeping the base bootstrap independently testable.
from services import metrc_facility_bootstrap as _metrc_facility_bootstrap
from services.metrc_facility_snapshot_bootstrap import SnapshottingMetrcFacilityBootstrapService

_metrc_facility_bootstrap.MetrcFacilityBootstrapService = SnapshottingMetrcFacilityBootstrapService

__all__ = ["SnapshottingMetrcFacilityBootstrapService"]
