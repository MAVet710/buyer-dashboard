"""Scaffold checks only. This does not establish a working intrusion detector."""
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from backend.app.security.privacy import pseudonym, source_identity
from backend.app.security.models import SecurityEvent, SecurityIncident, SecurityMonitorState
from backend.app.security.store import open_incident, append_events


def request(peer="127.0.0.1", **headers):
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def settings(cidrs=""):
    return SimpleNamespace(security_trusted_proxy_cidrs=cidrs)


def test_pseudonyms_are_stable_scoped_and_not_plaintext():
    key = "test-only-not-a-live-secret" * 2
    first = pseudonym(key, "subject", "sample-user")
    assert len(first) == 64 and "sample-user" not in first
    assert first == pseudonym(key, "subject", "sample-user")
    assert first != pseudonym(key, "source", "sample-user")
    assert first != pseudonym("different-test-key", "subject", "sample-user")
    assert pseudonym(key, "subject", "") == ""


def test_loopback_is_not_mistaken_for_one_shared_attacker():
    assert source_identity(request(), settings()) == ""


def test_forwarded_headers_from_untrusted_peer_are_ignored():
    r = request("192.0.2.9", **{"x-forwarded-for": "198.51.100.3", "x-advisory-client-ip": "198.51.100.3"})
    assert source_identity(r, settings()) == "192.0.2.9"


def test_explicit_trusted_peer_can_supply_overwritten_ingress_header():
    r = request(**{"x-advisory-client-ip": "198.51.100.3"})
    assert source_identity(r, settings("127.0.0.1/32")) == "198.51.100.3"


@pytest.mark.parametrize("value", ["", "garbage", "127.0.0.1", "::", "fe80::1%eth0", "1.1.1.1,2.2.2.2"])
def test_invalid_forwarded_addresses_do_not_create_source_groups(value):
    assert source_identity(request(**{"x-advisory-client-ip": value}), settings("127.0.0.1/32")) == ""


def test_invalid_proxy_configuration_does_not_grant_trust():
    assert source_identity(request(**{"x-advisory-client-ip": "198.51.100.3"}), settings("invalid")) == ""


@pytest.fixture()
def database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for model in (SecurityEvent, SecurityIncident, SecurityMonitorState):
        model.__table__.create(engine)
    yield engine
    engine.dispose()


def test_incident_deduplication_preserves_triage(database):
    with Session(database) as session, session.begin():
        row = open_incident(session, "login_failures", "test-subject", 8, 10000)
        identifier = row.id
        row.status = "acknowledged"
        session.flush()
        open_incident(session, "login_failures", "test-subject", 12, 10001)
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(SecurityIncident)) == 1
        row = session.get(SecurityIncident, identifier)
        assert row.status == "acknowledged" and row.occurrences == 12
        assert row.notification_status == "pending"


def test_event_retry_does_not_duplicate_stored_evidence(database):
    event = dict(id="test-event", occurred_at=10000, kind="login_failure",
                 subject_key="test-subject", source_key="", actor_id="",
                 organization_id="", route="/account/username-login", request_id="test-request", audit_id="")
    with Session(database) as session, session.begin():
        append_events(session, [event])
        append_events(session, [event])
        assert session.scalar(select(func.count()).select_from(SecurityEvent)) == 1
