from io import BytesIO
import hashlib
import json
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryLot
from ..auth import RequestContext, get_request_context, require_inventory_operation_capability
from ..database import get_engine
from ..schemas.inventory import InventoryAuditComplete, InventoryAuditCounts, InventoryAuditCreate, InventoryAuditDetail, InventoryAuditLineItem, InventoryAuditScanCount, InventoryAuditScanPreview, InventoryAuditStatusChange, InventoryAuditSummary, RetailAuditSnapshotImport
from ..services.audits import AuditService

router = APIRouter(prefix="/inventory/{operation}/audits", tags=["inventory-audits"])
WRITE_ROLES = {"dev", "admin", "buyer", "supervisor", "operator", "qa", "trial"}


def _validate(operation: str, context: RequestContext, engine: Engine, write: bool = False):
    if operation not in {"retail", "production"}:
        raise HTTPException(404, "Inventory operation not found.")
    require_inventory_operation_capability(context, engine, operation)
    if write and context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow inventory audit changes.")


def _audit_for_operation(service: AuditService, context: RequestContext, audit_id: str, operation: str) -> InventoryAuditDetail:
    try:
        detail = service.detail(context.organization_id, context.facility_id, audit_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if detail.audit.operation_type != operation:
        raise HTTPException(404, "Inventory audit was not found in the active operation.")
    return detail


@router.get("", response_model=list[InventoryAuditSummary])
def list_audits(operation: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, engine)
    return AuditService(engine).list(context.organization_id, context.facility_id, operation)


@router.post("", response_model=InventoryAuditSummary, status_code=201)
def create_audit(operation: str, payload: InventoryAuditCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, engine, True)
    try: return AuditService(engine).create(context.organization_id, context.facility_id, operation, payload, context.user_id)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.get("/{audit_id}", response_model=InventoryAuditDetail)
def audit_detail(operation: str, audit_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, engine)
    return _audit_for_operation(AuditService(engine), context, audit_id, operation)


@router.post("/{audit_id}/counts", response_model=InventoryAuditDetail)
def save_counts(operation: str, audit_id: str, payload: InventoryAuditCounts, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, engine, True); service = AuditService(engine)
    try:
        _audit_for_operation(service, context, audit_id, operation)
        service.repository.save_counts(context.organization_id, context.facility_id, audit_id, counts=[row.model_dump() for row in payload.counts], actor=context.user_id)
        return _audit_for_operation(service, context, audit_id, operation)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.post("/{audit_id}/status", response_model=InventoryAuditSummary)
def change_status(operation: str, audit_id: str, payload: InventoryAuditStatusChange, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, engine, True)
    service = AuditService(engine)
    try:
        _audit_for_operation(service, context, audit_id, operation)
        return service.status(context.organization_id, context.facility_id, audit_id, payload.status, context.user_id)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.post("/{audit_id}/complete", response_model=InventoryAuditSummary)
def complete_audit(operation: str, audit_id: str, payload: InventoryAuditComplete, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, engine, True); service = AuditService(engine)
    try:
        _audit_for_operation(service, context, audit_id, operation)
        audit = service.repository.complete_audit(context.organization_id, context.facility_id, audit_id, actor=context.user_id, post_adjustments=payload.post_adjustments)
        return service.summary(audit, service.repository.list_lines(context.organization_id, audit.id))
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.post("/{audit_id}/scan/preview", response_model=InventoryAuditLineItem)
def preview_scan(operation: str, audit_id: str, payload: InventoryAuditScanPreview, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, engine, True)
    service = AuditService(engine)
    try:
        _audit_for_operation(service, context, audit_id, operation)
        line = service.repository.preview_scanned_item(
            context.organization_id,
            context.facility_id,
            audit_id,
            raw_code=payload.raw_code,
            recount=payload.recount,
            actor=context.user_id,
        )
        return service.line_item(context.organization_id, context.facility_id, audit_id, line.id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{audit_id}/scan/count", response_model=InventoryAuditDetail)
def save_scanned_count(operation: str, audit_id: str, payload: InventoryAuditScanCount, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, engine, True)
    service = AuditService(engine)
    try:
        _audit_for_operation(service, context, audit_id, operation)
        service.repository.record_scanned_count(
            context.organization_id,
            context.facility_id,
            audit_id,
            raw_code=payload.raw_code,
            quantity=payload.quantity,
            recount=payload.recount,
            reason=payload.reason,
            notes=payload.notes,
            actor=context.user_id,
        )
        return _audit_for_operation(service, context, audit_id, operation)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _report_frame(detail: InventoryAuditDetail) -> pd.DataFrame:
    rows = []
    for line in detail.lines:
        rows.append({
            "Product Name": line.product_name,
            "SKU / UPC": line.sku_or_upc,
            "Lot / Batch": line.lot_code,
            "METRC Package": line.metrc_package,
            "Location": line.location,
            "Expected": line.expected_quantity,
            "First Count": line.first_count_quantity,
            "Recount": line.recount_quantity,
            "Final Count": line.counted_quantity,
            "Variance": line.variance_quantity,
            "Unit": line.unit,
            "Reason": line.reason,
            "Notes": line.notes,
            "Counted By": line.counted_by,
            "Unit Cost": line.unit_cost,
            "Retail Price": line.retail_price,
            "Cost Impact": line.variance_quantity * line.unit_cost,
            "Revenue Impact": line.variance_quantity * line.retail_price,
            "Scan Status": "Scanned" if line.first_count_quantity is not None else "Not scanned",
        })
    return pd.DataFrame(rows)


@router.get("/{audit_id}/report.csv")
def audit_csv(operation: str, audit_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, engine)
    detail = _audit_for_operation(AuditService(engine), context, audit_id, operation)
    payload = _report_frame(detail).to_csv(index=False).encode("utf-8")
    filename = f"inventory_audit_{detail.audit.audit_number}_{detail.audit.status}.csv"
    return StreamingResponse(iter([payload]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{audit_id}/report.xlsx")
def audit_excel(operation: str, audit_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, engine)
    detail = _audit_for_operation(AuditService(engine), context, audit_id, operation)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame([{
            "Audit": detail.audit.audit_number,
            "Status": detail.audit.status,
            "Scope": detail.audit.scope_label,
            "Started": detail.audit.started_at.isoformat(),
            "Created By": detail.audit.created_by,
        }]).to_excel(writer, sheet_name="Summary", index=False)
        _report_frame(detail).to_excel(writer, sheet_name="Audit Detail", index=False)
        pd.DataFrame([{
            "Action": event.action,
            "Actor": event.actor,
            "Time": event.occurred_at.isoformat(),
            "Changes": event.changes_json,
        } for event in detail.events]).to_excel(writer, sheet_name="Activity", index=False)
    filename = f"inventory_audit_{detail.audit.audit_number}_{detail.audit.status}.xlsx"
    return StreamingResponse(iter([output.getvalue()]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/retail-snapshot/preview")
async def preview_retail_snapshot(operation: str, file: UploadFile = File(...), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, engine, True)
    if operation != "retail":
        raise HTTPException(404, "Retail inventory snapshot intake is only available in Retail Ops.")
    suffix = Path(file.filename or "").suffix.casefold()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(422, "Dutchie inventory file must be CSV, XLSX, or XLS.")
    raw = await file.read()
    try:
        frame = pd.read_csv(BytesIO(raw)) if suffix == ".csv" else pd.read_excel(BytesIO(raw))
    except Exception as exc:
        raise HTTPException(422, f"The inventory file could not be read: {exc}") from exc
    if frame.empty:
        raise HTTPException(422, "The inventory file is empty.")
    if len(frame) > 50_000:
        raise HTTPException(422, "The inventory file cannot exceed 50,000 rows.")
    rows = json.loads(frame.to_json(orient="records", date_format="iso"))
    return {"reference": file.filename or "Dutchie inventory file", "columns": [str(column) for column in frame.columns], "rows": rows, "row_count": len(rows)}


@router.post("/retail-snapshot/import")
def import_retail_snapshot(operation: str, payload: RetailAuditSnapshotImport, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, engine, True)
    if operation != "retail":
        raise HTTPException(404, "Retail inventory snapshot intake is only available in Retail Ops.")
    normalized = []
    for source in payload.rows:
        row = {}
        for field, column in payload.mapping.items():
            row[field] = "" if column == "Not provided" else source.get(column, "")
        normalized.append(row)
    service = AuditService(engine)
    try:
        result = service.repository.import_retail_snapshot(
            context.organization_id,
            context.facility_id,
            rows=normalized,
            actor=context.user_id,
            reference=payload.reference,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    lot_codes = []
    for row in normalized:
        name = str(row.get("product_name") or "").strip()
        if not name:
            continue
        sku = str(row.get("sku") or row.get("upc") or row.get("external_product_id") or "").strip().upper()
        if not sku:
            sku = f"RETAIL-{hashlib.sha1(name.casefold().encode('utf-8')).hexdigest()[:10].upper()}"
        package_id = str(row.get("compliance_package_id") or "").strip()
        external_inventory_id = str(row.get("external_inventory_id") or "").strip()
        location = str(row.get("location_code") or "UNASSIGNED").strip().upper()
        lot_code = str(row.get("lot_code") or package_id or external_inventory_id or f"RETAIL-{sku}-{location}").strip().upper()
        if lot_code:
            lot_codes.append(lot_code)
    with Session(engine) as session:
        lot_ids = list(session.scalars(select(InventoryLot.id).where(
            InventoryLot.organization_id == context.organization_id,
            InventoryLot.facility_id == context.facility_id,
            InventoryLot.lot_code.in_(set(lot_codes)),
        ))) if lot_codes else []
    return {**result, "reference": payload.reference, "lot_ids": lot_ids}
