from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine

from modules.package_studio.service import PackageStudioService
from modules.traceability.inventory_adjustment import run_tracked_metrc_adjustment
from services.metrc_inventory_adjustments import fetch_package_adjustment_reasons
from services.metrc_receiving import (
    fetch_all_delivery_packages,
    fetch_all_incoming_transfers,
    fetch_all_transfer_deliveries,
    fetch_metrc_lab_results,
)
from ..auth import RequestContext, get_request_context, require_facility_capability
from ..config import Settings, get_settings
from ..database import get_engine
from ..schemas.inventory import (
    InventoryAdjustmentCreate,
    InventoryAdjustmentResult,
    InventoryReceiptCreate,
    InventoryReceiptHistoryItem,
    InventoryReceiptResult,
    InventoryResponse,
    PackageLineage,
    ProductOption,
    RetailSalesImport,
    RetailSalesImportResult,
)
from ..services.inventory import InventoryQueryService
from ..services.inventory_receiving import InventoryReceiptBatchService
from ..services.metrc_context import resolve_metrc_context

router = APIRouter(prefix="/inventory", tags=["inventory"])
ADJUSTMENT_ROLES = {"dev", "admin", "supervisor", "operator", "qa"}
RECEIVING_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa", "read_only", "trial", "user"}
LOCAL_ADJUSTMENT_REASONS = (
    "Inventory count correction",
    "Scale variance",
    "Damage / destruction",
    "Waste / disposal",
    "Found inventory",
    "Entry error",
    "Other",
)


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


def _require_operation(operation: str) -> None:
    if operation not in {"retail", "production"}:
        raise HTTPException(status_code=404, detail="Inventory operation not found.")


def _require_receiving(context: RequestContext) -> None:
    if context.role.casefold() not in RECEIVING_ROLES:
        raise HTTPException(status_code=403, detail="Your role does not allow inventory receiving.")


def _require_adjustment(context: RequestContext) -> None:
    if context.role.casefold() not in ADJUSTMENT_ROLES:
        raise HTTPException(status_code=403, detail="Your role does not allow inventory adjustments.")


def _metrc_context(
    *, context: RequestContext, engine: Engine, settings: Settings, operation: str
):
    _require_operation(operation)
    _require_receiving(context)
    require_facility_capability(context, engine, operation)
    try:
        _, metrc = resolve_metrc_context(engine, settings, context)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return metrc


def _adjustment_metrc_context(*, context: RequestContext, engine: Engine, settings: Settings, operation: str):
    _require_operation(operation)
    _require_adjustment(context)
    require_facility_capability(context, engine, operation)
    try:
        _, metrc = resolve_metrc_context(engine, settings, context)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return metrc


def _transfer_row(item: dict) -> dict:
    return {
        "transfer_id": str(item.get("Id") or item.get("TransferId") or ""),
        "delivery_id": str(item.get("DeliveryId") or ""),
        "manifest": str(item.get("ManifestNumber") or ""),
        "vendor": str(item.get("ShipperFacilityName") or item.get("ShipperFacilityLicenseNumber") or ""),
        "vendor_license": str(item.get("ShipperFacilityLicenseNumber") or ""),
        "package_count": int(item.get("PackageCount") or item.get("DeliveryPackageCount") or 0),
        "received_count": int(item.get("ReceivedPackageCount") or item.get("DeliveryReceivedPackageCount") or 0),
        "estimated_arrival": str(item.get("EstimatedArrivalDateTime") or ""),
        "source": "Metrc",
    }


def _package_row(item: dict, delivery: dict) -> dict:
    shipped = float(item.get("ShippedQuantity") or item.get("Quantity") or 0.0)
    received = float(item.get("ReceivedQuantity") or 0.0)
    quantity = max(0.0, shipped - received) if shipped else received
    package_label = str(item.get("PackageLabel") or item.get("Label") or item.get("PackageTag") or "")
    return {
        "package_record_id": str(item.get("Id") or item.get("PackageId") or ""),
        "package_id": package_label,
        "item_id": str(item.get("ItemId") or ""),
        "item_name": str(item.get("ItemName") or item.get("ProductName") or item.get("Name") or ""),
        "category": str(item.get("ItemCategoryName") or item.get("CategoryName") or ""),
        "quantity": quantity,
        "shipped_quantity": shipped,
        "received_quantity": received,
        "unit": str(item.get("ShippedUnitOfMeasureName") or item.get("UnitOfMeasureName") or item.get("Unit") or "unit"),
        "shipment_state": str(item.get("ShipmentPackageState") or item.get("State") or ""),
        "lab_testing_state": str(item.get("LabTestingState") or item.get("LabTestResultStatus") or ""),
        "delivery_id": str(delivery.get("Id") or delivery.get("DeliveryId") or ""),
        "delivery_number": str(delivery.get("DeliveryNumber") or ""),
    }


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


