"""A local facility must never mix sandbox and production provider evidence."""
from sqlalchemy import select
from modules.regulatory.models import RegulatoryFacilityMapping
from modules.integrations.models import IntegrationSyncState


def require_environment_isolation(session, organization_id, facility_id, environment):
    # Inactive mappings remain evidence of a previous provider environment.
    # Disabling a connection must not make historical identities safe to reuse.
    mapping=session.scalar(select(RegulatoryFacilityMapping.id).where(
        RegulatoryFacilityMapping.organization_id==organization_id,
        RegulatoryFacilityMapping.facility_id==facility_id,
        RegulatoryFacilityMapping.provider=='metrc',
        RegulatoryFacilityMapping.environment!=environment).limit(1))
    state=session.scalar(select(IntegrationSyncState.id).where(
        IntegrationSyncState.organization_id==organization_id,
        IntegrationSyncState.facility_id==facility_id,
        IntegrationSyncState.provider.in_(('metrc','metrc_sandbox')),
        IntegrationSyncState.environment!=environment).limit(1))
    if mapping is not None or state is not None:
        raise ValueError('This facility already contains Metrc evidence from another environment. Use a separate DoobieLogic facility; do not mix sandbox and production records.')
