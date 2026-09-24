"""Isolated behavioral tests; never contact production, Auth or mail providers."""
import json
import time
from types import SimpleNamespace
from uuid import uuid4
from datetime import datetime, timezone
import jwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from modules.coman.models import Base, Organization, Facility, AppUser, AppUserFacilityRole, AuditEvent
from backend.app.auth import get_authorization_engine
from backend.app.config import Settings, get_settings
from backend.app.database import get_engine
from backend.app.routers import account, security_center
from backend.app.security.models import SecurityEvent, SecurityIncident
from backend.app.security.runtime import SecurityMonitor
from backend.app.security.store import append_events, detect, collect_privileged_audits, open_incident


@pytest.fixture()
def env():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add_all([Organization(id="org-a",name="QA A",slug="qa-a"), Organization(id="org-b",name="QA B",slug="qa-b")]); session.flush()
        for organization, facility in (("org-a","fac-a"),("org-b","fac-b")):
            session.add(Facility(id=facility,organization_id=organization,name=facility,code=facility,production_enabled=True))
        session.flush()
        for role in ("dev","admin","buyer"):
            session.add(AppUser(id=role,organization_id="org-a",username=role,normalized_username=role,
                email=role+"@example.test",password_hash="not-used",role=role,active=True,must_change_password=False)); session.flush()
            session.add(AppUserFacilityRole(user_id=role,organization_id="org-a",facility_id="fac-a",role=role))
    settings = Settings(_env_file=None, app_env="production", supabase_url="https://security-qa.example.test",
        supabase_jwks_url="",supabase_jwt_secret="synthetic-jwt-test-key-not-production" * 2,
        security_monitor_enabled=True,security_hmac_secret="synthetic-observation-key-not-production" * 2)
    app=FastAPI(); app.include_router(account.router,prefix="/api/v1"); app.include_router(security_center.router,prefix="/api/v1")
    for dep in (get_engine,get_authorization_engine): app.dependency_overrides[dep]=lambda:engine
    app.dependency_overrides[get_settings]=lambda:settings
    monitor=SecurityMonitor(engine,settings); app.state.security_monitor=monitor
    client=TestClient(app)
    def headers(role="dev", organization="org-a", facility="fac-a"):
        token=jwt.encode({"sub":role,"email":role+"@example.test","iss":settings.supabase_url+"/auth/v1",
            "aud":settings.supabase_jwt_audience,"exp":int(time.time())+600},settings.supabase_jwt_secret,algorithm="HS256")
        return {"Authorization":"Bearer "+token,"X-Organization-Id":organization,"X-Facility-Id":facility}
    yield SimpleNamespace(engine=engine,settings=settings,app=app,client=client,monitor=monitor,headers=headers)
    client.close(); engine.dispose()


def event(kind="login_failure",subject="pseudonym-a",source="",now=None):
    return dict(id=str(uuid4()),occurred_at=time.time() if now is None else now,kind=kind,subject_key=subject,
        source_key=source,actor_id="",organization_id="",route="/account/username-login",request_id=str(uuid4()),audit_id="")


def rules(env,events,now):
    with Session(env.engine) as s,s.begin(): append_events(s,events); detect(s,now)
    with Session(env.engine) as s: return [r.rule for r in s.scalars(select(SecurityIncident))]


def test_failed_login_threshold_and_dedup(env):
    now=time.time()
    assert rules(env,[event(now=now) for _ in range(7)],now)==[]
    assert rules(env,[event(now=now)],now)==["login_failures"]
    assert rules(env,[event(now=now)],now)==["login_failures"]


def test_old_or_future_failures_are_not_current_evidence(env):
    now=time.time()
    assert rules(env,[event(now=now-301) for _ in range(10)]+[event(now=now+60) for _ in range(10)],now)==[]


