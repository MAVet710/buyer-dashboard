import time
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from modules.coman.models import Base
from backend.app.security.models import SecurityEvent, SecurityIncident, SecurityGuardState, SecurityInvestigation
from backend.app.security.guard import evaluate_guard, metrc_writes_allowed, HONEY_ROUTES
from backend.app.security.store import open_incident


def db():
    e=create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(e)
    return e

def test_normal_state_keeps_metrc_available():
    e=db()
    with Session(e) as s,s.begin():
        state=evaluate_guard(s,time.time())
    assert state["risk_score"]==0
    assert metrc_writes_allowed(e) is True

def test_single_weak_signal_does_not_trip_breaker():
    e=db(); now=time.time()
    with Session(e) as s,s.begin():
        open_incident(s,"login_failures","subject",8,now,{"outcome":"denied"})
        state=evaluate_guard(s,now)
    assert state["risk_score"]==35
    assert metrc_writes_allowed(e) is True

def test_correlated_honey_and_password_spray_trip_breaker():
    e=db(); now=time.time()
    with Session(e) as s,s.begin():
        open_incident(s,"password_spray","source",25,now,{"outcome":"denied"})
        s.add(SecurityEvent(id="h",occurred_at=now,kind="honey_touch",subject_key="honey",source_key="source",
            actor_id="",organization_id="",route="/internal/metrc/keys",request_id="r",audit_id=""))
        state=evaluate_guard(s,now)
    assert state["risk_score"]>=95
    assert state["metrc_write_protection"] is True
    assert metrc_writes_allowed(e) is False
    with Session(e) as s:
        inv=s.query(SecurityInvestigation).one()
        assert inv.evidence_hash and inv.recommended_state=="contain"

def test_honey_routes_are_synthetic_and_fixed():
    assert "/internal/metrc/keys" in HONEY_ROUTES
    assert all(route.startswith("/") for route in HONEY_ROUTES)


def test_old_investigation_recovers_after_signal_window_clears():
    e=db(); now=time.time()
    with Session(e) as s,s.begin():
        open_incident(s,"login_failures","subject",8,now-600,{"outcome":"denied"})
        s.add(SecurityInvestigation(
            id="old-investigation",fingerprint="old-fingerprint",opened_at=now-700,updated_at=now-400,
            status="open",risk_score=55,confidence=.7,classification="correlated_security_activity",
            subject_key="subject",source_key="",evidence_json="{}",ai_summary="",
            recommended_state="investigate",containment_json="{}",evidence_hash="hash"))
        state=evaluate_guard(s,now)
    assert state["risk_score"]==0
    with Session(e) as s:
        row=s.get(SecurityInvestigation,"old-investigation")
        assert row.status=="recovered"
        assert row.recommended_state=="observe"


def test_single_defender_alert_is_high_risk_but_not_automatic_containment():
    e=db(); now=time.time()
    with Session(e) as s,s.begin():
        s.add(SecurityEvent(id="defender",occurred_at=now,kind="defender_alert",
            subject_key="threat",source_key="local-host",actor_id="",organization_id="",
            route="windows_defender:1116",request_id="",audit_id=""))
        state=evaluate_guard(s,now)
    assert state["risk_score"]==80
    assert state["threat_level"]=="high"
    assert state["metrc_write_protection"] is False
