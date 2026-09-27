"""Guided setup uses real local services; only Metrc network reads are fixtures."""
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import json
import secrets
import os,shutil,subprocess,sys
from pathlib import Path
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from backend.app.auth import RequestContext, get_request_context
from backend.app.config import Settings, get_settings
from backend.app.database import get_engine
from backend.app.routers import guided_metrc_setup as routes, sandbox_integrations
from backend.app.services.guided_metrc_setup import GuidedMetrcSetup, single_setup, RUN_KEY
from backend.app.services.adoption_models import ReadinessAnnotation
from modules.coman.models import Base, AppUser, Facility, Organization
from modules.coman.permissions import AppUserPermissionOverride
from modules.cultivation import models as cultivation_models  # Registers referenced canonical plant metadata.
from modules.inventory_transfers import models as inventory_transfer_models  # Existing transfer-control FK targets.
from modules.alpha_mode import AlphaOperatingModeService
from modules.integrations import IntegrationConfigurationService
from modules.integrations.models import IntegrationConfiguration, IntegrationSyncState
from modules.regulatory.models import RegulatoryFacilityMapping

PREFIX='/api/v1/integration-wizard/metrc-setup'

@pytest.fixture(scope='module')
def schema_file(tmp_path_factory):
    path=tmp_path_factory.mktemp('wizard_schema')/'base.sqlite3'
    url='sqlite:///'+path.as_posix()
    env=dict(os.environ,APP_ENV='test',DATABASE_URL=url,COMAN_DATABASE_URL=url,
             PYTHON_DOTENV_DISABLED='1',AI_ALLOW_CLOUD_FALLBACK='false')
    result=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],
        cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True,text=True,timeout=120)
    assert result.returncode==0,(result.stdout+result.stderr)[-4000:]
    return path

@pytest.fixture
def setup(monkeypatch,tmp_path,schema_file):
    path=tmp_path/'test.sqlite3';shutil.copy2(schema_file,path)
    engine=create_engine('sqlite:///'+path.as_posix(),connect_args={'check_same_thread':False})
    with Session(engine) as session,session.begin():
        session.add_all([Organization(id='org',name='Own',slug='own'),Organization(id='other',name='Other',slug='other')])
        session.flush()
        session.add_all([Facility(id='facility',organization_id='org',name='New facility',code='NEW',cultivation_enabled=True),
                         Facility(id='foreign',organization_id='other',name='Foreign facility',code='OTHER')])
        session.add(AppUser(id='admin',organization_id='org',username='admin',normalized_username='admin',role='admin',password_hash='unusable-test'))
    context=RequestContext('admin','org','facility','admin')
    state={'context':context}
    settings=Settings(_env_file=None,app_env='test',integration_encryption_key='test-only-encryption-key')
    AlphaOperatingModeService(engine).set_mode('org','facility',mode='metrc_sandbox',actor='admin')
    service=IntegrationConfigurationService(engine,settings.integration_encryption_key)
    vendor_secret=secrets.token_urlsafe(32)
    service.save(scope_type='facility',scope_key='org:facility:sandbox',provider='metrc_sandbox',
        organization_id='org',facility_id='facility',configuration={'state':'MA','environment':'sandbox'},
        secret=vendor_secret,actor='admin')
    records=[{'Id':101,'Name':'Owned Grow','License':{'Number':'MC123456'},
              'FacilityType':{'Name':'Cultivator','CanGrowPlants':True}}]
    calls=[]
    def fetch(**kwargs):
        calls.append({k:v for k,v in kwargs.items() if k not in {'user_api_key','integrator_api_key'}})
        return {'ok':True,'records':records,'payload':records,'http_status':200}
    monkeypatch.setattr(sandbox_integrations,'fetch_metrc_resource',fetch)
    api=FastAPI()
    api.dependency_overrides[get_request_context]=lambda:state['context']
    api.dependency_overrides[get_engine]=lambda:engine
    api.dependency_overrides[get_settings]=lambda:settings
    api.include_router(routes.router,prefix='/api/v1')
    with TestClient(api) as client:
        yield SimpleNamespace(engine=engine,context=context,state=state,settings=settings,
                              client=client,service=service,records=records,calls=calls,vendor_secret=vendor_secret)
    engine.dispose()

def post(h,path,body=None):
    response=h.client.post(PREFIX+path,json=body if body is not None else {})
    assert response.status_code==200,response.text
    return response.json()

