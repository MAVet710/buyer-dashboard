from datetime import datetime,timedelta,timezone
import importlib
import json
import pytest
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,event,select,text,func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.app.auth import RequestContext,get_request_context
from backend.app.database import get_engine
from backend.app.routers.cultivation_intelligence_workspace import router
from modules.coman.models import Base,Organization,Facility,AppUser
from modules.coman.permissions import AppUserPermissionOverride
from modules.cultivation.intelligence_models import *
from modules.cultivation.intelligence_service import IntelligenceService
from modules.cultivation.gateway import TelemetryGatewayService
from modules.cultivation.edge_store import EdgeStore,Scope
from modules.cultivation.models import CultivationRoom,CultivationPlant,CultivationHarvestPlant,CultivationCostEntry
from modules.cultivation.telemetry import TelemetryService,Reading,TelemetryConflict
from modules.cultivation.telemetry_models import EnvironmentalObservation
from modules.cultivation.metrics import normalize_metric_value

AT=datetime(2026,1,2,12,tzinfo=timezone.utc)

@pytest.fixture
def setup(tmp_path):
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    @event.listens_for(engine,'connect')
    def fk(db,_):db.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    with Session(engine) as s,s.begin():
        s.add_all([Organization(id='o1',name='One',slug='one'),Organization(id='o2',name='Two',slug='two')]);s.flush()
        s.add_all([Facility(id='f1',organization_id='o1',name='One',code='one',cultivation_enabled=True),Facility(id='f2',organization_id='o2',name='Two',code='two',cultivation_enabled=True)]);s.flush()
        s.add_all([AppUser(id='a',organization_id='o1',username='a',normalized_username='a',password_hash='synthetic',role='admin'),AppUser(id='b',organization_id='o2',username='b',normalized_username='b',password_hash='synthetic',role='admin')])
        s.add_all([CultivationRoom(id='r1',organization_id='o1',facility_id='f1',room_code='A'),CultivationRoom(id='r2',organization_id='o2',facility_id='f2',room_code='A')])
        s.add_all([CultivationPlant(id='p1',organization_id='o1',facility_id='f1',plant_tag='1',strain_name='S',phase='flowering',room_code='A'),CultivationPlant(id='p2',organization_id='o2',facility_id='f2',plant_tag='2',strain_name='S',phase='flowering',room_code='A')])
    service=TelemetryGatewayService(engine,RequestContext('a','o1','f1','admin'),edge=EdgeStore(tmp_path/'edge.sqlite'))
    yield engine,service
    engine.dispose()

def cycle(service,code='C',**values):return service.create_cycle({'cycle_code':code,'display_name':code,**values})

def recipe(service):
    return service.create_recipe({'name':'Facility recipe','stages':[{'stage_key':'custom','display_name':'Custom stage','sequence':0,'targets':[{'metric':'temperature','unit':'C','minimum':20,'maximum':25}]}]})

def client(engine,role='admin',org='o1',facility='f1',user='a'):
    app=FastAPI();app.include_router(router,prefix='/api/v1');app.dependency_overrides[get_engine]=lambda:engine
    app.dependency_overrides[get_request_context]=lambda:RequestContext(user,org,facility,role)
    return TestClient(app)

def test_cycles_intervals_members_and_optimistic_version(setup):
    engine,s=setup;c=cycle(s)
    assert s.members(c['id'],{'version':1,'plant_ids':['p1'],'action':'add','effective_at':AT})['version']==2
    with pytest.raises(TelemetryConflict):s.members(c['id'],{'version':1,'plant_ids':['p1'],'action':'remove','effective_at':AT+timedelta(days=1)})
    other=cycle(s,'D')
    with pytest.raises(TelemetryConflict):s.members(other['id'],{'version':1,'plant_ids':['p1'],'action':'add','effective_at':AT+timedelta(hours=1)})
    with pytest.raises(LookupError):s.members(c['id'],{'version':2,'plant_ids':['p2'],'action':'add','effective_at':AT})
    s.occupancy(c['id'],{'version':2,'room_id':'r1','entered_at':AT,'exited_at':AT+timedelta(days=1)})
    with pytest.raises(TelemetryConflict):s.occupancy(c['id'],{'version':3,'room_id':'r1','entered_at':AT+timedelta(hours=1)})
    s.occupancy(c['id'],{'version':3,'room_id':'r1','entered_at':AT+timedelta(days=1)})
    assert len(s.cycle(c['id'])['occupancy'])==2
    assert s.exposure('p1')['exposure_status']=='unknown'


