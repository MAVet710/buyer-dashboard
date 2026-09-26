"""Explicit canonical Work action for duration-qualified imported evidence."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine

from modules.cultivation.edge_work import EdgeWorkService
from modules.cultivation.edge_store import EdgeError
from modules.cultivation.gateway import WindowInput
from modules.cultivation.telemetry import TelemetryConflict
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix='/cultivation-intelligence', tags=['cultivation'])


def call(engine, context, method, *args):
    try:
        return getattr(EdgeWorkService(engine, context), method)(*args)
    except TelemetryConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except EdgeError:
        raise HTTPException(503, 'Local evidence is unavailable. Retry after host storage is ready.', headers={'Retry-After': '5'}) from None
    except LookupError as exc:
        raise HTTPException(404, 'Room not found in the active facility.') from exc
    except ValueError as exc:
        raise HTTPException(422, 'Invalid UTC evidence window or local evidence limits.') from exc


@router.get('/rooms/{room_id}/deviations')
def deviations(room_id: str, window: Annotated[WindowInput, Query()],
    context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return call(engine, context, 'deviations', room_id, window)


@router.post('/rooms/{room_id}/deviations/{exception_id}/work')
def create_work(room_id: str, exception_id: str, payload: WindowInput,
    context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return call(engine, context, 'create_work', room_id, exception_id, payload)
