from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.operational_moats.webhook_delivery import WebhookDeliveryError, WebhookDeliveryService
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
legacy_router = APIRouter(prefix="/control-tower/enterprise", tags=["webhooks"])
ADMIN_ROLES = {"dev", "admin"}


class WebhookCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    target_url: str = Field(min_length=8, max_length=2048)
    event_types: list[str] = Field(min_length=1, max_length=100)
    facility_specific: bool = False


class WebhookStatusPayload(BaseModel):
    status: str


def _service(engine: Engine, settings: Settings) -> WebhookDeliveryService:
    try:
        return WebhookDeliveryService(engine, settings.integration_encryption_key)
    except WebhookDeliveryError as exc:
        raise HTTPException(503, str(exc)) from exc


def _admin(context: RequestContext) -> None:
    if context.role.casefold() not in ADMIN_ROLES:
        raise HTTPException(403, "Admin or DEV access is required for webhook administration.")


def _create_subscription(
    payload: WebhookCreatePayload,
    context: RequestContext,
    engine: Engine,
    settings: Settings,
    *,
    legacy: bool = False,
):
    _admin(context)
    try:
        row, secret = _service(engine, settings).create_subscription(
            organization_id=context.organization_id,
            facility_id=context.facility_id if payload.facility_specific else None,
            name=payload.name,
            target_url=payload.target_url,
            event_types=payload.event_types,
            actor=context.user_id,
        )
        result = {
            "id": row.id,
            "name": row.name,
            "target_url": row.target_url,
            "event_types": payload.event_types,
            "secret": secret,
            "warning": "The signing secret is shown once. Store it securely. DoobieLogic stores only an encrypted copy for delivery signing.",
        }
        if legacy:
            result["deprecated_route"] = "Use POST /api/v1/webhooks for new clients. This compatibility route now uses the same signed webhook service."
        return result
    except (ValueError, WebhookDeliveryError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
def list_webhooks(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _admin(context)
    return _service(engine, settings).list_subscriptions(context.organization_id, context.facility_id)


@router.post("", status_code=201)
def create_webhook(
    payload: WebhookCreatePayload,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    return _create_subscription(payload, context, engine, settings)


@legacy_router.post("/webhooks", status_code=201)
def create_webhook_legacy(
    payload: WebhookCreatePayload,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    return _create_subscription(payload, context, engine, settings, legacy=True)


@router.post("/{subscription_id}/rotate-secret")
def rotate_webhook_secret(
    subscription_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _admin(context)
    try:
        secret = _service(engine, settings).rotate_secret(
            organization_id=context.organization_id,
            subscription_id=subscription_id,
        )
        return {"id": subscription_id, "secret": secret, "warning": "The replacement signing secret is shown once."}
    except WebhookDeliveryError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{subscription_id}/status")
def set_webhook_status(
    subscription_id: str,
    payload: WebhookStatusPayload,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _admin(context)
    try:
        row = _service(engine, settings).set_status(
            organization_id=context.organization_id,
            subscription_id=subscription_id,
            status=payload.status,
        )
        return {"id": row.id, "status": row.status}
    except WebhookDeliveryError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/deliveries/{delivery_id}/send")
def send_delivery(
    delivery_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _admin(context)
    try:
        return _service(engine, settings).send_delivery(
            organization_id=context.organization_id,
            delivery_id=delivery_id,
        )
    except WebhookDeliveryError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/deliveries/send-batch")
def send_batch(
    limit: int = Query(default=20, ge=1, le=100),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _admin(context)
    return {
        "deliveries": _service(engine, settings).deliver_batch(
            organization_id=context.organization_id,
            limit=limit,
        )
    }