def test_recipe_approval_new_version_and_scope(setup):
    engine,s=setup;r=recipe(s)
    with pytest.raises(ValueError):cycle(s,recipe_id=r['id'])
    approved=s.approve_recipe(r['id'],{'version':r['version']})
    assert approved['approved_by']=='a' and approved['status']=='approved'
    with pytest.raises(TelemetryConflict):s.approve_recipe(r['id'],{'version':1})
    newer=recipe(s);assert newer['version']==2 and newer['status']=='draft'
    c=cycle(s,recipe_id=r['id'])
    assert c['recipe_id']==r['id']
    other=IntelligenceService(engine,RequestContext('b','o2','f2','admin'))
    with pytest.raises(LookupError):other.approve_recipe(r['id'],{'version':1})


@pytest.mark.parametrize('role',['read_only','buyer','planner'])
def test_http_and_direct_permissions(setup,role):
    engine,s=setup;body={'cycle_code':'C','display_name':'C'}
    assert client(engine,role).post('/api/v1/cultivation-intelligence/cycles',json=body).status_code==403
    direct=IntelligenceService(engine,RequestContext('a','o1','f1',role))
    with pytest.raises(HTTPException):direct.create_cycle(body)
    flags=client(engine,role).get('/api/v1/cultivation-intelligence/workspace').json()
    assert not flags['can_manage'] and not flags['can_manage_connections']


def test_http_scope_unknown_fields_override_and_connection_admin(setup):
    engine,s=setup;c=cycle(s);base='/api/v1/cultivation-intelligence'
    assert client(engine).post(base+'/cycles',json={'cycle_code':'bad','display_name':'bad','organization_id':'o2'}).status_code==422
    assert client(engine,org='o2',facility='f2',user='b').get(base+'/cycles/'+c['id']).status_code==404
    assert client(engine,'operator').post(base+'/connections',json={'provider':'json','label':'x'}).status_code==403
    with Session(engine) as db,db.begin():db.add(AppUserPermissionOverride(user_id='a',organization_id='o1',facility_id='f1',permission='cultivation.manage_intelligence',effect='deny',created_by='a',updated_by='a'))
    assert client(engine).post(base+'/events',json={'room_id':'r1','title':'x','event_type':'inspection','occurred_at':AT.isoformat()}).status_code==403


def test_real_sqlite_scoped_foreign_keys(setup):
    engine,s=setup;c=cycle(s)
    with pytest.raises(IntegrityError),Session(engine) as db,db.begin():
        db.add(CropCycleRoom(id='bad',organization_id='o1',facility_id='f1',cycle_id=c['id'],room_id='r2',entered_at=AT,assigned_by='a'));db.flush()
    with pytest.raises(IntegrityError),Session(engine) as db,db.begin():
        db.add(TelemetryConnection(id='bad',organization_id='o2',facility_id='f1',provider='json',mode='file',label='bad',created_by='a'));db.flush()


def test_original_http_model_dict_and_canonical_retry(setup):
    engine,s=setup;t=TelemetryService(engine)
    raw={'source':'manual','event_id':'x','metric':'air_temperature','value':77,'unit':'F','observed_at':AT}
    model=Reading(**raw);assert model.value==25
    assert Reading.model_validate(model)._original==('air_temperature',77,'F')
    t.ingest('o1','f1','r1',[model],actor='a')
    assert t.ingest('o1','f1','r1',[{**raw,'metric':'temperature','value':25,'unit':'C'}],actor='a')['duplicates']==1
    with Session(engine) as db:
        row=db.scalar(select(EnvironmentalObservation));assert (row.source_metric,row.original_value,row.original_unit)==('air_temperature',77,'F')
    with pytest.raises(ValueError):t.ingest('o1','f1','r1',[raw],actor='a',enrichment={('manual','x','temperature',''):{'cycle_id':'foreign'}})


@pytest.mark.parametrize('metric,value,unit',[('temperature',True,'C'),('hvac_state',2,'bool'),('hvac_state',0.5,'state'),('irrigation_volume',1,'gal'),('temperature',float('inf'),'C')])
def test_registry_rejects_invalid_evidence(metric,value,unit):
    with pytest.raises(ValueError):normalize_metric_value(metric,value,unit)


