from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session
from modules.coman.models import CommercialOrder, CommercialOrderLine, DataHubImport, InventoryLot, InventoryTransaction, Product, ProductionOrder, RetailSale, TradePartner, utc_now
from modules.cultivation.models import CultivationPlant
from modules.integrations.models import IntegrationConfiguration
from modules.product_master import ProductMasterRepository
from modules.product_master.models import ProductMasterProfile
from modules.traceability.models import TraceabilityTransaction
from ..auth import RequestContext, get_request_context
from ..database import get_engine
router = APIRouter(prefix="/home", tags=["home"])

@router.get("/summary")
def summary(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    with Session(engine) as session:
        lot_ids = select(InventoryLot.id).where(InventoryLot.organization_id == context.organization_id, InventoryLot.facility_id == context.facility_id)
        return {"inventory_quantity": float(session.scalar(select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(InventoryTransaction.lot_id.in_(lot_ids))) or 0), "package_count": int(session.scalar(select(func.count()).select_from(InventoryLot).where(InventoryLot.organization_id == context.organization_id, InventoryLot.facility_id == context.facility_id)) or 0), "plant_count": int(session.scalar(select(func.count()).select_from(CultivationPlant).where(CultivationPlant.organization_id == context.organization_id, CultivationPlant.facility_id == context.facility_id, CultivationPlant.phase.not_in(("harvested", "destroyed")))) or 0), "open_production": int(session.scalar(select(func.count()).select_from(ProductionOrder).where(ProductionOrder.organization_id == context.organization_id, ProductionOrder.facility_id == context.facility_id, ProductionOrder.status.not_in(("complete", "cancelled")))) or 0), "open_orders": int(session.scalar(select(func.count()).select_from(CommercialOrder).where(CommercialOrder.organization_id == context.organization_id, CommercialOrder.facility_id == context.facility_id, CommercialOrder.status.not_in(("fulfilled", "cancelled")))) or 0), "compliance_exceptions": int(session.scalar(select(func.count()).select_from(TraceabilityTransaction).where(TraceabilityTransaction.organization_id == context.organization_id, TraceabilityTransaction.facility_id == context.facility_id, TraceabilityTransaction.status.in_(("rejected", "reconciliation_required")))) or 0), "active_data_sources": int(session.scalar(select(func.count()).select_from(DataHubImport).where(DataHubImport.organization_id == context.organization_id, DataHubImport.facility_id == context.facility_id, DataHubImport.status == "active")) or 0)}

@router.get("/search")
def universal_search(q: str = Query(min_length=2, max_length=120), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    term = f"%{q.strip()}%"; results = []
    with Session(engine) as session:
        for row in session.scalars(select(Product).where(Product.organization_id == context.organization_id, Product.active.is_(True), or_(Product.name.ilike(term), Product.sku.ilike(term))).limit(10)): results.append({"kind": "product", "id": row.id, "title": row.name, "subtitle": row.sku, "workspace": "Inventory"})
        for row in session.scalars(select(InventoryLot).where(InventoryLot.organization_id == context.organization_id, InventoryLot.facility_id == context.facility_id, or_(InventoryLot.lot_code.ilike(term), InventoryLot.compliance_package_id.ilike(term))).limit(10)): results.append({"kind": "package", "id": row.id, "title": row.compliance_package_id or row.lot_code, "subtitle": row.location_code, "workspace": "Inventory"})
        for row in session.scalars(select(CultivationPlant).where(CultivationPlant.organization_id == context.organization_id, CultivationPlant.facility_id == context.facility_id, or_(CultivationPlant.plant_tag.ilike(term), CultivationPlant.strain_name.ilike(term))).limit(10)): results.append({"kind": "plant", "id": row.id, "title": row.plant_tag, "subtitle": f"{row.strain_name} · {row.phase}", "workspace": "Inventory"})
        for row in session.scalars(select(ProductionOrder).where(ProductionOrder.organization_id == context.organization_id, ProductionOrder.facility_id == context.facility_id, or_(ProductionOrder.order_number.ilike(term), ProductionOrder.product_name.ilike(term))).limit(10)): results.append({"kind": "production order", "id": row.id, "title": row.order_number, "subtitle": row.product_name, "workspace": "Production"})
        for row in session.scalars(select(CommercialOrder).where(CommercialOrder.organization_id == context.organization_id, CommercialOrder.facility_id == context.facility_id, CommercialOrder.order_number.ilike(term)).limit(10)): results.append({"kind": "commercial order", "id": row.id, "title": row.order_number, "subtitle": row.status, "workspace": "Orders"})
        for row in session.scalars(select(TradePartner).where(TradePartner.organization_id == context.organization_id, TradePartner.name.ilike(term)).limit(10)): results.append({"kind": "partner", "id": row.id, "title": row.name, "subtitle": row.partner_type, "workspace": "Orders"})
    return results[:30]


@router.get("/inbox")
def operations_inbox(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    now = utc_now(); items = []
    with Session(engine) as session:
        held = list(session.execute(select(InventoryLot, Product).join(Product, Product.id == InventoryLot.product_id).where(InventoryLot.organization_id == context.organization_id, InventoryLot.facility_id == context.facility_id, func.lower(InventoryLot.status).in_(["hold", "quarantine", "failed"])).limit(20)))
        for lot, product in held: items.append({"id": f"hold:{lot.id}", "severity": "high", "area": "Inventory", "title": f"{product.name} is on {lot.status}", "detail": lot.compliance_package_id or lot.lot_code, "workspace": "Inventory", "entity_id": lot.id})
        failures = list(session.scalars(select(TraceabilityTransaction).where(TraceabilityTransaction.organization_id == context.organization_id, TraceabilityTransaction.facility_id == context.facility_id, TraceabilityTransaction.status.in_(["rejected", "reconciliation_required"])).order_by(TraceabilityTransaction.requested_at.desc()).limit(20)))
        for row in failures: items.append({"id": f"traceability:{row.id}", "severity": "critical" if row.status == "rejected" else "high", "area": "Compliance", "title": f"{row.operation_type.replace('_', ' ').title()} needs attention", "detail": row.error_message or row.reason or row.status.replace("_", " "), "workspace": "Compliance", "entity_id": row.id})
        overdue_production = list(session.scalars(select(ProductionOrder).where(ProductionOrder.organization_id == context.organization_id, ProductionOrder.facility_id == context.facility_id, ProductionOrder.due_at.is_not(None), ProductionOrder.due_at < now, ProductionOrder.status.not_in(["complete", "cancelled"])).limit(20)))
        for row in overdue_production: items.append({"id": f"production:{row.id}", "severity": "high", "area": "Production", "title": f"{row.order_number} is overdue", "detail": f"{row.product_name} · {row.status}", "workspace": "Production", "entity_id": row.id})
        overdue_orders = list(session.scalars(select(CommercialOrder).where(CommercialOrder.organization_id == context.organization_id, CommercialOrder.facility_id == context.facility_id, CommercialOrder.due_at.is_not(None), CommercialOrder.due_at < now, CommercialOrder.status.not_in(["fulfilled", "cancelled"])).limit(20)))
        for row in overdue_orders: items.append({"id": f"order:{row.id}", "severity": "medium", "area": "Orders", "title": f"{row.order_number} is overdue", "detail": f"{row.order_type} order · {row.status}", "workspace": "Orders", "entity_id": row.id})
        unmapped = int(session.scalar(select(func.count()).select_from(RetailSale).where(RetailSale.organization_id == context.organization_id, RetailSale.facility_id == context.facility_id, RetailSale.product_id.is_(None), RetailSale.sold_at >= now - timedelta(days=7))) or 0)
        if unmapped: items.append({"id": "unmapped-sales", "severity": "medium", "area": "Data", "title": f"{unmapped} sales lines need product mapping", "detail": "Unmapped lines are excluded from product-level velocity.", "workspace": "Data & Settings", "entity_id": ""})
        failed_integrations = list(session.scalars(select(IntegrationConfiguration).where(IntegrationConfiguration.status == "failed", ((IntegrationConfiguration.scope_type == "user") & (IntegrationConfiguration.scope_key == context.user_id)) | ((IntegrationConfiguration.organization_id == context.organization_id) & (IntegrationConfiguration.facility_id == context.facility_id)))))
        for row in failed_integrations: items.append({"id": f"integration:{row.id}", "severity": "high", "area": "Integrations", "title": f"{row.provider.upper()} connection failed", "detail": row.last_error or "Retest the saved connection.", "workspace": "Integrations", "entity_id": row.id})
    priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    items.sort(key=lambda item: (priority[item["severity"]], item["area"], item["title"]))
    return {"items": items[:50], "summary": {"critical": sum(item["severity"] == "critical" for item in items), "high": sum(item["severity"] == "high" for item in items), "total": len(items)}}


@router.get("/products/{product_id}")
def product_360(product_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try: snapshot = ProductMasterRepository(engine).snapshot(context.organization_id, product_id, history_limit=20)
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc
    product = snapshot["product"]
    with Session(engine) as session:
        balance_rows = list(session.execute(select(InventoryLot, func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).outerjoin(InventoryTransaction, InventoryTransaction.lot_id == InventoryLot.id).where(InventoryLot.organization_id == context.organization_id, InventoryLot.facility_id == context.facility_id, InventoryLot.product_id == product_id).group_by(InventoryLot.id).order_by(InventoryLot.received_at.desc())))
        since = utc_now() - timedelta(days=30)
        sales = session.execute(select(func.coalesce(func.sum(RetailSale.quantity), 0.0), func.coalesce(func.sum(RetailSale.net_sales), 0.0)).where(RetailSale.organization_id == context.organization_id, RetailSale.facility_id == context.facility_id, RetailSale.product_id == product_id, RetailSale.sold_at >= since, RetailSale.sold_at <= utc_now())).one()
        order_lines = list(session.execute(select(CommercialOrderLine, CommercialOrder).join(CommercialOrder, CommercialOrder.id == CommercialOrderLine.commercial_order_id).where(CommercialOrderLine.organization_id == context.organization_id, CommercialOrderLine.product_id == product_id, CommercialOrder.facility_id == context.facility_id, CommercialOrder.status.not_in(["fulfilled", "cancelled"])).order_by(CommercialOrder.created_at.desc()).limit(20)))
        production = list(session.scalars(select(ProductionOrder).where(ProductionOrder.organization_id == context.organization_id, ProductionOrder.facility_id == context.facility_id, or_(ProductionOrder.sku == product.sku, ProductionOrder.product_name == product.name)).order_by(ProductionOrder.created_at.desc()).limit(20)))
    profile = snapshot["profile"]
    packages = [{"id": lot.id, "package_id": lot.compliance_package_id or lot.lot_code, "lot_code": lot.lot_code, "location": lot.location_code, "status": lot.status, "balance": float(balance), "unit": product.base_unit, "received_at": lot.received_at, "expiration_at": lot.expiration_at} for lot, balance in balance_rows]
    return {"product": {key: getattr(product, key) for key in ("id", "sku", "name", "item_type", "base_unit", "unit_cost", "retail_price", "upc", "active")}, "profile": {key: getattr(profile, key) for key in ("brand", "category", "subcategory", "strain", "manufacturer", "product_format", "description", "retail_enabled", "production_enabled")} if profile else None, "inventory": {"packages": packages, "on_hand": sum(row["balance"] for row in packages), "package_count": len(packages)}, "sales_30d": {"quantity": float(sales[0]), "net_sales": float(sales[1]), "daily_velocity": float(sales[0]) / 30}, "open_orders": [{"id": order.id, "order_number": order.order_number, "order_type": order.order_type, "status": order.status, "quantity": float(line.quantity), "fulfilled_quantity": float(line.fulfilled_quantity), "unit": line.unit} for line, order in order_lines], "production_orders": [{key: getattr(row, key) for key in ("id", "order_number", "status", "requested_units", "due_at", "product_format")} for row in production], "aliases": [{"alias": row.alias, "source": row.source} for row in snapshot["aliases"]], "mappings": [{"system_name": row.system_name, "external_id": row.external_id, "external_name": row.external_name} for row in snapshot["mappings"]], "value_history": [{"value_type": row.value_type, "amount": row.amount, "currency": row.currency, "effective_at": row.effective_at} for row in snapshot["value_history"]]}
