from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Literal

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
from services.metrc_client import MetrcTransport
from ..auth import RequestContext, get_request_context, require_any_facility_capability
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.metrc_context import metrc_scope_key, resolve_metrc_context

router = APIRouter(prefix="/location-settings", tags=["location-settings"])
DATASET_KEY = "location_settings"
DEFAULTS = {"auto_map_products_during_receive": False, "default_receiving_room": "Receiving"}
WRITE_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa", "trial"}
FACILITY_SETUP_MANAGE_ROLES = {"dev", "admin", "planner", "supervisor"}
FACILITY_CAPABILITIES = ("retail", "production", "cultivation", "commercial")


class LocationSettingsUpdate(BaseModel):
    auto_map_products_during_receive: bool = False
    default_receiving_room: str = Field(default="Receiving", max_length=160)


class MetrcEmployeeIdentityUpdate(BaseModel):
    employee_license_number: str = Field(default="", max_length=160)


class MetrcActionPreview(BaseModel):
    operation_type: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


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
        timeout_seconds=12,
        max_attempts=2,
    )


def _provider_rows(result: dict[str, Any], label: str) -> list[dict[str, Any]]:
    if not result.get("ok"):
        status = 403 if result.get("status") == "forbidden" else 502
        raise HTTPException(status, str(result.get("message") or f"Metrc {label} request failed."))
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
        {"key": "items", "label": "Products & Metrc Items", "priority": "P0", "status": "catalogued", "description": "Item and brand administration is registered for the next payload-verification pass."},
        {"key": "production", "label": "Production Processes", "priority": "P1", "status": "catalogued", "description": "Processing Job Type administration stays in Facility Setup rather than a hidden Metrc screen."},
        {"key": "cultivation", "label": "Cultivation Programs", "priority": "P1", "status": "catalogued", "description": "Additive templates and cultivation setup are registered without enabling unverified writes."},
        {"key": "transportation", "label": "Transportation", "priority": "P2", "status": "catalogued", "description": "Driver and vehicle administration is registered for transfer/manifest workflows."},
    ]
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
        "actions": [row.public() for row in list_facility_setup_actions()],
        "lab_data_scope": {
            "mode": "read_only",
            "included": ["testing status", "results", "COA/document references", "retest/remediation context", "release readiness"],
            "excluded": ["record lab result", "release lab result", "lab employee workflow"],
        },
        "retail_scope": {"mode": "deferred", "message": "POS/register, patient, receipt, and retail-delivery operations are intentionally outside this phase."},
        "documentation_scope": "MA v2 master-data writes are documented here; provider dispatch remains locked until sandbox write/readback verification.",
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
    common = {"licenseNumber": metrc.license_number, "pageSize": 100, "pageNumber": 1}
    active = _provider_rows(transport.get("locations/v2/active", common), "active locations")
    inactive = _provider_rows(transport.get("locations/v2/inactive", common), "inactive locations")
    types = _provider_rows(transport.get("locations/v2/types", {"licenseNumber": metrc.license_number}), "location types")
    sublocations = _provider_rows(transport.get("sublocations/v2/active", common), "active sublocations")
    inactive_sublocations = _provider_rows(transport.get("sublocations/v2/inactive", common), "inactive sublocations")
    return {
        "source": "metrc_live",
        "jurisdiction_code": metrc.state.upper(),
        "license_number": metrc.license_number,
        "environment": metrc.environment,
        "locations": active,
        "inactive_locations": inactive,
        "location_types": types,
        "sublocations": sublocations,
        "inactive_sublocations": inactive_sublocations,
        "bounded": True,
        "page_size": 100,
    }


@router.get("/metrc-strains")
def metrc_strains(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _, metrc = _trusted_metrc(context, engine, settings)
    transport = _transport(metrc)
    common = {"licenseNumber": metrc.license_number, "pageSize": 100, "pageNumber": 1}
    active = _provider_rows(transport.get("strains/v2/active", common), "active strains")
    inactive = _provider_rows(transport.get("strains/v2/inactive", common), "inactive strains")
    return {
        "source": "metrc_live",
        "jurisdiction_code": metrc.state.upper(),
        "license_number": metrc.license_number,
        "environment": metrc.environment,
        "strains": active,
        "inactive_strains": inactive,
        "bounded": True,
        "page_size": 100,
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
    if metrc.state.upper() != "MA":
        raise HTTPException(409, "This first Facility Setup write-contract pass is verified against the current Massachusetts v2 documentation only.")
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
    return {
        "operation": spec.public(),
        "provider_request": {
            "method": spec.method,
            "path": path,
            "query": {"licenseNumber": metrc.license_number},
            "body": body,
        },
        "dispatch_enabled": False,
        "requires_human_confirmation": True,
        "message": "Request validated. Network execution remains locked until a controlled Metrc sandbox write and fresh readback verify this contract; DoobieLogic will not fake success.",
    }
