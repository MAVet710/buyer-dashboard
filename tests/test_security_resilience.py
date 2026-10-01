import json
import time
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.security.models import Base, SecurityIncident, SecurityMonitorState, SecuritySourceState
from backend.app.security.runtime import SecurityMonitor
from backend.app.security import perimeter
from backend.app.security.store import open_incident
from backend.app.services import spacemail


def engine():
    value = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(value)
    return value


def settings(**updates):
    return Settings(_env_file=None, security_monitor_enabled=True,
                    security_hmac_secret="s" * 32, **updates)


def quiet_perimeter(monitor):
    monitor.perimeter.tick = lambda now=None: None
    monitor.perimeter.public = lambda: {}


def test_monitor_incident_counts_new_failures_and_recovers_after_clean_cycles():
    db = engine()
    monitor = SecurityMonitor(db, settings())
    quiet_perimeter(monitor)
    monitor.failures = 2
    monitor.last_error_category = "database_connection_timeout"
    monitor.last_error_at = 990
    monitor.tick(1000)
    with Session(db) as session:
        row = session.scalar(select(SecurityIncident).where(SecurityIncident.rule == "monitoring_degraded"))
        assert row.occurrences == 2
        evidence = json.loads(row.evidence_json)
        assert evidence["new_failures"] == 2
        assert evidence["lifetime_failures"] == 2
        assert evidence["last_error_category"] == "database_connection_timeout"
        assert row.status == "open"
    for stamp in (1010, 1020, 1030):
        monitor.tick(stamp)
    with Session(db) as session:
        row = session.scalar(select(SecurityIncident).where(SecurityIncident.rule == "monitoring_degraded"))
        state = session.get(SecurityMonitorState, monitor.identifier)
        assert row.status == "recovered"
        assert row.recovered_at == 1030
        assert json.loads(row.recovery_json)["clean_cycles"] == 3
        assert state.failures == 2
        assert state.clean_cycles == 3


def test_recovered_monitoring_incident_reopens_only_for_new_failure():
    db = engine()
    now = 2000
    with Session(db) as session, session.begin():
        row = open_incident(session, "monitoring_degraded", "worker:test", 2, now,
                            {"new_failures": 2}, "warning")
        row.status = "recovered"
        row.recovered_at = now + 30
        row.recovery_json = json.dumps({"clean_cycles": 3})
    with Session(db) as session, session.begin():
        row = open_incident(session, "monitoring_degraded", "worker:test", 1, now + 40,
                            {"new_failures": 1, "lifetime_failures": 3}, "warning")
        assert row.status == "open"
        assert row.occurrences == 1
        assert row.recovered_at == 0
        assert json.loads(row.recovery_json) == {}


def test_perimeter_failure_isolated_from_core_monitor(monkeypatch):
    db = engine()
    monitor = SecurityMonitor(db, settings())
    monkeypatch.setattr(perimeter, "collect_defender", lambda *args: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(perimeter, "collect_supabase_auth", lambda *args: None)
    monkeypatch.setattr(perimeter, "collect_cloudflare_liveness", lambda *args: None)
    monitor.tick(3000)
    assert monitor.last_tick_failed is False
    assert monitor.failures == 0
    assert monitor.clean_cycles == 1


def test_defender_metadata_normalization_never_persists_event_message(monkeypatch):
    db = engine()
    payload = json.dumps([
        {"TimeCreated": "2026-10-01T10:00:00.0000000Z", "Id": 1116,
         "RecordId": 22, "LevelDisplayName": "Warning"}
    ])
    monkeypatch.setattr(perimeter.os, "name", "nt")
    monkeypatch.setattr(perimeter.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=payload, returncode=0))
    result = perimeter.collect_defender(db, "s" * 32, 4000)
    assert result["status"] == "observing"
    with Session(db) as session:
        source = session.get(SecuritySourceState, "windows:defender")
        incident = session.scalar(select(SecurityIncident).where(SecurityIncident.rule == "defender_alert"))
        assert source.cursor == "22"
        assert json.loads(source.detail_json)["message_collected"] is False
        assert json.loads(incident.evidence_json)["message_collected"] is False


def test_resend_configuration_does_not_decrypt_stale_smtp_secret(monkeypatch):
    class FakeService:
        def __init__(self, *_args, **_kwargs): pass
        def get(self, *_args): return object()
        def public(self, _row):
            return {"configuration": {"from_email": "support@doobielogic.io",
                                      "from_name": "DoobieLogic Security"}}
        def secret(self, _row):
            raise AssertionError("SMTP secret must not be decrypted when Resend is configured")
    monkeypatch.setattr(spacemail, "IntegrationConfigurationService", FakeService)
    db = engine()
    configured = Settings(_env_file=None, resend_api_key="re_test_key",
                          integration_encryption_key="not-used",
                          spacemail_smtp_password="")
    resolved = spacemail.resolve_spacemail_settings(db, configured)
    assert resolved.resend_is_configured
    assert resolved.spacemail_from_email == "support@doobielogic.io"


def test_alert_delivery_degradation_is_visible_and_recovers_without_fake_delivery():
    db = engine()
    monitor = SecurityMonitor(db, settings(
        security_notifications_enabled=True,
        security_notification_recipient="owner@example.com",
    ))
    quiet_perimeter(monitor)
    monitor.notifier.state = "mail_credentials_unavailable"
    monitor.tick(5000)
    with Session(db) as session:
        row = session.scalar(select(SecurityIncident).where(
            SecurityIncident.rule == "alert_delivery_degraded"))
        assert row.status == "open"
        assert row.notification_attempts == 0
        assert json.loads(row.evidence_json)["provider_delivery_confirmed"] is False
    monitor.notifier.state = "ready"
    monitor.tick(5030)
    with Session(db) as session:
        row = session.scalar(select(SecurityIncident).where(
            SecurityIncident.rule == "alert_delivery_degraded"))
        assert row.status == "recovered"
        assert row.recovered_at == 5030
        assert json.loads(row.recovery_json)["notification_state"] == "ready"


def test_local_ai_is_not_executed_inline_with_monitor_heartbeat(monkeypatch):
    db = engine()
    monitor = SecurityMonitor(db, settings())
    quiet_perimeter(monitor)
    with Session(db) as session, session.begin():
        open_incident(session, "password_spray", "source", 25, 6000,
                      {"outcome": "denied"}, "high")
    calls = []
    def slow_review(*_args):
        time.sleep(0.4)
        calls.append(True)
        return True
    import backend.app.security.runtime as runtime_module
    monkeypatch.setattr(runtime_module, "local_ai_review", slow_review)
    started = time.perf_counter()
    monitor.tick(6000)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.25
    assert calls == []
    assert monitor.ai_review_state is not None
