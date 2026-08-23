from __future__ import annotations

from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import CrewAvailability, Facility, FacilityMachine, Organization, ProductionActual, ProductionOrder
from modules.extraction.repository import ExtractionRepository
from reports.buyer_report import _build_buyer_executive_report_pdf
from reports.coman_report import _build_coman_executive_report_pdf
from reports.executive_system import combine_report_pdfs
from reports.extraction_report import _build_extraction_executive_report_pdf
from reports.white_label_report import _build_white_label_repack_report_pdf
from .buyer_parity import _model as buyer_model
from ..auth import RequestContext, get_request_context, get_retail_context
from ..database import get_engine

router = APIRouter(prefix="/executive-reports", tags=["executive-reports"])

DEFAULT_BUYER_CONTROLS = {
    "target_doh": 21,
    "velocity_adjustment": 0.5,
    "sales_days": 60,
    "sku_window": 56,
}


def _context_names(context: RequestContext, engine: Engine) -> tuple[str, str]:
    with Session(engine) as session:
        organization = session.get(Organization, context.organization_id)
        facility = session.get(Facility, context.facility_id)
    return (organization.name if organization else "Current organization", facility.name if facility else "Current facility")


def _numeric_sum(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def _buyer_controls(payload: dict | None) -> dict[str, float | int]:
    raw = (payload or {}).get("buyer_controls") if isinstance(payload, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    try:
        target = max(1, min(60, int(raw.get("target_doh", DEFAULT_BUYER_CONTROLS["target_doh"]))))
        velocity = max(0.01, min(5.0, float(raw.get("velocity_adjustment", DEFAULT_BUYER_CONTROLS["velocity_adjustment"]))))
        days = max(7, min(120, int(raw.get("sales_days", DEFAULT_BUYER_CONTROLS["sales_days"]))))
        sku_window = int(raw.get("sku_window", DEFAULT_BUYER_CONTROLS["sku_window"]))
        if sku_window not in {28, 56, 84}:
            sku_window = 56
    except (TypeError, ValueError):
        return dict(DEFAULT_BUYER_CONTROLS)
    return {"target_doh": target, "velocity_adjustment": velocity, "sales_days": days, "sku_window": sku_window}


def _buyer_report(context: RequestContext, engine: Engine, payload: dict | None = None) -> tuple[bytes, bool]:
    organization, facility = _context_names(context, engine)
    controls = _buyer_controls(payload)
    detail, product, inventory, sales, _inventory_source, _sales_source = buyer_model(
        context,
        engine,
        int(controls["target_doh"]),
        float(controls["velocity_adjustment"]),
        int(controls["sales_days"]),
    )
    payload = {
        "store_name": organization,
        "organization": organization,
        "facility": facility,
        "reporting_period": f"Current Buyer Dashboard source set · {controls['sales_days']} day sales period",
        "detail_view": detail,
        "detail_product": product,
        "inv_df": inventory,
        "sales_df": sales,
        "controls": controls,
        "doh_threshold": int(controls["target_doh"]),
        "kpis": {
            "total_units_sold": _numeric_sum(product, "unitssold"),
            "total_units_on_hand": _numeric_sum(product, "onhandunits"),
            "avg_days_on_hand": float(pd.to_numeric(product["daysonhand"], errors="coerce").fillna(0).mean()) if len(product) and "daysonhand" in product else 0.0,
            "total_reorder_qty": _numeric_sum(detail, "reorderqty"),
        },
    }
    has_data = any(not frame.empty for frame in (detail, product, inventory, sales))
    return _build_buyer_executive_report_pdf(payload), has_data


def _production_report(context: RequestContext, engine: Engine) -> tuple[bytes, bool]:
    organization, facility = _context_names(context, engine)
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
    return _build_coman_executive_report_pdf(payload), bool(orders or actuals or machines or crew)


def _extraction_report(context: RequestContext, engine: Engine) -> tuple[bytes, bool]:
    organization, facility = _context_names(context, engine)
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
    return _build_extraction_executive_report_pdf(payload), bool(runs)


def _white_label_report(payload: dict, context: RequestContext, engine: Engine) -> bytes:
    organization, facility = _context_names(context, engine)
    report_payload = dict(payload)
    report_payload["organization"] = organization
    report_payload["facility"] = facility
    return _build_white_label_repack_report_pdf(report_payload)


def _pdf_response(pdf: bytes, filename: str) -> Response:
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _retail_pack_parts(payload: dict | None, context: RequestContext, engine: Engine) -> list[tuple[str, bytes]]:
    parts: list[tuple[str, bytes]] = []
    try:
        buyer_pdf, buyer_has_data = _buyer_report(context, engine, payload)
        if buyer_has_data:
            parts.append(("Buyer Operations", buyer_pdf))
    except HTTPException:
        pass
    white_label = (payload or {}).get("white_label") if isinstance(payload, dict) else None
    if isinstance(white_label, dict) and white_label:
        parts.append(("White Label / Repack", _white_label_report(white_label, context, engine)))
    return parts


def _production_pack_parts(context: RequestContext, engine: Engine) -> list[tuple[str, bytes]]:
    parts: list[tuple[str, bytes]] = []
    production_pdf, production_has_data = _production_report(context, engine)
    if production_has_data:
        parts.append(("Co-Man Production", production_pdf))
    extraction_pdf, extraction_has_data = _extraction_report(context, engine)
    if extraction_has_data:
        parts.append(("Extraction Operations", extraction_pdf))
    return parts


@router.get("/catalog")
def catalog(context: RequestContext = Depends(get_request_context)):
    return {
        "items": [
            {"key": "buyer", "label": "Buyer Operations Executive Report", "capability": "retail"},
            {"key": "production", "label": "Co-Man Production Executive Report", "capability": "production"},
            {"key": "extraction", "label": "Extraction Operations Executive Report", "capability": "production"},
        ]
    }


@router.post("/buyer.pdf")
def buyer_report_pdf(
    payload: dict | None = Body(default=None),
    context: RequestContext = Depends(get_retail_context),
    engine: Engine = Depends(get_engine),
):
    pdf, _has_data = _buyer_report(context, engine, payload)
    return _pdf_response(pdf, f"buyer_executive_summary_{datetime.now().strftime('%Y-%m-%d')}.pdf")


@router.post("/white-label.pdf")
def white_label_report_pdf(
    payload: dict = Body(...),
    context: RequestContext = Depends(get_retail_context),
    engine: Engine = Depends(get_engine),
):
    """Render the current White Label / Repack scenario with Streamlit's PDF builder."""
    return _pdf_response(_white_label_report(payload, context, engine), "retail_ops_repack_report.pdf")


@router.post("/packs/retail.pdf")
def retail_pack_pdf(
    payload: dict | None = Body(default=None),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    parts = _retail_pack_parts(payload, context, engine)
    if not parts:
        raise HTTPException(422, "No Retail Ops reports are available for the current facility and session.")
    pdf = combine_report_pdfs([report for _, report in parts], title="DoobieLogic Retail Ops Executive Pack", division="Retail Ops")
    return _pdf_response(pdf, f"retail_ops_executive_pack_{datetime.now().strftime('%Y-%m-%d')}.pdf")


@router.post("/packs/production.pdf")
def production_pack_pdf(
    payload: dict | None = Body(default=None),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    del payload
    parts = _production_pack_parts(context, engine)
    if not parts:
        raise HTTPException(422, "No Production Ops reports are available for the current facility.")
    pdf = combine_report_pdfs([report for _, report in parts], title="DoobieLogic Production Ops Executive Pack", division="Production Ops")
    return _pdf_response(pdf, f"production_ops_executive_pack_{datetime.now().strftime('%Y-%m-%d')}.pdf")


@router.post("/packs/company.pdf")
def company_pack_pdf(
    payload: dict | None = Body(default=None),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    retail = _retail_pack_parts(payload, context, engine)
    production = _production_pack_parts(context, engine)
    if not retail or not production:
        raise HTTPException(422, "The Company Executive Pack requires at least one available Retail Ops report and one available Production Ops report.")
    pdf = combine_report_pdfs([report for _, report in retail + production], title="DoobieLogic Company Executive Pack", division="All Operations")
    return _pdf_response(pdf, f"company_executive_pack_{datetime.now().strftime('%Y-%m-%d')}.pdf")


@router.get("/{report_key}.pdf")
def report_pdf(report_key: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if report_key == "buyer":
        pdf, _has_data = _buyer_report(context, engine)
        filename = "Buyer_Operations_Executive_Report.pdf"
    elif report_key == "production":
        pdf, _has_data = _production_report(context, engine)
        filename = "CoMan_Production_Executive_Report.pdf"
    elif report_key == "extraction":
        pdf, _has_data = _extraction_report(context, engine)
        filename = "Extraction_Operations_Executive_Report.pdf"
    else:
        raise HTTPException(404, "Unknown executive report.")
    return _pdf_response(pdf, filename)