@router.get("/{operation}/inbound")
def inbound_queue(
    operation: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _metrc_context(context=context, engine=engine, settings=settings, operation=operation)
    if not metrc.configured:
        return {"configured": False, "message": metrc.message, "transfers": []}
    result = fetch_all_incoming_transfers(
        state=metrc.state,
        user_api_key=metrc.user_api_key,
        integrator_api_key=metrc.integrator_api_key,
        license_number=metrc.license_number,
    )
    if not result.get("ok"):
        raise HTTPException(502, str(result.get("message") or "METRC inbound transfer request failed."))
    transfers = [_transfer_row(row) for row in result.get("transfers") or []]
    transfers = [row for row in transfers if row["transfer_id"]]
    return {
        "configured": True,
        "message": "METRC inbound queue loaded. State acceptance remains read-only and must still occur in METRC.",
        "license_number": metrc.license_number,
        "transfers": transfers,
    }


@router.get("/{operation}/inbound/{transfer_id}")
def inbound_transfer_details(
    operation: str,
    transfer_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _metrc_context(context=context, engine=engine, settings=settings, operation=operation)
    if not metrc.configured:
        raise HTTPException(422, metrc.message)
    deliveries_result = fetch_all_transfer_deliveries(
        state=metrc.state,
        user_api_key=metrc.user_api_key,
        integrator_api_key=metrc.integrator_api_key,
        transfer_id=transfer_id,
    )
    if not deliveries_result.get("ok"):
        raise HTTPException(502, str(deliveries_result.get("message") or "METRC transfer delivery request failed."))
    deliveries = list(deliveries_result.get("deliveries") or [])
    packages: list[dict] = []
    warnings: list[str] = []
    for delivery in deliveries:
        delivery_id = str(delivery.get("Id") or delivery.get("DeliveryId") or "").strip()
        if not delivery_id:
            warnings.append("One METRC delivery had no delivery id and could not be expanded.")
            continue
        package_result = fetch_all_delivery_packages(
            state=metrc.state,
            user_api_key=metrc.user_api_key,
            integrator_api_key=metrc.integrator_api_key,
            delivery_id=delivery_id,
        )
        if not package_result.get("ok"):
            warnings.append(str(package_result.get("message") or f"Unable to load packages for delivery {delivery_id}."))
            continue
        packages.extend(_package_row(row, delivery) for row in package_result.get("packages") or [])
    return {
        "transfer_id": transfer_id,
        "deliveries": deliveries,
        "packages": packages,
        "warnings": warnings,
        "read_only_traceability": True,
    }


@router.get("/{operation}/inbound/packages/{package_record_id}/lab-results")
def inbound_package_lab_results(
    operation: str,
    package_record_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _metrc_context(context=context, engine=engine, settings=settings, operation=operation)
    if not metrc.configured:
        raise HTTPException(422, metrc.message)
    result = fetch_metrc_lab_results(
        state=metrc.state,
        user_api_key=metrc.user_api_key,
        integrator_api_key=metrc.integrator_api_key,
        license_number=metrc.license_number,
        package_id=package_record_id,
    )
    if not result.get("ok"):
        raise HTTPException(502, str(result.get("message") or "METRC lab result request failed."))
    return {"package_record_id": package_record_id, "lab_results": result.get("lab_results") or [], "read_only": True}


@router.post("/{operation}/receipts", response_model=InventoryReceiptResult, status_code=201)
def receive_inventory(
    operation: str,
    payload: InventoryReceiptCreate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_operation(operation)
    _require_receiving(context)
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


@router.post("/{operation}/receipts/batch", response_model=list[InventoryReceiptResult], status_code=201)
def receive_inventory_batch(
    operation: str,
    payload: list[InventoryReceiptCreate],
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_operation(operation)
    _require_receiving(context)
    require_facility_capability(context, engine, operation)
    try:
        return InventoryReceiptBatchService(engine).post(
            context.organization_id,
            context.facility_id,
            operation=operation,
            rows=payload,
            actor=context.user_id,
        )
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=409 if "already exists" in detail.casefold() or "duplicate" in detail.casefold() else 422, detail=detail) from exc


@router.get("/{operation}/receive-history", response_model=list[InventoryReceiptHistoryItem])
def inventory_receive_history(
    operation: str,
    limit: int = Query(default=100, ge=1, le=500),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_operation(operation)
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


@router.get("/{operation}/adjustment-reasons")
def inventory_adjustment_reasons(
    operation: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _adjustment_metrc_context(context=context, engine=engine, settings=settings, operation=operation)
    rows: list[dict] = []
    if metrc.configured:
        result = fetch_package_adjustment_reasons(
            state=metrc.state,
            user_api_key=metrc.user_api_key,
            integrator_api_key=metrc.integrator_api_key,
            license_number=metrc.license_number,
        )
        if result.get("ok"):
            rows = [dict(item) for item in result.get("reasons") or [] if isinstance(item, dict)]
    if not rows:
        rows = [{"Name": reason, "RequiresNote": reason == "Other"} for reason in LOCAL_ADJUSTMENT_REASONS]
    return {
        "reasons": [
            {"name": str(row.get("Name") or "").strip(), "requires_note": bool(row.get("RequiresNote"))}
            for row in rows
            if str(row.get("Name") or "").strip()
        ],
        "metrc_ready": bool(metrc.configured),
        "can_bypass": bool(metrc.configured and context.role.casefold() in {"dev", "admin"}),
        "license_number": metrc.license_number if metrc.configured else "",
    }


@router.post("/{operation}/adjustments", response_model=InventoryAdjustmentResult, status_code=201)
def adjust_inventory(
    operation: str,
    payload: InventoryAdjustmentCreate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_operation(operation)
    _require_adjustment(context)
    require_facility_capability(context, engine, operation)
    # Streamlit requires an explicit review confirmation in the operator work
    # window. The React work window enforces that exact interaction before it
    # can call this endpoint. The API keeps backwards compatibility for existing
    # durable callers that predate the UI review checkbox.
    if payload.sync_to_metrc and payload.bypass_state_system:
        raise HTTPException(status_code=422, detail="Choose either METRC sync or state-system bypass, not both.")
    if payload.bypass_state_system and context.role.casefold() not in {"dev", "admin"}:
        raise HTTPException(status_code=403, detail="Only DEV or admin may bypass the state system.")

    service = InventoryQueryService(engine)
    package_snapshot = service.list_packages(
        context.organization_id,
        context.facility_id,
        operation=operation,
    )
    item = next((row for row in package_snapshot.items if row.id == payload.lot_id), None)
    if item is None:
        raise HTTPException(status_code=422, detail="Inventory lot was not found in the active facility.")
    package_id = payload.package_id.strip() or item.package_id.strip()
    if payload.sync_to_metrc and not package_id:
        raise HTTPException(status_code=422, detail="An External Package ID is required for tracked METRC adjustment.")

    metrc = _adjustment_metrc_context(context=context, engine=engine, settings=settings, operation=operation)
    reason_rows: list[dict] = []
    if metrc.configured:
        try:
            reason_result = fetch_package_adjustment_reasons(
                state=metrc.state,
                user_api_key=metrc.user_api_key,
                integrator_api_key=metrc.integrator_api_key,
                license_number=metrc.license_number,
            )
            if reason_result.get("ok"):
                reason_rows = [dict(row) for row in reason_result.get("reasons") or [] if isinstance(row, dict)]
        except Exception:
            reason_rows = []
    if not reason_rows:
        reason_rows = [{"Name": reason, "RequiresNote": reason == "Other"} for reason in LOCAL_ADJUSTMENT_REASONS]
    reason_meta = next((row for row in reason_rows if str(row.get("Name") or "").strip() == payload.reason.strip()), None)
    if reason_meta and bool(reason_meta.get("RequiresNote")) and not payload.reason_note.strip():
        raise HTTPException(status_code=422, detail="This adjustment reason requires a note.")

    if payload.sync_to_metrc:
        if not metrc.configured:
            raise HTTPException(status_code=422, detail="METRC sync was requested, but this user/facility does not have a complete METRC connection.")
        previous = float(item.available)
        final = previous + float(payload.quantity) if payload.adjustment_type == "incremental" else float(payload.quantity)
        metrc_quantity = final - previous if payload.adjustment_type == "incremental" else final
        local_result: list[InventoryAdjustmentResult] = []

        def local_apply() -> tuple[float, str]:
            result = service.adjust_inventory(context.organization_id, context.facility_id, payload, context.user_id)
            local_result.append(result)
            return float(result.delta), str(result.unit)

        try:
            _delta, _unit, traceability_id = run_tracked_metrc_adjustment(
                organization_id=context.organization_id,
                facility_id=context.facility_id,
                actor=context.user_id,
                credentials=metrc,
                package_id=package_id,
                adjustment_type="incremental" if payload.adjustment_type == "incremental" else "absolute",
                quantity=metrc_quantity,
                unit=item.unit,
                reason=payload.reason,
                reason_note=payload.reason_note,
                local_apply=local_apply,
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        result = local_result[0]
        return result.model_copy(update={"metrc_status": "synced", "traceability_transaction_id": traceability_id})

    try:
        result = service.adjust_inventory(context.organization_id, context.facility_id, payload, context.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result.model_copy(update={
        "metrc_status": "bypassed" if payload.bypass_state_system else "not_configured" if not metrc.configured else "local_only",
        "traceability_transaction_id": "",
    })


@router.get("/{operation}/packages/{lot_id}/lineage", response_model=PackageLineage)
def package_lineage(
    operation: str,
    lot_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_operation(operation)
    require_facility_capability(context, engine, operation)
    try:
        return PackageStudioService(engine).source_trail(
            lot_id, organization_id=context.organization_id, facility_id=context.facility_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc