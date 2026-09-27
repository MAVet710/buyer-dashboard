"""Opt-in loopback acceptance only. Synthetic providers, actual app handlers and DB."""
from pathlib import Path
import argparse
import os
import sys
import json
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--allow-synthetic-loopback',action='store_true')
    parser.add_argument('--directory',required=True)
    args=parser.parse_args()
    if not args.allow_synthetic_loopback:raise SystemExit('Explicit synthetic loopback opt-in is required')
    folder=Path(args.directory).resolve();folder.mkdir(parents=True,exist_ok=True)
    url='sqlite:///'+(folder/'app.sqlite3').as_posix()
    if (folder/'app.sqlite3').exists():raise SystemExit('Use a new isolated directory')
    safe={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE','APPDATA','LOCALAPPDATA','COMSPEC','PATHEXT','NUMBER_OF_PROCESSORS','PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMW6432'}}
    os.environ.clear();os.environ.update(safe)
    os.environ.update(APP_ENV='test',DATABASE_URL=url,COMAN_DATABASE_URL=url,PYTHON_DOTENV_DISABLED='1',
        AI_ALLOW_CLOUD_FALLBACK='false',SANDBOX_STARTUP_SEED_ENABLED='false',
        INTEGRATION_ENCRYPTION_KEY='synthetic-only-browser-encryption',ALLOWED_HOSTS='127.0.0.1,localhost,testserver',
        CORS_ORIGINS='http://127.0.0.1:4194',CULTIVATION_EDGE_PATH=str(folder/'edge.sqlite3'),
        CULTIVATION_RADIO_CONFIG='',CULTIVATION_NETWORK_CONFIG='',CULTIVATION_MAINTENANCE_CONFIG='')
    from alembic import command
    from alembic.config import Config
    command.upgrade(Config(str(ROOT/'alembic.ini')),'head')
    from backend.app.main import app
    from backend.app.database import get_engine
    from backend.app.auth import RequestContext,get_request_context
    from backend.app.config import get_settings
    from fastapi import Request
    from sqlalchemy.orm import Session
    from modules.coman.models import Organization,Facility,AppUser
    from modules.cultivation.models import CultivationRoom
    from modules.alpha_mode import AlphaOperatingModeService
    from modules.integrations import IntegrationConfigurationService
    engine=get_engine();settings=get_settings()
    with Session(engine) as session,session.begin():
        session.add(Organization(id='fixture-org',name='Synthetic acceptance',slug='synthetic-acceptance'));session.flush()
        session.add(Facility(id='fixture-facility',organization_id='fixture-org',name='Synthetic grow',code='SYNTHETIC',cultivation_enabled=True,production_enabled=True));session.flush()
        session.add(AppUser(id='fixture-admin',organization_id='fixture-org',username='synthetic-admin',normalized_username='synthetic-admin',role='admin',password_hash='unusable-fixture',must_change_password=False))
        session.add(CultivationRoom(id='fixture-room',organization_id='fixture-org',facility_id='fixture-facility',room_code='FLOWER',display_name='Synthetic Flower Room'))
    AlphaOperatingModeService(engine).set_mode('fixture-org','fixture-facility',mode='metrc_sandbox',actor='fixture-admin')
    configs=IntegrationConfigurationService(engine,settings.integration_encryption_key)
    configs.save(scope_type='platform',scope_key='vendor:MA:sandbox',provider='metrc',organization_id=None,facility_id=None,
        configuration={'state':'MA','environment':'sandbox'},secret='synthetic-vendor-credential',actor='fixture-admin',audit_organization_id='fixture-org')
    def context(request:Request):
        role='read_only' if request.cookies.get('synthetic_fixture_role')=='read_only' or request.headers.get('x-user-role')=='read_only' else 'admin'
        return RequestContext('fixture-admin','fixture-org','fixture-facility',role)
    app.dependency_overrides[get_request_context]=context
    from backend.app.routers import sandbox_integrations,cultivation_networks
    from services import metrc_facility_bootstrap
    facility={'Id':101,'Name':'Synthetic licensed grow','License':{'Number':'MC123456'},'FacilityType':{'Name':'Cultivator','CanGrowPlants':True}}
    def facilities(**kwargs):return {'ok':True,'http_status':200,'records':[facility],'payload':[facility]}
    sandbox_integrations.fetch_metrc_resource=facilities
    payloads={'locations_active':[{'Id':10,'Name':'Imported Flower Room'}],
        'items_active':[{'Id':20,'Name':'Synthetic Provider Flower','ProductCategoryName':'Buds','UnitOfMeasureName':'Grams'}],
        'packages_active':[{'Id':30,'Label':'1A4FF0100000000000000300','Item':{'Id':20,'Name':'Synthetic Provider Flower','ProductCategoryName':'Buds','UnitOfMeasureName':'Grams'},'Quantity':100,'UnitOfMeasureName':'Grams','LocationId':10,'LocationName':'Imported Flower Room','LabTestingState':'TestPassed'}]}
    def fetched(**kwargs):
        rows=payloads.get(kwargs['resource'],[])
        return {'ok':True,'http_status':200,'payload':{'Data':rows,'TotalPages':1},'records':[{'provider':'metrc','resource':kwargs['resource'],'provider_id':str(row['Id']),'source':row} for row in rows]}
    metrc_facility_bootstrap.fetch_metrc_resource=fetched
    from services import metrc_incremental_sync
    metrc_incremental_sync.fetch_metrc_resource=fetched
    metrc_facility_bootstrap.MetrcTransport.get=lambda self,path,params=None:{'ok':True,'http_status':200,'payload':{'Data':[],'TotalPages':1},'records':[]}
    from modules.cultivation.network.config import NetworkHostConfig
    from modules.cultivation.network.runtime import NetworkRuntime
    from modules.cultivation.edge_store import EdgeStore
    from tests.test_cultivation_networks import FakeHttp,FakeCapture,sample_uplink
    http=FakeHttp()
    host=NetworkHostConfig((('fixture-org','fixture-facility'),))
    NetworkHostConfig.verify_mqtt=lambda self:None
    runtime=NetworkRuntime(engine,host,settings.integration_encryption_key,edge=EdgeStore(folder/'edge.sqlite3'),http=http,capture_factory=FakeCapture)
    cultivation_networks.get_network_runtime=lambda:runtime
    from sqlalchemy import select
    from modules.cultivation.intelligence_models import TelemetryConnection
    counter=0
    @app.get('/fixture')
    def fixture():return {'organization_id':'fixture-org','facility_id':'fixture-facility','user_id':'fixture-admin','room_id':'fixture-room'}
    @app.get('/fixture/counts')
    def counts():
        from sqlalchemy import func
        from modules.coman.models import Product,InventoryLot,InventoryTransaction
        with Session(engine) as session:
            return {name:session.scalar(select(func.count()).select_from(model)) for name,model in
                    [('products',Product),('lots',InventoryLot),('inventory_transactions',InventoryTransaction)]}
    @app.post('/fixture/sample')
    def sample():
        nonlocal counter
        counter+=1;http.at=datetime.now(timezone.utc).isoformat()
        runtime.tick()
        for capture,_version in list(runtime.captures.values()):
            payload=sample_uplink();payload['uplink_message']['f_cnt']=counter
            capture.queue.put({'topic':'v3/grow-app@ttn/devices/sensor-1/up','payload':payload})
        runtime.tick()
        with Session(engine) as session:
            identities=session.scalars(select(TelemetryConnection.id).where(TelemetryConnection.mode=='network')).all()
        for identity in identities:
            control=runtime.control(identity)
            if control['data'].get('enabled'):
                if control['data']['adapter']=='aranet_cloud':runtime._poll(control)
                runtime._persist(control)
        return {'synthetic':True,'provider_mutations':0,'sequence':counter}
    import requests
    requests.sessions.Session.send=lambda *_args,**_kwargs: (_ for _ in ()).throw(RuntimeError('External network forbidden in synthetic acceptance'))
    import uvicorn
    try:uvicorn.run(app,host='127.0.0.1',port=8021,lifespan='off',access_log=False)
    finally:runtime.stop();engine.dispose()

if __name__=='__main__':main()
