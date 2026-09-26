"""Authenticated physical dispatch API. No external-provider writes."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from modules.wholesale_logistics.schemas import AddStop, EditRun, Outcome, Reorder, RunInput, VersionInput
from modules.wholesale_logistics.service import LogisticsService
from ..auth import RequestContext, get_commercial_context
from ..database import get_engine
from ..permissions import require_permission


def access(request: Request, context: RequestContext = Depends(get_commercial_context), engine: Engine = Depends(get_engine)):
    require_permission(context, engine, "wholesale.view")
    if request.method != "GET":
        require_permission(context, engine, "wholesale.manage_dispatch")
    return LogisticsService(engine, context.organization_id, context.facility_id, context.user_id)


router = APIRouter(prefix="/wholesale-logistics", tags=["wholesale-logistics"])


def execute(call):
    try:
        return call()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (IntegrityError, StaleDataError) as exc:
        raise HTTPException(409, "Dispatch changed or shipment is already assigned. Refresh and retry.") from exc


@router.get("/runs")
def board(service_date: date, offset: int = Query(0, ge=0), service=Depends(access)):
    return service.board(service_date, offset)


@router.get("/shipments")
def candidates(offset: int = Query(0, ge=0), service=Depends(access)):
    return service.candidates(offset)


@router.post("/runs")
def create(payload: RunInput, service=Depends(access)):
    return execute(lambda: service.create(payload))


@router.get("/runs/{run_id}")
def detail(run_id: str, service=Depends(access)):
    return execute(lambda: service.detail(run_id))


@router.post("/runs/{run_id}")
def edit(run_id: str, payload: EditRun, service=Depends(access)):
    return execute(lambda: service.mutate(run_id, payload.version, "edit", payload.model_dump(exclude={"version"})))


@router.post("/runs/{run_id}/stops")
def add(run_id: str, payload: AddStop, service=Depends(access)):
    return execute(lambda: service.mutate(run_id, payload.version, "add", payload.model_dump(exclude={"version"})))


@router.post("/runs/{run_id}/reorder")
def reorder(run_id: str, payload: Reorder, service=Depends(access)):
    return execute(lambda: service.mutate(run_id, payload.version, "reorder", payload.stop_ids))


@router.post("/runs/{run_id}/plan")
def plan(run_id: str, payload: VersionInput, service=Depends(access)):
    return execute(lambda: service.mutate(run_id, payload.version, "plan"))


@router.post("/runs/{run_id}/stops/{stop_id}/status")
def outcome(run_id: str, stop_id: str, payload: Outcome, service=Depends(access)):
    return execute(lambda: service.mutate(run_id, payload.version, "status", payload.model_dump(exclude={"version"}), stop_id))


@router.post("/runs/{run_id}/stops/{stop_id}/remove")
def remove(run_id: str, stop_id: str, payload: VersionInput, service=Depends(access)):
    return execute(lambda: service.mutate(run_id, payload.version, "remove", stop_id=stop_id))


@router.post("/runs/{run_id}/stops/{stop_id}/create-reconciliation-work")
def create_reconciliation_work(run_id: str, stop_id: str, payload: VersionInput,
                               service=Depends(access), context: RequestContext = Depends(get_commercial_context),
                               engine: Engine = Depends(get_engine)):
    from ..services.work import WorkService
    return execute(lambda: service.create_reconciliation_work(run_id, stop_id, payload.version, WorkService(engine, context)))
