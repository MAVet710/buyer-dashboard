"""Scoped work service. Mutations and their audit events commit together."""
import calendar
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import case, exists, or_, select, update
from sqlalchemy.orm import Session

from modules.coman.audit import record_audit_event
from modules.coman.models import AppUser, AppUserFacilityRole, WorkItem, WorkTemplate, new_id, utc_now

WRITE_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa"}


def require_write(context):
    if context.role not in WRITE_ROLES:
        raise HTTPException(403, "Your role cannot change operational work.")


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def snapshot(row):
    return {col.name: (utc(value).isoformat() if isinstance(value := getattr(row, col.name), datetime) else value)
            for col in row.__table__.columns}


def scope(model, context):
    return (model.organization_id == context.organization_id, model.facility_id == context.facility_id)


def assignee_query(context):
    membership = exists().where(
        AppUserFacilityRole.user_id == AppUser.id,
        AppUserFacilityRole.organization_id == context.organization_id,
        AppUserFacilityRole.facility_id == context.facility_id,
        AppUserFacilityRole.role.in_(WRITE_ROLES),
    )
    return select(AppUser).where(AppUser.active.is_(True), AppUser.organization_id == context.organization_id,
                                 or_(AppUser.role.in_({"admin", "dev"}), membership))


def validate_assignee(session, context, user_id):
    if user_id and session.scalar(assignee_query(context).where(AppUser.id == user_id)) is None:
        raise HTTPException(422, "Assignee must be an active work-capable user in this facility.")


def audit(session, context, row, action, before=None):
    record_audit_event(session, organization_id=context.organization_id, facility_id=context.facility_id,
                       entity_type="work_template" if isinstance(row, WorkTemplate) else "work_item",
                       entity_id=row.id, action=action, actor=context.user_id, source="api",
                       correlation_id=row.id, before=before, after=snapshot(row))


def occurrence(starts_at, frequency, index):
    """UTC anchor; month-end clamping never drifts subsequent months."""
    anchor = utc(starts_at)
    if frequency == "monthly":
        month = anchor.year * 12 + anchor.month - 1 + index
        year, month0 = divmod(month, 12)
        return anchor.replace(year=year, month=month0 + 1,
                              day=min(anchor.day, calendar.monthrange(year, month0 + 1)[1]))
    return anchor + timedelta(days=index * (7 if frequency == "weekly" else 1))


class WorkService:
    def __init__(self, engine, context):
        self.engine, self.context = engine, context

    def assignees(self):
        with Session(self.engine) as session:
            rows = session.scalars(assignee_query(self.context).order_by(AppUser.display_name, AppUser.id).limit(501)).all()
            return {"items": [{"id": row.id, "name": row.display_name or row.username} for row in rows[:500]],
                    "has_more": len(rows) > 500}

    def list(self, *, view="all", status=None, priority=None, assignee_id=None, workspace=None,
             entity_type=None, entity_id=None, offset=0, limit=50):
        context = self.context
        query = select(WorkItem).where(*scope(WorkItem, context))
        now = utc_now()
        for column, value in ((WorkItem.status, status), (WorkItem.priority, priority),
                              (WorkItem.assignee_id, assignee_id), (WorkItem.workspace, workspace),
                              (WorkItem.entity_type, entity_type), (WorkItem.entity_id, entity_id)):
            if value is not None:
                query = query.where(column == value)
        if view in {"mine", "attention"}:
            query = query.where(WorkItem.assignee_id == context.user_id)
        if view != "all":
            query = query.where(WorkItem.status != "completed")
        if view == "overdue":
            query = query.where(WorkItem.due_at < now)
        if view == "due":
            query = query.where(WorkItem.due_at >= now, WorkItem.due_at <= now + timedelta(hours=24))
        if view == "attention":
            query = query.where(or_(WorkItem.due_at < now, WorkItem.priority.in_(["high", "critical"])))
        rank = case((WorkItem.priority == "critical", 0), (WorkItem.priority == "high", 1),
                    (WorkItem.priority == "medium", 2), else_=3)
        query = query.order_by(rank, WorkItem.due_at.asc().nulls_last(), WorkItem.id).offset(offset).limit(limit + 1)
        with Session(self.engine) as session:
            # Long notes, descriptions and evidence hydrate only in the detail endpoint.
            from sqlalchemy.orm import load_only
            columns = [getattr(WorkItem, c.name) for c in WorkItem.__table__.columns
                       if c.name not in {"notes", "evidence", "description"}]
            rows = session.scalars(query.options(load_only(*columns))).all()
            return {"items": [{c.key: (utc(v).isoformat() if isinstance(v := getattr(row, c.key), datetime) else v)
                               for c in columns} for row in rows[:limit]], "has_more": len(rows) > limit}

    def get(self, work_id):
        with Session(self.engine) as session:
            return snapshot(self._get(session, WorkItem, work_id))

    def _get(self, session, model, row_id):
        row = session.scalar(select(model).where(*scope(model, self.context), model.id == row_id).with_for_update())
        if row is None:
            raise HTTPException(404, "Work was not found in this facility.")
        return row

    def create(self, payload, template=False):
        require_write(self.context)
        values = payload.model_dump()
        if template:
            for key in ("due_at", "notes", "evidence"):
                values.pop(key)
        with Session(self.engine) as session, session.begin():
            validate_assignee(session, self.context, values.get("assignee_id"))
            row = (WorkTemplate if template else WorkItem)(**values, id=new_id(),
                    organization_id=self.context.organization_id, facility_id=self.context.facility_id,
                    created_by=self.context.user_id)
            session.add(row)
            session.flush()
            audit(session, self.context, row, "created")
            return snapshot(row)

    def update(self, work_id, payload, template=False):
        require_write(self.context)
        with Session(self.engine) as session, session.begin():
            row = self._get(session, WorkTemplate if template else WorkItem, work_id)
            before = snapshot(row)
            if row.version != payload.version:
                raise HTTPException(409, "Work changed. Refresh before saving.")
            changes = payload.model_dump(exclude_unset=True, exclude={"version"})
            if "assignee_id" in changes:
                validate_assignee(session, self.context, changes["assignee_id"])
            if not template:
                target = changes.get("status", row.status)
                if target == "blocked" and not changes.get("blocked_reason", row.blocked_reason):
                    raise HTTPException(422, "A blocked reason is required.")
                if target != "blocked":
                    changes["blocked_reason"] = ""
                if target == "completed" and row.status != "completed":
                    changes.update(completed_by=self.context.user_id, completed_at=utc_now())
                elif target != "completed":
                    changes.update(completed_by=None, completed_at=None)
            self._save(session, row, changes)
            audit(session, self.context, row, "updated", before)
            return snapshot(row)

    def _save(self, session, row, changes):
        model = type(row)
        result = session.execute(update(model).where(*scope(model, self.context), model.id == row.id,
                         model.version == row.version).values(**changes, version=row.version + 1, updated_at=utc_now())
                         .execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise HTTPException(409, "Work changed. Refresh before saving.")
        session.refresh(row)

    def templates(self, offset=0):
        with Session(self.engine) as session:
            rows = session.scalars(select(WorkTemplate).where(*scope(WorkTemplate, self.context))
                                   .order_by(WorkTemplate.id).offset(offset).limit(51)).all()
            return {"items": [snapshot(row) for row in rows[:50]], "has_more": len(rows) > 50}

    def generate(self, now=None):
        """Bounded catch-up, safely repeatable after a lost response or interruption."""
        require_write(self.context)
        now = utc(now or utc_now())
        generated = 0
        with Session(self.engine) as session, session.begin():
            templates = session.scalars(select(WorkTemplate).where(*scope(WorkTemplate, self.context),
                WorkTemplate.active.is_(True)).order_by(WorkTemplate.updated_at, WorkTemplate.id)
                .limit(100).with_for_update()).all()
            for template in templates:
                before = snapshot(template)
                index = template.next_occurrence
                due = occurrence(template.starts_at, template.frequency, index)
                while due <= now and (not template.ends_at or due <= utc(template.ends_at)) and generated < 100:
                    try:
                        validate_assignee(session, self.context, template.assignee_id)
                    except HTTPException as exc:
                        raise HTTPException(422, f"Template '{template.title}' has an unavailable assignee. Update its future assignee or pause it, then generate again.") from exc
                    values = {key: getattr(template, key) for key in ("title", "description", "priority",
                              "assignee_id", "entity_type", "entity_id", "workspace", "route")}
                    row = WorkItem(**values, id=new_id(), organization_id=self.context.organization_id,
                        facility_id=self.context.facility_id, created_by=self.context.user_id,
                        due_at=due, template_id=template.id, occurrence_at=due)
                    session.add(row)
                    session.flush()
                    audit(session, self.context, row, "generated")
                    index += 1
                    generated += 1
                    due = occurrence(template.starts_at, template.frequency, index)
                # Touch considered templates so batches fairly rotate beyond the first 100.
                active = not template.ends_at or due <= utc(template.ends_at)
                self._save(session, template, {"next_occurrence": index, "active": active})
                audit(session, self.context, template, "generation_checked", before)
                if generated == 100:
                    break
        return {"generated": generated, "batch_limit": 100, "may_have_more": generated == 100 or len(templates) == 100}
