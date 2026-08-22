from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from modules.coman.models import Facility
from modules.coman.repository import ComanRepository
from modules.commercial.analytics import commercial_dashboard_metrics, fulfillment_by_order, order_value_by_id
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance.service import CommercialFinanceService
from ..auth import RequestContext, get_request_context, get_commercial_context
from ..database import get_engine

router = APIRouter(prefix="/commercial", tags=["commercial"], dependencies=[Depends(get_commercial_context)])

class OrderLineCreate(BaseModel):
    product_id: str; quantity: float; unit: str; unit_price: float = 0; description: str = ""; notes: str = ""
class OrderCreate(BaseModel):
    partner_id: str; order_number: str; order_type: str; order_date: date = Field(default_factory=date.today); due_date: date | None = None; lines: list[OrderLineCreate]; external_reference: str = ""; notes: str = ""
class InvoiceCreate(BaseModel):
    invoice_number: str; due_days: int = 30; discount_usd: float = 0; tax_usd: float = 0
class PaymentCreate(BaseModel):
    amount_usd: float; method: str = "other"; reference: str = ""; payment_date: date | None = None; notes: str = ""
class ShipmentCreate(BaseModel):
    shipment_number: str; manifest_reference: str = ""; carrier: str = ""; tracking_reference: str = ""
class ShipmentStatus(BaseModel): status: str
class PartnerCreate(BaseModel):
    name: str; partner_type: str; license_or_registration: str = ""; contact_name: str = ""; contact_email: str = ""; contact_phone: str = ""; payment_terms: str = "Net 30"
class AllocationCreate(BaseModel): lot_id: str; quantity: float
class FulfillmentCreate(BaseModel): lot_id: str; quantity: float; reference: str = ""
class PurchaseReceiptCreate(BaseModel):
    lot_code: str; quantity: float; package_id: str = ""; location_code: str = "RECEIVING"; reference: str = ""
class PaymentStatusUpdate(BaseModel): payment_status: str
class InventoryLotCreate(BaseModel):
    product_id: str; lot_code: str; location: str = "RECEIVING"; unit: str = "unit"
class CustomerPriceCreate(BaseModel):
    partner_id: str; product_id: str; price_usd: float = Field(default=0, ge=0); discount_pct: float = Field(default=0, ge=0, le=100); notes: str = ""

def _repo(engine: Engine) -> CommercialRepository:
    return CommercialRepository(engine)

