"""Platform-only telemetry; canonical operational audit remains authoritative."""
from sqlalchemy import Column, String, Float, Integer, Text, Index, Boolean
from modules.coman.models import Base


class SecurityEvent(Base):
    __tablename__ = "security_events"
    id = Column(String(36), primary_key=True)
    occurred_at = Column(Float, nullable=False)
    kind = Column(String(40), nullable=False)
    subject_key = Column(String(64), nullable=False, default="")
    source_key = Column(String(64), nullable=False, default="")
    actor_id = Column(String(36), nullable=False, default="")
    organization_id = Column(String(36), nullable=False, default="")
    route = Column(String(200), nullable=False, default="")
    request_id = Column(String(36), nullable=False, default="")
    audit_id = Column(String(36), nullable=False, default="")
    __table_args__ = (
        Index("ix_security_event_kind_time_subject", "kind", "occurred_at", "subject_key"),
        Index("ix_security_event_time", "occurred_at"),
    )


class SecurityIncident(Base):
    __tablename__ = "security_incidents"
    id = Column(String(36), primary_key=True)
    fingerprint = Column(String(64), unique=True, nullable=False)
    rule = Column(String(40), nullable=False)
    severity = Column(String(12), nullable=False)
    title = Column(String(160), nullable=False)
    group_key = Column(String(64), nullable=False)
    first_seen = Column(Float, nullable=False)
    last_seen = Column(Float, nullable=False)
    occurrences = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="open")
    version = Column(Integer, nullable=False, default=1)
    evidence_json = Column(Text, nullable=False, default="{}")
    notification_status = Column(String(24), nullable=False, default="pending")
    notification_updated_at = Column(Float, nullable=False, default=0)
    notification_reference = Column(String(120), nullable=False, default="")
    notification_attempts = Column(Integer, nullable=False, default=0)
    __table_args__ = (Index("ix_security_incident_time", "last_seen"),
                      Index("ix_security_incident_notification", "notification_status", "notification_updated_at"))


class SecurityMonitorState(Base):
    __tablename__ = "security_monitor_state"
    id = Column(String(80), primary_key=True)
    checked_at = Column(Float, nullable=False)
    status = Column(String(32), nullable=False)
    dropped = Column(Integer, nullable=False, default=0)
    failures = Column(Integer, nullable=False, default=0)


class SecurityGuardState(Base):
    __tablename__ = "security_guard_state"
    id = Column(String(80), primary_key=True)
    checked_at = Column(Float, nullable=False)
    state = Column(String(24), nullable=False, default="observing")
    threat_level = Column(String(16), nullable=False, default="normal")
    risk_score = Column(Integer, nullable=False, default=0)
    active_investigations = Column(Integer, nullable=False, default=0)
    metrc_write_protection = Column(Boolean, nullable=False, default=False)
    deception_armed = Column(Boolean, nullable=False, default=True)
    ai_state = Column(String(24), nullable=False, default="not_checked")
    ai_last_success = Column(Float, nullable=False, default=0)
    detail_json = Column(Text, nullable=False, default="{}")


class SecurityInvestigation(Base):
    __tablename__ = "security_investigations"
    id = Column(String(36), primary_key=True)
    fingerprint = Column(String(64), unique=True, nullable=False)
    opened_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)
    status = Column(String(24), nullable=False, default="open")
    risk_score = Column(Integer, nullable=False, default=0)
    confidence = Column(Float, nullable=False, default=0)
    classification = Column(String(80), nullable=False, default="suspicious_activity")
    subject_key = Column(String(64), nullable=False, default="")
    source_key = Column(String(64), nullable=False, default="")
    evidence_json = Column(Text, nullable=False, default="{}")
    ai_summary = Column(Text, nullable=False, default="")
    recommended_state = Column(String(24), nullable=False, default="observe")
    containment_json = Column(Text, nullable=False, default="{}")
    evidence_hash = Column(String(64), nullable=False, default="")
    __table_args__ = (Index("ix_security_investigation_status_risk", "status", "risk_score", "updated_at"),)
