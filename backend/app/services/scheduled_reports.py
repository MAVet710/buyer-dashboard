"""Explicit, facility-scoped scheduler with durable at-most-once SMTP attempts."""
import calendar
import json
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from modules.coman.audit import record_audit_event
from modules.coman.models import new_id
from ..auth import require_facility_capability
from .adoption_models import ReportDelivery, ReportSubscription
from .implementation_readiness import scope
from . import spacemail

REPORT_CAPABILITIES = {"buyer": "retail", "production": "production", "extraction": "production",
    **{key: "cultivation" for key in ("cultivation", "cultivation-plants", "cultivation-harvests", "cultivation-rooms")}}


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def next_occurrence(value, cadence):
    value = utc(value)
    if cadence in {"daily", "weekly"}:
        return value + timedelta(days=1 if cadence == "daily" else 7)
    if cadence != "monthly":
        raise ValueError("Unsupported cadence")
    year, month = (value.year + 1, 1) if value.month == 12 else (value.year, value.month + 1)
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def audit(session, context, entity, action, before=None, after=None):
    record_audit_event(session, organization_id=context.organization_id, facility_id=context.facility_id,
        entity_type="report_subscription" if isinstance(entity, ReportSubscription) else "implementation_readiness" if hasattr(entity, "item_key") else "report_delivery",
        entity_id=entity.id, actor=context.user_id, action=action, before=before, after=after)


def public(row):
    result = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    if "recipients_json" in result:
        result["recipients"] = json.loads(result.pop("recipients_json"))
    return result


def generate_report(report_type, context, engine):
    from ..routers import executive_reports as reports
    if report_type == "buyer":
        pdf, _ = reports._buyer_report(context, engine)
    elif report_type == "production":
        pdf, _ = reports._production_report(context, engine)
    elif report_type == "extraction":
        pdf, _ = reports._extraction_report(context, engine)
    else:
        pdf, _ = reports._cultivation_report(context, engine, reports.CULTIVATION_REPORTS[report_type][0])
    return reports._validated_pdf(pdf, report_type)


def deliver(engine, settings, context, subscription_id, *, request_key=None, test=False, now=None):
    now = utc(now or datetime.now(timezone.utc))
    with Session(engine) as session:
        subscription = session.scalar(select(ReportSubscription).where(*scope(ReportSubscription, context), ReportSubscription.id == subscription_id))
        if not subscription:
            raise HTTPException(404, "Subscription not found.")
        scheduled = request_key is None
        key = "due:" + utc(subscription.next_run).isoformat() if scheduled else ("test:" if test else "manual:") + request_key
        existing = session.scalar(select(ReportDelivery).where(*scope(ReportDelivery, context), ReportDelivery.subscription_id == subscription_id, ReportDelivery.run_key == key))
        if existing:
            return public(existing)
        if scheduled and (not subscription.active or utc(subscription.next_run) > now):
            return None
        # Compare-and-swap the schedule in the same transaction as the unique receipt.
        if scheduled:
            next_run = next_occurrence(subscription.next_run, subscription.cadence)
            while next_run <= now:
                next_run = next_occurrence(next_run, subscription.cadence)
            claimed = session.execute(update(ReportSubscription).where(*scope(ReportSubscription, context),
                ReportSubscription.id == subscription.id, ReportSubscription.active.is_(True),
                ReportSubscription.next_run == subscription.next_run).values(next_run=next_run, last_run=now))
            if claimed.rowcount != 1:
                session.rollback()
                return None
        else:
            subscription.last_run = now
        run = ReportDelivery(id=new_id(), organization_id=context.organization_id, facility_id=context.facility_id,
            subscription_id=subscription.id, run_key=key, report_type=subscription.report_type,
            recipients_json=subscription.recipients_json, created_at=now)
        session.add(run)
        audit(session, context, run, "report_delivery_reserved")
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = session.scalar(select(ReportDelivery).where(*scope(ReportDelivery, context), ReportDelivery.subscription_id == subscription_id, ReportDelivery.run_key == key))
            if existing:
                return public(existing)
            raise
        run_id, report_type, recipients = run.id, run.report_type, json.loads(run.recipients_json)
    status, detail = "deferred", "Spacemail is unavailable or validation failed. No email was sent."
    sending = False
    try:
        require_facility_capability(context, engine, REPORT_CAPABILITIES[report_type])
        mail = spacemail.resolve_spacemail_settings(engine, settings)
        if mail.spacemail_is_configured and spacemail.test_spacemail_connection(mail)["ok"]:
            pdf = generate_report(report_type, context, engine)
            message = EmailMessage()
            message["Subject"] = f"DoobieLogic {'test ' if test else ''}report: {report_type}"
            message["From"] = mail.spacemail_from_email
            # Bcc envelope prevents exposing the recipient list to other recipients.
            message["To"] = mail.spacemail_from_email
            message["Message-ID"] = f"<{run_id}@doobielogic.io>"
            message.set_content("Your facility-scoped Executive Report is attached.")
            message.add_attachment(pdf, maintype="application", subtype="pdf", filename=f"{report_type}.pdf")
            with spacemail._smtp_login(mail) as smtp:
                smtp.login(mail.spacemail_smtp_username, mail.spacemail_smtp_password)
                sending = True
                refused = smtp.send_message(message, to_addrs=recipients)
            status = "needs_review" if refused else "sent"
            detail = "Some recipients were refused. Review delivery before resending." if refused else "Spacemail accepted the report for delivery."
    except Exception:
        # Provider exceptions may include addresses, credentials or report data.
        status = "needs_review" if sending else "failed"
        detail = "Delivery outcome is uncertain. Review before sending again." if sending else "Report preparation or mail validation failed. No email was sent."
    with Session(engine) as session:
        run = session.scalar(select(ReportDelivery).where(*scope(ReportDelivery, context), ReportDelivery.id == run_id))
        run.status, run.detail, run.finished_at = status, detail, datetime.now(timezone.utc)
        audit(session, context, run, "report_delivery_finished", after={"status": status})
        session.commit()
        return public(run)


def process_due(engine, settings, context, now=None):
    now = utc(now or datetime.now(timezone.utc))
    with Session(engine) as session:
        ids = list(session.scalars(select(ReportSubscription.id).where(*scope(ReportSubscription, context),
            ReportSubscription.active.is_(True), ReportSubscription.next_run <= now).order_by(ReportSubscription.next_run).limit(10)))
    results = []
    for subscription_id in ids:
        result = deliver(engine, settings, context, subscription_id, now=now)
        if result:
            results.append(result)
    return {"items": results}
