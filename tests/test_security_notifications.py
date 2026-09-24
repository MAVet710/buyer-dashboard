"""Notification tests run only against disposable SQLite and an injected sender."""
import time
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from backend.app.config import Settings
from backend.app.security.models import SecurityIncident, SecurityEvent, SecurityMonitorState
from backend.app.security.notifications import SecurityNotifier, message_for, valid_recipient
from backend.app.security.store import open_incident
from backend.app.security.retention import maintain


@pytest.fixture()
def case():
    engine=create_engine("sqlite+pysqlite:///:memory:")
    for model in (SecurityIncident,SecurityEvent,SecurityMonitorState):model.__table__.create(engine)
    settings=Settings(_env_file=None,security_notifications_enabled=True,
        security_notification_recipient="owner@example.test",spacemail_from_email="alerts@example.test",
        spacemail_smtp_password="synthetic-not-a-production-secret",resend_api_key="")
    with Session(engine) as s,s.begin():
        incident=open_incident(s,"test_alert","test",1,time.time());identifier=incident.id
    yield SimpleNamespace(engine=engine,settings=settings,id=identifier)
    engine.dispose()


def test_sender_acceptance_is_not_marked_delivered_and_not_repeated(case):
    sent=[]
    n=SecurityNotifier(case.engine,case.settings,sender=lambda settings,msg:sent.append(msg) or "test_transport")
    n.tick();n.tick()
    assert len(sent)==1
    with Session(case.engine) as s:
        row=s.get(SecurityIncident,case.id)
        assert row.notification_status=="accepted" and row.notification_attempts==1
    assert n.health()["delivery_confirmation"]=="not_connected"


def test_ambiguous_result_is_never_replayed(case):
    calls=[]
    def fail(settings,msg):
        calls.append(1);raise TimeoutError("synthetic")
    n=SecurityNotifier(case.engine,case.settings,sender=fail);n.tick();n.tick()
    assert len(calls)==1
    with Session(case.engine) as s:assert s.get(SecurityIncident,case.id).notification_status=="uncertain"


def test_disabled_or_invalid_configuration_never_sends(case):
    def refuse(*args):raise AssertionError("must not send")
    for overrides in ({"security_notifications_enabled":False},{"security_notification_recipient":"a@b.test\nBcc:evil@c.test"}):
        n=SecurityNotifier(case.engine,case.settings.model_copy(update=overrides),sender=refuse);n.tick()
        assert n.last_attempt==0


def test_notification_contains_no_incident_payload_or_credentials(case):
    row=dict(id=case.id,title="TEST",severity="high",first_seen=time.time(),evidence_json='SECRET_BODY')
    raw=message_for(row,case.settings).as_string()
    assert "SECRET_BODY" not in raw and case.settings.spacemail_smtp_password not in raw
    assert "not proof" in raw and "Auto-Submitted: auto-generated" in raw


def test_hourly_budget_is_durable_across_notifier_instances(case):
    settings=case.settings.model_copy(update={"security_notification_hourly_limit":1})
    sent=[]
    SecurityNotifier(case.engine,settings,sender=lambda *args:sent.append(1) or "test").tick()
    with Session(case.engine) as s,s.begin():open_incident(s,"test_alert","second",1,time.time())
    second=SecurityNotifier(case.engine,settings,sender=lambda *args:sent.append(1) or "test");second.tick()
    assert sent==[1] and second.state=="rate_limited"


def test_retention_preserves_unresolved_incidents(case):
    now=time.time()
    with Session(case.engine) as s,s.begin():
        row=s.get(SecurityIncident,case.id);row.last_seen=now-100*86400
        maintain(s,now)
        assert s.scalar(select(func.count()).select_from(SecurityIncident))==1
        row.status="resolved";s.flush();maintain(s,now)
        assert s.scalar(select(func.count()).select_from(SecurityIncident))==0


@pytest.mark.parametrize("value",["", "x", "name <a@b.test>", "a@b.test\r\nX:evil", "a@b.test,c@d.test"])
def test_recipient_must_be_one_plain_address(value):assert not valid_recipient(value)
