from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import CommercialOrder, CommercialOrderLine, InventoryLot, InventoryTransaction, Product
from modules.commercial.repository import CommercialRepository
from ..auth import RequestContext, get_commercial_context, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/warehouse", tags=["warehouse"], dependencies=[Depends(get_commercial_context)])


class PickAction(BaseModel):
    order_line_id: str
    lot_id: str
    quantity: float = Field(gt=0)
    scan_code: str = Field(min_length=1, max_length=512)
    action: str = "reserve"
    reference: str = ""


def _available_lots(session: Session, context: RequestContext, product_id: str) -> list[dict]:
    rows = list(session.execute(
        select(
            InventoryLot,
            func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0).label("balance"),
        )
        .outerjoin(InventoryTransaction, InventoryTransaction.lot_id == InventoryLot.id)
        .where(
            InventoryLot.organization_id == context.organization_id,
            InventoryLot.facility_id == context.facility_id,
            InventoryLot.product_id == product_id,
            InventoryLot.status.in_(["available", "released"]),
        )
        .group_by(InventoryLot.id)
    ))
    available = []
    for lot, balance in rows:
        quantity = float(balance or 0)
        if quantity <= 0:
            continue
        available.append({
            "id": lot.id,
            "lot_code": lot.lot_code,
            "package_id": lot.compliance_package_id,
            "barcode": lot.barcode_value,
            "location": lot.location_code,
            "status": lot.status,
            "on_hand": quantity,
            "received_at": lot.received_at,
            "expiration_at": lot.expiration_at,
        })
    # FEFO first. Non-expiring inventory falls back to oldest received lot.
    max_dt = datetime.max.replace(tzinfo=None)
    def key(row: dict):
        expiry = row["expiration_at"]
        received = row["received_at"]
        expiry_key = expiry.replace(tzinfo=None) if expiry else max_dt
        received_key = received.replace(tzinfo=None) if received else max_dt
        return (expiry_key, received_key, row["lot_code"])
    return sorted(available, key=key)


@router.get("/pick-queue")
def pick_queue(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    repo = CommercialRepository(engine)
    orders = [row for row in repo.list_orders(context.organization_id, context.facility_id, open_only=True) if row.order_type == "sales"]
    order_ids = {row.id for row in orders}
    lines = [row for row in repo.list_order_lines(context.organization_id) if row.commercial_order_id in order_ids and float(row.fulfilled_quantity) + 1e-9 < float(row.quantity)]
    order_by_id = {row.id: row for row in orders}
    with Session(engine) as session:
        products = {row.id: row for row in session.scalars(select(Product).where(Product.organization_id == context.organization_id))}
        queue = []
        for line in sorted(lines, key=lambda row: (order_by_id[row.commercial_order_id].due_at or datetime.max, order_by_id[row.commercial_order_id].order_number, row.position)):
            order = order_by_id[line.commercial_order_id]
            lots = _available_lots(session, context, line.product_id)
            queue.append({
                "order_id": order.id,
                "order_number": order.order_number,
                "due_at": order.due_at,
                "order_status": order.status,
                "line_id": line.id,
                "position": line.position,
                "product_id": line.product_id,
                "product_name": getattr(products.get(line.product_id), "name", line.description),
                "sku": getattr(products.get(line.product_id), "sku", line.sku_snapshot),
                "unit": line.unit,
                "ordered": float(line.quantity),
                "fulfilled": float(line.fulfilled_quantity),
                "remaining": max(0.0, float(line.quantity) - float(line.fulfilled_quantity)),
                "recommended_lot": lots[0] if lots else None,
                "available_lots": lots,
            })
    return {"facility_id": context.facility_id, "open_sales_orders": len(orders), "lines_to_pick": len(queue), "queue": queue}


@router.post("/pick")
def pick_action(payload: PickAction, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    action = payload.action.strip().casefold()
    if action not in {"reserve", "ship"}:
        raise HTTPException(422, "Warehouse action must be reserve or ship.")
    repo = CommercialRepository(engine)
    order_line = next((row for row in repo.list_order_lines(context.organization_id) if row.id == payload.order_line_id), None)
    if not order_line:
        raise HTTPException(404, "Order line was not found in this organization.")
    order = next((row for row in repo.list_orders(context.organization_id, context.facility_id) if row.id == order_line.commercial_order_id), None)
    if not order or order.order_type != "sales":
        raise HTTPException(404, "Sales order was not found in the active facility.")
    with Session(engine) as session:
        lot = session.get(InventoryLot, payload.lot_id)
        if not lot or lot.organization_id != context.organization_id or lot.facility_id != context.facility_id:
            raise HTTPException(404, "Inventory lot was not found in the active facility.")
        if lot.product_id != order_line.product_id:
            raise HTTPException(422, "Scanned lot does not match the order-line product.")
        normalized = payload.scan_code.strip().casefold()
        valid_codes = {str(value or "").strip().casefold() for value in (lot.id, lot.lot_code, lot.compliance_package_id, lot.barcode_value) if str(value or "").strip()}
        if normalized not in valid_codes:
            raise HTTPException(422, "Scanned code does not match the selected lot. Nothing was posted.")
    try:
        if action == "reserve":
            row = repo.allocate_lot(
                organization_id=context.organization_id,
                facility_id=context.facility_id,
                order_line_id=payload.order_line_id,
                lot_id=payload.lot_id,
                quantity=payload.quantity,
                actor=context.user_id,
            )
            return {"action": "reserved", "allocation_id": row.id, "status": row.status, "quantity": row.quantity}
        row = repo.post_fulfillment(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            order_line_id=payload.order_line_id,
            lot_id=payload.lot_id,
            quantity=payload.quantity,
            reference=payload.reference or order.order_number,
            actor=context.user_id,
        )
        return {"action": "shipped", "transaction_id": row.id, "quantity_delta": row.quantity_delta, "unit": row.unit, "occurred_at": row.occurred_at}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
