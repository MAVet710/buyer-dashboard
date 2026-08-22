from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import CrewAvailability, Facility, FacilityMachine, Organization, ProductionActual, ProductionOrder
from modules.extraction.repository import ExtractionRepository
from reports.buyer_report import _build_buyer_executive_report_pdf
from reports.coman_report import _build_coman_executive_report_pdf
from reports.extraction_report import _build_extraction_executive_report_pdf
from .buyer_parity import _model as buyer_model
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/executive-reports", tags=["executive-reports"])


def _context_names(context: RequestContext, engine: Engine) -> tuple[str, str]:
    with Session(engine) as session:
        organization = session.get(Organization, context.organization_id)
        facility = session.get(Facility, context.facility_id)
    return (organization.name if organization else "Current organization", facility.name if facility else "Current facility")


@router.get("/catalog")
def catalog(context: RequestContext = Depends(get_request_context)):
    return {
        "items": [
            {"key": "buyer", "label": "Buyer Operations Executive Report", "capability": "retail"},
            {"key": "production", "label": "Co-Man Production Executive Report", "capability": "production"},
            {"key": "extraction", "label": "Extraction Operations Executive Report", "capability": "production"},
        ]
    }


@router.get("/{report_key}.pdf")
def report_pdf(report_key: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    organization, facility = _context_names(context, engine)
    if report_key == "buyer":
        try:
            detail, product, inventory, sales, _inventory_source, _sales_source = buyer_model(context, engine, 21, 0.5, 60)
        except HTTPException:
            raise
        payload = {
            "store_name": organization,
            "organization": organization,
            "facility": facility,
            "reporting_period": "Current Buyer Dash source set",
            "detail_view": detail,
            "detail_product": product,
            "inv_df": inventory,
            "sales_df": sales,
            "kpis": {
                "total_units_sold": float(pd.to_numeric(product.get("unitssold", 0), errors="coerce").fillna(0).sum()),
                "total_units_on_hand": float(pd.to_numeric(product.get("onhandunits", 0), errors="coerce").fillna(0).sum()),
                "avg_days_on_hand": float(pd.to_numeric(product.get("daysonhand", 0), errors="coerce").fillna(0).mean()) if len(product) else 0,
                "total_reorder_qty": float(pd.to_numeric(detail.get("reorderqty", 0), errors="coerce").fillna(0).sum()),
            },
        }
        pdf = _build_buyer_executive_report_pdf(payload)
        filename = "Buyer_Operations_Executive_Report.pdf"
    elif report_key == "production":
        with Session(engine) as session:
            orders = list(session.scalars(select(ProductionOrder).where(ProductionOrder.organization_id == context.organization_id, ProductionOrder.facility_id == context.facility_id).order_by(ProductionOrder.due_at)))
            actuals = list(session.scalars(select(ProductionActual).where(ProductionActual.organization_id == context.organization_id, ProductionActual.facility_id == context.facility_id)))
            machines = list(session.scalars(select(FacilityMachine).where(FacilityMachine.organization_id == context.organization_id, FacilityMachine.facility_id == context.facility_id)))
            crew = list(session.scalars(select(CrewAvailability).where(CrewAvailability.organization_id == context.organization_id, CrewAvailability.facility_id == context.facility_id).order_by(CrewAvailability.work_date)))
        order_by_id = {row.id: row for row in orders}
        payload = {
            "organization": organization,
            "facility": facility,
            "reporting_period": "Current production queue",
            "orders": pd.DataFrame([{"Order": row.order_number, "Type": row.work_type, "Product": row.product_name, "SKU": row.sku, "Format": row.product_format, "Units": row.requested_units, "Due": row.due_at, "Priority": row.priority, "Status": row.status} for row in orders]),
            "actuals": pd.DataFrame([{"Order": order_by_id.get(row.production_order_id).order_number if order_by_id.get(row.production_order_id) else row.production_order_id, "Actual Units": row.actual_units, "Scrap": row.scrap_units, "Rework": row.rework_units, "Machine Hours": row.actual_machine_hours, "Labor Hours": row.actual_labor_hours, "Attainment %": (row.actual_units / order_by_id[row.production_order_id].requested_units * 100) if order_by_id.get(row.production_order_id) and order_by_id[row.production_order_id].requested_units else 0, "Completed": row.completed_at} for row in actuals]),
            "machines": pd.DataFrame([{"Machine": row.display_name, "Asset": row.asset_code, "Effective Rate": row.effective_rate, "Rate Unit": row.rate_unit, "Crew": row.preferred_crew_size, "Setup Minutes": row.setup_minutes, "Cleanup Minutes": row.cleanup_minutes} for row in machines]),
            "crew": pd.DataFrame([{"Date": row.work_date, "Shift": row.shift_name, "People": row.available_people, "Shift Hours": row.shift_hours, "Notes": row.notes} for row in crew]),
            "customers": pd.DataFrame(),
        }
        pdf = _build_coman_executive_report_pdf(payload)
        filename = "CoMan_Production_Executive_Report.pdf"
    elif report_key == "extraction":
        repo = ExtractionRepository(engine)
        runs = repo.list_runs(context.organization_id, context.facility_id, include_closed=True)
        performance = []
        profitability = []
        for run in runs:
            mass = repo.mass_balance(context.organization_id, context.facility_id, run.id)
            cogs = repo.cogs_summary(context.organization_id, context.facility_id, run.id)
            qa_events = repo.list_qa_events(context.organization_id, context.facility_id, run.id)
            performance.append({"Run": run.batch_number, "Product Name": run.product_family, "Method": run.method, "Material": run.strain, "Input Weight g": mass.get("consumed_input", 0), "Finished Output g": mass.get("recorded_output", 0), "Yield %": mass.get("yield_pct", 0), "Efficiency %": 0, "QA Hold": run.status == "hold", "COA Status": "failed" if any(row.result == "failed" for row in qa_events) else "passed" if any(row.result == "passed" for row in qa_events) else "pending"})
            profitability.append({"Run": run.batch_number, "Product Name": run.product_family, "Revenue": 0, "COGS": cogs.get("total", 0), "Gross Profit": -cogs.get("total", 0), "Gross Margin %": 0, "Value Risk": "Hold" if run.status == "hold" else ""})
        payload = {
            "summary": {"organization": organization, "facility_context": facility, "reporting_period": "Current extraction run history"},
            "run_performance": pd.DataFrame(performance),
            "profitability": pd.DataFrame(profitability),
            "extraction_inventory": pd.DataFrame(repo.list_available_lots(context.organization_id, context.facility_id)),
            "kpis": {"total_runs": len(runs), "qa_holds_or_coa_pending": sum(1 for row in runs if row.status in {"hold", "qa"})},
        }
        pdf = _build_extraction_executive_report_pdf(payload)
        filename = "Extraction_Operations_Executive_Report.pdf"
    else:
        raise HTTPException(404, "Unknown executive report.")
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
