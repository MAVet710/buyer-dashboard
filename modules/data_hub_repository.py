"""Tenant-scoped durable storage for reviewed Data Hub source files."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import sessionmaker

from modules.coman.models import DataHubImport, Facility, utc_now


MAX_DURABLE_UPLOAD_BYTES = 10 * 1024 * 1024
DEFAULT_VERSION_RETENTION = 3


@dataclass(frozen=True)
class PublishedSource:
    id: str
    dataset_key: str
    dataset_label: str
    cache_key: str
    filename: str
    fingerprint: str
    payload: bytes
    payload_size: int
    row_count: int
    column_count: int
    quality: str
    imported_by: str
    activated_at: Any


class DataHubRepository:
    """Persist file versions while enforcing organization/facility ownership."""

    def __init__(self, engine: Engine):
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @staticmethod
    def _validate_scope(organization_id: str, facility_id: str) -> tuple[str, str]:
        organization_id = str(organization_id or "").strip()
        facility_id = str(facility_id or "").strip()
        if not organization_id or not facility_id:
            raise ValueError("Select an organization and facility before publishing data.")
        return organization_id, facility_id

    def publish_source(
        self,
        *,
        organization_id: str,
        facility_id: str,
        dataset_key: str,
        dataset_label: str,
        cache_key: str,
        filename: str,
        fingerprint: str,
        payload: bytes,
        inspection: Mapping[str, Any] | None = None,
        content_type: str = "",
        imported_by_user_id: str | None = None,
        imported_by: str = "system",
        retain_versions: int = DEFAULT_VERSION_RETENTION,
    ) -> DataHubImport:
        organization_id, facility_id = self._validate_scope(organization_id, facility_id)
        payload = bytes(payload)
        if not payload:
            raise ValueError("The source file is empty.")
        if len(payload) > MAX_DURABLE_UPLOAD_BYTES:
            raise ValueError("The source file exceeds the 10 MB durable upload limit.")
        if len(str(fingerprint)) != 64:
            raise ValueError("A valid SHA-256 fingerprint is required.")

        inspection = dict(inspection or {})
        compressed = gzip.compress(payload, compresslevel=6)
        now = utc_now()
        with self._session_factory.begin() as session:
            facility = session.get(Facility, facility_id)
            if not facility or facility.organization_id != organization_id:
                raise ValueError("The selected facility does not belong to the organization.")

            scope = (
                DataHubImport.organization_id == organization_id,
                DataHubImport.facility_id == facility_id,
                DataHubImport.dataset_key == str(dataset_key),
            )
            existing = session.scalar(
                select(DataHubImport).where(
                    *scope,
                    DataHubImport.fingerprint == str(fingerprint),
                )
            )
            session.execute(
                update(DataHubImport)
                .where(*scope, DataHubImport.status == "active")
                .values(status="archived", updated_at=now)
            )
            if existing is None:
                existing = DataHubImport(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    dataset_key=str(dataset_key),
                    dataset_label=str(dataset_label),
                    cache_key=str(cache_key),
                    filename=str(filename),
                    content_type=str(content_type or ""),
                    fingerprint=str(fingerprint),
                    payload_compressed=compressed,
                    payload_size=len(payload),
                    compressed_size=len(compressed),
                    row_count=max(0, int(inspection.get("rows") or 0)),
                    column_count=max(0, int(inspection.get("columns") or 0)),
                    quality=str(inspection.get("quality") or ""),
                    mapping_json=json.dumps(inspection.get("matches") or {}, sort_keys=True),
                    missing_fields_json=json.dumps(inspection.get("missing") or []),
                    status="active",
                    imported_by_user_id=imported_by_user_id or None,
                    imported_by=str(imported_by or "system"),
                    activated_at=now,
                )
                session.add(existing)
                session.flush()
            else:
                existing.status = "active"
                existing.activated_at = now
                existing.imported_by_user_id = imported_by_user_id or existing.imported_by_user_id
                existing.imported_by = str(imported_by or existing.imported_by)
                existing.updated_at = now

            keep = max(1, min(int(retain_versions), 25))
            version_ids = list(
                session.scalars(
                    select(DataHubImport.id)
                    .where(*scope)
                    .order_by(DataHubImport.activated_at.desc(), DataHubImport.created_at.desc())
                )
            )
            stale_ids = version_ids[keep:]
            if stale_ids:
                session.execute(delete(DataHubImport).where(DataHubImport.id.in_(stale_ids)))
        return existing

    def list_active_sources(
        self, organization_id: str, facility_id: str
    ) -> list[PublishedSource]:
        organization_id, facility_id = self._validate_scope(organization_id, facility_id)
        with self._session_factory() as session:
            records = list(
                session.scalars(
                    select(DataHubImport)
                    .where(
                        DataHubImport.organization_id == organization_id,
                        DataHubImport.facility_id == facility_id,
                        DataHubImport.status == "active",
                    )
                    .order_by(DataHubImport.dataset_label)
                )
            )
            return [self._published(record) for record in records]

    def list_history(
        self, organization_id: str, facility_id: str, *, limit: int = 100
    ) -> list[DataHubImport]:
        organization_id, facility_id = self._validate_scope(organization_id, facility_id)
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(DataHubImport)
                    .where(
                        DataHubImport.organization_id == organization_id,
                        DataHubImport.facility_id == facility_id,
                    )
                    .order_by(DataHubImport.activated_at.desc())
                    .limit(max(1, min(int(limit), 500)))
                )
            )

    def archive_active_sources(self, organization_id: str, facility_id: str) -> int:
        organization_id, facility_id = self._validate_scope(organization_id, facility_id)
        with self._session_factory.begin() as session:
            result = session.execute(
                update(DataHubImport)
                .where(
                    DataHubImport.organization_id == organization_id,
                    DataHubImport.facility_id == facility_id,
                    DataHubImport.status == "active",
                )
                .values(status="archived", updated_at=utc_now())
            )
            return int(result.rowcount or 0)

    @staticmethod
    def _published(record: DataHubImport) -> PublishedSource:
        try:
            payload = gzip.decompress(bytes(record.payload_compressed))
        except (OSError, EOFError) as exc:
            raise ValueError(f"Stored source {record.filename} is corrupted.") from exc
        if len(payload) != int(record.payload_size):
            raise ValueError(f"Stored source {record.filename} failed its size check.")
        return PublishedSource(
            id=record.id,
            dataset_key=record.dataset_key,
            dataset_label=record.dataset_label,
            cache_key=record.cache_key,
            filename=record.filename,
            fingerprint=record.fingerprint,
            payload=payload,
            payload_size=record.payload_size,
            row_count=record.row_count,
            column_count=record.column_count,
            quality=record.quality,
            imported_by=record.imported_by,
            activated_at=record.activated_at,
        )


def hydrate_durable_sources(
    state: MutableMapping[str, Any],
    repository: DataHubRepository,
    *,
    organization_id: str,
    facility_id: str,
    cache_keys: tuple[str, ...],
) -> int:
    """Restore active sources and prevent cached files crossing tenant boundaries."""

    scope = f"{organization_id}|{facility_id}"
    previous_scope = str(state.get("_durable_data_hub_scope") or "")
    if previous_scope != scope:
        for cache_key in cache_keys:
            state.pop(cache_key, None)
        state["_durable_data_hub_scope"] = scope

    restored = 0
    for source in repository.list_active_sources(organization_id, facility_id):
        if source.cache_key not in cache_keys:
            continue
        state[source.cache_key] = {
            "name": source.filename,
            "bytes": source.payload,
            "fingerprint": source.fingerprint,
            "staged_at": source.activated_at.isoformat() if source.activated_at else "",
            "dataset": source.dataset_label,
            "durable_id": source.id,
            "durable": True,
            "rows": source.row_count,
            "columns": source.column_count,
            "quality": source.quality,
        }
        restored += 1
    state["_durable_data_hub_restored_scope"] = scope
    return restored
