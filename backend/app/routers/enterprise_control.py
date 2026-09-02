from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Facility
from modules.commercial_finance.service import CommercialFinanceService
from modules.operational_moats.service import OperationalMoatService
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from ..auth import RequestContext, get_request_context
from ..database import get_engine
from ..services.enterprise_control_fast import organization_facility_metrics

router = APIRouter(prefix="/enterprise", tags=["enterprise-control"])


@router.get("/control-tower")
def enterprise_control_tower(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    finance = CommercialFinanceService(engine)
    moat = OperationalMoatService(engine)
    trace = TraceabilityBackofficeRepository(engine)
    with Session(engine) as session:
        facilities = list(session.scalars(select(Facility).where(Facility.organization_id == context.organization_id, Facility.active.is_(True)).order_by(Facility.name)))
    core = organization_facility_metrics(engine, context.organization_id)
    rows = []
    for facility in facilities:
        inventory = core["inventory"].get(facility.id, {"positive_lots": 0, "value": 0.0})
        order_metrics = core["orders"].get(facility.id, {"sales": 0, "purchase": 0, "overdue": 0})
        production_metrics = core["production"].get(facility.id, {"open": 0, "units": 0})
        trace_summary = trace.summary(context.organization_id, facility.id)
        deviations = moat.list_deviations(context.organization_id, facility.id)
        label_reviews = moat.list_label_reviews(context.organization_id, facility.id, limit=100)
        ar = finance.ar_summary(context.organization_id, facility.id)
        risk_score = (
            int(trace_summary.get("needs_reconciliation", 0)) * 8
            + int(order_metrics["overdue"]) * 5
            + sum(row.severity == "critical" for row in deviations) * 8
            + sum(row.severity == "high" for row in deviations) * 5
            + sum(row.status == "fail" for row in label_reviews) * 3
            + int(production_metrics["open"])
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
            "inventory": {"positive_lots": int(inventory["positive_lots"]), "value": float(inventory["value"])},
            "orders": {"sales": int(order_metrics["sales"]), "purchase": int(order_metrics["purchase"]), "overdue": int(order_metrics["overdue"])},
            "production": {"open": int(production_metrics["open"]), "units": int(production_metrics["units"])},
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
