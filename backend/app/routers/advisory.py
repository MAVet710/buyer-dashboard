from __future__ import annotations

from collections import deque
import hashlib
from ipaddress import ip_address, ip_network
import threading
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.routing import APIRoute
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from modules.advisory.schemas import EventInput, LeadInput, LeadStatus, LeadUpdate, ScoreInput
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from ..services import advisory

MAX_BODY_BYTES = 32_768


def rate_limit_peer(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else 'unknown'
    try:
        address = ip_address(peer)
    except ValueError:
        return peer
    networks = []
    for raw in settings.doobielogic_advisory_trusted_proxy_cidrs.split(','):
        if not raw.strip():
            continue
        try:
            networks.append(ip_network(raw.strip(), strict=False))
        except ValueError:
            # Invalid configuration never grants proxy trust.
            continue
    if not any(address in network for network in networks):
        return str(address)
    forwarded = request.headers.get('x-advisory-client-ip', '').strip()
    if not forwarded or '%' in forwarded:
        return str(address)
    try:
        return str(ip_address(forwarded))
    except ValueError:
        return str(address)


class IntakeLimiter:
    """Bounded process-local abuse guard; not a distributed edge limiter."""
    def __init__(self, max_keys=4096):
        self.max_keys = max_keys
        self.buckets = {}
        self.lock = threading.Lock()

    def check(self, peer: str, bucket: str, *, now=None):
        current = time.monotonic() if now is None else now
        window, maximum = (900, 5) if bucket == 'leads' else (60, 120)
        key = (hashlib.sha256(peer.encode()).hexdigest(), bucket)
        with self.lock:
            expired = [key for key, (_, expiry) in self.buckets.items() if expiry <= current]
            for old in expired:
                del self.buckets[old]
            if key not in self.buckets:
                if len(self.buckets) >= self.max_keys:
                    raise HTTPException(429, 'Please try again shortly.', headers={'Retry-After': '60'})
                self.buckets[key] = (deque(), current + window)
            timestamps, _ = self.buckets[key]
            while timestamps and timestamps[0] <= current - window:
                timestamps.popleft()
            if len(timestamps) >= maximum:
                retry = max(1, int(window - (current - timestamps[0])) + 1)
                raise HTTPException(429, 'Too many requests. Please try again shortly.', headers={'Retry-After': str(retry)})
            timestamps.append(current)
            self.buckets[key] = (timestamps, current + window)


limiter = IntakeLimiter()


class AdvisoryRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def guarded(request: Request):
            # Runs before FastAPI JSON/Pydantic parsing and dependency resolution.
            if request.method in {'POST', 'PATCH'}:
                origin = request.headers.get('origin')
                settings = get_settings()
                allowed = {'https://doobielogic.io', 'https://www.doobielogic.io', 'https://ops.doobielogic.io'}
                if settings.is_development:
                    allowed.update(settings.allowed_origins)
                if origin and origin not in allowed:
                    raise HTTPException(403, 'This request origin is not allowed.')
                if '/admin/' not in request.url.path:
                    peer = rate_limit_peer(request, settings)
                    limiter.check(peer, request.url.path.rstrip('/').split('/')[-1])
                length = request.headers.get('content-length')
                if length:
                    try:
                        if int(length) > MAX_BODY_BYTES or int(length) < 0:
                            raise HTTPException(413, 'Request body is too large.')
                    except ValueError:
                        raise HTTPException(400, 'Invalid content length.') from None
                chunks = []
                total = 0
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > MAX_BODY_BYTES:
                        raise HTTPException(413, 'Request body is too large.')
                    chunks.append(chunk)
                request._body = b''.join(chunks)
            try:
                return await handler(request)
            except SQLAlchemyError:
                # Never echo SQL parameters/contact data or claim acceptance on a failed write.
                raise HTTPException(503, 'Advisory storage is temporarily unavailable. Please retry.') from None
        return guarded


router = APIRouter(prefix='/advisory', tags=['advisory'], route_class=AdvisoryRoute)


def advisory_admin(context: RequestContext = Depends(get_request_context)) -> RequestContext:
    if context.role.casefold() != 'dev':
        raise HTTPException(403, 'Platform DEV access is required for advisory leads.')
    return context


@router.post('/leads', status_code=202)
def create_lead(payload: LeadInput, engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    return advisory.capture_lead(engine, settings, payload)


@router.post('/score')
def evaluate_score(payload: ScoreInput):
    return advisory.calculate_score(payload.tool_inputs)


@router.post('/events', status_code=202)
def record_event(payload: EventInput, engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    return advisory.capture_event(engine, settings, payload)


@router.get('/booking')
def booking(settings: Settings = Depends(get_settings)):
    return advisory.booking_config(settings)


@router.get('/admin/leads')
def admin_leads(status: LeadStatus | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=100000),
                context: RequestContext = Depends(advisory_admin), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    return advisory.list_leads(engine, settings, status=status, limit=limit, offset=offset)


@router.get('/admin/leads/{lead_id}')
def admin_lead(lead_id: UUID, context: RequestContext = Depends(advisory_admin), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    return advisory.lead_detail(engine, settings, str(lead_id))


@router.patch('/admin/leads/{lead_id}')
def admin_update(lead_id: UUID, payload: LeadUpdate, context: RequestContext = Depends(advisory_admin), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    return advisory.update_lead(engine, settings, str(lead_id), payload, context.user_id)


@router.get('/admin/metrics')
def admin_metrics(days: int = Query(30, ge=1, le=366), context: RequestContext = Depends(advisory_admin), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    return advisory.metrics(engine, settings, days=days)
