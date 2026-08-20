"""Durable DEV Sandbox source-file persistence backed by Supabase PostgreSQL.

The living demo remains easy to regenerate, but its published source files are
persisted in the same tenant/facility-scoped Data Hub repository used by real
uploads. Streamlit session state is treated as a cache, never the authoritative
copy for sandbox files once a database is available.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from typing import Any, Mapping, MutableMapping

import pandas as pd

from modules.coman.db import create_coman_engine
from modules.data_hub_repository import DataHubRepository, PublishedSource


SANDBOX_DATASET_PREFIX = "sandbox_"
SANDBOX_MANIFEST_DATASET_KEY = "sandbox_state"
SANDBOX_MANIFEST_CACHE_KEY = "_sandbox_state_manifest"
SANDBOX_CONTRACT_VERSION = "sandbox-v6-120d-inventory-complete"
SANDBOX_REQUIRED_SOURCE_KEYS = {
    "buyer_catalog",
    "buyer_inventory",
    "buyer_sales",
    "buyer_extra_sales",
    "buyer_quarantine",
    "delivery_manifest",
    "delivery_sales",
    "compliance_sources",
    "production_inventory",
    "extraction_inventory",
    "extraction_runs",
    "extraction_jobs",
    "nomenclature_catalog",
    "nomenclature_manifest",
    "commercial_partners",
    "commercial_orders",
    "commercial_order_lines",
    "commercial_ledger",
    "production_orders",
    "production_machines",
    "production_crew",
    "purchasing_budget",
}


@dataclass(frozen=True)
class RestoredSandbox:
    manifest: dict[str, Any]
    sources: dict[str, PublishedSource]

    @property
    def available(self) -> bool:
        return bool(manifest_version(self.manifest) == SANDBOX_CONTRACT_VERSION and self.sources)


def manifest_version(manifest: Mapping[str, Any]) -> str:
    return str(manifest.get("contract_version") or manifest.get("version") or "").strip()


def _repository(repository: DataHubRepository | None = None) -> DataHubRepository:
    return repository or DataHubRepository(create_coman_engine())


def _scope(state: MutableMapping[str, Any]) -> tuple[str, str]:
    organization_id = str(state.get("active_organization_id") or "").strip()
    facility_id = str(state.get("active_facility_id") or "").strip()
    if not organization_id or not facility_id:
        raise ValueError("DEV Sandbox requires an active organization and facility before persistence.")
    return organization_id, facility_id


def _dataset_key(source_key: str) -> str:
    value = f"{SANDBOX_DATASET_PREFIX}{source_key}"
    if len(value) > 48:
        raise ValueError(f"Sandbox source key is too long for durable storage: {source_key}")
    return value


def _source_key(dataset_key: str) -> str:
    if not str(dataset_key).startswith(SANDBOX_DATASET_PREFIX):
        return ""
    return str(dataset_key)[len(SANDBOX_DATASET_PREFIX) :]


def _csv_inspection(payload: bytes) -> dict[str, Any]:
    try:
        frame = pd.read_csv(BytesIO(payload))
    except Exception:
        return {"rows": 0, "columns": 0, "quality": "Sandbox source"}
    return {
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "quality": "Sandbox source",
        "matches": {},
        "missing": [],
    }


def _manifest_payload(
    state: MutableMapping[str, Any],
    payload: Mapping[str, Any],
    *,
    version: str,
) -> bytes:
    as_of = payload.get("as_of_date")
    if isinstance(as_of, (date, datetime)):
        as_of_value = as_of.isoformat()
    else:
        as_of_value = str(as_of or "")
    manifest = {
        "version": str(version),
        "contract_version": SANDBOX_CONTRACT_VERSION,
        "as_of_date": as_of_value,
        "sales_window_days": 120,
        "scale": str(payload.get("scale") or state.get("demo_dataset_scale") or "medium"),
        "problems": list(payload.get("problems") or state.get("demo_problem_set") or []),
        "company_profile": dict(payload.get("company_profile") or {}),
        "company_seed": int(state.get("demo_company_seed") or 710),
        "catalog_seed": int(state.get("demo_catalog_seed") or 811),
        "history_seed": int(state.get("demo_history_seed") or 912),
        "selected_scenario": str(state.get("demo_selected_scenario") or "Healthy baseline"),
    }
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _production_inventory_upload(payload: Mapping[str, Any]) -> tuple[str, bytes, str] | None:
    frame = payload.get("production_inventory")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    return (
        "demo_production_inventory.csv",
        frame.to_csv(index=False).encode("utf-8"),
        "text/csv",
    )


def persist_sandbox_sources(
    state: MutableMapping[str, Any],
    payload: Mapping[str, Any],
    *,
    version: str,
    actor: str = "demo",
    repository: DataHubRepository | None = None,
) -> int:
    """Publish every generated sandbox source plus a state manifest to Supabase."""

    organization_id, facility_id = _scope(state)
    repo = _repository(repository)
    uploads = dict(payload.get("uploads") or {})
    production_upload = _production_inventory_upload(payload)
    if production_upload is not None:
        uploads["production_inventory"] = production_upload

    missing = SANDBOX_REQUIRED_SOURCE_KEYS - set(uploads)
    if missing:
        raise ValueError(
            "Sandbox payload is incomplete and will not be persisted. Missing: "
            + ", ".join(sorted(missing))
        )

    persisted = 0
    for source_key, upload in sorted(uploads.items()):
        if not isinstance(upload, tuple) or len(upload) != 3:
            continue
        filename, content, mime_type = upload
        content = bytes(content)
        fingerprint = hashlib.sha256(content).hexdigest()
        repo.publish_source(
            organization_id=organization_id,
            facility_id=facility_id,
            dataset_key=_dataset_key(str(source_key)),
            dataset_label=f"DEV Sandbox · {str(source_key).replace('_', ' ').title()}",
            cache_key=f"_sandbox_{source_key}",
            filename=str(filename),
            fingerprint=fingerprint,
            payload=content,
            inspection=_csv_inspection(content),
            content_type=str(mime_type or "text/csv"),
            imported_by=str(actor or "demo"),
            retain_versions=3,
        )
        persisted += 1

    manifest = _manifest_payload(state, payload, version=version)
    repo.publish_source(
        organization_id=organization_id,
        facility_id=facility_id,
        dataset_key=SANDBOX_MANIFEST_DATASET_KEY,
        dataset_label="DEV Sandbox · State Manifest",
        cache_key=SANDBOX_MANIFEST_CACHE_KEY,
        filename="dev_sandbox_state.json",
        fingerprint=hashlib.sha256(manifest).hexdigest(),
        payload=manifest,
        inspection={"rows": 1, "columns": 11, "quality": "Sandbox state"},
        content_type="application/json",
        imported_by=str(actor or "demo"),
        retain_versions=3,
    )
    state["_sandbox_supabase_persisted"] = True
    state["_sandbox_supabase_source_count"] = persisted
    state["_sandbox_contract_version"] = SANDBOX_CONTRACT_VERSION
    state.pop("_sandbox_supabase_error", None)
    return persisted


def _validate_restored_contract(
    manifest: dict[str, Any],
    sources: dict[str, PublishedSource],
) -> tuple[bool, str]:
    version = manifest_version(manifest)
    if version != SANDBOX_CONTRACT_VERSION:
        return False, (
            f"Persisted sandbox contract {version or 'unknown'} is stale; "
            f"{SANDBOX_CONTRACT_VERSION} is required."
        )
    missing = SANDBOX_REQUIRED_SOURCE_KEYS - set(sources)
    if missing:
        return False, "Persisted sandbox source set is incomplete: " + ", ".join(sorted(missing))
    sales = sources.get("buyer_sales")
    if sales is not None:
        try:
            frame = pd.read_csv(BytesIO(sales.payload))
            times = pd.to_datetime(frame.get("Order Time"), errors="coerce").dropna()
            span = int((times.max().normalize() - times.min().normalize()).days) + 1 if not times.empty else 0
            if span != 120:
                return False, f"Persisted sandbox sales span {span} days; 120 days are required."
        except Exception as exc:
            return False, f"Persisted sandbox sales could not be validated: {type(exc).__name__}: {exc}"
    return True, ""


def restore_sandbox_sources(
    state: MutableMapping[str, Any],
    *,
    repository: DataHubRepository | None = None,
) -> RestoredSandbox:
    """Load the active persisted sandbox source set for the selected tenant.

    Stale or incomplete source sets are rejected so the caller can regenerate a
    complete deterministic baseline and republish it into the same Supabase scope.
    """

    organization_id, facility_id = _scope(state)
    records = _repository(repository).list_active_sources(organization_id, facility_id)
    manifest: dict[str, Any] = {}
    sources: dict[str, PublishedSource] = {}
    for record in records:
        if record.dataset_key == SANDBOX_MANIFEST_DATASET_KEY:
            try:
                manifest = json.loads(record.payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
                manifest = {}
            continue
        source_key = _source_key(record.dataset_key)
        if source_key:
            sources[source_key] = record

    valid, error = _validate_restored_contract(manifest, sources)
    if not valid:
        state["_sandbox_supabase_restored"] = False
        state["_sandbox_supabase_source_count"] = len(sources)
        state["_sandbox_supabase_error"] = error
        return RestoredSandbox(manifest={}, sources={})

    state["_sandbox_supabase_restored"] = True
    state["_sandbox_supabase_source_count"] = len(sources)
    state["_sandbox_contract_version"] = SANDBOX_CONTRACT_VERSION
    state.pop("_sandbox_supabase_error", None)
    return RestoredSandbox(manifest=manifest, sources=sources)