def configure(s):
    connection=s.create_connection({'provider':'json','label':'Fixture'})
    device=s.create_device(connection['id'],{'version':1,'source_device_id':'dev'})
    s.map_device(device['id'],{'version':1,'room_id':'r1','effective_at':AT-timedelta(days=1)})
    s.create_sensor(device['id'],{'version':2,'source_channel':'air','source_metric':'temp','source_unit':'F','metric':'temperature'})
    raw={'event_id':'one','source_device_id':'dev','source_channel':'air','source_metric':'temp','value':77,'unit':'F','observed_at':AT.isoformat()}
    payload={'format':'json','content':json.dumps([raw]),'mappings':[{'source_channel':'air','source_metric':'temp','metric':'temperature','unit':'F'}]}
    return connection,device,payload


def test_gateway_authorizes_before_parse_and_fixture_never_live(setup,monkeypatch):
    engine,s=setup;connection,device,payload=configure(s)
    preview=s.preview(connection['id'],payload);assert preview['can_commit']
    result=s.import_content(connection['id'],{**payload,'digest':preview['digest']});assert result['accepted']==1
    assert s.import_content(connection['id'],{**payload,'digest':preview['digest']})['duplicates']==1
    assert s.health(connection['id'])['connection']['status']=='configured'
    assert not s.health(connection['id'])['connection']['live_supported']
    with Session(engine) as db:assert db.scalar(select(func.count()).select_from(EnvironmentalObservation))==0
    calls=[]
    monkeypatch.setattr(s,'_parse',lambda p:calls.append(p))
    with pytest.raises(LookupError):s.preview('other',payload)
    assert calls==[]
    s.revoke(connection['id'],{'version':s.health(connection['id'])['connection']['version']})
    with pytest.raises(TelemetryConflict):s.preview(connection['id'],payload)
    assert calls==[]


def test_ambiguous_cycles_do_not_guess_and_boundary_is_half_open(setup):
    engine,s=setup;connection,device,payload=configure(s)
    c1=cycle(s,'C1');c2=cycle(s,'C2')
    for c in (c1,c2):s.occupancy(c['id'],{'version':1,'room_id':'r1','entered_at':AT-timedelta(hours=1),'exited_at':AT+timedelta(hours=1)})
    with Session(engine) as db:
        resolve=s._resolver(db,connection['id']);snapshot=resolve(Scope('o1','f1',connection['id']),json.loads(payload['content'])[0])
        assert snapshot['cycle_id'] is None and snapshot['room_id']=='r1'
        raw=json.loads(payload['content'])[0];raw['observed_at']=(AT+timedelta(hours=1)).isoformat()
        assert resolve(Scope('o1','f1',connection['id']),raw)['cycle_id'] is None


def test_harvest_exact_membership_and_costs_once(setup):
    engine,s=setup;c=cycle(s);s.members(c['id'],{'version':1,'plant_ids':['p1'],'action':'add','effective_at':AT})
    with Session(engine) as db,db.begin():
        db.add(CultivationHarvest(id='h',organization_id='o1',facility_id='f1',harvest_code='H',strain='S',created_by='a',harvested_at=AT+timedelta(days=1)));db.flush()
        db.add(CultivationHarvestPlant(id='hp',organization_id='o1',facility_id='f1',harvest_id='h',plant_id='p1',assigned_by='a'))
        db.add(CultivationCostEntry(id='cost',organization_id='o1',facility_id='f1',entity_type='harvest',entity_id='h',cost_type='labor',amount=100,actor='a'))
    s.link_harvest(c['id'],{'version':2,'harvest_id':'h'})
    assert s.cycle(c['id'])['economics']['allocated_cost']==100
    assert s.cycle(c['id'])['economics']['true_cogs'] is None
    other=cycle(s,'other')
    with pytest.raises(ValueError):s.link_harvest(other['id'],{'version':1,'harvest_id':'h'})
    assert s.cycle(other['id'])['economics']['allocated_cost'] is None


def test_workspace_queries_are_bounded(setup):
    engine,s=setup
    for i in range(10):cycle(s,str(i))
    queries=[]
    def count(*args):queries.append(args[2])
    event.listen(engine,'before_cursor_execute',count)
    try:result=s.workspace()
    finally:event.remove(engine,'before_cursor_execute',count)
    assert len(result['cycles'])==10 and len(queries)<=12


