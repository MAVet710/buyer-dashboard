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
