"""Production is a separate facility environment, never a sandbox key fallback."""
from modules.integrations import IntegrationConfigurationService
from modules.regulatory import RegulatoryMappingService


def production_vendor_scope(context):
    return f'{context.organization_id}:{context.facility_id}:production'


def platform_vendor_scope(state, environment):
    return f'vendor:{state}:{environment}'


def resolve_production_metrc(engine, settings, context):
    from .metrc_context import MetrcContext, metrc_scope_key
    if not settings.integration_encryption_key:
        return None, MetrcContext(configured=False, environment='production', status='credential_storage_unavailable',
            message='Protected production credential storage is unavailable.')
    service=IntegrationConfigurationService(engine,settings.integration_encryption_key)
    user=service.get('user',metrc_scope_key(context),'metrc')
    vendor=service.get('facility',production_vendor_scope(context),'metrc')
    config=service.public(user).get('configuration') or {}
    vendor_config=service.public(vendor).get('configuration') or {}
    state=str(config.get('state') or '').upper()
    license_number=str(config.get('license_number') or '').strip()
    scoped=lambda row: bool(row and row.organization_id==context.organization_id and row.facility_id==context.facility_id)
    pair=bool(scoped(user) and scoped(vendor) and state and license_number and
        config.get('environment')=='production' and vendor_config.get('environment')=='production' and
        vendor_config.get('state')==state and vendor_config.get('license_number')==license_number)
    if not pair:
        return service,MetrcContext(configured=False,state=state,license_number=license_number,
            environment='production',status='production_pairing_required',row=user,
            message='Confirm the exact production license with the platform vendor connection before importing or submitting records.')
    user_key=service.secret(user)
    vendor_key=service.secret(vendor)
    configured=bool(user_key and vendor_key and user_key!=vendor_key)
    mapping=RegulatoryMappingService(engine).get(organization_id=context.organization_id,
        facility_id=context.facility_id,provider='metrc',license_number=license_number,environment='production')
    trusted=bool(mapping and mapping.integration_configuration_id==user.id and mapping.jurisdiction_code==state
                 and mapping.verified_at is not None)
    connected=user.status=='connected' and vendor.status=='connected'
    # Read-only onboarding does not bypass the existing production dispatch gate.
    dispatch=None
    capabilities={}
    for source in (vendor_config.get('provider_capabilities'),config.get('provider_capabilities')):
        if isinstance(source,dict):
            capabilities.update({key:value for key,value in source.items() if isinstance(key,str) and type(value) is bool})
    return service,MetrcContext(configured=configured,state=state,license_number=license_number,
        user_api_key=user_key if configured else '',integrator_api_key=vendor_key if configured else '',
        environment='production',status='connected' if connected else 'configured',trusted_mapping=trusted,
        provider_capabilities=capabilities,row=user,mapping=mapping,provider_dispatch=dispatch,
        message='Production connection verified. Each write still requires its supported operation and approval checks.'
            if configured and trusted and connected else 'Validate the exact production connection and facility mapping before continuing.')
