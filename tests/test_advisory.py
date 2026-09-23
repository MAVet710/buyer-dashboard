from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext, get_request_context
from backend.app.config import Settings, get_settings
from backend.app.database import get_engine
from backend.app.routers import advisory as route_module
from backend.app.services import advisory
from modules.advisory.models import AdvisoryDailyEvent, AdvisoryLead
from modules.advisory.schemas import QUESTION_IDS
from modules.coman.models import AuditEvent, Base, Facility, Organization


@pytest.fixture
def environment(monkeypatch):
    engine = create_engine('sqlite+pysqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine, tables=[Organization.__table__, Facility.__table__, AuditEvent.__table__, AdvisoryLead.__table__, AdvisoryDailyEvent.__table__])
    owner = str(uuid4()); customer = str(uuid4())
    with Session(engine) as session:
        session.add_all([Organization(id=owner, name='Test Advisory', slug='test-advisory'), Organization(id=customer, name='Test Customer', slug='test-customer')]); session.commit()
    settings = Settings(app_env='production', doobielogic_advisory_organization_id=owner)
    app = FastAPI(); app.include_router(route_module.router, prefix='/api/v1')
    context = {'role':'dev'}
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_request_context] = lambda: RequestContext('test-actor', customer, 'existing-context-facility', context['role'])
    monkeypatch.setattr(route_module, 'get_settings', lambda: settings)
    monkeypatch.setattr(route_module, 'limiter', route_module.IntakeLimiter())
    with TestClient(app) as client:
        yield SimpleNamespace(engine=engine, client=client, settings=settings, owner=owner, customer=customer, context=context)
    engine.dispose()


def lead(**overrides):
    return dict(name='Test Operator', email='operator@example.invalid', phone='', company='Test Company', role='Operations',
        state='MA', operation='Retail', locations=2, challenge='Purchasing and inventory handoffs need clearer review.',
        service='inventory-profit-audit', message='', consent=True, website='', **overrides)


def post(env, payload=None):
    return env.client.post('/api/v1/advisory/leads', json=payload or lead())


def count(env, model):
    with Session(env.engine) as session:
        return session.scalar(select(func.count()).select_from(model))


def test_capture_is_durable_without_email_and_audited_under_server_owner(environment):
    env=environment
    result=post(env); assert result.status_code==202
    reference=result.json()['reference']; assert result.json()['accepted'] is True
    with Session(env.engine) as session:
        row=session.get(AdvisoryLead,reference)
        assert row.organization_id==env.owner != env.customer
        assert row.status=='NEW' and row.consent and row.version==1
        event=session.scalar(select(AuditEvent))
        assert event.organization_id==env.owner and event.entity_id==reference
        assert event.actor=='public:advisory-intake'
        assert 'operator@example.invalid' not in event.changes_json


@pytest.mark.parametrize('patch', [
    {'consent':False},{'consent':1},{'consent':'true'},{'name':'  '},{'email':'bad'},
    {'locations':0},{'locations':10001},{'locations':True},{'locations':1.5},
    {'service':'invented'},{'challenge':'short'},{'phone':'x'*41},
    {'organization_id':'attacker'},{'score_summary':{'overall_score':100}},
    {'source_tool':'inventory-health-check','tool_inputs':{'raw_csv':'private'}},
])
def test_validation_fails_closed_and_creates_no_record(environment,patch):
    payload=lead();payload.update(patch)
    assert post(environment,payload).status_code==422
    assert count(environment,AdvisoryLead)==0


def test_honeypot_is_generic_and_does_not_persist(environment):
    payload=lead();payload['website']='spam.invalid'
    assert post(environment,payload).json()['accepted'] is True
    assert count(environment,AdvisoryLead)==count(environment,AuditEvent)==0


def test_missing_owner_configuration_and_inactive_owner_fail_closed(environment):
    env=environment;env.settings.doobielogic_advisory_organization_id=''
    assert post(env).status_code==503
    env.settings.doobielogic_advisory_organization_id=env.owner
    with Session(env.engine) as session:
        session.get(Organization,env.owner).active=False;session.commit()
    assert post(env).status_code==503
    assert count(env,AdvisoryLead)==0