def test_populated_0085_upgrade_preserves_originals_and_refuses_downgrade():
    old=importlib.import_module('migrations.versions.0085_cultivation_telemetry')
    new=importlib.import_module('migrations.versions.0086_cultivation_intelligence')
    engine=create_engine('sqlite://')
    with engine.begin() as conn:
        # Minimal canonical predecessor with populated legacy evidence, no current ORM DDL.
        for table in ('coman_facilities','cultivation_plants','cultivation_plant_groups','cultivation_harvests','integration_configurations','cultivation_rooms'):
            conn.execute(text(f'CREATE TABLE {table} (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36), facility_id VARCHAR(36))'))
        conn.execute(text('CREATE TABLE app_users (id VARCHAR(36) PRIMARY KEY)'))
        conn.execute(text("INSERT INTO cultivation_rooms VALUES ('r1','o1','f1')"))
        with Operations.context(MigrationContext.configure(conn)):
            old.upgrade()
            conn.execute(text("INSERT INTO cultivation_environment_observations VALUES ('e1','o1','f1','r1','temperature','manual','event','','25','C','valid','2026-01-02','2026-01-02')"))
            new.upgrade()
            row=conn.execute(text('SELECT original_value,original_unit,source_metric FROM cultivation_environment_observations')).one()
            assert tuple(row)==(None,None,None)
            conn.execute(text("UPDATE cultivation_environment_observations SET original_value=77,original_unit='F'"))
            with pytest.raises(RuntimeError,match='Original telemetry evidence'):new.downgrade()
            conn.execute(text('UPDATE cultivation_environment_observations SET original_value=NULL,original_unit=NULL'))
            new.downgrade()
            assert conn.execute(text('SELECT count(*) FROM cultivation_environment_observations')).scalar()==1
            new.upgrade()
            conn.execute(text("INSERT INTO cultivation_recipes (id,organization_id,facility_id,name,version,description,status,created_by,created_at,updated_at,approved_by,approved_at) VALUES ('recipe','o1','f1','Recipe',1,'','approved','a','2026-01-01','2026-01-01','a','2026-01-01')"))
            with pytest.raises(IntegrityError,match='approved_recipe_immutable'):conn.execute(text("UPDATE cultivation_recipes SET name='changed'"))
            with pytest.raises(RuntimeError,match='evidence exists'):new.downgrade()



def test_zone_room_binding_and_open_stage_close(setup):
    engine,s=setup
    zone=s.create_zone('r1',{'zone_code':'bench-a','display_name':'Bench A'})
    assert s.room('r1')['zones'][0]['id']==zone['id']
    c=cycle(s)
    interval=s.occupancy(c['id'],{'version':1,'room_id':'r1','zone_id':zone['id'],'entered_at':AT})
    future=datetime.now(timezone.utc)+timedelta(hours=1)
    result=s.close_occupancy(c['id'],interval['id'],{'version':2,'exited_at':future})
    assert result['version']==3
    s.occupancy(c['id'],{'version':3,'room_id':'r1','zone_id':zone['id'],'entered_at':future})
    with pytest.raises(TelemetryConflict):s.close_occupancy(c['id'],interval['id'],{'version':4,'exited_at':future+timedelta(hours=1)})
    with pytest.raises(IntegrityError),Session(engine) as db,db.begin():
        db.add(DeviceMapping(id='invalid',organization_id='o1',facility_id='f1',device_id='absent',room_id='r2',zone_id=zone['id'],effective_at=AT,created_by='a'));db.flush()


def test_original_http_alias_whitespace_and_no_double_conversion(setup):
    from backend.app.routers.cultivation_telemetry import router as legacy
    engine,s=setup
    app=FastAPI();app.include_router(legacy,prefix='/api/v1')
    app.dependency_overrides[get_engine]=lambda:engine
    app.dependency_overrides[get_request_context]=lambda:s.context
    http=TestClient(app)
    response=http.post('/api/v1/inventory/production/plants/telemetry/rooms/r1/observations',json={'observations':[{'source':'manual','event_id':'original','metric':' air_temperature ','value':77,'unit':' F ','observed_at':AT.isoformat()}]})
    assert response.status_code==200,response.text
    with Session(engine) as db:
        row=db.scalar(select(EnvironmentalObservation))
        assert (row.value,row.unit)==(25,'C')
        assert (row.source_metric,row.original_value,row.original_unit)==(' air_temperature ',77,' F ')
    snapshot=TelemetryService(engine).snapshot('o1','f1','r1',now=AT)
    observed=next(r for r in snapshot['readings'] if r['value'] is not None)
    assert observed['original']['provenance']=='captured'


