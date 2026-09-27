"""Resolve explicitly scoped provider pairs without global-key environment guesses."""
from fastapi import HTTPException
from .metrc_context import metrc_scope_key, metrc_sandbox_scope_key
from .metrc_production_context import platform_vendor_scope, production_vendor_scope


def vendor_for_setup(service,context,environment):
    provider='metrc' if environment=='production' else 'metrc_sandbox'
    scope=production_vendor_scope(context) if environment=='production' else metrc_sandbox_scope_key(context)
    row=service.get('facility',scope,provider)
    if row is not None:
        if row.organization_id!=context.organization_id or row.facility_id!=context.facility_id:
            return None
    else:
        row=service.get('platform',platform_vendor_scope('MA',environment),'metrc')
        if row is not None and (row.organization_id is not None or row.facility_id is not None):
            return None
    config=service.public(row).get('configuration') or {}
    if config.get('state')!='MA' or config.get('environment')!=environment:
        return None
    return row


def discover_pair(service,context,environment):
    from ..routers.sandbox_integrations import fetch_metrc_resource
    vendor=vendor_for_setup(service,context,environment)
    user=service.get('user',metrc_scope_key(context),'metrc')
    config=service.public(user).get('configuration') or {}
    if not vendor or not vendor.encrypted_secret or not user or not user.encrypted_secret:
        raise HTTPException(409,'Save your user key and configure the platform key for this state and environment first.')
    if (user.organization_id!=context.organization_id or user.facility_id!=context.facility_id
            or config.get('state')!='MA' or config.get('environment')!=environment):
        raise HTTPException(409,'The user credential does not match this facility environment.')
    user_key=service.secret(user)
    vendor_key=service.secret(vendor)
    if user_key==vendor_key:
        raise HTTPException(422,'The user API key must be distinct from the platform integrator key.')
    result=fetch_metrc_resource(state='MA',user_api_key=user_key,integrator_api_key=vendor_key,
        resource='facilities',environment=environment,timeout_seconds=30,max_attempts=1)
    if not result.get('ok'):
        status=result.get('http_status')
        status=status if status in {403,429} else 502
        raise HTTPException(status,'Metrc discovery could not be verified. Check the saved user key, provider permissions and platform connection.')
    records=result.get('records')
    if not isinstance(records,list) or len(records)>100 or any(not isinstance(row,dict) for row in records):
        raise HTTPException(502,'Metrc returned an unsupported facility list. No local records were created.')
    return vendor,user,records


def finish_link(engine,settings,context,environment,record):
    from modules.integrations import IntegrationConfigurationService
    from . import metrc_natural_sync
    service=IntegrationConfigurationService(engine,settings.integration_encryption_key)
    credential=service.get('user',metrc_scope_key(context),'metrc')
    vendor=vendor_for_setup(service,context,environment)
    if credential is None or vendor is None or vendor.scope_type!='facility':
        raise RuntimeError('Scoped provider pair was not created')
    service.validation_result(credential.id,ok=True)
    service.validation_result(vendor.id,ok=True)
    # Reuse the same composed snapshot bootstrap as the normal integration path.
    metrc_natural_sync.ResilientSnapshottingMetrcFacilityBootstrapService(engine)._persist(
        organization_id=context.organization_id,facility_id=context.facility_id,
        resource='facility_profile',environment=environment,actor=context.user_id,
        records=[record],transport='metrc_facilities')