def test_retry_idempotency_and_changed_payload_conflict(environment):
    env=environment;payload=lead(submission_id=str(uuid4()))
    first=post(env,payload);again=post(env,payload)
    assert first.json()==again.json()
    payload['challenge']='Different intent must not overwrite an existing submission.'
    assert post(env,payload).status_code==409
    assert count(env,AdvisoryLead)==count(env,AuditEvent)==1


def test_attribution_strips_query_tokens_and_disallows_extra_fields(environment):
    payload=lead(attribution={'landing_page':'/consulting?token=private#section','referrer':'https://example.com/private?token=secret','utm_source':'newsletter'})
    response=post(environment,payload);assert response.status_code==202
    detail=environment.client.get('/api/v1/advisory/admin/leads/'+response.json()['reference']).json()
    assert detail['attribution']['landing_page']=='/consulting'
    assert detail['attribution']['referrer']=='https://example.com'
    assert 'private' not in json.dumps(detail['attribution'])


def test_score_recomputed_from_versioned_questions_and_na_excluded(environment):
    answers={key:4 for key in QUESTION_IDS}
    for key in QUESTION_IDS[:10]:answers[key]=None
    payload=lead(source_tool='operations-score',tool_inputs=answers)
    response=post(environment,payload);assert response.status_code==202
    detail=environment.client.get('/api/v1/advisory/admin/leads/'+response.json()['reference']).json()
    score=detail['score_summary']
    assert score['overall_score']==100 and score['applicable_answers']==15 and score['not_applicable_answers']==10
    assert score['verified'] is False and score['source']=='self-reported'
    assert score['categories'][0]['score'] is None
    assert environment.client.post('/api/v1/advisory/score',json={'tool_inputs':answers}).json()==score


@pytest.mark.parametrize('kind',['missing','unknown','bool','float','range','too_few'])
def test_score_input_contract(environment,kind):
    answers={key:2 for key in QUESTION_IDS}
    if kind=='missing':answers.pop(QUESTION_IDS[0])
    if kind=='unknown':answers['unexpected']=1
    if kind=='bool':answers[QUESTION_IDS[0]]=True
    if kind=='float':answers[QUESTION_IDS[0]]=2.5
    if kind=='range':answers[QUESTION_IDS[0]]=5
    if kind=='too_few':answers.update({key:None for key in QUESTION_IDS[:11]})
    assert post(environment,lead(source_tool='operations-score',tool_inputs=answers)).status_code==422


@pytest.mark.parametrize('role',['admin','buyer','operator','trial','supervisor'])
def test_tenant_roles_cannot_read_or_mutate_platform_leads(environment,role):
    env=environment;reference=post(env).json()['reference'];env.context['role']=role
    for path in ('leads','leads/'+reference,'metrics'):
        assert env.client.get('/api/v1/advisory/admin/'+path).status_code==403
    assert env.client.patch('/api/v1/advisory/admin/leads/'+reference,json={'status':'QUALIFIED','expected_version':1}).status_code==403


def test_authenticated_dependency_required_without_override(environment):
    env=environment;env.client.app.dependency_overrides.pop(get_request_context)
    assert env.client.get('/api/v1/advisory/admin/leads').status_code in {400,401,403,503}


def test_owner_scoping_lifecycle_concurrency_and_cumulative_funnel(environment):
    env=environment;reference=post(env).json()['reference'];path='/api/v1/advisory/admin/leads/'+reference
    assert env.client.patch(path,json={'status':'QUALIFIED','expected_version':1,'note':'Fit reviewed'}).json()['version']==2
    assert env.client.patch(path,json={'status':'CLOSED_LOST','expected_version':1}).status_code==409
    assert env.client.patch(path,json={'status':'CONTACTED','expected_version':2}).status_code==200
    other=env.settings.model_copy(update={'doobielogic_advisory_organization_id':env.customer})
    other_reference=advisory.capture_lead(env.engine,other,route_module.LeadInput(**lead()))['reference']
    assert env.client.get('/api/v1/advisory/admin/leads/'+other_reference).status_code==404
    assert env.client.patch('/api/v1/advisory/admin/leads/'+other_reference,json={'status':'CLIENT','expected_version':1}).status_code==404
    listing=env.client.get('/api/v1/advisory/admin/leads').json();assert listing['total']==1
    metrics=env.client.get('/api/v1/advisory/admin/metrics').json()
    assert metrics['status_counts']=={'CONTACTED':1}
    assert metrics['cumulative_stage_counts']=={'NEW':1,'QUALIFIED':1,'CONTACTED':1}
    with Session(env.engine) as session:
        events=session.scalars(select(AuditEvent).where(AuditEvent.organization_id==env.owner)).all()
        assert len(events)==3 and events[-1].actor=='test-actor'