def configured(h):
    secret=secrets.token_urlsafe(32)
    post(h,'/credentials',{'state':'MA','api_key':secret})
    preview=post(h,'/preview')
    return secret,preview


def test_key_save_is_encrypted_and_preview_never_creates_facilities(setup):
    h=setup
    first=h.client.get(PREFIX)
    assert first.status_code==200 and h.calls==[]
    secret,preview=configured(h)
    assert preview['local_records_created']==0 and preview['provider_mutations']==0
    assert preview['facilities'][0]['license_number']=='MC123456'
    with Session(h.engine) as session:
        assert session.scalar(select(func.count()).select_from(Facility))==2
        assert session.scalar(select(func.count()).select_from(RegulatoryFacilityMapping))==0
        row=session.scalar(select(IntegrationConfiguration).where(IntegrationConfiguration.provider=='metrc'))
        assert secret not in row.encrypted_secret and h.service.secret(row)==secret
    assert all(call['resource']=='facilities' and call['environment']=='sandbox' for call in h.calls)
    result=h.client.get(PREFIX).text
    assert secret not in result and h.vendor_secret not in result and 'secret_hint' not in result


def test_link_is_explicit_scoped_and_repeated_import_does_not_create_facility(setup):
    h=setup
    _,preview=configured(h)
    body={'license_number':'MC123456','preview_id':preview['preview_id'],'confirmed':True}
    assert post(h,'/link',body)['linked']
    with Session(h.engine) as session:
        assert session.get(Facility,'facility').license_number=='MC123456'
        assert session.scalar(select(func.count()).select_from(RegulatoryFacilityMapping))==1
        assert session.scalar(select(func.count()).select_from(Facility))==2
    # Binding changes credentials' metadata, so stale confirmation is rejected.
    assert h.client.post(PREFIX+'/link',json=body).status_code==409
    refreshed=post(h,'/preview')
    assert post(h,'/link',dict(body,preview_id=refreshed['preview_id']))['linked']
    status=h.client.get(PREFIX).json()
    assert status['trusted_mapping'] and status['configured']
    assert status['production_writes_enabled'] is False
    with Session(h.engine) as session:
        assert session.scalar(select(func.count()).select_from(RegulatoryFacilityMapping))==1


def test_permission_denials_precede_secret_parse_and_provider_network(setup):
    h=setup
    h.state['context']=replace(h.context,role='read_only')
    result=h.client.post(PREFIX+'/credentials',content='not valid json')
    assert result.status_code==403
    assert h.client.post(PREFIX+'/preview',json={}).status_code==403
    assert h.calls==[]
    h.state['context']=replace(h.context,organization_id='other',facility_id='foreign')
    assert h.client.get(PREFIX).status_code==403 and h.calls==[]


def test_invalid_secret_never_echoed_and_production_not_implicitly_enabled(setup):
    h=setup
    secret='PRIVATE-CREDENTIAL-DO-NOT-ECHO'
    response=h.client.post(PREFIX+'/credentials',json={'state':'MA','api_key':secret,'environment':'production'})
    assert response.status_code==422 and secret not in response.text
    AlphaOperatingModeService(h.engine).set_mode('org','facility',mode='doobielogic_sandbox',actor='admin')
    assert h.client.post(PREFIX+'/credentials',json={'state':'MA','api_key':secret}).status_code==409
    assert h.client.post(PREFIX+'/preview',json={}).status_code==409
    assert h.calls==[]


def test_preview_drift_and_conflicting_local_license_are_rejected(setup):
    h=setup
    _,preview=configured(h)
    body={'license_number':'MC123456','preview_id':preview['preview_id'],'confirmed':True}
    h.records[0]['Name']='Changed provider name'
    assert h.client.post(PREFIX+'/link',json=body).status_code==409
    preview=post(h,'/preview')
    with Session(h.engine) as session,session.begin():
        session.get(Facility,'facility').license_number='MC-OTHER'
    assert h.client.post(PREFIX+'/link',json=dict(body,preview_id=preview['preview_id'])).status_code==409
    with Session(h.engine) as session:
        assert session.scalar(select(func.count()).select_from(RegulatoryFacilityMapping))==0


def test_setup_lock_blocks_duplicate_attempt_and_releases_after_failure(setup):
    h=setup
    with single_setup(h.engine,'org','facility'):
        with pytest.raises(HTTPException) as failure:
            with single_setup(h.engine,'org','facility'):
                pytest.fail('Overlapping operation was admitted')
        assert failure.value.status_code==409
    with pytest.raises(RuntimeError):
        with single_setup(h.engine,'org','facility'):
            raise RuntimeError('simulated interruption')
    with single_setup(h.engine,'org','facility'):
        pass