def test_preview_digest_scope_content_and_replay_after_future_remap(setup):
    engine,s=setup;connection,device,payload=configure(s)
    preview=s.preview(connection['id'],payload)
    first=s.import_content(connection['id'],{**payload,'digest':preview['digest']})
    assert first['accepted']==1
    scope=Scope('o1','f1',connection['id'])
    original=s.edge().evidence(scope)['items'][0]['snapshot']
    s.map_device(device['id'],{'version':3,'room_id':'r1','effective_at':datetime.now(timezone.utc)+timedelta(days=1)})
    with pytest.raises(TelemetryConflict):s.import_content(connection['id'],{**payload,'digest':preview['digest']})
    preview=s.preview(connection['id'],payload)
    replay=s.import_content(connection['id'],{**payload,'digest':preview['digest']})
    assert replay['duplicates']==1
    assert s.edge().evidence(scope)['items'][0]['snapshot']==original
    with pytest.raises(TelemetryConflict):s.import_content(connection['id'],{**payload,'content':payload['content'].replace('77','78'),'digest':preview['digest']})


def test_authorized_configuration_and_membership_concurrent_file_sqlite(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    engine=create_engine('sqlite:///'+str(tmp_path/'concurrency.sqlite'),connect_args={'timeout':10})
    @event.listens_for(engine,'connect')
    def fk(db,_):db.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    with Session(engine) as db,db.begin():
        db.add(Organization(id='o',name='O',slug='o'));db.flush()
        db.add(Facility(id='f',organization_id='o',name='F',code='f',cultivation_enabled=True));db.flush()
        db.add(AppUser(id='u',organization_id='o',username='u',normalized_username='u',password_hash='synthetic',role='admin'))
        db.add(CultivationPlant(id='p',organization_id='o',facility_id='f',plant_tag='p',strain_name='S',phase='flowering'))
    s=IntelligenceService(engine,RequestContext('u','o','f','admin'))
    first,second=cycle(s,'first'),cycle(s,'second')
    def join(c):
        try:return s.members(c['id'],{'version':1,'plant_ids':['p'],'action':'add','effective_at':AT})
        except TelemetryConflict:return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(join,[first,second]))
    assert sum(r=='conflict' for r in results)==1
    with Session(engine) as db:assert db.scalar(select(func.count()).select_from(CropCyclePlant))==1
    engine.dispose()


def test_cycle_reads_canonical_postharvest_and_lineage_without_writes(setup):
    from modules.cultivation.post_harvest import CultivationPostHarvestBatch
    from modules.material_lineage.models import MaterialTransformation
    engine,s=setup;c=cycle(s)
    s.members(c['id'],{'version':1,'plant_ids':['p1'],'action':'add','effective_at':AT})
    with Session(engine) as db,db.begin():
        db.add(CultivationHarvest(id='canonical-h',organization_id='o1',facility_id='f1',harvest_code='canonical',strain='S',created_by='a',harvested_at=AT+timedelta(days=1)));db.flush()
        db.add(CultivationHarvestPlant(id='canonical-hp',organization_id='o1',facility_id='f1',harvest_id='canonical-h',plant_id='p1',assigned_by='a'))
        db.add(CultivationPostHarvestBatch(id='canonical-batch',organization_id='o1',facility_id='f1',harvest_id='canonical-h',stage='drying',created_by='a'))
        db.add(MaterialTransformation(id='canonical-transform',organization_id='o1',facility_id='f1',transformation_type='harvest_allocation',source_entity_type='harvest',source_entity_id='canonical-h',actor='a'))
    s.link_harvest(c['id'],{'version':2,'harvest_id':'canonical-h'})
    mutations=[]
    def writes(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):mutations.append(statement)
    event.listen(engine,'before_cursor_execute',writes)
    try:detail=s.cycle(c['id'])
    finally:event.remove(engine,'before_cursor_execute',writes)
    assert detail['post_harvest']['id']=='canonical-batch'
    assert detail['lineage'][0]['id']=='canonical-transform'
    assert detail['quality']==[] and detail['lineage_outputs']==[]
    assert mutations==[]