def test_success_after_failures_is_suspicious_not_confirmed_intrusion(env):
    now=time.time()
    assert set(rules(env,[event(now=now-1) for _ in range(8)]+[event("login_success",now=now)],now))=={"login_failures","login_after_failures"}
    with Session(env.engine) as s:
        row=s.scalar(select(SecurityIncident).where(SecurityIncident.rule=="login_after_failures"))
        assert json.loads(row.evidence_json)["outcome"]=="review_session_not_confirmed_compromise"


def test_success_before_failures_is_not_post_failure_login(env):
    now=time.time()
    assert rules(env,[event("login_success",now=now-5)]+[event(now=now) for _ in range(8)],now)==["login_failures"]


def test_source_correlation_requires_distinct_accounts_and_real_source(env):
    now=time.time()
    values=[event(subject=f"account-{i%5}",source="trusted-source-hash",now=now) for i in range(20)]
    assert rules(env,values,now)==["password_spray"]


def test_missing_source_is_not_one_shared_attacker(env):
    now=time.time()
    assert rules(env,[event(subject=f"account-{i%5}",source="",now=now) for i in range(20)],now)==[]


def test_scope_denial_threshold(env):
    now=time.time()
    assert rules(env,[event("scope_denial",now=now) for _ in range(9)],now)==[]
    assert rules(env,[event("scope_denial",now=now)],now)==["scope_denials"]


@pytest.mark.parametrize("role",["admin","buyer"])
def test_customer_roles_cannot_read_global_incidents(env,role):
    headers={**env.headers(role),"X-User-Role":"dev"}
    for path in ("/api/v1/security/status","/api/v1/security/incidents"):
        assert env.client.get(path,headers=headers).status_code==403


def test_unauthenticated_and_invalid_tokens_denied(env):
    for headers in ({"X-User-Role":"dev"},{**env.headers(),"Authorization":"Bearer invalid"}):
        assert env.client.get("/api/v1/security/incidents",headers=headers).status_code==401


def test_dev_can_review_and_triage_with_canonical_audit(env):
    with Session(env.engine) as s,s.begin():
        row=open_incident(s,"scope_denials","test-hash",10,time.time()); identifier=row.id
    path=f"/api/v1/security/incidents/{identifier}/triage"
    assert env.client.get("/api/v1/security/incidents",headers=env.headers()).json()["total"]==1
    response=env.client.post(path,headers=env.headers(),json={"status":"acknowledged","expected_version":1})
    assert response.status_code==200 and response.json()["version"]==2
    assert env.client.post(path,headers=env.headers(),json={"status":"resolved","expected_version":1}).status_code==409
    with Session(env.engine) as s:
        audit=s.scalar(select(AuditEvent).where(AuditEvent.action=="security_incident_triaged"))
        assert audit.actor=="dev" and audit.entity_id==identifier


def test_unknown_and_extra_triage_fields_are_rejected(env):
    for payload in ({"status":"ban_user","expected_version":1},{"status":"resolved","expected_version":1,"role":"dev"}):
        assert env.client.post("/api/v1/security/incidents/missing/triage",headers=env.headers(),json=payload).status_code==422


def test_failed_username_login_capture_redacts_secrets(env,monkeypatch):
    def invalid(*args): raise HTTPException(400,"Invalid login credentials.")
    monkeypatch.setattr(account,"_supabase_password_session",invalid)
    response=env.client.post("/api/v1/account/username-login",json={"username":"buyer","password":"never-record-this-password"})
    assert response.status_code==400
    queued=env.monitor.queue.get_nowait(); serialized=json.dumps(queued)
    assert queued["kind"]=="login_failure" and len(queued["subject_key"])==64
    assert "never-record-this-password" not in serialized and "buyer" not in serialized


def test_auth_provider_outage_not_counted_as_wrong_password(env,monkeypatch):
    def unavailable(*args): raise HTTPException(503,"Authentication service is unavailable.")
    monkeypatch.setattr(account,"_supabase_password_session",unavailable)
    assert env.client.post("/api/v1/account/username-login",json={"username":"buyer","password":"test"}).status_code==503
    assert env.monitor.queue.empty()


