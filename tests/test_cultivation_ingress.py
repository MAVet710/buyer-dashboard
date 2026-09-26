"""Synthetic HTTP service-account acceptance using actual admission and EdgeStore."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, IntegrityError
from backend.app.database import get_engine
from backend.app.auth import get_request_context
from backend.app.routers import cultivation_ingress as route
from backend.app.routers import cultivation_intelligence_workspace as human
from modules.cultivation.ingress import IngressGrantService, AdmissionLimiter
from modules.cultivation.ingress_models import CultivationIngressGrant
from modules.cultivation.intelligence_models import TelemetryConnection
from modules.operational_moats.models import ServiceAccount
from modules.coman.models import Facility, AuditEvent
from tests.test_cultivation_intelligence_foundation import setup


@pytest.fixture
def h(setup,monkeypatch):
    engine,service=setup
    connection=service.create_connection({'provider':'json','label':'Push','mode':'push','stale_after_seconds':60})
    grants=IngressGrantService(engine,service.context)
    issued=grants.issue_grant(connection['id'],{'version':1,'label':'Collector','expires_at':datetime.now(timezone.utc)+timedelta(days=1)})
    app=FastAPI();app.include_router(route.router,prefix='/api/v1');app.include_router(human.router,prefix='/api/v1')
    app.dependency_overrides[get_engine]=lambda:engine
    app.dependency_overrides[get_request_context]=lambda:service.context
    monkeypatch.setattr(route,'edge_factory',lambda:service.edge())
    monkeypatch.setattr(route,'limiter',AdmissionLimiter(rate=1000))
    monkeypatch.setenv('CULTIVATION_EDGE_PATH',str(service.edge().path))
    with TestClient(app) as client:
        yield SimpleNamespace(engine=engine,s=service,grants=grants,issued=issued,c=connection,client=client,
            path='/api/v1/external/v1/cultivation-telemetry/'+connection['id']+'/batches',
            human='/api/v1/cultivation-intelligence/connections/'+connection['id']+'/ingress-grants',
            headers={'Authorization':'Bearer '+issued['token']})


def envelope(**changes):
    row={'event_id':'e1','source_device_id':'d1','source_channel':'ch1','source_metric':'temperature','value':24.5,'unit':'C','observed_at':'2026-01-02T12:00:00Z','quality':'valid'}
    row.update(changes)
    return {'schema_version':1,'batch_id':'b1','readings':[row]}


def post(h,body=None,**kwargs):
    return h.client.post(h.path,json=envelope() if body is None else body,headers=h.headers,**kwargs)


def test_real_service_token_commit_replay_conflict_no_sql_writes(h):
    sql=[]
    def record(conn,cursor,statement,*_):sql.append(statement)
    event.listen(h.engine,'before_cursor_execute',record)
    first=post(h);assert first.status_code==200,first.text
    assert first.json()['committed'] and first.json()['pending']==1
    again=post(h);assert again.json()['duplicates']==1
    changed=post(h,envelope(value=25));assert changed.json()['conflicts']==1
    assert not any(s.lstrip().upper().startswith(('UPDATE','INSERT','DELETE')) for s in sql)
    with Session(h.engine) as s:assert s.get(ServiceAccount,h.issued['grant']['service_account_id']).last_used_at is None
    assert h.issued['token'] not in first.text and '24.5' not in first.text


@pytest.mark.parametrize('kind',['missing','invalid','wildcard','revoked','expired','foreign','disabled','facility','file','scope_header'])
def test_denied_before_body_or_filesystem(h,monkeypatch,kind):
    headers=dict(h.headers)
    with Session(h.engine) as s,s.begin():
        account=s.get(ServiceAccount,h.issued['grant']['service_account_id'])
        grant=s.get(CultivationIngressGrant,h.issued['grant']['id'])
        if kind=='missing':headers={}
        elif kind=='invalid':headers={'Authorization':'Bearer dla_invalid_synthetic_token'}
        elif kind=='wildcard':account.scopes_json='["*"]'
        elif kind=='revoked':grant.revoked_at=datetime.now(timezone.utc)
        elif kind=='expired':grant.expires_at=datetime.now(timezone.utc)-timedelta(days=1)
        elif kind=='foreign':h.path=h.path.replace(h.c['id'],'other-connection')
        elif kind=='disabled':account.active=False
        elif kind=='facility':s.get(Facility,'f1').cultivation_enabled=False
        elif kind=='file':s.get(TelemetryConnection,h.c['id']).mode='file'
        elif kind=='scope_header':headers['X-Facility-Id']='f2'
    monkeypatch.setattr(route,'edge_factory',lambda:pytest.fail('Filesystem accessed before authorization'))
    response=h.client.post(h.path,content='not-json-secret',headers=headers)
    assert response.status_code in (401,403),response.text
    assert 'not-json-secret' not in response.text


@pytest.mark.parametrize('change',[{'event_id':''},{'event_id':'../secret'},{'organization_id':'o2'},{'received_at':'secret'},{'metadata':{'secret':'value'}},{'value':{'nested':'secret'}}])
def test_structural_rejection_has_no_input_echo(h,monkeypatch,change):
    monkeypatch.setattr(route,'edge_factory',lambda:pytest.fail('Structural rejection touched storage'))
    response=post(h,envelope(**change))
    assert response.status_code==422,response.text
    assert 'secret' not in response.text


@pytest.mark.parametrize('change',[{'observed_at':'bad-time'},{'quality':'bad'},{'value':True},{'observed_at':'2999-01-01T00:00:00Z'}])
def test_measurement_invalidity_is_durable(h,change):
    response=post(h,envelope(**change));assert response.status_code==200,response.text
    assert response.json()['committed'] and response.json()['quarantined']==1


def test_envelope_byte_count_media_depth_and_duplicate_fields(h,monkeypatch):
    monkeypatch.setattr(route,'edge_factory',lambda:pytest.fail('Invalid structure touched storage'))
    for content,status in [('{'+'"a":'*10,400),('['*5000,422),('{"schema_version":1,"schema_version":1}',422)]:
        response=h.client.post(h.path,content=content,headers={**h.headers,'Content-Type':'application/json'})
        assert response.status_code==status,response.text
    huge=envelope();huge['readings']*=501
    assert post(h,huge).status_code==413
    assert h.client.post(h.path,content=b'x'*1048577,headers={**h.headers,'Content-Type':'application/json'}).status_code==413
    assert h.client.post(h.path,content='{}',headers={**h.headers,'Content-Type':'text/plain'}).status_code==415
    assert h.client.post(h.path,content='{}',headers={**h.headers,'Content-Type':'application/json','Content-Encoding':'gzip'}).status_code==415


def test_auth_db_outage_fails_closed(h,monkeypatch):
    assert post(h).status_code==200
    def unavailable(*_):raise OperationalError('SELECT',{},Exception('synthetic unavailable'))
    event.listen(h.engine,'before_cursor_execute',unavailable)
    monkeypatch.setattr(route,'edge_factory',lambda:pytest.fail('Storage reached on auth outage'))
    response=post(h);assert response.status_code==503
    assert response.json()=={'detail':'ingress_unavailable'}


def test_lost_ack_rotation_and_split_preserve_identity(h,monkeypatch):
    edge=h.s.edge();original=edge.ingest
    def lost(*args,**kwargs):
        original(*args,**kwargs)
        raise OSError('synthetic lost acknowledgement')
    monkeypatch.setattr(edge,'ingest',lost)
    assert post(h).status_code==503
    monkeypatch.setattr(edge,'ingest',original)
    issued=h.grants.issue_grant(h.c['id'],{'version':2,'label':'Rotated','expires_at':datetime.now(timezone.utc)+timedelta(days=1)})
    h.headers={'Authorization':'Bearer '+issued['token']}
    data=envelope();data['batch_id']='split-new-batch'
    response=post(h,data);assert response.status_code==200 and response.json()['duplicates']==1


def test_http_versioned_grants_and_audit(h):
    rows=h.client.get(h.human).json();assert rows['grants'][0]['status']=='active'
    assert 'token' not in json.dumps(rows) and 'token_hash' not in json.dumps(rows)
    payload={'version':1,'label':'Another','expires_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}
    assert h.client.post(h.human,json=payload).status_code==409
    payload['version']=2
    created=h.client.post(h.human,json=payload);assert created.status_code==200,created.text
    grant=created.json()['grant'];assert created.json()['token']!=h.issued['token']
    path=h.human+'/'+grant['id']+'/revoke'
    assert h.client.post(path,json={'version':1}).json()['status']=='revoked'
    assert h.client.post(path,json={'version':1}).status_code==409
    with Session(h.engine) as s:
        audit=s.scalars(select(AuditEvent).where(AuditEvent.entity_id==grant['id'])).all()
        assert len(audit)==2 and all(a.actor=='a' for a in audit)


def test_scoped_composite_fk_cannot_bind_foreign_account(h):
    with Session(h.engine) as s,s.begin():
        foreign=ServiceAccount(organization_id='o2',facility_id='f2',name='foreign',token_hash='a'*64,scopes_json='["cultivation:ingest"]',created_by='b')
        s.add(foreign);s.flush();identity=foreign.id
    with pytest.raises(IntegrityError),Session(h.engine) as s,s.begin():
        s.add(CultivationIngressGrant(organization_id='o1',facility_id='f1',connection_id=h.c['id'],service_account_id=identity,label='invalid',expires_at=datetime.now(timezone.utc),created_by='a'))


def test_set_query_count_does_not_grow_with_samples(h):
    counts=[]
    def record(*args):counts.append(args[2])
    event.listen(h.engine,'before_cursor_execute',record)
    assert post(h).status_code==200
    first=len(counts);counts.clear()
    data=envelope();data['readings']=[dict(data['readings'][0],event_id='e'+str(i)) for i in range(500)]
    assert post(h,data).status_code==200
    assert len(counts)==first and first==18  # 17 set reads + explicit SQLite read transaction


def test_rate_and_concurrency_have_retry_after(h,monkeypatch):
    local=AdmissionLimiter(concurrency=1,rate=1);monkeypatch.setattr(route,'limiter',local)
    with local.slot():
        response=post(h);assert response.status_code==429 and response.headers['Retry-After']=='5'
    assert post(h).status_code==200
    assert post(h).status_code==429


def test_health_import_is_not_receiving(h):
    payload={'format':'json','content':json.dumps(envelope()['readings']),'mappings':[]}
    preview=h.s.preview(h.c['id'],payload)
    h.s.import_content(h.c['id'],{**payload,'digest':preview['digest']})
    imported=h.s.health(h.c['id'])
    assert imported['ingress']['transport_state']=='awaiting'
    assert imported['ingress']['last_push_received_at'] is None
    assert imported['connection']['last_import_at'] is not None
    assert post(h).status_code==200
    health=h.s.health(h.c['id'])
    assert health['freshness']['live_connected'] is False
    assert health['freshness']['sensor_freshness_status']=='unknown'
    # Without optional edge push receipt metadata, never infer push from raw/import.
    if not health['ingress']['last_push_received_at']:assert health['ingress']['transport_state']=='awaiting'


def test_duplicate_conflicting_scope_headers_denied(h):
    headers=[('Authorization',h.headers['Authorization']),('X-Facility-Id','f1'),('X-Facility-Id','f2')]
    assert h.client.post(h.path,json=envelope(),headers=headers).status_code==403


def test_chunked_stream_rejected_before_json_and_storage(h,monkeypatch):
    import asyncio
    calls=[];sent=[]
    chunks=[b'x'*600000,b'x'*500000,b'secret-must-not-read']
    async def receive():
        calls.append(1)
        return {'type':'http.request','body':chunks[len(calls)-1],'more_body':True}
    async def send(message):sent.append(message)
    monkeypatch.setattr(route,'edge_factory',lambda:pytest.fail('Oversized chunks reached storage'))
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'POST','scheme':'http','path':h.path,'raw_path':h.path.encode(),'query_string':b'','root_path':'','headers':[(b'authorization',h.headers['Authorization'].encode()),(b'content-type',b'application/json'),(b'transfer-encoding',b'chunked')],'client':('127.0.0.1',1000),'server':('testserver',80)}
    asyncio.run(h.client.app(scope,receive,send))
    assert sent[0]['status']==413 and len(calls)==2
    assert b'secret' not in sent[1]['body']


def test_final_admission_observes_revoke_during_body(h,monkeypatch):
    original=route._parse
    def revoke(body):
        h.grants.revoke_grant(h.c['id'],h.issued['grant']['id'],{'version':1})
        return original(body)
    monkeypatch.setattr(route,'_parse',revoke)
    monkeypatch.setattr(route,'edge_factory',lambda:pytest.fail('Revoked final admission reached storage'))
    assert post(h).status_code in (401,403)


def test_real_human_jwt_and_permission_override(h,monkeypatch):
    import jwt
    from backend.app import auth,config
    from modules.coman.models import AppUser
    from modules.coman.permissions import AppUserPermissionOverride
    app=h.client.app
    with Session(h.engine) as s,s.begin():s.get(AppUser,'a').must_change_password=False
    app.dependency_overrides.pop(get_request_context)
    settings=config.Settings(_env_file=None,app_env='test',database_url='sqlite://',supabase_url='https://synthetic.invalid',supabase_jwks_url='',supabase_jwt_secret='synthetic-only-secret-with-32-bytes',supabase_jwt_audience='authenticated')
    app.dependency_overrides[config.get_settings]=lambda:settings
    app.dependency_overrides[auth.get_authorization_engine]=lambda:h.engine
    token=jwt.encode({'sub':'a','aud':'authenticated','iss':'https://synthetic.invalid/auth/v1','exp':datetime.now(timezone.utc)+timedelta(minutes=5)},settings.supabase_jwt_secret,algorithm='HS256')
    headers={'Authorization':'Bearer '+token,'X-Organization-Id':'o1','X-Facility-Id':'f1'}
    payload={'version':2,'label':'JWT collector','expires_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}
    response=h.client.post(h.human,json=payload,headers=headers)
    assert response.status_code==200,response.text
    with Session(h.engine) as s,s.begin():
        s.add(AppUserPermissionOverride(organization_id='o1',facility_id='f1',user_id='a',permission='cultivation.manage_connections',effect='deny',created_by='a',updated_by='a'))
    payload['version']=3
    assert h.client.post(h.human,json=payload,headers=headers).status_code==403


def test_http_historical_mapping_and_recipe_boundaries(h):
    from modules.cultivation.intelligence_models import DeviceMapping, CultivationRecipe
    from modules.cultivation.models import CultivationRoom
    from modules.cultivation.edge_store import Scope
    device=h.s.create_device(h.c['id'],{'version':2,'source_device_id':'d1'})
    h.s.create_sensor(device['id'],{'version':1,'source_channel':'ch1','source_metric':'temperature','source_unit':'C','metric':'temperature'})
    h.s.map_device(device['id'],{'version':2,'room_id':'r1','effective_at':'2026-01-01T00:00:00Z'})
    with Session(h.engine) as s,s.begin():
        s.add(CultivationRoom(id='later-room',organization_id='o1',facility_id='f1',room_code='B'));s.flush()
        s.add(DeviceMapping(organization_id='o1',facility_id='f1',device_id=device['id'],room_id='later-room',effective_at=datetime(2026,1,2,12,1,tzinfo=timezone.utc),created_by='a'))
    before=envelope()['readings'][0]
    after=dict(before,event_id='after',observed_at='2026-01-02T12:01:00Z')
    response=post(h,{'schema_version':1,'batch_id':'history','readings':[before,after]})
    assert response.status_code==200 and response.json()['accepted']==2,response.text
    evidence=h.s.edge().evidence(Scope('o1','f1',h.c['id']))['items']
    # Detail evidence retains canonical snapshots; source identities survive.
    snapshots=[row['snapshot'] for row in evidence]
    assert {row['room_id'] for row in snapshots}=={'r1','later-room'}
    earlier=next(row for row in snapshots if row['room_id']=='r1')
    assert earlier['effective_to']=='2026-01-02T12:01:00+00:00'
    assert all(row['organization_id']=='o1' and row['facility_id']=='f1' for row in snapshots)


def test_storage_failure_and_configured_batch_limit_no_false_ack(h,monkeypatch):
    edge=h.s.edge();edge.max_batch=1
    data=envelope();data['readings']*=2
    assert post(h,data).status_code==413
    edge.max_scope_rows=1
    assert post(h).status_code==200
    response=post(h,envelope(event_id='e2'))
    assert response.status_code==503
    from modules.cultivation.edge_store import Scope
    assert edge.diagnostics(Scope('o1','f1',h.c['id']))['scope_rows']==1


def test_supplied_request_identity_headers_do_not_authorize(h):
    headers={'X-User-Id':'a','X-User-Role':'admin','X-Organization-Id':'o1','X-Facility-Id':'f1'}
    assert h.client.post(h.path,json=envelope(),headers=headers).status_code==401
