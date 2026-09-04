from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.data_hub_repository import DataHubRepository
from modules.integrations import IntegrationConfigurationService
from modules.regulatory.facility_setup_contracts import (
    build_facility_setup_payload,
    get_facility_setup_action,
    list_facility_setup_actions,
)
from modules.regulatory.registry import get_jurisdiction
from services.metrc_client import MetrcTransport
from ..auth import RequestContext, get_request_context, require_any_facility_capability
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.metrc_context import metrc_scope_key, resolve_metrc_context
from ..services.metrc_master_data_actions import (
    PROMOTED_MASTER_DATA_ACTIONS,
    MetrcMasterDataActionError,
    MetrcMasterDataActionService,
    master_data_confirmation_token,
)

router = APIRouter(prefix="/location-settings", tags=["location-settings"])
DATASET_KEY = "location_settings"
DEFAULTS = {"auto_map_products_during_receive": False, "default_receiving_room": "Receiving"}
WRITE_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa", "trial"}
FACILITY_SETUP_MANAGE_ROLES = {"dev", "admin", "planner", "supervisor"}
FACILITY_CAPABILITIES = ("retail", "production", "cultivation", "commercial")
# Metrc locations/strains v2 reject pageSize > 50. Routine reads stay small;
# operator-triggered master-data edit loads walk bounded 50-row pages.
LIVE_PAGE_SIZE = 20
MASTER_DATA_PAGE_SIZE = 20
MASTER_DATA_EDIT_PAGE_SIZE = 50
MASTER_DATA_EDIT_MAX_PAGES = 20


class LocationSettingsUpdate(BaseModel):
    auto_map_products_during_receive: bool = False
    default_receiving_room: str = Field(default="Receiving", max_length=160)


class MetrcEmployeeIdentityUpdate(BaseModel):
    employee_license_number: str = Field(default="", max_length=160)


class MetrcActionPreview(BaseModel):
    operation_type: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


class MetrcActionExecute(MetrcActionPreview):
    confirmation_id: str = Field(min_length=1, max_length=80)
    confirmation_token: str = Field(min_length=32, max_length=128)


def _load(repository: DataHubRepository, context: RequestContext) -> dict[str, object]:
    source = next(
        (row for row in repository.list_active_sources(context.organization_id, context.facility_id) if str(row.dataset_key) == DATASET_KEY),
        None,
    )
    if source is None:
        return dict(DEFAULTS)
    try:
        parsed = json.loads(source.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return dict(DEFAULTS)
    return {**DEFAULTS, **(parsed if isinstance(parsed, dict) else {})}


def _metrc_configuration(service: IntegrationConfigurationService | None, row: Any) -> dict[str, Any]:
    if service is None or row is None:
        return {}
    public = service.public(row)
    config = public.get("configuration")
    return dict(config) if isinstance(config, dict) else {}


def _trusted_metrc(
    context: RequestContext,
    engine: Engine,
    settings: Settings,
):
    require_any_facility_capability(context, engine, FACILITY_CAPABILITIES)
    try:
        service, metrc = resolve_metrc_context(engine, settings, context)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not metrc.configured:
        raise HTTPException(409, metrc.message)
    if metrc.status != "connected":
        raise HTTPException(409, "Validate the Metrc connection for this exact facility before loading live Facility Setup data.")
    if not metrc.trusted_mapping:
        raise HTTPException(409, "Verify the exact Metrc facility/license mapping before loading live Facility Setup data.")
    return service, metrc


def _transport(metrc) -> MetrcTransport:
    return MetrcTransport(
        state=metrc.state,
        user_api_key=metrc.user_api_key,
        integrator_api_key=metrc.integrator_api_key,
        environment=metrc.environment,
        timeout_seconds=12,
        max_attempts=2,
    )


def _provider_rows(result: dict[str, Any], label: str) -> list[dict[str, Any]]:
    if not result.get("ok"):
        status = 403 if result.get("status") == "forbidden" else 502
        message = str(result.get("message") or "Provider request failed.")
        raise HTTPException(status, f"Metrc {label}: {message}")
    payload = result.get("payload")
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("Data", "data", "Results", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(row) for row in value if isinstance(row, dict)]
    return []


def _permissions_from_payload(value: Any) -> list[str]:
    found: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, str):
            clean = node.strip()
            if clean:
                found.add(clean)
            return
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if isinstance(node, dict):
            for key, item in node.items():
                if isinstance(item, bool):
                    if item:
                        found.add(str(key).strip())
                elif str(key).casefold() in {"name", "permission", "permissionname", "displayname"} and isinstance(item, str):
                    visit(item)
                else:
                    visit(item)

    visit(value)
    return sorted(permission for permission in found if permission)


