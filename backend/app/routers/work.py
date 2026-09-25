from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine

from ..auth import RequestContext, get_request_context
from ..database import get_engine
from ..schemas.work import Priority, TemplateCreate, TemplateUpdate, WorkCreate, WorkStatus, WorkUpdate, WorkVersion
from ..services.work import WorkService

router = APIRouter(prefix="/work", tags=["work"])


def service(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return WorkService(engine, context)


@router.get("")
def list_work(view: Literal["all", "mine", "due", "overdue", "attention"] = "all",
              status: WorkStatus | None = None, priority: Priority | None = None,
              assignee_id: str | None = None, workspace: str | None = None,
              entity_type: str | None = None, entity_id: str | None = None,
              offset: int = Query(0, ge=0, le=100000), limit: int = Query(50, ge=1, le=100),
              work: WorkService = Depends(service)):
    return work.list(view=view, status=status, priority=priority, assignee_id=assignee_id,
                     workspace=workspace, entity_type=entity_type, entity_id=entity_id, offset=offset, limit=limit)


@router.post("", status_code=201)
def create(payload: WorkCreate, work: WorkService = Depends(service)):
    return work.create(payload)


@router.get("/assignees")
def assignees(work: WorkService = Depends(service)):
    return work.assignees()


@router.get("/templates")
def templates(offset: int = Query(0, ge=0, le=100000), work: WorkService = Depends(service)):
    return work.templates(offset)


@router.post("/templates", status_code=201)
def create_template(payload: TemplateCreate, work: WorkService = Depends(service)):
    return work.create(payload, template=True)


@router.post("/templates/generate")
def generate(work: WorkService = Depends(service)):
    return work.generate()


@router.patch("/templates/{template_id}")
def update_template(template_id: str, payload: TemplateUpdate, work: WorkService = Depends(service)):
    return work.update(template_id, payload, template=True)


@router.get("/{work_id}")
def detail(work_id: str, work: WorkService = Depends(service)):
    return work.get(work_id)


@router.patch("/{work_id}")
def update(work_id: str, payload: WorkUpdate, work: WorkService = Depends(service)):
    return work.update(work_id, payload)


@router.post("/{work_id}/complete")
def complete(work_id: str, payload: WorkVersion, work: WorkService = Depends(service)):
    return work.update(work_id, WorkUpdate(version=payload.version, status="completed"))


@router.post("/{work_id}/reopen")
def reopen(work_id: str, payload: WorkVersion, work: WorkService = Depends(service)):
    return work.update(work_id, WorkUpdate(version=payload.version, status="open"))