def test_successful_login_works_if_monitoring_raises(env,monkeypatch):
    monkeypatch.setattr(account,"_supabase_password_session",lambda *args:dict(auth_user_id="buyer",access_token="test-only",refresh_token="test-only"))
    def broken(*args): raise RuntimeError("test observer failure")
    monkeypatch.setattr(env.monitor,"emit",broken)
    response=env.client.post("/api/v1/account/username-login",json={"username":"buyer","password":"test"})
    assert response.status_code==200


def test_scope_event_uses_verified_actor_not_client_identity(env):
    headers={**env.headers("buyer","org-b","fac-b"),"X-User-Id":"spoofed-dev"}
    assert env.client.get("/api/v1/account/context",headers=headers).status_code==403
    item=env.monitor.queue.get_nowait()
    assert item["kind"]=="scope_denial" and item["actor_id"]=="buyer" and item["organization_id"]=="org-a"
    assert "spoofed-dev" not in json.dumps(item)


def test_bounded_queue_and_durable_incident(env):
    monitor=SecurityMonitor(env.engine,env.settings,capacity=2)
    request=SimpleNamespace(scope={},headers={},client=SimpleNamespace(host="127.0.0.1"))
    for _ in range(3): monitor.emit(request,"login_failure","sample")
    assert monitor.queue.qsize()==2 and monitor.dropped==1
    monitor.tick()
    with Session(env.engine) as s:
        assert s.scalar(select(func.count()).select_from(SecurityEvent))==2
        assert s.scalar(select(SecurityIncident).where(SecurityIncident.rule=="monitoring_degraded")) is not None


def test_database_failure_keeps_pending_observations(env,monkeypatch):
    import backend.app.security.runtime as runtime
    request=SimpleNamespace(scope={},headers={},client=None)
    env.monitor.emit(request,"login_failure","sample")
    def fail(*args): raise RuntimeError("synthetic storage outage")
    monkeypatch.setattr(runtime,"append_events",fail)
    env.monitor.tick()
    assert len(env.monitor.pending)==1 and env.monitor.failures==1
    assert env.monitor.health()["notifications"]=="not_connected"


def test_privileged_audit_projection_is_idempotent_and_private(env):
    now=time.time()
    with Session(env.engine) as s,s.begin():
        s.add(AuditEvent(id="test-audit",organization_id="org-a",facility_id="fac-a",entity_type="app_user",
            entity_id="buyer",actor="dev",action="authorization_updated",changes_json='{"private":"do-not-copy"}',
            occurred_at=datetime.fromtimestamp(now,timezone.utc)))
    with Session(env.engine) as s,s.begin():
        collect_privileged_audits(s,env.settings.security_hmac_secret,now)
        collect_privileged_audits(s,env.settings.security_hmac_secret,now)
        detect(s,now)
        assert s.scalar(select(func.count()).select_from(SecurityEvent))==1
        incident=s.scalar(select(SecurityIncident)); assert incident.rule=="privileged_change"
        assert "do-not-copy" not in incident.evidence_json


def test_default_settings_do_not_activate_monitoring():
    settings=Settings(_env_file=None,security_monitor_enabled=False)
    monitor=SecurityMonitor(None,settings)
    assert monitor.health()["state"]=="disabled"
    monitor.tick()


def test_short_secret_refuses_observation(env):
    settings=env.settings.model_copy(update={"security_hmac_secret":"short"})
    assert SecurityMonitor(env.engine,settings).health()["state"]=="configuration_required"


def test_failures_after_success_do_not_hide_prior_suspicious_sequence(env):
    now=time.time()
    events=[event(now=now-5) for _ in range(8)]+[event("login_success",now=now-2),event(now=now)]
    assert "login_after_failures" in rules(env,events,now)


def test_current_storage_failure_is_not_reported_as_observing(env,monkeypatch):
    import backend.app.security.runtime as runtime
    env.monitor.tick()
    def fail(*args): raise RuntimeError("test read failure")
    monkeypatch.setattr(runtime,"append_events",fail)
    env.monitor.tick()
    assert env.monitor.health()["state"]=="degraded"