def test_event_requires_consent_and_counts_without_identity(environment):
    env=environment;payload={'event':'consulting_page_view','placement':'consulting','item':'overview','consent':True}
    for _ in range(2): assert env.client.post('/api/v1/advisory/events',json=payload).status_code==202
    with Session(env.engine) as session:
        rows=session.scalars(select(AdvisoryDailyEvent)).all();assert len(rows)==1 and rows[0].count==2
    assert env.client.post('/api/v1/advisory/events',json={**payload,'consent':False}).status_code==422
    assert env.client.post('/api/v1/advisory/events',json={**payload,'email':'private@example.invalid'}).status_code==422
    assert env.client.post('/api/v1/advisory/events',json={**payload,'event':'unapproved_event'}).status_code==422
    assert env.client.get('/api/v1/advisory/admin/metrics').json()['event_counts']=={'consulting_page_view':2}
    assert not any('ip' in column.name or 'user' in column.name for column in AdvisoryDailyEvent.__table__.columns)


def test_booking_config_is_explicit_and_safe(environment):
    env=environment;assert env.client.get('/api/v1/advisory/booking').json()=={'available':False,'url':None}
    env.settings.doobielogic_advisory_booking_url='https://calendar.example.invalid/advisory'
    assert env.client.get('/api/v1/advisory/booking').json()['available'] is True
    env.settings.doobielogic_advisory_booking_url='javascript:alert(1)'
    assert env.client.get('/api/v1/advisory/booking').json()['available'] is False


def test_guard_rejects_origin_and_large_body_before_validation(environment):
    env=environment
    assert env.client.post('/api/v1/advisory/leads',headers={'origin':'https://evil.example'},json=lead()).status_code==403
    assert env.client.post('/api/v1/advisory/leads',content=b'x'*32769).status_code==413
    assert env.client.post('/api/v1/advisory/leads',content=iter([b'x'*17000,b'x'*17000])).status_code==413
    assert count(env,AdvisoryLead)==0


def test_public_rate_guard_and_bounded_memory(environment):
    env=environment
    for _ in range(5): assert post(env).status_code==202
    response=post(env);assert response.status_code==429 and int(response.headers['retry-after'])>0
    guard=route_module.IntakeLimiter(max_keys=1);guard.check('peer-one','leads',now=0)
    with pytest.raises(Exception) as error:guard.check('peer-two','leads',now=1)
    assert error.value.status_code==429
    guard.check('peer-two','leads',now=901);assert len(guard.buckets)==1
    assert 'peer-two' not in repr(guard.buckets)


