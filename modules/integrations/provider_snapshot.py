from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import utc_now
from .models import IntegrationProviderSnapshot


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _source(record: Mapping[str, Any]) -> Mapping[str, Any]:
    value = record.get("source")
    return value if isinstance(value, Mapping) else record


def provider_external_id(record: Mapping[str, Any]) -> str:
    source = _source(record)
    for key in ("provider_id", "external_id", "Id", "ID", "id", "Label", "label", "Tag", "tag", "Name", "name"):
        value = record.get(key)
        if value in (None, ""):
            value = source.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return _fingerprint(record)[:32]


def provider_label(record: Mapping[str, Any]) -> str:
    source = _source(record)
    for key in ("label", "Label", "name", "Name", "Tag", "tag", "ManifestNumber", "manifest_number"):
        value = record.get(key)
        if value in (None, ""):
            value = source.get(key)
        if value not in (None, ""):
            return str(value).strip()[:255]
    return provider_external_id(record)[:255]


def normalized_snapshot_record(
    *,
    provider: str,
    environment: str,
    resource: str,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(record.get("source"), Mapping) and record.get("provider"):
        return dict(record)
    return {
        "provider": provider.removesuffix("_sandbox"),
        "environment": environment,
        "resource": resource,
        "external_id": provider_external_id(record),
        "source": dict(record),
    }


def replace_snapshot_in_session(
    session: Session,
    *,
    organization_id: str,
    facility_id: str,
    provider: str,
    environment: str,
    resource: str,
    run_id: str,
    records: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    """Replace current membership for one fully successful provider resource.

    This function must only be called after the caller has a complete snapshot for
    the resource. Existing rows are batch-loaded once, marked not-present, then
    current rows are upserted in-memory. No per-row SQL reads are performed.
    """

    provider = str(provider or "").strip().casefold()
    environment = str(environment or "").strip().casefold()
    resource = str(resource or "").strip().casefold()
    now = utc_now()
    existing_rows = list(
        session.scalars(
            select(IntegrationProviderSnapshot).where(
                IntegrationProviderSnapshot.organization_id == organization_id,
                IntegrationProviderSnapshot.facility_id == facility_id,
                IntegrationProviderSnapshot.provider == provider,
                IntegrationProviderSnapshot.environment == environment,
                IntegrationProviderSnapshot.resource == resource,
            )
        )
    )
    by_external = {row.external_id: row for row in existing_rows}
    for row in existing_rows:
        row.present = False

    seen: set[str] = set()
    created = 0
    updated = 0
    duplicates = 0
    for source_record in records:
        record = dict(source_record)
        external_id = provider_external_id(record)
        if external_id in seen:
            duplicates += 1
            continue
        seen.add(external_id)
        raw = _json(record)
        normalized = normalized_snapshot_record(
            provider=provider,
            environment=environment,
            resource=resource,
            record=record,
        )
        fingerprint = _fingerprint(record)
        row = by_external.get(external_id)
        if row is None:
            row = IntegrationProviderSnapshot(
                organization_id=organization_id,
                facility_id=facility_id,
                provider=provider,
                environment=environment,
                resource=resource,
                external_id=external_id,
                provider_label=provider_label(record),
                fingerprint=fingerprint,
                raw_payload_json=raw,
                normalized_payload_json=_json(normalized),
                present=True,
                snapshot_run_id=run_id,
                last_seen_at=now,
            )
            session.add(row)
            by_external[external_id] = row
            created += 1
        else:
            row.provider_label = provider_label(record)
            row.fingerprint = fingerprint
            row.raw_payload_json = raw
            row.normalized_payload_json = _json(normalized)
            row.present = True
            row.snapshot_run_id = run_id
            row.last_seen_at = now
            updated += 1

    return {
        "present": len(seen),
        "created": created,
        "updated": updated,
        "removed": sum(1 for row in existing_rows if not row.present),
        "duplicates": duplicates,
    }


class IntegrationProviderSnapshotRepository:
    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def replace(
        self,
        *,
        organization_id: str,
        facility_id: str,
        provider: str,
        environment: str,
        resource: str,
        run_id: str,
        records: Iterable[Mapping[str, Any]],
    ) -> dict[str, int]:
        with self.sessions.begin() as session:
            return replace_snapshot_in_session(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                provider=provider,
                environment=environment,
                resource=resource,
                run_id=run_id,
                records=records,
            )

    def current(
        self,
        *,
        organization_id: str,
        facility_id: str,
        provider: str | tuple[str, ...],
        resources: tuple[str, ...] | None = None,
        environment: str | None = None,
        limit: int = 5000,
    ) -> list[IntegrationProviderSnapshot]:
        providers = (provider,) if isinstance(provider, str) else provider
        with self.sessions() as session:
            query = select(IntegrationProviderSnapshot).where(
                IntegrationProviderSnapshot.organization_id == organization_id,
                IntegrationProviderSnapshot.facility_id == facility_id,
                IntegrationProviderSnapshot.provider.in_(tuple(str(value).casefold() for value in providers)),
                IntegrationProviderSnapshot.present.is_(True),
            )
            if resources:
                query = query.where(IntegrationProviderSnapshot.resource.in_(resources))
            if environment:
                query = query.where(IntegrationProviderSnapshot.environment == environment.casefold())
            return list(
                session.scalars(
                    query.order_by(
                        IntegrationProviderSnapshot.resource,
                        IntegrationProviderSnapshot.provider_label,
                        IntegrationProviderSnapshot.external_id,
                    ).limit(max(1, min(int(limit), 10000)))
                )
            )
