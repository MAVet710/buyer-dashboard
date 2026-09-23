from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import Engine, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from modules.advisory.models import AdvisoryDailyEvent, AdvisoryLead
from modules.advisory.schemas import EventInput, LeadInput, LeadUpdate, QUESTION_IDS
from modules.coman.audit import record_audit_event
from modules.coman.models import AuditEvent, Organization, new_id, utc_now


@lru_cache(maxsize=1)
def score_definition() -> dict:
    definition = json.loads((Path(__file__).resolve().parents[3] / 'shared' / 'advisory_score.json').read_text(encoding='utf-8-sig'))
    questions = definition.get('questions', [])
    if definition.get('version') != 1 or len(questions) != 25 or {q['id'] for q in questions} != set(QUESTION_IDS):
        raise RuntimeError('Invalid advisory score definition')
    return definition


def calculate_score(answers: dict[str, int | None]) -> dict:
    from modules.advisory.schemas import validate_answers
    validate_answers(answers)
    definition = score_definition()
    groups: dict[str, list[int]] = defaultdict(list)
    for question in definition['questions']:
        value = answers[question['id']]
        groups.setdefault(question['category'], [])
        if value is not None:
            groups[question['category']].append(value)
    def percentage(values):
        if not values:
            return None
        return int((Decimal(sum(values)) * 100 / (4 * len(values))).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    applicable = [value for value in answers.values() if value is not None]
    return {
        'version': definition['version'], 'source': 'self-reported', 'verified': False,
        'overall_score': percentage(applicable), 'applicable_answers': len(applicable),
        'not_applicable_answers': 25 - len(applicable),
        'categories': [{'category': key, 'score': percentage(values), 'applicable_answers': len(values)} for key, values in groups.items()],
        'inputs': answers,
    }


def owner_id(settings) -> str:
    value = str(settings.doobielogic_advisory_organization_id or '').strip()
    if not value:
        raise HTTPException(503, 'Advisory intake is not configured yet. Please contact the team.')
    return value


def require_owner(session: Session, settings) -> str:
    owner = owner_id(settings)
    organization = session.get(Organization, owner)
    if not organization or not organization.active:
        raise HTTPException(503, 'Advisory intake is temporarily unavailable. Please contact the team.')
    return owner


def _replay(session: Session, owner: str, payload: LeadInput, digest: str):
    if payload.submission_id is None:
        return None
    existing = session.scalar(select(AdvisoryLead).where(AdvisoryLead.organization_id == owner, AdvisoryLead.submission_id == str(payload.submission_id)))
    if existing:
        if existing.request_hash != digest:
            raise HTTPException(409, 'This submission reference was already used for different answers.')
        return {'accepted': True, 'reference': existing.id}
    return None


def capture_lead(engine: Engine, settings, payload: LeadInput) -> dict:
    # Do not reveal the honeypot outcome and do not create records or notifications.
    if payload.website:
        return {'accepted': True, 'reference': new_id()}
    data = payload.model_dump(mode='json', exclude={'website', 'submission_id'})
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    score = calculate_score(payload.tool_inputs) if payload.source_tool == 'operations-score' else {}
    with Session(engine) as session:
        owner = require_owner(session, settings)
        replay = _replay(session, owner, payload, digest)
        if replay:
            return replay
        row = AdvisoryLead(
            organization_id=owner, submission_id=str(payload.submission_id) if payload.submission_id else None,
            request_hash=digest,
            **{key: data[key] for key in ('name', 'email', 'phone', 'company', 'role', 'state', 'operation', 'locations', 'challenge', 'service', 'message', 'consent')},
            source_tool=payload.source_tool or '', score_summary_json=json.dumps(score, sort_keys=True),
            attribution_json=json.dumps(payload.attribution.model_dump(), sort_keys=True),
        )
        session.add(row)
        try:
            session.flush()
            record_audit_event(session, organization_id=owner, facility_id=None, entity_type='advisory_lead', entity_id=row.id,
                action='advisory.lead.created', actor='public:advisory-intake', source='api', correlation_id=row.id,
                after={'status': 'NEW', 'version': 1}, metadata={'service': row.service, 'source_tool': row.source_tool, 'consent_version': row.consent_version})
            reference = row.id
            session.commit()
        except IntegrityError:
            session.rollback()
            replay = _replay(session, owner, payload, digest)
            if replay:
                return replay
            raise HTTPException(503, 'Your submission could not be saved. Please retry.') from None
    return {'accepted': True, 'reference': reference}


def serialize_lead(row: AdvisoryLead, *, detail=False) -> dict:
    result = {key: getattr(row, key) for key in ('id', 'name', 'email', 'phone', 'company', 'role', 'state', 'operation', 'locations', 'service', 'source_tool', 'status', 'version', 'created_at', 'updated_at')}
    if detail:
        result.update(challenge=row.challenge, message=row.message, consent=row.consent, consent_version=row.consent_version,
                      score_summary=json.loads(row.score_summary_json), attribution=json.loads(row.attribution_json))
    return result


def list_leads(engine, settings, *, status=None, limit=50, offset=0):
    with Session(engine) as session:
        owner = require_owner(session, settings)
        predicates = [AdvisoryLead.organization_id == owner]
        if status:
            predicates.append(AdvisoryLead.status == status)
        total = session.scalar(select(func.count()).select_from(AdvisoryLead).where(*predicates))
        rows = session.scalars(select(AdvisoryLead).where(*predicates).order_by(AdvisoryLead.created_at.desc(), AdvisoryLead.id).limit(limit).offset(offset)).all()
        return {'total': total, 'limit': limit, 'offset': offset, 'items': [serialize_lead(row) for row in rows]}


def lead_detail(engine, settings, lead_id):
    with Session(engine) as session:
        owner = require_owner(session, settings)
        row = session.scalar(select(AdvisoryLead).where(AdvisoryLead.id == lead_id, AdvisoryLead.organization_id == owner))
        if not row:
            raise HTTPException(404, 'Lead not found.')
        return serialize_lead(row, detail=True)


STATUS_TRANSITIONS = {
    'NEW': {'CONTACTED', 'QUALIFIED', 'CLOSED_LOST'},
    'CONTACTED': {'QUALIFIED', 'CONSULTATION_BOOKED', 'CLOSED_LOST'},
    'QUALIFIED': {'CONTACTED', 'CONSULTATION_BOOKED', 'PROPOSAL_SENT', 'CLOSED_LOST'},
    'CONSULTATION_BOOKED': {'QUALIFIED', 'PROPOSAL_SENT', 'CLOSED_LOST'},
    'PROPOSAL_SENT': {'QUALIFIED', 'CONSULTATION_BOOKED', 'CLIENT', 'CLOSED_LOST'},
    'CLIENT': {'QUALIFIED'},
    'CLOSED_LOST': {'CONTACTED', 'QUALIFIED'},
}


def update_lead(engine, settings, lead_id: str, payload: LeadUpdate, actor: str):
    with Session(engine) as session:
        owner = require_owner(session, settings)
        row = session.scalar(select(AdvisoryLead).where(AdvisoryLead.id == lead_id, AdvisoryLead.organization_id == owner))
        if not row:
            raise HTTPException(404, 'Lead not found.')
        if row.version != payload.expected_version:
            raise HTTPException(409, 'This lead changed. Reload before updating it.')
        if payload.status != row.status and payload.status not in STATUS_TRANSITIONS[row.status]:
            raise HTTPException(409, 'This lifecycle transition is not allowed. Update the next relevant stage first.')
        before = {'status': row.status, 'version': row.version}
        if row.status == payload.status and not payload.note:
            return serialize_lead(row, detail=True)
        changed = session.execute(update(AdvisoryLead).where(AdvisoryLead.id == lead_id, AdvisoryLead.organization_id == owner, AdvisoryLead.version == payload.expected_version)
            .values(status=payload.status, version=payload.expected_version + 1, updated_at=utc_now()))
        if changed.rowcount != 1:
            raise HTTPException(409, 'This lead changed. Reload before updating it.')
        record_audit_event(session, organization_id=owner, facility_id=None, entity_type='advisory_lead', entity_id=lead_id,
            action='advisory.lead.status_changed', actor=actor, source='user', reason=payload.note, correlation_id=lead_id,
            before=before, after={'status': payload.status, 'version': payload.expected_version + 1})
        session.commit()
        session.refresh(row)
        return serialize_lead(row, detail=True)


def capture_event(engine, settings, payload: EventInput):
    with Session(engine) as session:
        owner = require_owner(session, settings)
        values = dict(id=new_id(), organization_id=owner, day=utc_now().date(), event=payload.event, placement=payload.placement, item=payload.item, count=1)
        if engine.dialect.name == 'postgresql':
            from sqlalchemy.dialects.postgresql import insert
        elif engine.dialect.name == 'sqlite':
            from sqlalchemy.dialects.sqlite import insert
        else:
            raise HTTPException(503, 'Analytics storage is unavailable.')
        statement = insert(AdvisoryDailyEvent).values(**values).on_conflict_do_update(
            index_elements=['organization_id', 'day', 'event', 'placement', 'item'], set_={'count': AdvisoryDailyEvent.count + 1})
        session.execute(statement)
        session.commit()
    return {'accepted': True}


def metrics(engine, settings, days=30):
    since = utc_now().date() - timedelta(days=days - 1)
    with Session(engine) as session:
        owner = require_owner(session, settings)
        status_counts = dict(session.execute(select(AdvisoryLead.status, func.count()).where(AdvisoryLead.organization_id == owner).group_by(AdvisoryLead.status)).all())
        events = session.execute(select(AdvisoryDailyEvent.event, func.sum(AdvisoryDailyEvent.count)).where(AdvisoryDailyEvent.organization_id == owner, AdvisoryDailyEvent.day >= since).group_by(AdvisoryDailyEvent.event)).all()
        # Canonical history is authoritative; SQL groups unique reached statuses,
        # avoiding unbounded audit hydration and per-lead queries.
        if engine.dialect.name == 'postgresql':
            from sqlalchemy import cast
            from sqlalchemy.dialects.postgresql import JSONB
            stage = cast(AuditEvent.changes_json, JSONB)['_event']['after']['status'].astext
        else:
            stage = func.json_extract(AuditEvent.changes_json, '$._event.after.status')
        funnel = dict(session.execute(select(stage, func.count(func.distinct(AuditEvent.entity_id))).where(
            AuditEvent.organization_id == owner, AuditEvent.entity_type == 'advisory_lead',
            AuditEvent.action.in_(['advisory.lead.created', 'advisory.lead.status_changed']), stage.is_not(None)).group_by(stage)).all())
        return {'status_counts': status_counts, 'cumulative_stage_counts': funnel, 'event_counts': dict(events), 'event_window_days': days, 'event_window_start': since}


def booking_config(settings):
    value = str(settings.doobielogic_advisory_booking_url or '').strip()
    parsed = urlsplit(value)
    valid = parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password
    return {'available': bool(valid), 'url': value if valid else None}