def migration_module():
    spec=importlib.util.spec_from_file_location('advisory_migration',Path('migrations/versions/0078_advisory_leads.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_migration_creates_expected_schema_and_downgrades_without_runtime_createall():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    engine=create_engine('sqlite+pysqlite:///:memory:')
    with engine.begin() as connection:
        Organization.__table__.create(connection)
        module=migration_module();module.op=Operations(MigrationContext.configure(connection));module.upgrade()
        assert set(AdvisoryLead.__table__.columns.keys())=={column['name'] for column in inspect(connection).get_columns('advisory_leads')}
        module.downgrade();assert 'advisory_leads' not in inspect(connection).get_table_names()
    assert 'create_all' not in Path('backend/app/services/advisory.py').read_text()


def test_migration_postgres_rls_and_public_grants_are_fail_closed():
    module=migration_module();statements=[]
    module.op=SimpleNamespace(create_table=lambda *a,**kw:None,create_index=lambda *a,**kw:None,
        get_bind=lambda:SimpleNamespace(dialect=SimpleNamespace(name='postgresql')),execute=statements.append)
    module.upgrade();sql='\n'.join(statements)
    for table in ('advisory_leads','advisory_daily_events'):
        assert f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY' in sql
        assert f'REVOKE ALL ON TABLE public.{table} FROM PUBLIC' in sql
    assert "['anon', 'authenticated']" in sql
    assert module.down_revision=='0077_dev_reference_metrc_tags' and len(module.revision)<=32

def test_failed_database_commit_never_returns_acceptance_or_leaves_partial_audit(environment,monkeypatch):
    from sqlalchemy.exc import OperationalError
    def fail_commit(self): raise OperationalError('commit',None,RuntimeError('test unavailable'))
    monkeypatch.setattr(Session,'commit',fail_commit)
    response=post(environment)
    assert response.status_code==503
    assert 'accepted' not in response.json()
    assert count(environment,AdvisoryLead)==count(environment,AuditEvent)==0


def test_score_uses_equal_question_weight_not_equal_category_weight():
    answers={key:None for key in QUESTION_IDS}
    answers.update({key:4 for key in QUESTION_IDS[:5]})
    answers.update({key:0 for key in QUESTION_IDS[5:16]})
    assert advisory.calculate_score(answers)['overall_score']==31


def test_event_rejects_non_boolean_consent(environment):
    response=environment.client.post('/api/v1/advisory/events',json={'event':'consulting_page_view','placement':'consulting','consent':1})
    assert response.status_code==422


def test_origin_allowlist_does_not_trust_suffixes_or_caller_forwarded_headers(environment):
    env=environment
    assert env.client.post('/api/v1/advisory/leads',json=lead(),headers={'origin':'https://doobielogic.io.attacker.invalid'}).status_code==403
    for i in range(5):
        assert env.client.post('/api/v1/advisory/leads',json=lead(),headers={'origin':'https://doobielogic.io','x-forwarded-for':f'198.51.100.{i}'}).status_code==202
    assert env.client.post('/api/v1/advisory/leads',json=lead(),headers={'x-forwarded-for':'198.51.100.99'}).status_code==429

def test_known_lifecycle_booking_proposal_client_and_closed_reopen(environment):
    env=environment;reference=post(env).json()['reference'];path='/api/v1/advisory/admin/leads/'+reference
    assert env.client.patch(path,json={'status':'CLIENT','expected_version':1}).status_code==409
    assert env.client.patch(path,json={'status':'archived','expected_version':1}).status_code==422
    version=1
    for status in ['CONTACTED','QUALIFIED','CONSULTATION_BOOKED','PROPOSAL_SENT','CLIENT','QUALIFIED','CLOSED_LOST','CONTACTED']:
        response=env.client.patch(path,json={'status':status,'expected_version':version})
        assert response.status_code==200
        version+=1
        assert response.json()['status']==status and response.json()['version']==version


def test_proxy_ip_only_from_explicitly_trusted_peer():
    from starlette.requests import Request
    def request(peer,headers):
        return Request({'type':'http','method':'POST','path':'/','headers':[(k.encode(),v.encode()) for k,v in headers.items()],'client':(peer,1234)})
    settings=Settings(doobielogic_advisory_trusted_proxy_cidrs='127.0.0.1/32,::1/128')
    headers={'x-advisory-client-ip':'198.51.100.42','cf-connecting-ip':'198.51.100.66','x-forwarded-for':'198.51.100.99'}
    assert route_module.rate_limit_peer(request('127.0.0.1',headers),settings)=='198.51.100.42'
    assert route_module.rate_limit_peer(request('203.0.113.1',headers),settings)=='203.0.113.1'
    assert route_module.rate_limit_peer(request('127.0.0.1',{'x-forwarded-for':'198.51.100.99'}),settings)=='127.0.0.1'
    for value in ['invalid','198.51.100.42, 198.51.100.43','fe80::1%iface']:
        assert route_module.rate_limit_peer(request('127.0.0.1',{'x-advisory-client-ip':value}),settings)=='127.0.0.1'
    settings.doobielogic_advisory_trusted_proxy_cidrs=''
    assert route_module.rate_limit_peer(request('127.0.0.1',headers),settings)=='127.0.0.1'


def test_score_rounds_half_up_to_frontend_integer():
    answers={key:None for key in QUESTION_IDS}
    answers.update({key:0 for key in QUESTION_IDS[:20]})
    answers[QUESTION_IDS[0]]=4;answers[QUESTION_IDS[1]]=4;answers[QUESTION_IDS[2]]=2
    assert advisory.calculate_score(answers)['overall_score']==13
