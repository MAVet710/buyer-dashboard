from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine

from ..auth import RequestContext, get_request_context, require_facility_capability
from ..database import get_engine
from ..schemas.inventory import InventoryAdjustmentCreate, InventoryAdjustmentResult, InventoryReceiptCreate, InventoryReceiptHistoryItem, InventoryReceiptResult, InventoryResponse, PackageLineage, ProductOption, RetailSalesImport, RetailSalesImportResult
from modules.package_studio.service import PackageStudioService
from ..services.inventory import InventoryQueryService

router = APIRouter(prefix="/inventory", tags=["inventory"])
ADJUSTMENT_ROLES = {"dev", "admin", "supervisor", "operator", "qa"}


def _list_packages(
    operation: str,
    context: RequestContext,
    engine: Engine,
    search: str,
    status: str,
    material_type: str,
    location: str,
    source: str,
    view: str,
) -> InventoryResponse:
    require_facility_capability(context, engine, operation)
    return InventoryQueryService(engine).list_packages(
        context.organization_id,
        context.facility_id,
        operation=operation,
        search=search,
        status=status,
        material_type=material_type,
        location=location,
        source=source,
        view=view,
    )


@router.get("/production/packages", response_model=InventoryResponse)
def list_production_packages(
    search: str = Query(default="", max_length=200),
    status: str = "",
    material_type: str = "",
    location: str = "",
    source: str = "",
    view: str = "all",
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
) -> InventoryResponse:
    return _list_packages("production", context, engine, search, status, material_type, location, source, view)


@router.get("/retail/packages", response_model=InventoryResponse)
def list_retail_packages(
    search: str = Query(default="", max_length=200),
    status: str = "",
    material_type: str = "",
    location: str = "",
    source: str = "",
    view: str = "all",
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
) -> InventoryResponse:
    return _list_packages("retail", context, engine, search, status, material_type, location, source, view)


@router.get("/products", response_model=list[ProductOption])
def list_inventory_products(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return InventoryQueryService(engine).list_products(context.organization_id)


@router.post("/{operation}/receipts", response_model=InventoryReceiptResult, status_code=201)
def receive_inventory(
    operation: str,
    payload: InventoryReceiptCreate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if operation not in {"retail", "production"}:
        raise HTTPException(status_code=404, detail="Inventory operation not found.")
    require_facility_capability(context, engine, operation)
    try:
        return InventoryQueryService(engine).receive(
            context.organization_id,
            context.facility_id,
            operation=operation,
            payload=payload,
            actor=context.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409 if "already exists" in str(exc) else 422, detail=str(exc)) from exc


@router.get("/{operation}/receive-history", response_model=list[InventoryReceiptHistoryItem])
def inventory_receive_history(
    operation: str,
    limit: int = Query(default=100, ge=1, le=500),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if operation not in {"retail", "production"}:
        raise HTTPException(status_code=404, detail="Inventory operation not found.")
    require_facility_capability(context, engine, operation)
    return InventoryQueryService(engine).receive_history(context.organization_id, context.facility_id, operation, limit)


@router.post("/retail/sales/import", response_model=RetailSalesImportResult, status_code=201)
def import_retail_sales(
    payload: RetailSalesImport,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    require_facility_capability(context, engine, "retail")
    try:
        return InventoryQueryService(engine).import_retail_sales(
            context.organization_id, context.facility_id, payload, context.user_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{operation}/adjustments", response_model=InventoryAdjustmentResult, status_code=201)
def adjust_inventory(
    operation: str,
    payload: InventoryAdjustmentCreate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if operation not in {"retail", "production"}:
        raise HTTPException(status_code=404, detail="Inventory operation not found.")
    if context.role.casefold() not in ADJUSTMENT_ROLES:
        raise HTTPException(status_code=403, detail="Your role does not allow inventory adjustments.")
    require_facility_capability(context, engine, operation)
    try:
        return InventoryQueryService(engine).adjust_inventory(
            context.organization_id, context.facility_id, payload, context.user_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{operation}/packages/{lot_id}/lineage", response_model=PackageLineage)
def package_lineage(
    operation: str,
    lot_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if operation not in {"retail", "production"}:
        raise HTTPException(status_code=404, detail="Inventory operation not found.")
    require_facility_capability(context, engine, operation)
    try:
        return PackageStudioService(engine).source_trail(
            lot_id, organization_id=context.organization_id, facility_id=context.facility_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
