from __future__ import annotations

import os
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.data_hub_repository import DataHubRepository
from modules.extraction.repository import ExtractionRepository
from modules.integrations import IntegrationConfigurationService
from modules.inventory_audit.repository import InventoryAuditRepository
from services.agent_registry import AgentProfile, PROFILES, resolve_agent_profile
from services.doobie_client import DoobieClient
from services.doobie_connection import DEFAULT_DOOBIE_BASE_URL
from services.gemini_agent import GeminiWorkspaceAgent, _frame_records, _objects_frame

from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from .buyer_parity import _model

router = APIRouter(prefix="/ai-agents", tags=["ai-agents"])


class AgentMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=8000)


class AgentRun(BaseModel):
    agent_key: str = Field(default="", max_length=64)
    app_mode: str = Field(default="", max_length=120)
    section: str = Field(default="", max_length=160)
    question: str = Field(min_length=1, max_length=8000)
    history: list[AgentMessage] = Field(default_factory=list, max_length=20)


def _profile_payload(profile: AgentProfile) -> dict[str, Any]:
    return {
        "key": profile.key,
        "name": profile.name,
        "role": profile.role,
        "description": profile.description,
        "focus": list(profile.focus),
        "suggested_questions": list(profile.suggested_questions),
        "compliance_grounded_only": profile.compliance_grounded_only,
    }


def _active_profile(agent_key: str, app_mode: str, section: str) -> AgentProfile:
    requested = str(agent_key or "").strip().casefold()
    if requested:
        profile = PROFILES.get(requested)
        if profile is None:
            raise HTTPException(422, f"Unknown AI agent '{agent_key}'.")
        return profile
    return resolve_agent_profile(app_mode, section)


def _integration_service(engine: Engine, settings: Settings) -> IntegrationConfigurationService | None:
    try:
        return IntegrationConfigurationService(engine, settings.integration_encryption_key)
    except RuntimeError:
        return None


def _doobie_configuration(engine: Engine, settings: Settings) -> tuple[str, str, str]:
    service = _integration_service(engine, settings)
    if service is None:
        return DEFAULT_DOOBIE_BASE_URL, "", "not_connected"
    row = service.get("platform", "global", "doobie")
    if row is None:
        return DEFAULT_DOOBIE_BASE_URL, "", "not_connected"
    public = service.public(row)
    configuration = public.get("configuration") or {}
    base_url = str(configuration.get("base_url") or DEFAULT_DOOBIE_BASE_URL).strip().rstrip("/")
    try:
        secret = service.secret(row)
    except RuntimeError:
        secret = ""
    return base_url, secret, str(public.get("status") or "configured")


def _provider_status(engine: Engine, settings: Settings) -> dict[str, Any]:
    gemini_ready = bool(str(os.getenv("GEMINI_API_KEY") or "").strip())
    _base_url, doobie_key, doobie_status = _doobie_configuration(engine, settings)
    doobie_ready = bool(doobie_key)
    if gemini_ready:
        return {"provider": "Gemini", "configured": True, "status": "connected", "fallback_configured": doobie_ready}
    if doobie_ready:
        return {"provider": "Doobie", "configured": True, "status": doobie_status, "fallback_configured": False}
    return {
        "provider": "Not configured",
        "configured": False,
        "status": "not_connected",
        "fallback_configured": False,
        "message": "Configure the platform Doobie AI connection in Data & Settings → AI & METRC Integrations.",
    }


def _put_frame(output: dict[str, pd.DataFrame], name: str, value: Any) -> None:
    if isinstance(value, pd.DataFrame):
        frame = value.copy()
    elif isinstance(value, list):
        frame = _objects_frame(value)
        if frame.empty and value and isinstance(value[0], dict):
            frame = pd.DataFrame(value)
    else:
        frame = _objects_frame([value]) if value is not None else pd.DataFrame()
    if not frame.empty:
        output[name] = frame


def _buyer_datasets(context: RequestContext, engine: Engine) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    try:
        detail, product, inventory, sales, inventory_source, sales_source = _model(context, engine, 21, 1.0, 60)
        output.update(
            {
                "inventory": inventory,
                "sales": sales,
                "buyer_forecast": detail,
                "buyer_product_forecast": product,
                "buyer_sources": pd.DataFrame(
                    [
                        {"dataset": "inventory", "filename": inventory_source.filename, "rows": inventory_source.row_count},
                        {"dataset": "product_sales", "filename": sales_source.filename, "rows": sales_source.row_count},
                    ]
                ),
            }
        )
    except HTTPException as exc:
        output["buyer_data_status"] = pd.DataFrame([{"status": "unavailable", "message": str(exc.detail)}])
    except Exception as exc:
        output["buyer_data_status"] = pd.DataFrame([{"status": "unavailable", "message": str(exc)}])
    return output


def _data_hub_datasets(context: RequestContext, engine: Engine) -> dict[str, pd.DataFrame]:
    rows = DataHubRepository(engine).list_active_sources(context.organization_id, context.facility_id)
    metadata = [
        {
            "dataset_key": getattr(row, "dataset_key", ""),
            "filename": getattr(row, "filename", ""),
            "row_count": getattr(row, "row_count", 0),
            "column_count": getattr(row, "column_count", 0),
            "activated_at": getattr(row, "activated_at", None),
        }
        for row in rows
    ]
    return {"active_data_sources": pd.DataFrame(metadata)} if metadata else {}


def _extraction_datasets(context: RequestContext, engine: Engine) -> dict[str, pd.DataFrame]:
    repo = ExtractionRepository(engine)
    output: dict[str, pd.DataFrame] = {}
    _put_frame(output, "extraction_runs", repo.list_runs(context.organization_id, context.facility_id, include_closed=True, limit=500))
    lots = repo.list_available_lots(context.organization_id, context.facility_id)
    if lots:
        output["extraction_inventory"] = pd.DataFrame(lots)
    return output


def _coman_datasets(context: RequestContext, engine: Engine) -> dict[str, pd.DataFrame]:
    repo = ComanRepository(engine)
    output: dict[str, pd.DataFrame] = {}
    loaders = {
        "production_orders": lambda: repo.list_production_orders(context.organization_id, context.facility_id),
        "production_actuals": lambda: repo.list_production_actuals(context.organization_id, context.facility_id),
        "facility_machines": lambda: repo.list_facility_machines(context.organization_id, context.facility_id),
        "products": lambda: repo.list_products(context.organization_id),
        "inventory_lots": lambda: repo.list_inventory_lots(context.organization_id, context.facility_id),
        "inventory_transactions": lambda: repo.list_inventory_transactions(context.organization_id, context.facility_id, limit=250),
        "material_reservations": lambda: repo.list_material_reservations(context.organization_id, context.facility_id),
    }
    for name, loader in loaders.items():
        try:
            _put_frame(output, name, loader())
        except Exception:
            continue
    return output


def _commercial_datasets(context: RequestContext, engine: Engine) -> dict[str, pd.DataFrame]:
    repo = CommercialRepository(engine)
    output: dict[str, pd.DataFrame] = {}
    loaders = {
        "trade_partners": lambda: repo.list_trade_partners(context.organization_id),
        "commercial_orders": lambda: repo.list_orders(context.organization_id, context.facility_id),
        "commercial_order_lines": lambda: repo.list_order_lines(context.organization_id),
        "order_allocations": lambda: repo.list_allocations(context.organization_id, context.facility_id),
        "commercial_transactions": lambda: repo.list_commercial_transactions(context.organization_id, context.facility_id),
    }
    for name, loader in loaders.items():
        try:
            _put_frame(output, name, loader())
        except Exception:
            continue
    return output


def _audit_datasets(context: RequestContext, engine: Engine, app_mode: str) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    operation_type = "production" if "production" in str(app_mode or "").casefold() else "retail"
    try:
        repo = InventoryAuditRepository(engine)
        audits = repo.list_audits(context.organization_id, context.facility_id, operation_type=operation_type)
        _put_frame(output, "inventory_audits", audits)
        active = next((row for row in audits if getattr(row, "status", "") in {"in_progress", "paused", "stopped"}), audits[0] if audits else None)
        if active is not None:
            _put_frame(output, "audit_lines", repo.list_lines(context.organization_id, active.id))
            _put_frame(output, "audit_scans", repo.list_scans(context.organization_id, active.id))
    except Exception:
        return output
    return output


def _datasets_for(profile: AgentProfile, context: RequestContext, engine: Engine, app_mode: str) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    buyer_keys = {"ops", "buyer", "purchasing", "inventory", "compliance", "nomenclature", "data_hub"}
    if profile.key in buyer_keys:
        output.update(_buyer_datasets(context, engine))
    if profile.key in {"ops", "data_hub"}:
        output.update(_data_hub_datasets(context, engine))
    if profile.key in {"ops", "extraction"}:
        output.update(_extraction_datasets(context, engine))
    if profile.key in {"ops", "coman", "repack"}:
        output.update(_coman_datasets(context, engine))
    if profile.key in {"ops", "commercial"}:
        output.update(_commercial_datasets(context, engine))
    if profile.key in {"ops", "audit"}:
        output.update(_audit_datasets(context, engine, app_mode))
    return output


def _doobie_persona(profile: AgentProfile) -> str:
    return {
        "buyer": "buyer",
        "purchasing": "buyer",
        "inventory": "inventory",
        "audit": "inventory",
        "compliance": "compliance",
        "nomenclature": "buyer",
        "repack": "ops",
        "coman": "ops",
        "extraction": "extraction",
        "commercial": "ops",
        "data_hub": "ops",
        "ops": "ops",
    }.get(profile.key, "ops")


def _sanitized_context(datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
    return {
        name: {"rows": int(len(frame)), "preview": _frame_records(frame, limit=40)}
        for name, frame in datasets.items()
        if isinstance(frame, pd.DataFrame)
    }


@router.get("")
def agents(
    app_mode: str = "",
    section: str = "",
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    active = resolve_agent_profile(app_mode, section)
    return {
        "active_agent": _profile_payload(active),
        "agents": [_profile_payload(profile) for profile in PROFILES.values()],
        "provider": _provider_status(engine, settings),
        "workspace": {"app_mode": app_mode, "section": section, "organization_id": context.organization_id, "facility_id": context.facility_id},
    }


@router.post("/run")
def run_agent(
    payload: AgentRun,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    profile = _active_profile(payload.agent_key, payload.app_mode, payload.section)
    datasets = _datasets_for(profile, context, engine, payload.app_mode)
    history = [item.model_dump() for item in payload.history][-20:]
    provider_errors: list[str] = []

    gemini = GeminiWorkspaceAgent(profile=profile)
    if gemini.enabled:
        try:
            answer = gemini.run(
                payload.question.strip(),
                datasets,
                app_mode=payload.app_mode,
                section=payload.section,
                history=history,
                profile=profile,
            )
            return {
                "answer": answer,
                "provider": "Gemini",
                "agent": _profile_payload(profile),
                "datasets": sorted(datasets),
                "read_only": True,
            }
        except Exception as exc:
            provider_errors.append(f"Gemini: {exc}")

    base_url, api_key, _status = _doobie_configuration(engine, settings)
    if api_key:
        client = DoobieClient(base_url=base_url, api_key=api_key, timeout_seconds=12)
        framed_question = (
            f"You are {profile.name}, {profile.role}. Focus on {', '.join(profile.focus)}. "
            f"This is read-only analysis; do not claim to modify operational systems.\n\n{payload.question.strip()}"
        )
        result = client.copilot(
            question=framed_question,
            data=_sanitized_context(datasets),
            persona=_doobie_persona(profile),
            state="MA",
            department=profile.key,
            history=history,
        )
        answer = str(result.get("answer") or "").strip()
        if answer and result.get("error") not in {"missing_service_key", "service_key_rejected", "disabled"}:
            return {
                "answer": answer,
                "provider": "Doobie",
                "agent": _profile_payload(profile),
                "datasets": sorted(datasets),
                "read_only": True,
                "confidence": result.get("confidence"),
                "sources": result.get("sources") or [],
            }
        provider_errors.append(f"Doobie: {result.get('error') or 'no response'}")

    detail = " · ".join(provider_errors)
    message = "AI agents are restored, but no live AI provider is configured. Level DEV can connect Doobie AI in Data & Settings → AI & METRC Integrations."
    if detail:
        message += f" Provider detail: {detail}"
    raise HTTPException(503, message)