def test_effective_permission_denial_blocks_key_save(setup):
    h=setup
    with Session(h.engine) as session,session.begin():
        session.add(AppUserPermissionOverride(user_id='admin',organization_id='org',facility_id='facility',
            permission='integrations.manage_metrc',effect='deny',created_by='admin',updated_by='admin'))
    assert h.client.post(PREFIX+'/credentials',json={'state':'MA','api_key':'synthetic-key'}).status_code==403
    assert h.calls==[]


def production_setup(h):
    AlphaOperatingModeService(h.engine).set_mode('org','facility',mode='metrc_production',actor='admin')
    h.service.save(scope_type='platform',scope_key='vendor:MA:production',provider='metrc',
        organization_id=None,facility_id=None,configuration={'state':'MA','environment':'production'},
        secret=secrets.token_urlsafe(32),actor='platform-test',audit_organization_id='org')


def test_explicit_production_import_pair_does_not_enable_unverified_writes(setup):
    h=setup;production_setup(h)
    _,preview=configured(h)
    assert preview['environment']=='production'
    linked=post(h,'/link',{'license_number':'MC123456','preview_id':preview['preview_id'],'confirmed':True})
    assert linked['environment']=='production'
    from backend.app.services.metrc_context import resolve_metrc_context
    _,context=resolve_metrc_context(h.engine,h.settings,h.context)
    assert context.configured and context.trusted_mapping and context.status=='connected'
    assert context.environment=='production' and context.provider_dispatch is None
    assert not h.client.get(PREFIX).json()['production_writes_enabled']
    assert all(call['environment']=='production' and call['resource']=='facilities' for call in h.calls)
    with pytest.raises(ValueError,match='another environment'):
        AlphaOperatingModeService(h.engine).set_mode('org','facility',mode='metrc_sandbox',actor='admin')


def test_production_never_reuses_sandbox_platform_key(setup):
    h=setup
    AlphaOperatingModeService(h.engine).set_mode('org','facility',mode='metrc_production',actor='admin')
    post(h,'/credentials',{'state':'MA','api_key':secrets.token_urlsafe(24)})
    response=h.client.post(PREFIX+'/preview',json={})
    assert response.status_code==409 and h.calls==[]


def test_link_failure_rolls_back_credentials_mapping_and_facility(setup,monkeypatch):
    h=setup
    _,preview=configured(h)
    from backend.app.services import guided_metrc_setup
    def fail(*args,**kwargs):raise RuntimeError('synthetic completion failure')
    monkeypatch.setattr(guided_metrc_setup,'finish_link',fail)
    response=h.client.post(PREFIX+'/link',json={'license_number':'MC123456','preview_id':preview['preview_id'],'confirmed':True})
    assert response.status_code==503
    with Session(h.engine) as session:
        assert session.get(Facility,'facility').license_number==''
        assert session.scalar(select(func.count()).select_from(RegulatoryFacilityMapping))==0
        credential=session.scalar(select(IntegrationConfiguration).where(IntegrationConfiguration.scope_type=='user'))
        assert not json.loads(credential.configuration_json).get('license_number')


def test_import_returns_before_provider_work_and_persists_progress(setup,monkeypatch):
    from threading import Event
    import time
    from backend.app.services.guided_metrc_setup import MetrcPolicySyncControlService
    h=setup;_,preview=configured(h)
    post(h,'/link',{'license_number':'MC123456','preview_id':preview['preview_id'],'confirmed':True})
    entered,release=Event(),Event()
    def sync(*args,**kwargs):
        entered.set()
        assert release.wait(5)
        return {'sync_mode':'full_hydration','totals':{'records':4,'accepted':4,'errors':0}}
    monkeypatch.setattr(MetrcPolicySyncControlService,'sync',sync)
    try:
        response=h.client.post(PREFIX+'/import',json={'confirmed':True})
        assert response.status_code==202
        assert entered.wait(2)
        assert h.client.get(PREFIX).json()['run']['status']=='running'
        assert h.client.post(PREFIX+'/import',json={'confirmed':True}).status_code==409
        assert h.client.post(PREFIX+'/credentials',json={'state':'MA','api_key':'different-test-key'}).status_code==409
    finally:release.set()
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        run=h.client.get(PREFIX).json()['run']
        if run['status']=='completed':break
        time.sleep(.05)
    assert run['status']=='completed' and run['id']==response.json()['id']
    assert run['provider_mutations']==0 and run['totals']['records']==4