def _page_query(metrc, page_size: int = LIVE_PAGE_SIZE, page_number: int = 1) -> dict[str, Any]:
    return {
        "licenseNumber": metrc.license_number,
        "pageSize": max(1, min(int(page_size or LIVE_PAGE_SIZE), 50)),
        "pageNumber": max(1, int(page_number or 1)),
    }


def _paged_provider_rows(
    transport: MetrcTransport,
    metrc,
    path: str,
    label: str,
    *,
    page_size: int = MASTER_DATA_EDIT_PAGE_SIZE,
    max_pages: int = MASTER_DATA_EDIT_MAX_PAGES,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Walk user-requested Metrc master-data pages with a hard provider-call bound."""

    safe_page_size = max(1, min(int(page_size or MASTER_DATA_EDIT_PAGE_SIZE), 50))
    safe_max_pages = max(1, min(int(max_pages or MASTER_DATA_EDIT_MAX_PAGES), MASTER_DATA_EDIT_MAX_PAGES))
    rows: list[dict[str, Any]] = []
    pages_loaded = 0
    last_page_count = 0
    for page_number in range(1, safe_max_pages + 1):
        page_rows = _provider_rows(
            transport.get(path, _page_query(metrc, safe_page_size, page_number)),
            label,
        )
        rows.extend(page_rows)
        pages_loaded = page_number
        last_page_count = len(page_rows)
        if last_page_count < safe_page_size:
            break
    truncated = pages_loaded == safe_max_pages and last_page_count == safe_page_size
    return rows, {
        "page_size": safe_page_size,
        "pages_loaded": pages_loaded,
        "records_loaded": len(rows),
        "truncated": truncated,
        "max_pages": safe_max_pages,
    }


def _license_query(metrc) -> dict[str, Any]:
    return {"licenseNumber": metrc.license_number}


def _live_envelope(metrc, page_size: int = LIVE_PAGE_SIZE) -> dict[str, Any]:
    return {
        "source": "metrc_live",
        "jurisdiction_code": metrc.state.upper(),
        "license_number": metrc.license_number,
        "environment": metrc.environment,
        "bounded": True,
        "page_size": page_size,
    }


def _master_data_execution_enabled(metrc, operation_type: str) -> bool:
    return bool(
        str(operation_type or "").strip().casefold() in PROMOTED_MASTER_DATA_ACTIONS
        and str(metrc.state or "").strip().upper() == "MA"
        and str(metrc.environment or "").strip().casefold() == "sandbox"
        and metrc.configured
        and metrc.status == "connected"
        and metrc.trusted_mapping
    )


def _facility_setup_actions(metrc) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for spec in list_facility_setup_actions():
        public = spec.public()
        if _master_data_execution_enabled(metrc, spec.operation_type):
            public["dispatch_enabled"] = True
            public["verification_status"] = "ma_sandbox_write_readback_promoted"
            public["note"] = (
                "This exact MA sandbox create/update action uses the #452 evaluation payload and requires HTTP 200 plus fresh by-ID readback before DoobieLogic marks it verified."
            )
        output.append(public)
    return output


@router.get("")
def get_location_settings(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    return _load(DataHubRepository(engine), context)


@router.post("")
def save_location_settings(
    payload: LocationSettingsUpdate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role can review location settings but cannot change them.")
    room = payload.default_receiving_room.strip() or "Receiving"
    value = {
        "auto_map_products_during_receive": bool(payload.auto_map_products_during_receive),
        "default_receiving_room": room,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    row = DataHubRepository(engine).publish_source(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        dataset_key=DATASET_KEY,
        dataset_label="Location Settings",
        cache_key="_cache_location_settings",
        filename="location_settings.json",
        fingerprint=sha256(raw).hexdigest(),
        payload=raw,
        inspection={"rows": 1, "columns": len(value), "quality": "Ready", "matches": {}, "missing": []},
        content_type="application/json",
        imported_by_user_id=context.user_id,
        imported_by=context.user_id,
    )
    return {**value, "id": str(row.id)}


@router.get("/facility-setup")
def facility_setup_overview(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    require_any_facility_capability(context, engine, FACILITY_CAPABILITIES)
    try:
        service, metrc = resolve_metrc_context(engine, settings, context)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    config = _metrc_configuration(service, metrc.row)
    sections = [
        {"key": "rooms", "label": "Rooms & Locations", "priority": "P0", "status": "live-read", "description": "Metrc locations and sublocations, with reviewed create/edit/discontinue requests."},
        {"key": "strains", "label": "Strains", "priority": "P0", "status": "live-read", "description": "Active/inactive Metrc strains and staged master-data actions."},
        {"key": "items", "label": "Products & Metrc Items", "priority": "P0", "status": "live-read", "description": "Inspect active/inactive Metrc items, brands, item categories, and units of measure from the active facility."},
        {"key": "production", "label": "Production Processes", "priority": "P1", "status": "live-read", "description": "Inspect Metrc Processing Job Types, categories, and attributes without putting provider latency on routine page load."},
        {"key": "cultivation", "label": "Cultivation Programs", "priority": "P1", "status": "live-read", "description": "Inspect active/inactive Metrc additive templates used by cultivation while unverified provider-changing actions remain locked."},
        {"key": "transportation", "label": "Transportation", "priority": "P2", "status": "live-read", "description": "Inspect Metrc transport drivers and vehicles used by transfer and manifest workflows."},
    ]
    promoted = str(metrc.state or "").strip().upper() == "MA" and str(metrc.environment or "").strip().casefold() == "sandbox"
    return {
        "workspace": "Facility Setup",
        "facility_id": context.facility_id,
        "role": context.role,
        "can_manage": context.role.casefold() in FACILITY_SETUP_MANAGE_ROLES,
        "metrc": {
            "configured": metrc.configured,
            "status": metrc.status,
            "trusted_mapping": metrc.trusted_mapping,
            "jurisdiction_code": metrc.state.upper() if metrc.state else "",
            "license_number": metrc.license_number,
            "environment": metrc.environment,
            "employee_license_number": str(config.get("employee_license_number") or ""),
            "message": metrc.message,
        },
        "sections": sections,
        "actions": _facility_setup_actions(metrc),
        "lab_data_scope": {
            "mode": "read_only",
            "included": ["testing status", "results", "COA/document references", "retest/remediation context", "release readiness"],
            "excluded": ["record lab result", "release lab result", "lab employee workflow"],
        },
        "retail_scope": {"mode": "deferred", "message": "POS/register, patient, receipt, and retail-delivery operations are intentionally outside this phase."},
        "documentation_scope": (
            "The six #452 location/strain/item create/update contracts are promoted for the trusted Massachusetts sandbox and require HTTP 200 plus fresh exact by-ID readback. Other documented Facility Setup mutations remain preview-only until separately proven."
            if promoted
            else "Metrc v2 Facility Setup request previews are bounded to reviewed provider fields; provider dispatch remains locked until jurisdiction-specific sandbox write/readback verification."
        ),
    }


@router.post("/metrc-employee")
def save_metrc_employee_identity(
    payload: MetrcEmployeeIdentityUpdate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    if context.role.casefold() not in FACILITY_SETUP_MANAGE_ROLES:
        raise HTTPException(403, "Your DoobieLogic role cannot change Facility Setup identity settings.")
    try:
        service, metrc = resolve_metrc_context(engine, settings, context)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    if service is None or metrc.row is None:
        raise HTTPException(409, "Save the Metrc connection for this facility before adding an employee license number.")
    existing = service.public(metrc.row)
    configuration = dict(existing.get("configuration") or {})
    configuration["employee_license_number"] = payload.employee_license_number.strip()
    prior_status = str(existing.get("status") or "")
    saved = service.save(
        scope_type="user",
        scope_key=metrc_scope_key(context),
        provider="metrc",
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        configuration=configuration,
        secret=None,
        actor=context.user_id,
    )
    if prior_status == "connected":
        saved = service.validation_result(saved.id, ok=True)
    return {
        "employee_license_number": configuration["employee_license_number"],
        "status": saved.status,
        "message": "Metrc employee identity saved for permission introspection at this facility.",
    }


@router.get("/metrc-permissions")
def metrc_permissions(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    service, metrc = _trusted_metrc(context, engine, settings)
    config = _metrc_configuration(service, metrc.row)
    employee_license = str(config.get("employee_license_number") or "").strip()
    if not employee_license:
        return {
            "status": "identity_missing",
            "can_introspect": False,
            "permissions": [],
            "message": "Add this user's Metrc employee license number to check facility-specific permissions. Metrc still enforces the user API key on every provider request.",
        }
    result = _transport(metrc).get(
        "employees/v2/permissions",
        {"employeeLicenseNumber": employee_license, "licenseNumber": metrc.license_number},
    )
    if result.get("status") == "forbidden":
        return {
            "status": "provider_enforced",
            "can_introspect": False,
            "permissions": [],
            "message": "Metrc did not allow permission introspection for this user. This endpoint itself requires Manage Employees; provider permissions will still be enforced on each action.",
        }
    if not result.get("ok"):
        raise HTTPException(502, str(result.get("message") or "Metrc permission lookup failed."))
    permissions = _permissions_from_payload(result.get("payload"))
    return {
        "status": "synced",
        "can_introspect": True,
        "permissions": permissions,
        "employee_license_number": employee_license,
        "message": "Facility-specific Metrc permissions loaded for this employee.",
    }


@router.get("/metrc-rooms")
def metrc_rooms(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _, metrc = _trusted_metrc(context, engine, settings)
    transport = _transport(metrc)
    active, active_page = _paged_provider_rows(transport, metrc, "locations/v2/active", "active locations")
    inactive, inactive_page = _paged_provider_rows(transport, metrc, "locations/v2/inactive", "inactive locations")
    types = _provider_rows(transport.get("locations/v2/types", _license_query(metrc)), "location types")
    sublocations, sublocation_page = _paged_provider_rows(transport, metrc, "sublocations/v2/active", "active sublocations")
    inactive_sublocations, inactive_sublocation_page = _paged_provider_rows(transport, metrc, "sublocations/v2/inactive", "inactive sublocations")
    return {
        **_live_envelope(metrc, MASTER_DATA_EDIT_PAGE_SIZE),
        "locations": active,
        "inactive_locations": inactive,
        "location_types": types,
        "sublocations": sublocations,
        "inactive_sublocations": inactive_sublocations,
        "pagination": {
            "locations": active_page,
            "inactive_locations": inactive_page,
            "sublocations": sublocation_page,
            "inactive_sublocations": inactive_sublocation_page,
        },
    }


@router.get("/metrc-strains")
def metrc_strains(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _, metrc = _trusted_metrc(context, engine, settings)
    transport = _transport(metrc)
    active, active_page = _paged_provider_rows(transport, metrc, "strains/v2/active", "active strains")
    inactive, inactive_page = _paged_provider_rows(transport, metrc, "strains/v2/inactive", "inactive strains")
    return {
        **_live_envelope(metrc, MASTER_DATA_EDIT_PAGE_SIZE),
        "strains": active,
        "inactive_strains": inactive,
        "pagination": {"strains": active_page, "inactive_strains": inactive_page},
    }


@router.get("/metrc-items")
def metrc_items(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _, metrc = _trusted_metrc(context, engine, settings)
    transport = _transport(metrc)
    active, active_page = _paged_provider_rows(transport, metrc, "items/v2/active", "active items")
    inactive, inactive_page = _paged_provider_rows(transport, metrc, "items/v2/inactive", "inactive items")
    categories, category_page = _paged_provider_rows(transport, metrc, "items/v2/categories", "item categories")
    brands, brand_page = _paged_provider_rows(transport, metrc, "items/v2/brands", "item brands")
    units = _provider_rows(transport.get("unitsofmeasure/v2/active", {}), "units of measure")
    return {
        **_live_envelope(metrc, MASTER_DATA_EDIT_PAGE_SIZE),
        "items": active,
        "inactive_items": inactive,
        "categories": categories,
        "brands": brands,
        "units_of_measure": units,
        "pagination": {
            "items": active_page,
            "inactive_items": inactive_page,
            "categories": category_page,
            "brands": brand_page,
        },
    }


@router.get("/metrc-processing-setup")
def metrc_processing_setup(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _, metrc = _trusted_metrc(context, engine, settings)
    transport = _transport(metrc)
    common = _page_query(metrc, MASTER_DATA_PAGE_SIZE)
    license_query = _license_query(metrc)
    active = _provider_rows(transport.get("processing/v2/jobtypes/active", common), "active processing job types")
    inactive = _provider_rows(transport.get("processing/v2/jobtypes/inactive", common), "inactive processing job types")
    attributes = _provider_rows(transport.get("processing/v2/jobtypes/attributes", license_query), "processing job type attributes")
    categories = _provider_rows(transport.get("processing/v2/jobtypes/categories", license_query), "processing job type categories")
    return {
        **_live_envelope(metrc, MASTER_DATA_PAGE_SIZE),
        "job_types": active,
        "inactive_job_types": inactive,
        "attributes": attributes,
        "categories": categories,
    }


@router.get("/metrc-additive-templates")
def metrc_additive_templates(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _, metrc = _trusted_metrc(context, engine, settings)
    transport = _transport(metrc)
    common = _page_query(metrc, MASTER_DATA_PAGE_SIZE)
    active = _provider_rows(transport.get("additivestemplates/v2/active", common), "active additive templates")
    inactive = _provider_rows(transport.get("additivestemplates/v2/inactive", common), "inactive additive templates")
    return {
        **_live_envelope(metrc, MASTER_DATA_PAGE_SIZE),
        "additive_templates": active,
        "inactive_additive_templates": inactive,
    }


@router.get("/metrc-transportation")
def metrc_transportation(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _, metrc = _trusted_metrc(context, engine, settings)
    transport = _transport(metrc)
    common = _page_query(metrc, MASTER_DATA_PAGE_SIZE)
    drivers = _provider_rows(transport.get("transporters/v2/drivers", common), "transport drivers")
    vehicles = _provider_rows(transport.get("transporters/v2/vehicles", common), "transport vehicles")
    return {
        **_live_envelope(metrc, MASTER_DATA_PAGE_SIZE),
        "drivers": drivers,
        "vehicles": vehicles,
    }


@router.post("/metrc-action-preview")
def metrc_action_preview(
    request: MetrcActionPreview,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    if context.role.casefold() not in FACILITY_SETUP_MANAGE_ROLES:
        raise HTTPException(403, "Your DoobieLogic role can review Facility Setup but cannot prepare provider-changing actions.")
    _, metrc = _trusted_metrc(context, engine, settings)
    profile = get_jurisdiction(metrc.state)
    if profile is None or not profile.documentation_verified:
        raise HTTPException(409, "Facility Setup request previews require a documentation-verified Metrc jurisdiction. Provider execution remains unavailable.")
    spec = get_facility_setup_action(request.operation_type)
    if spec is None:
        raise HTTPException(422, "Select a registered Facility Setup action.")
    try:
        body = build_facility_setup_payload(spec.operation_type, request.payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    path = spec.path
    if "{id}" in path:
        provider_id = request.payload.get("id")
        if provider_id in (None, ""):
            raise HTTPException(422, "Provider ID is required for this action.")
        path = path.replace("{id}", str(provider_id))

    dispatch_enabled = _master_data_execution_enabled(metrc, spec.operation_type)
    confirmation_id = str(uuid4()) if dispatch_enabled else ""
    confirmation_token = ""
    if dispatch_enabled:
        try:
            confirmation_token = master_data_confirmation_token(
                operation_type=spec.operation_type,
                payload=request.payload,
                state=metrc.state,
                environment=metrc.environment,
                license_number=metrc.license_number,
                confirmation_id=confirmation_id,
            )
        except MetrcMasterDataActionError as exc:
            raise HTTPException(422, str(exc)) from exc

    operation = spec.public()
    if dispatch_enabled:
        operation["dispatch_enabled"] = True
        operation["verification_status"] = "ma_sandbox_write_readback_promoted"
        operation["note"] = "Human confirmation submits this exact #452-reviewed request and requires fresh by-ID readback before verification."

    return {
        "operation": operation,
        "jurisdiction": {
            "code": profile.code,
            "documentation_verified": profile.documentation_verified,
            "documentation_url": profile.documentation_url,
        },
        "provider_request": {
            "method": spec.method,
            "path": path,
            "query": {"licenseNumber": metrc.license_number},
            "body": body,
        },
        "dispatch_enabled": dispatch_enabled,
        "requires_human_confirmation": True,
        "confirmation_id": confirmation_id,
        "confirmation_token": confirmation_token,
        "message": (
            "Review this change, then confirm it. DoobieLogic will submit the exact reviewed Massachusetts sandbox request, capture the HTTP result, perform fresh exact by-ID readback, and mark the action verified only when that readback matches."
            if dispatch_enabled
            else "Request preview validated against the bounded v2 adapter. Network execution remains locked until this exact action passes its controlled Metrc sandbox write and fresh readback promotion gate."
        ),
    }


@router.post("/metrc-action-execute")
def metrc_action_execute(
    request: MetrcActionExecute,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    if context.role.casefold() not in FACILITY_SETUP_MANAGE_ROLES:
        raise HTTPException(403, "Your DoobieLogic role cannot confirm Facility Setup provider actions.")
    _, metrc = _trusted_metrc(context, engine, settings)
    if not _master_data_execution_enabled(metrc, request.operation_type):
        raise HTTPException(409, "This Facility Setup action is not promoted for execution in the active Metrc facility/environment.")
    try:
        result = MetrcMasterDataActionService(engine).execute(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            actor=context.user_id,
            operation_type=request.operation_type,
            payload=request.payload,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
            integrator_api_key=metrc.integrator_api_key,
            user_api_key=metrc.user_api_key,
            confirmation_id=request.confirmation_id,
            confirmation_token=request.confirmation_token,
        )
    except MetrcMasterDataActionError as exc:
        raise HTTPException(422, str(exc)) from exc
    return result
