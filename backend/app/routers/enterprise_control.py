from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Facility
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance.service import CommercialFinanceService
from modules.operational_moats.service import OperationalMoatService
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/enterprise", tags=["enterprise-control"])


@router.get("/control-tower")
def enterprise_control_tower(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    coman = ComanRepository(engine)
    commercial = CommercialRepository(engine)
    finance = CommercialFinanceService(engine)
    moat = OperationalMoatService(engine)
    trace = TraceabilityBackofficeRepository(engine)
    with Session(engine) as session:
        facilities = list(session.scalars(select(Facility).where(Facility.organization_id == context.organization_id, Facility.active.is_(True)).order_by(Facility.name)))
    products = {row.id: row for row in coman.list_products(context.organization_id)}
    now = datetime.now(timezone.utc)
    rows = []
    for facility in facilities:
        lots = coman.list_inventory_lots(context.organization_id, facility.id)
        inventory_value = 0.0
        positive_lots = 0
        for lot in lots:
            balance = coman.inventory_balance(context.organization_id, lot.id)
            if balance > 0:
                positive_lots += 1
                inventory_value += balance * float(getattr(products.get(lot.product_id), "unit_cost", 0.0) or 0.0)
        orders = commercial.list_orders(context.organization_id, facility.id, open_only=True)
        open_sales = [row for row in orders if row.order_type == "sales"]
        open_purchases = [row for row in orders if row.order_type == "purchase"]
        overdue_orders = sum(bool(row.due_at and ((row.due_at if row.due_at.tzinfo else row.due_at.replace(tzinfo=timezone.utc)) < now)) for row in orders)
        production_orders = [row for row in coman.list_production_orders(context.organization_id, facility.id) if row.status not in {"complete", "cancelled"}]
        trace_summary = trace.summary(context.organization_id, facility.id)
        deviations = moat.list_deviations(context.organization_id, facility.id)
        label_reviews = moat.list_label_reviews(context.organization_id, facility.id, limit=100)
        ar = finance.ar_summary(context.organization_id, facility.id)
        risk_score = (
            int(trace_summary.get("needs_reconciliation", 0)) * 8
            + overdue_orders * 5
            + sum(row.severity == "critical" for row in deviations) * 8
            + sum(row.severity == "high" for row in deviations) * 5
            + sum(row.status == "fail" for row in label_reviews) * 3
            + len(production_orders)
        )
        rows.append({
            "facility": {
                "id": facility.id,
                "name": facility.name,
                "code": facility.code,
                "license_number": facility.license_number,
                "license_type": facility.license_type,
                "capabilities": {
                    "retail": facility.retail_enabled,
                    "production": facility.production_enabled,
                    "cultivation": facility.cultivation_enabled,
                    "commercial": facility.commercial_enabled,
                },
            },
            "inventory": {"positive_lots": positive_lots, "value": inventory_value},
            "orders": {"sales": len(open_sales), "purchase": len(open_purchases), "overdue": overdue_orders},
            "production": {"open": len(production_orders), "units": sum(int(row.requested_units or 0) for row in production_orders)},
            "traceability": trace_summary,
            "compliance": {
                "open_sop_deviations": len(deviations),
                "critical_sop": sum(row.severity == "critical" for row in deviations),
                "high_sop": sum(row.severity == "high" for row in deviations),
                "label_failures": sum(row.status == "fail" for row in label_reviews),
            },
            "finance": {"ar": float(ar.get("total_ar", 0.0))},
            "risk_score": risk_score,
        })
    rows.sort(key=lambda row: (row["risk_score"], row["finance"]["ar"], row["inventory"]["value"]), reverse=True)
    return {
        "organization_id": context.organization_id,
        "facility_count": len(rows),
        "summary": {
            "inventory_value": sum(row["inventory"]["value"] for row in rows),
            "open_sales_orders": sum(row["orders"]["sales"] for row in rows),
            "open_purchase_orders": sum(row["orders"]["purchase"] for row in rows),
            "open_production_orders": sum(row["production"]["open"] for row in rows),
            "reconciliation_actions": sum(int(row["traceability"].get("needs_reconciliation", 0)) for row in rows),
            "open_ar": sum(row["finance"]["ar"] for row in rows),
            "facilities_at_risk": sum(row["risk_score"] > 0 for row in rows),
        },
        "facilities": rows,
    }
