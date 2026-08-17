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


@dataclass(frozen=True)
class RestoredSandbox:
    manifest: dict[str, Any]
    sources: dict[str, PublishedSource]

    @property
    def available(self) -> bool:
        return bool(self.manifest and self.sources)


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
        "as_of_date": as_of_value,
        "scale": str(payload.get("scale") or state.get("demo_dataset_scale") or "medium"),
        "problems": list(payload.get("problems") or state.get("demo_problem_set") or []),
        "company_profile": dict(payload.get("company_profile") or {}),
        "company_seed": int(state.get("demo_company_seed") or 710),
        "catalog_seed": int(state.get("demo_catalog_seed") or 811),
        "history_seed": int(state.get("demo_history_seed") or 912),
        "selected_scenario": str(state.get("demo_selected_scenario") or "Healthy baseline"),
    }
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


def persist_sandbox_sources(
    state: MutableMapping[str, Any],
    payload: Mapping[str, Any],
    *,
    version: str,
    actor: str = "demo",
    repository: DataHubRepository | None = None,
) -> int:
    """Publish every generated sandbox source plus a state manifest to Supabase.

    Existing active versions are archived by DataHubRepository. The latest three
    versions remain available for QA/debugging without allowing session resets to
    destroy the durable sandbox source history.
    """

    organization_id, facility_id = _scope(state)
    repo = _repository(repository)
    uploads = dict(payload.get("uploads") or {})
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
        inspection={"rows": 1, "columns": 8, "quality": "Sandbox state"},
        content_type="application/json",
        imported_by=str(actor or "demo"),
        retain_versions=3,
    )
    state["_sandbox_supabase_persisted"] = True
    state["_sandbox_supabase_source_count"] = persisted
    state.pop("_sandbox_supabase_error", None)
    return persisted


def restore_sandbox_sources(
    state: MutableMapping[str, Any],
    *,
    repository: DataHubRepository | None = None,
) -> RestoredSandbox:
    """Load the active persisted sandbox source set for the selected tenant."""

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

    state["_sandbox_supabase_restored"] = bool(manifest and sources)
    state["_sandbox_supabase_source_count"] = len(sources)
    return RestoredSandbox(manifest=manifest, sources=sources)