@router.get("/workspace")
def workspace(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    commercial = _repo(engine)
    coman = ComanRepository(engine)
    partners = commercial.list_trade_partners(context.organization_id)
    orders = commercial.list_orders(context.organization_id, context.facility_id)
    order_ids = {row.id for row in orders}
    lines = [row for row in commercial.list_order_lines(context.organization_id) if row.commercial_order_id in order_ids]
    products = coman.list_products(context.organization_id)
    lots = coman.list_inventory_lots(context.organization_id, context.facility_id)
    transactions = commercial.list_commercial_transactions(context.organization_id, context.facility_id)
    partner_by_id = {row.id: row for row in partners}
    product_by_id = {row.id: row for row in products}
    order_by_id = {row.id: row for row in orders}
    line_by_id = {row.id: row for row in lines}
    lot_by_id = {row.id: row for row in lots}
    values = order_value_by_id(lines)
    fulfillment = fulfillment_by_order(lines)
    balances = {row.id: coman.inventory_balance(context.organization_id, row.id) for row in lots}
    inventory_value = sum(max(0.0, balances[row.id]) * float(getattr(product_by_id.get(row.product_id), "unit_cost", 0.0) or 0.0) for row in lots)
    inventory_exceptions = [row for row in lots if balances[row.id] <= 0 or row.status not in {"available", "released"}]
    metrics = commercial_dashboard_metrics(orders, lines, inventory_value=inventory_value)
    with Session(engine) as session:
        facility = session.get(Facility, context.facility_id)
    return {
        "facility_name": getattr(facility, "name", "Active facility"),
        "metrics": {**metrics, "tracked_lots": len(lots), "inventory_exceptions": len(inventory_exceptions)},
        "partners": [{key: getattr(row, key) for key in ("id", "name", "partner_type", "license_or_registration", "contact_name", "contact_email", "contact_phone", "payment_terms", "active")} for row in partners],
        "orders": [{
            **{key: getattr(row, key) for key in ("id", "partner_id", "order_number", "order_type", "order_date", "due_at", "status", "payment_status", "currency", "external_reference", "notes")},
            "partner_name": getattr(partner_by_id.get(row.partner_id), "name", "Unknown partner"),
            "order_total": values.get(str(row.id), 0.0),
            "requested_quantity": fulfillment.get(str(row.id), (0.0, 0.0))[0],
            "fulfilled_quantity": fulfillment.get(str(row.id), (0.0, 0.0))[1],
        } for row in orders],
        "lines": [{key: getattr(row, key) for key in ("id", "commercial_order_id", "product_id", "position", "description", "sku_snapshot", "quantity", "unit", "unit_price", "fulfilled_quantity", "notes")} for row in lines],
        "products": [{key: getattr(row, key) for key in ("id", "sku", "name", "item_type", "base_unit", "unit_cost")} for row in products],
        "lots": [{**{key: getattr(row, key) for key in ("id", "product_id", "lot_code", "compliance_package_id", "location_code", "status")}, "product_name": getattr(product_by_id.get(row.product_id), "name", "Unknown product"), "on_hand": balances[row.id]} for row in lots],
        "inventory_exceptions": [{"lot_code": row.lot_code, "product_name": getattr(product_by_id.get(row.product_id), "name", "Unknown product"), "on_hand": balances[row.id], "status": row.status} for row in inventory_exceptions],
        "transactions": [{
            "id": row.id, "occurred_at": row.occurred_at,
            "order": getattr(order_by_id.get(row.commercial_order_id), "order_number", row.reference),
            "type": row.transaction_type.title(),
            "product_name": getattr(product_by_id.get(getattr(line_by_id.get(row.commercial_order_line_id), "product_id", "")), "name", "Unknown"),
            "lot": getattr(lot_by_id.get(row.lot_id), "lot_code", row.lot_id),
            "quantity": row.quantity_delta, "unit": row.unit, "reference": row.reference, "actor": row.actor,
        } for row in transactions],
    }

@router.get("/partners")
def partners(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return [{key: getattr(row, key) for key in ("id", "name", "partner_type", "license_or_registration", "contact_name", "contact_email", "contact_phone", "payment_terms", "active")} for row in _repo(engine).list_trade_partners(context.organization_id, active_only=False)]

@router.post("/partners", status_code=201)
def create_partner(payload: PartnerCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if context.role.casefold() not in {"dev", "admin", "supervisor", "buyer"}: raise HTTPException(403, "Your role does not allow partner creation.")
    try:
        row = _repo(engine).create_trade_partner(context.organization_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(row, key) for key in ("id", "name", "partner_type", "license_or_registration", "contact_name", "contact_email", "contact_phone", "payment_terms", "active")}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.get("/orders")
def orders(open_only: bool = False, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    repo = _repo(engine)
    partner_names = {row.id: row.name for row in repo.list_trade_partners(context.organization_id, active_only=False)}
    result = []
    for order in repo.list_orders(context.organization_id, context.facility_id, open_only=open_only):
        lines = repo.list_order_lines(context.organization_id, order_id=order.id)
        result.append({
            **{key: getattr(order, key) for key in ("id", "order_number", "order_type", "order_date", "due_at", "status", "payment_status", "currency", "external_reference", "notes")},
            "partner_name": partner_names.get(order.partner_id, "Unknown partner"),
            "line_count": len(lines),
            "order_total": sum(float(row.quantity) * float(row.unit_price) for row in lines),
            "fulfilled_quantity": sum(float(row.fulfilled_quantity) for row in lines),
        })
    return result

@router.post("/orders", status_code=201)
def create_order(payload: OrderCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).create_order(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, **payload.model_dump())
        return {"id": row.id, "order_number": row.order_number, "status": row.status}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.get("/orders/{order_id}")
def order_detail(order_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    repo = _repo(engine)
    order = next((row for row in repo.list_orders(context.organization_id, context.facility_id) if row.id == order_id), None)
    if not order:
        raise HTTPException(404, "Commercial order was not found in the active facility.")
    lines = repo.list_order_lines(context.organization_id, order_id=order.id)
    allocations = repo.list_allocations(context.organization_id, context.facility_id, order_id=order.id)
    finance = CommercialFinanceService(engine).order_finance(context.organization_id, context.facility_id, order.id)
    return {"order": {key: getattr(order, key) for key in ("id", "partner_id", "order_number", "order_type", "order_date", "due_at", "status", "payment_status", "currency", "external_reference", "notes")}, "lines": [{key: getattr(row, key) for key in ("id", "commercial_order_id", "product_id", "position", "description", "sku_snapshot", "quantity", "unit", "unit_price", "fulfilled_quantity", "notes")} for row in lines], "allocations": [{key: getattr(row, key) for key in ("id", "commercial_order_line_id", "lot_id", "quantity", "fulfilled_quantity", "status")} for row in allocations], "invoices": [{key: getattr(row, key) for key in ("id", "invoice_number", "status", "issue_date", "due_date", "total_usd", "balance_usd")} for row in finance["invoices"]], "shipments": [{key: getattr(row, key) for key in ("id", "shipment_number", "status", "manifest_reference", "carrier", "tracking_reference", "shipped_at", "delivered_at")} for row in finance["shipments"]]}

@router.post("/orders/{order_id}/actions/{action}")
def order_action(order_id: str, action: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    repo = _repo(engine)
    try:
        if action == "confirm": row = repo.confirm_order(order_id, organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id)
        elif action == "cancel": row = repo.cancel_order(order_id, organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id)
        else: raise HTTPException(404, "Unsupported order action.")
        return {"id": row.id, "status": row.status}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@router.post("/orders/{order_id}/payment")
def update_payment_status(order_id: str, payload: PaymentStatusUpdate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).set_payment_status(order_id, organization_id=context.organization_id, facility_id=context.facility_id, payment_status=payload.payment_status, actor=context.user_id)
        return {"id": row.id, "payment_status": row.payment_status}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@router.post("/inventory-lots", status_code=201)
def create_receiving_lot(payload: InventoryLotCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = ComanRepository(engine).create_inventory_lot(context.organization_id, context.facility_id, product_id=payload.product_id, lot_code=payload.lot_code, actor=context.user_id, opening_quantity=0, location_code=payload.location, unit=payload.unit)
        return {"id": row.id, "product_id": row.product_id, "lot_code": row.lot_code, "location_code": row.location_code, "status": row.status}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@router.post("/order-lines/{line_id}/allocations", status_code=201)
def allocate_order_line(line_id: str, payload: AllocationCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).allocate_lot(organization_id=context.organization_id, facility_id=context.facility_id, order_line_id=line_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(row, key) for key in ("id", "commercial_order_line_id", "lot_id", "quantity", "fulfilled_quantity", "status")}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/order-lines/{line_id}/fulfill", status_code=201)
def fulfill_order_line(line_id: str, payload: FulfillmentCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).post_fulfillment(organization_id=context.organization_id, facility_id=context.facility_id, order_line_id=line_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(row, key) for key in ("id", "lot_id", "quantity_delta", "unit", "transaction_type", "reference", "occurred_at")}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/order-lines/{line_id}/receive", status_code=201)
def receive_purchase_line(line_id: str, payload: PurchaseReceiptCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).receive_purchase_line(organization_id=context.organization_id, facility_id=context.facility_id, order_line_id=line_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(row, key) for key in ("id", "lot_id", "quantity_delta", "unit", "transaction_type", "reference", "occurred_at")}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.get("/ar")
def ar_summary(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return CommercialFinanceService(engine).ar_summary(context.organization_id, context.facility_id)

@router.post("/customer-prices", status_code=201)
def save_customer_price(payload: CustomerPriceCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = CommercialFinanceService(engine).upsert_customer_price(organization_id=context.organization_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(row, key) for key in ("id", "partner_id", "product_id", "price_usd", "discount_pct", "active")}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@router.post("/orders/{order_id}/invoices", status_code=201)
def create_invoice(order_id: str, payload: InvoiceCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = CommercialFinanceService(engine).create_invoice_from_order(organization_id=context.organization_id, facility_id=context.facility_id, order_id=order_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(row, key) for key in ("id", "invoice_number", "status", "total_usd", "balance_usd", "due_date")}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/invoices/{invoice_id}/send")
def send_invoice(invoice_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = CommercialFinanceService(engine).send_invoice(organization_id=context.organization_id, facility_id=context.facility_id, invoice_id=invoice_id); return {"id": row.id, "status": row.status}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/invoices/{invoice_id}/payments", status_code=201)
def record_payment(invoice_id: str, payload: PaymentCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = CommercialFinanceService(engine).record_payment(organization_id=context.organization_id, facility_id=context.facility_id, invoice_id=invoice_id, actor=context.user_id, **payload.model_dump()); return {key: getattr(row, key) for key in ("id", "amount_usd", "payment_date", "method", "reference", "recorded_at")}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/orders/{order_id}/shipments", status_code=201)
def create_shipment(order_id: str, payload: ShipmentCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = CommercialFinanceService(engine).create_shipment(organization_id=context.organization_id, facility_id=context.facility_id, order_id=order_id, actor=context.user_id, **payload.model_dump()); return {key: getattr(row, key) for key in ("id", "shipment_number", "status", "manifest_reference", "carrier", "tracking_reference")}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/shipments/{shipment_id}/status")
def shipment_status(shipment_id: str, payload: ShipmentStatus, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = CommercialFinanceService(engine).update_shipment_status(organization_id=context.organization_id, facility_id=context.facility_id, shipment_id=shipment_id, status=payload.status); return {"id": row.id, "status": row.status, "shipped_at": row.shipped_at, "delivered_at": row.delivered_at}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
