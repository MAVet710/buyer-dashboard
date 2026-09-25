from datetime import date, datetime, timezone
import json
import re
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Facility, new_id
from ..auth import RequestContext, get_request_context, require_facility_capability
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.adoption_models import ReadinessAnnotation, ReportDelivery, ReportSubscription
from ..services.implementation_readiness import ITEMS, MANUAL_ITEMS, readiness, scope
from ..services.integration_wizard import PROVIDERS, wizard
from ..services.scheduled_reports import REPORT_CAPABILITIES, audit, deliver, next_occurrence, process_due, public

router = APIRouter(tags=["implementation-and-reporting"])


def admin(context: RequestContext = Depends(get_request_context)):
    if context.role.casefold() not in {"admin", "dev"}:
        raise HTTPException(403, "Facility administrator access is required.")
    return context


class AnnotationInput(BaseModel):
    notes: str = Field(default="", max_length=4000)
    owner: str = Field(default="", max_length=160)
    target_date: date | None = None
    manual_status: Literal["complete", "incomplete", "not_applicable", "needs_review"] | None = None


class SubscriptionInput(BaseModel):
    report_type: str
    recipients: list[str] = Field(min_length=1, max_length=20)
    cadence: Literal["daily", "weekly", "monthly"]

    @field_validator("report_type")
    @classmethod
    def valid_report(cls, value):
        if value not in REPORT_CAPABILITIES:
            raise ValueError("Choose an Executive Report from the catalog.")
        return value

    @field_validator("recipients")
    @classmethod
    def valid_recipients(cls, values):
        normalized = list(dict.fromkeys(value.strip().casefold() for value in values))
        if any(len(value) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", value) for value in normalized):
            raise ValueError("Enter valid email addresses without display names.")
        return normalized


class ActiveInput(BaseModel):
    active: bool


class RunInput(BaseModel):
    test: bool = False


@router.get("/implementation-readiness")
def get_readiness(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    result = readiness(engine, context)
    for item in wizard(engine, settings, context)["items"]:
        result["items"].append({**item, "key": "wizard_" + item["key"], "label": item["label"] + " setup",
            "manual": False, "manual_status": None, "notes": "", "owner": "", "target_date": None})
    return result


class WizardProgress(BaseModel):
    step: Literal["facility", "systems", "connect", "validate", "map", "evidence", "summary"]


class WizardChoice(BaseModel):
    skipped: bool


@router.get("/integration-wizard")
def get_wizard(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    return wizard(engine, settings, context)


def save_wizard_annotation(key, notes, context, engine):
    with Session(engine) as session:
        if not session.scalar(select(Facility.id).where(Facility.id == context.facility_id, Facility.organization_id == context.organization_id)):
            raise HTTPException(404, "Facility not found in this organization.")
        row = session.scalar(select(ReadinessAnnotation).where(*scope(ReadinessAnnotation, context), ReadinessAnnotation.item_key == key).with_for_update())
        before = {"notes": row.notes} if row else None
        if row is None:
            row = ReadinessAnnotation(id=new_id(), organization_id=context.organization_id, facility_id=context.facility_id, item_key=key)
            session.add(row)
        row.notes, row.updated_by, row.updated_at = notes, context.user_id, datetime.now(timezone.utc)
        audit(session, context, row, "integration_wizard_saved", before=before, after={"notes": notes})
        session.commit()


@router.post("/integration-wizard/progress")
def wizard_progress(payload: WizardProgress, context: RequestContext = Depends(admin), engine: Engine = Depends(get_engine)):
    save_wizard_annotation("wizard_progress", json.dumps({"step": payload.step}), context, engine)
    return {"step": payload.step}


@router.post("/integration-wizard/providers/{provider}")
def wizard_choice(provider: str, payload: WizardChoice, context: RequestContext = Depends(admin), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    if provider not in PROVIDERS:
        raise HTTPException(404, "Provider not supported.")
    item = next(item for item in wizard(engine, settings, context)["items"] if item["key"] == provider)
    if payload.skipped and item["required"]:
        raise HTTPException(422, "Required providers cannot be skipped. Resolve the remaining evidence or review the facility operating mode.")
    save_wizard_annotation("wizard_" + provider, "skipped" if payload.skipped else "selected", context, engine)
    return {"provider": provider, "skipped": payload.skipped}


@router.post("/implementation-readiness/{item_key}")
def annotate(item_key: str, payload: AnnotationInput, context: RequestContext = Depends(admin), engine: Engine = Depends(get_engine)):
    if item_key not in ITEMS:
        raise HTTPException(404, "Checklist item not found.")
    if payload.manual_status and item_key not in MANUAL_ITEMS:
        raise HTTPException(422, "Automatic evidence cannot be overridden.")
    if payload.manual_status and not payload.notes.strip():
        raise HTTPException(422, "Supporting notes are required for a manual attestation.")
    with Session(engine) as session:
        row = session.scalar(select(ReadinessAnnotation).where(*scope(ReadinessAnnotation, context), ReadinessAnnotation.item_key == item_key))
        before = public(row) if row else None
        if row is None:
            row = ReadinessAnnotation(id=new_id(), organization_id=context.organization_id, facility_id=context.facility_id, item_key=item_key)
            session.add(row)
        for name, value in payload.model_dump().items():
            setattr(row, name, value)
        row.updated_by, row.updated_at = context.user_id, datetime.now(timezone.utc)
        # JSON-mode payload preserves date values as ISO strings for the audit envelope.
        audit(session, context, row, "readiness_annotation_saved", before=_json_safe(before), after=payload.model_dump(mode="json"))
        session.commit()
        return public(row)


def _json_safe(value):
    return json.loads(json.dumps(value, default=str)) if value is not None else None


@router.get("/report-subscriptions")
def subscriptions(context: RequestContext = Depends(admin), engine: Engine = Depends(get_engine), offset: int = 0):
    if offset < 0 or offset > 100000:
        raise HTTPException(422, "Invalid subscription offset.")
    with Session(engine) as session:
        rows = session.scalars(select(ReportSubscription).where(*scope(ReportSubscription, context)).order_by(ReportSubscription.created_at.desc(), ReportSubscription.id).offset(offset).limit(100))
        return {"items": [public(row) for row in rows]}


@router.post("/report-subscriptions")
def create_subscription(payload: SubscriptionInput, context: RequestContext = Depends(admin), engine: Engine = Depends(get_engine)):
    require_facility_capability(context, engine, REPORT_CAPABILITIES[payload.report_type])
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        row = ReportSubscription(id=new_id(), organization_id=context.organization_id, facility_id=context.facility_id,
            report_type=payload.report_type, recipients_json=json.dumps(payload.recipients), cadence=payload.cadence,
            next_run=next_occurrence(now, payload.cadence), created_by=context.user_id)
        session.add(row)
        audit(session, context, row, "subscription_created", after=payload.model_dump())
        session.commit()
        return public(row)


@router.post("/report-subscriptions/process-due")
def run_due(context: RequestContext = Depends(admin), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    return process_due(engine, settings, context)


@router.get("/report-subscriptions/history")
def history(context: RequestContext = Depends(admin), engine: Engine = Depends(get_engine), offset: int = 0):
    if offset < 0 or offset > 100000:
        raise HTTPException(422, "Invalid history offset.")
    with Session(engine) as session:
        rows = session.scalars(select(ReportDelivery).where(*scope(ReportDelivery, context)).order_by(ReportDelivery.created_at.desc(), ReportDelivery.id).offset(offset).limit(50))
        return {"items": [public(row) for row in rows]}


@router.post("/report-subscriptions/{subscription_id}/active")
def set_active(subscription_id: str, payload: ActiveInput, context: RequestContext = Depends(admin), engine: Engine = Depends(get_engine)):
    with Session(engine) as session:
        row = session.scalar(select(ReportSubscription).where(*scope(ReportSubscription, context), ReportSubscription.id == subscription_id).with_for_update())
        if not row:
            raise HTTPException(404, "Subscription not found.")
        before = {"active": row.active}
        row.active = payload.active
        audit(session, context, row, "subscription_activity_changed", before=before, after=payload.model_dump())
        session.commit()
        return public(row)


@router.post("/report-subscriptions/{subscription_id}/run")
def run_subscription(subscription_id: str, payload: RunInput, context: RequestContext = Depends(admin),
                     engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings),
                     idempotency_key: str = Header(alias="X-Idempotency-Key", min_length=1, max_length=64)):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", idempotency_key):
        raise HTTPException(422, "Invalid idempotency key.")
    return deliver(engine, settings, context, subscription_id, request_key=idempotency_key, test=payload.test)
