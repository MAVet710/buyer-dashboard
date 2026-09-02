from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Facility
from ..auth import RequestContext, get_request_context
from ..database import get_engine
from ..services.enterprise_control_fast import organization_facility_metrics, organization_secondary_metrics

router = APIRouter(prefix="/enterprise", tags=["enterprise-control"])


@router.get("/control-tower")
def enterprise_control_tower(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    with Session(engine) as session:
        facilities = list(session.scalars(select(Facility).where(Facility.organization_id == context.organization_id, Facility.active.is_(True)).order_by(Facility.name)))
    core = organization_facility_metrics(engine, context.organization_id)
    secondary = organization_secondary_metrics(engine, context.organization_id)
    rows = []
    for facility in facilities:
        inventory = core["inventory"].get(facility.id, {"positive_lots": 0, "value": 0.0})
        order_metrics = core["orders"].get(facility.id, {"sales": 0, "purchase": 0, "overdue": 0})
        production_metrics = core["production"].get(facility.id, {"open": 0, "units": 0})
        trace_summary = secondary["traceability"].get(
            facility.id,
            {"total": 0, "needs_reconciliation": 0, "in_flight": 0},
        )
        compliance = secondary["compliance"].get(
            facility.id,
            {
                "open_sop_deviations": 0,
                "critical_sop": 0,
                "high_sop": 0,
                "label_failures": 0,
            },
        )
        finance = secondary["finance"].get(facility.id, {"ar": 0.0})
        risk_score = (
            int(trace_summary.get("needs_reconciliation", 0)) * 8
            + int(order_metrics["overdue"]) * 5
            + int(compliance["critical_sop"]) * 8
            + int(compliance["high_sop"]) * 5
            + int(compliance["label_failures"]) * 3
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
                "open_sop_deviations": int(compliance["open_sop_deviations"]),
                "critical_sop": int(compliance["critical_sop"]),
                "high_sop": int(compliance["high_sop"]),
                "label_failures": int(compliance["label_failures"]),
            },
            "finance": {"ar": float(finance["ar"])},
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
