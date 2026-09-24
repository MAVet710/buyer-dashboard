"""Bounded owner alerts. Submission is not proof of inbox delivery.

An ambiguous SMTP/HTTP result is never automatically replayed. Credentials and
incident evidence are never included in notification messages or error logs.
"""
import re
import time
from email.message import EmailMessage
from email.utils import formatdate
from sqlalchemy import select, func, update, text
from sqlalchemy.orm import Session
from ..services.spacemail import resolve_spacemail_settings, send_transactional_message
from .models import SecurityIncident, SecurityMonitorState
from .store import insert_for

EMAIL = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


def valid_recipient(value):
    return isinstance(value, str) and len(value) <= 254 and bool(EMAIL.fullmatch(value))


def message_for(row, settings):
    message = EmailMessage()
    message["From"] = settings.spacemail_from_email
    message["To"] = settings.security_notification_recipient
    message["Subject"] = "DoobieLogic Security: " + row["title"]
    message["Date"] = formatdate(row["first_seen"], localtime=False)
    message["Message-ID"] = "<security-" + row["id"] + "@doobielogic.io>"
    message["Auto-Submitted"] = "auto-generated"
    message.set_content("A DoobieLogic security event needs review.\n\n"
        + "Incident: " + row["id"] + "\nSeverity: " + row["severity"] + "\n"
        + "This is an observation, not proof of a successful intrusion.\n"
        + "Open the authenticated Security Center in Admin Tools: https://ops.doobielogic.io/admin\n"
        + "No account details, credentials, or customer records are included in this message.\n")
    return message


class SecurityNotifier:
    def __init__(self, engine, settings, sender=None):
        self.engine, self.settings = engine, settings
        self.sender = sender or send_transactional_message
        self.state = "not_connected"
        self.last_attempt = 0.0
        self.last_accepted = 0.0
        self.last_error = ""

    def tick(self, now=None):
        now = time.time() if now is None else now
        if not self.settings.security_notifications_enabled:
            self.state = "not_connected"
            return
        if not valid_recipient(self.settings.security_notification_recipient):
            self.state = "recipient_required"
            return
        try:
            settings = resolve_spacemail_settings(self.engine, self.settings)
        except Exception:
            self.state = "mail_credentials_unavailable"
            return
        if not (settings.spacemail_is_configured or settings.resend_is_configured):
            self.state = "mail_credentials_required"
            return
        if not valid_recipient(settings.spacemail_from_email):
            self.state = "sender_required"
            return
        try:
            with Session(self.engine) as session, session.begin():
                if self.engine.dialect.name == "postgresql":
                    session.execute(text("SET LOCAL statement_timeout = '2500ms'"))
                    if not session.scalar(text("SELECT pg_try_advisory_xact_lock(1780262429)")):
                        return
                # Locking one durable row serializes the budget across workers.
                session.execute(insert_for(session, SecurityMonitorState).values(
                    id="notification-budget", checked_at=now, status="ready", dropped=0, failures=0
                ).on_conflict_do_nothing(index_elements=["id"]))
                session.scalar(select(SecurityMonitorState).where(SecurityMonitorState.id == "notification-budget").with_for_update())
                session.execute(update(SecurityIncident).where(SecurityIncident.notification_status == "sending",
                    SecurityIncident.notification_updated_at < now - 120).values(notification_status="uncertain"))
                I = SecurityIncident
                for window, maximum in ((3600, settings.security_notification_hourly_limit),
                                        (86400, settings.security_notification_daily_limit)):
                    count = session.scalar(select(func.count()).select_from(I).where(
                        I.notification_attempts > 0, I.notification_updated_at >= now - window))
                    if count >= maximum:
                        self.state = "rate_limited"
                        return
                incident = session.scalar(select(I).where(I.notification_status == "pending", I.status != "resolved")
                    .order_by(I.first_seen, I.id).limit(1).with_for_update(skip_locked=True))
                if incident is None:
                    self.state = "ready"
                    return
                values = {key:getattr(incident, key) for key in ("id", "title", "severity", "first_seen")}
                incident.notification_status = "sending"
                incident.notification_updated_at = now
                incident.notification_attempts += 1
            self.last_attempt = now
            try:
                transport = self.sender(settings, message_for(values, settings))
                outcome, reference = "accepted", str(transport)[:30] + ":" + values["id"]
                self.last_accepted = now
                self.last_error = ""
            except Exception:
                outcome, reference = "uncertain", ""
                self.last_error = "provider_result_uncertain_no_automatic_retry"
            with Session(self.engine) as session, session.begin():
                session.execute(update(SecurityIncident).where(SecurityIncident.id == values["id"],
                    SecurityIncident.notification_status == "sending").values(notification_status=outcome,
                        notification_reference=reference, notification_updated_at=now))
            self.state = "ready" if outcome == "accepted" else "attention_required"
        except Exception:
            self.state = "storage_unavailable"
            self.last_error = "notification_storage_unavailable"

    def health(self):
        return {"state":self.state, "last_attempt":self.last_attempt or None,
                "last_accepted":self.last_accepted or None, "last_error":self.last_error,
                "delivery_confirmation":"not_connected", "automatic_retry":False}
