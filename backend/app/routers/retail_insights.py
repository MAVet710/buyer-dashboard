from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryLot, InventoryTransaction, Product, RetailSale, utc_now
from modules.product_master.models import ProductMasterProfile
from ..auth import RequestContext, get_request_context, get_retail_context
from ..database import get_engine

router = APIRouter(prefix="/retail-insights", tags=["retail-insights"], dependencies=[Depends(get_retail_context)])


def _category(profile: ProductMasterProfile | None) -> str:
    return str(profile.category or "Uncategorized") if profile else "Uncategorized"


@router.get("/trends")
def retail_trends(days: int = Query(default=30, ge=7, le=365), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    since = utc_now() - timedelta(days=days)
    with Session(engine) as session:
        sales = list(session.execute(select(RetailSale, Product, ProductMasterProfile).outerjoin(Product, Product.id == RetailSale.product_id).outerjoin(ProductMasterProfile, ProductMasterProfile.product_id == Product.id).where(RetailSale.organization_id == context.organization_id, RetailSale.facility_id == context.facility_id, RetailSale.sold_at >= since, RetailSale.sold_at <= utc_now()).order_by(RetailSale.sold_at)))
    daily: dict[str, dict] = {}; categories: dict[str, dict] = {}; products: dict[str, dict] = {}
    for sale, product, profile in sales:
        day = sale.sold_at.date().isoformat(); daily_row = daily.setdefault(day, {"date": day, "quantity": 0.0, "net_sales": 0.0}); daily_row["quantity"] += float(sale.quantity); daily_row["net_sales"] += float(sale.net_sales)
        category = _category(profile); cat = categories.setdefault(category, {"category": category, "quantity": 0.0, "net_sales": 0.0}); cat["quantity"] += float(sale.quantity); cat["net_sales"] += float(sale.net_sales)
        key = product.id if product else f"unmapped:{sale.sku or sale.product_name}"; row = products.setdefault(key, {"product_id": product.id if product else None, "sku": product.sku if product else sale.sku, "product_name": product.name if product else sale.product_name, "category": category, "quantity": 0.0, "net_sales": 0.0}); row["quantity"] += float(sale.quantity); row["net_sales"] += float(sale.net_sales)
    total_sales = sum(row["net_sales"] for row in daily.values()); total_units = sum(row["quantity"] for row in daily.values())
    return {"window_days": days, "summary": {"net_sales": total_sales, "units": total_units, "average_daily_sales": total_sales / days, "mapped_sales_pct": (sum(float(s.net_sales) for s, p, _ in sales if p) / total_sales * 100) if total_sales else 0}, "daily": list(daily.values()), "categories": sorted(categories.values(), key=lambda row: row["net_sales"], reverse=True), "products": sorted(products.values(), key=lambda row: row["net_sales"], reverse=True)}


@router.get("/slow-movers")
def slow_movers(days: int = Query(default=30, ge=7, le=180), threshold_doh: float = Query(default=60, ge=1, le=1000), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    since = utc_now() - timedelta(days=days)
    balance = select(InventoryLot.product_id, func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0).label("on_hand"), func.min(InventoryLot.received_at).label("oldest_received")).join(InventoryTransaction, InventoryTransaction.lot_id == InventoryLot.id).where(InventoryLot.organization_id == context.organization_id, InventoryLot.facility_id == context.facility_id).group_by(InventoryLot.product_id).subquery()
    sales = select(RetailSale.product_id, func.coalesce(func.sum(RetailSale.quantity), 0.0).label("sold"), func.coalesce(func.sum(RetailSale.net_sales), 0.0).label("net_sales")).where(RetailSale.organization_id == context.organization_id, RetailSale.facility_id == context.facility_id, RetailSale.sold_at >= since, RetailSale.sold_at <= utc_now(), RetailSale.product_id.is_not(None)).group_by(RetailSale.product_id).subquery()
    with Session(engine) as session:
        rows = list(session.execute(select(Product, ProductMasterProfile, balance.c.on_hand, balance.c.oldest_received, func.coalesce(sales.c.sold, 0.0), func.coalesce(sales.c.net_sales, 0.0)).join(balance, balance.c.product_id == Product.id).outerjoin(sales, sales.c.product_id == Product.id).outerjoin(ProductMasterProfile, ProductMasterProfile.product_id == Product.id).where(Product.organization_id == context.organization_id, balance.c.on_hand > 0)))
    result = []
    for product, profile, on_hand, oldest, sold, net_sales in rows:
        velocity = float(sold) / days; doh = float(on_hand) / velocity if velocity > 0 else None; age = max(0, (utc_now() - oldest).days) if oldest else 0
        if doh is not None and doh < threshold_doh: continue
        severity = 100 if velocity == 0 else min(100, max(0, (float(doh or 0) - threshold_doh) / max(threshold_doh, 1) * 50 + min(age, 180) / 3.6))
        discount = 30 if severity >= 85 else 20 if severity >= 65 else 10 if severity >= 40 else 0
        result.append({"product_id": product.id, "sku": product.sku, "product_name": product.name, "brand": profile.brand if profile else "", "category": _category(profile), "on_hand": float(on_hand), "unit": product.base_unit, "sold": float(sold), "net_sales": float(net_sales), "daily_velocity": velocity, "days_on_hand": doh, "oldest_age_days": age, "score": severity, "suggested_discount_pct": discount, "inventory_value": float(on_hand) * float(product.unit_cost or 0)})
    result.sort(key=lambda row: (row["score"], row["inventory_value"]), reverse=True)
    return {"window_days": days, "threshold_doh": threshold_doh, "summary": {"product_count": len(result), "units_at_risk": sum(row["on_hand"] for row in result), "cost_at_risk": sum(row["inventory_value"] for row in result), "zero_velocity_count": sum(row["daily_velocity"] == 0 for row in result)}, "items": result}


@router.get("/deliveries")
def deliveries(limit: int = Query(default=100, ge=1, le=500), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    with Session(engine) as session:
        rows = list(session.execute(select(InventoryTransaction, InventoryLot, Product).join(InventoryLot, InventoryLot.id == InventoryTransaction.lot_id).join(Product, Product.id == InventoryLot.product_id).where(InventoryTransaction.organization_id == context.organization_id, InventoryTransaction.facility_id == context.facility_id, InventoryTransaction.transaction_type.in_(["receipt", "receive"]), InventoryTransaction.quantity_delta > 0).order_by(InventoryTransaction.occurred_at.desc()).limit(limit)))
    return [{"transaction_id": tx.id, "received_at": tx.occurred_at, "reference": tx.reference, "product_id": product.id, "product_name": product.name, "sku": product.sku, "package_id": lot.compliance_package_id or lot.lot_code, "quantity": float(tx.quantity_delta), "unit": tx.unit, "purchase_order_id": tx.commercial_order_id} for tx, lot, product in rows]


@router.get("/deliveries/{transaction_id}/impact")
def delivery_impact(transaction_id: str, window_days: int = Query(default=14, ge=3, le=60), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    with Session(engine) as session:
        row = session.execute(select(InventoryTransaction, InventoryLot, Product).join(InventoryLot, InventoryLot.id == InventoryTransaction.lot_id).join(Product, Product.id == InventoryLot.product_id).where(InventoryTransaction.id == transaction_id, InventoryTransaction.organization_id == context.organization_id, InventoryTransaction.facility_id == context.facility_id)).first()
        if not row: raise HTTPException(404, "Delivery receipt was not found in the active facility.")
        tx, lot, product = row; before_start = tx.occurred_at - timedelta(days=window_days); after_end = tx.occurred_at + timedelta(days=window_days)
        sales = list(session.scalars(select(RetailSale).where(RetailSale.organization_id == context.organization_id, RetailSale.facility_id == context.facility_id, RetailSale.product_id == product.id, RetailSale.sold_at >= before_start, RetailSale.sold_at < after_end)))
    before = [row for row in sales if row.sold_at < tx.occurred_at]; after = [row for row in sales if row.sold_at >= tx.occurred_at]
    def metrics(rows): return {"units": sum(float(row.quantity) for row in rows), "net_sales": sum(float(row.net_sales) for row in rows), "orders": len({row.source_record_id for row in rows})}
    before_metrics = metrics(before); after_metrics = metrics(after)
    return {"delivery": {"transaction_id": tx.id, "received_at": tx.occurred_at, "reference": tx.reference, "product_name": product.name, "sku": product.sku, "package_id": lot.compliance_package_id or lot.lot_code, "quantity": float(tx.quantity_delta), "unit": tx.unit}, "window_days": window_days, "before": before_metrics, "after": after_metrics, "lift": {"units": after_metrics["units"] - before_metrics["units"], "net_sales": after_metrics["net_sales"] - before_metrics["net_sales"], "net_sales_pct": ((after_metrics["net_sales"] - before_metrics["net_sales"]) / before_metrics["net_sales"] * 100) if before_metrics["net_sales"] else None}}