def test_missing_facility_can_be_created_from_provider_and_reused(setup):
    h=setup;_,preview=configured(h)
    body={'license_number':'MC123456','preview_id':preview['preview_id'],'confirmed':True,'create_new':True}
    first=post(h,'/link',body)
    assert first['facility_id']!='facility'
    with Session(h.engine) as session:
        row=session.get(Facility,first['facility_id'])
        assert row.name=='Owned Grow' and row.license_number=='MC123456'
        assert session.scalar(select(func.count()).select_from(Facility))==3
        assert session.get(Facility,'facility').license_number==''
    # The original discovery credential is unchanged when linking a new mirror.
    again=post(h,'/link',body)
    assert again['facility_id']==first['facility_id']
    with Session(h.engine) as session:
        assert session.scalar(select(func.count()).select_from(Facility))==3
    h.state['context']=replace(h.context,facility_id=first['facility_id'])
    read=h.client.get(PREFIX).json()
    assert read['configured'] and read['trusted_mapping'] and read['mode']=='metrc_sandbox'


def test_full_import_populates_canonical_workspaces_and_replay_is_idempotent(setup,monkeypatch):
    from backend.app.services import metrc_natural_sync
    from services.metrc_natural_bootstrap import NaturalMetrcFacilityBootstrapService
    from services import metrc_facility_bootstrap
    from modules.coman.models import Product,InventoryLot,InventoryTransaction
    from modules.cultivation.models import CultivationPlant,CultivationRoom
    h=setup;_,preview=configured(h)
    post(h,'/link',{'license_number':'MC123456','preview_id':preview['preview_id'],'confirmed':True})
    payloads={
        'locations_active':[{'Id':10,'Name':'Flower 4'}],
        'items_active':[{'Id':20,'Name':'Provider Flower','ProductCategoryName':'Buds','UnitOfMeasureName':'Grams'}],
        'packages_active':[{'Id':30,'Label':'1A4FF0100000000000000300','Item':{'Id':20,'Name':'Provider Flower','ProductCategoryName':'Buds','UnitOfMeasureName':'Grams'},'Quantity':100,'UnitOfMeasureName':'Grams','LocationId':10,'LocationName':'Flower 4','LabTestingState':'TestPassed'}],
        'plants_vegetative':[{'Id':40,'Label':'1A4FF0100000000000000400','StrainName':'Gelato','LocationId':10,'LocationName':'Flower 4'}],
    }
    reads=[]
    def fetched(**kwargs):
        reads.append((kwargs['resource'],kwargs['environment'],kwargs['license_number']))
        rows=payloads.get(kwargs['resource'],[])
        return {'ok':True,'http_status':200,'payload':{'Data':rows,'TotalPages':1},
            'records':[{'provider':'metrc','resource':kwargs['resource'],'provider_id':str(row['Id']),'source':row} for row in rows]}
    def direct(self,path,params):
        return {'ok':True,'http_status':200,'payload':{'Data':[],'TotalPages':1},'records':[]}
    monkeypatch.setattr(metrc_facility_bootstrap,'fetch_metrc_resource',fetched)
    monkeypatch.setattr(metrc_facility_bootstrap.MetrcTransport,'get',direct)
    monkeypatch.setattr(metrc_natural_sync,'ResilientSnapshottingMetrcFacilityBootstrapService',NaturalMetrcFacilityBootstrapService)
    service=GuidedMetrcSetup(h.engine,h.settings,h.context)
    first=service.import_records()
    assert first['status']=='completed',first
    def counts():
        with Session(h.engine) as session:
            return tuple(session.scalar(select(func.count()).select_from(model)) for model in
                         (Product,InventoryLot,InventoryTransaction,CultivationPlant,CultivationRoom))
    before=counts()
    assert all(value==1 for value in before),before
    # Force a full rebaseline, preserving and exercising canonical identities.
    with Session(h.engine) as session,session.begin():
        row=session.scalar(select(IntegrationSyncState).where(IntegrationSyncState.resource=='items'))
        row.status='failed'
    second=service.import_records()
    assert second['status']=='completed' and counts()==before
    assert reads and all(environment=='sandbox' and license_number=='MC123456' for _,environment,license_number in reads)
    with Session(h.engine) as session:
        assert session.scalar(select(InventoryLot.lot_code))=='1A4FF0100000000000000300'
        assert session.scalar(select(CultivationPlant.plant_tag))=='1A4FF0100000000000000400'
