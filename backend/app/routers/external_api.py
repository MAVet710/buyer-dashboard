"""Scoped service-account API for integrations and machine connectivity."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import CommercialOrder, CommercialOrderLine, Facility, Product
from modules.coman.repository import ComanRepository
from modules.operational_moats.external_api import ServiceAccountContext, authenticate_service_account
from modules.operational_moats.intelligence import profitability_360
from modules.operational_moats.service import OperationalMoatService

from ..database import get_engine

router = APIRouter(prefix="/external/v1", tags=["external-api"])


class TelemetryPayload(BaseModel):
    machine_id: str
    event_type: str
    metric_key: str = ""
    numeric_value: float | None = None
    unit: str = ""
    state: str = ""
    external_event_id: str = ""
    payload: dict[str, Any] = {}
    recorded_at: datetime | None = None


def _token(authorization: str) -> str:
    scheme, _, value = str(authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not value.strip():
        raise HTTPException(401, "Use Authorization: Bearer <DoobieLogic service token>.")
    return value.strip()


def _service_context(engine: Engine, authorization: str, scope: str) -> ServiceAccountContext:
    try:
        return authenticate_service_account(engine, _token(authorization), scope)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc


def _facility(engine: Engine, context: ServiceAccountContext, requested: str) -> str:
    facility_id = context.facility_id or str(requested or "").strip()
    if not facility_id:
        raise HTTPException(400, "X-Facility-Id is required for organization-wide service accounts.")
    with Session(engine) as session:
        facility = session.get(Facility, facility_id)
        if not facility or facility.organization_id != context.organization_id:
            raise HTTPException(403, "The requested facility is outside the service-account organization.")
    return facility_id


@router.get("/inventory")
def external_inventory(
    authorization: str = Header(default=""),
    x_facility_id: str = Header(default="", alias="X-Facility-Id"),
    engine: Engine = Depends(get_engine),
):
    context = _service_context(engine, authorization, "inventory:read")
    facility_id = _facility(engine, context, x_facility_id)
    repo = ComanRepository(engine)
    products = {row.id: row for row in repo.list_products(context.organization_id)}
    rows = []
    for lot in repo.list_inventory_lots(context.organization_id, facility_id):
        product = products.get(lot.product_id)
        rows.append(
            {
                "lot_id": lot.id,
                "lot_code": lot.lot_code,
                "product_id": lot.product_id,
                "sku": product.sku if product else "",
                "product_name": product.name if product else "",
                "status": lot.status,
                "location_code": lot.location_code,
                "compliance_package_id": lot.compliance_package_id,
                "quantity": repo.inventory_balance(context.organization_id, lot.id),
                "unit": product.base_unit if product else "",
            }
        )
    return {"facility_id": facility_id, "inventory": rows}


@router.get("/products")
def external_products(
    authorization: str = Header(default=""),
    engine: Engine = Depends(get_engine),
):
    context = _service_context(engine, authorization, "inventory:read")
    products = ComanRepository(engine).list_products(context.organization_id)
    return [
        {
            "id": row.id,
            "sku": row.sku,
            "name": row.name,
            "item_type": row.item_type,
            "base_unit": row.base_unit,
            "upc": row.upc,
            "external_product_id": row.external_product_id,
            "active": row.active,
        }
        for row in products
    ]


@router.get("/orders")
def external_orders(
    authorization: str = Header(default=""),
    x_facility_id: str = Header(default="", alias="X-Facility-Id"),
    limit: int = Query(default=250, ge=1, le=1000),
    engine: Engine = Depends(get_engine),
):
    context = _service_context(engine, authorization, "orders:read")
    facility_id = _facility(engine, context, x_facility_id)
    with Session(engine) as session:
        orders = list(
            session.scalars(
                select(CommercialOrder)
                .where(
                    CommercialOrder.organization_id == context.organization_id,
                    CommercialOrder.facility_id == facility_id,
                )
                .order_by(CommercialOrder.created_at.desc())
                .limit(limit)
            )
        )
        order_ids = tuple(row.id for row in orders)
        line_rows = list(
            session.scalars(
                select(CommercialOrderLine).where(
                    CommercialOrderLine.organization_id == context.organization_id,
                    CommercialOrderLine.commercial_order_id.in_(order_ids or ("",)),
                )
            )
        )
        product_ids = {line.product_id for line in line_rows}
        products = {row.id: row for row in session.scalars(select(Product).where(Product.organization_id == context.organization_id, Product.id.in_(tuple(product_ids) or ("",))))}
    by_order: dict[str, list[dict[str, Any]]] = {}
    for line in line_rows:
        product = products.get(line.product_id)
        by_order.setdefault(line.commercial_order_id, []).append(
            {
                "id": line.id,
                "product_id": line.product_id,
                "sku": product.sku if product else "",
                "product_name": product.name if product else line.description,
                "quantity": line.quantity,
                "fulfilled_quantity": line.fulfilled_quantity,
                "unit": line.unit,
                "unit_price": line.unit_price,
            }
        )
    return [
        {
            "id": row.id,
            "order_number": row.order_number,
            "order_type": row.order_type,
            "status": row.status,
            "partner_id": row.partner_id,
            "order_date": row.order_date,
            "due_date": row.due_date,
            "external_reference": row.external_reference,
            "lines": by_order.get(row.id, []),
        }
        for row in orders
    ]


@router.get("/profitability")
def external_profitability(
    authorization: str = Header(default=""),
    x_facility_id: str = Header(default="", alias="X-Facility-Id"),
    engine: Engine = Depends(get_engine),
):
    context = _service_context(engine, authorization, "finance:read")
    facility_id = _facility(engine, context, x_facility_id)
    return profitability_360(engine, context.organization_id, facility_id)


@router.post("/machine-telemetry")
def external_machine_telemetry(
    payload: TelemetryPayload,
    authorization: str = Header(default=""),
    x_facility_id: str = Header(default="", alias="X-Facility-Id"),
    engine: Engine = Depends(get_engine),
):
    context = _service_context(engine, authorization, "telemetry:write")
    facility_id = _facility(engine, context, x_facility_id)
    try:
        row = OperationalMoatService(engine).record_telemetry(
            organization_id=context.organization_id,
            facility_id=facility_id,
            machine_id=payload.machine_id,
            event_type=payload.event_type,
            actor=f"service-account:{context.id}",
            metric_key=payload.metric_key,
            numeric_value=payload.numeric_value,
            unit=payload.unit,
            state=payload.state,
            source=f"service-account:{context.name}",
            external_event_id=payload.external_event_id,
            payload=payload.payload,
            recorded_at=payload.recorded_at,
        )
        return {"id": row.id, "accepted": True, "recorded_at": row.recorded_at}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
