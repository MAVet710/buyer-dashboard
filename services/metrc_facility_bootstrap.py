from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Callable

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import utc_now
from modules.integrations.models import IntegrationSyncAttempt, IntegrationSyncRecord, IntegrationSyncState
from modules.regulatory.metrc_resources import payload_rows
from services.metrc_client import MetrcTransport, fetch_metrc_resource


class MetrcFacilityBootstrapError(RuntimeError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _external_id(record: dict[str, Any]) -> str:
    source = record.get("source") if isinstance(record.get("source"), dict) else record
    for key in ("Id", "ID", "id", "Label", "label", "Name", "name", "Number", "number"):
        value = source.get(key) if isinstance(source, dict) else None
        if value not in (None, ""):
            return str(value).strip()
    return _fingerprint(record)[:24]


class MetrcFacilityBootstrapService:
    """Prime one mapped facility with provider-owned Metrc state.

    The first pass is intentionally bounded to page 1 / 100 rows per collection.
    It gives operators useful master/traceability state immediately while durable
    sync state records where continuation work belongs. Permission-specific 403s
    are treated as skipped capabilities rather than breaking the whole facility.
    """

    NORMALIZED_RESOURCES: tuple[tuple[str, str], ...] = (
        ("locations", "locations_active"),
        ("strains", "strains_active"),
        ("items", "items_active"),
        ("package_tags", "package_tags_available"),
        ("plant_tags", "plant_tags_available"),
        ("packages", "packages_active"),
        ("plant_batches", "plant_batches_active"),
        ("plants_vegetative", "plants_vegetative"),
        ("plants_flowering", "plants_flowering"),
        ("harvests", "harvests_active"),
    )
    DIRECT_RESOURCES: tuple[tuple[str, str, bool], ...] = (
        ("sublocations", "sublocations/v2/active", True),
        ("location_types", "locations/v2/types", False),
        ("item_categories", "items/v2/categories", True),
        ("item_brands", "items/v2/brands", True),
        ("units_of_measure", "unitsofmeasure/v2/active", False),
    )

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def sync(
        self,
        *,
        organization_id: str,
        facility_id: str,
        license_number: str,
        state: str,
        environment: str,
        integrator_api_key: str,
        user_api_key: str,
        actor: str,
        facility_record: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        summaries: list[dict[str, Any]] = []
        if facility_record:
            summaries.append(self._persist(
                organization_id=organization_id,
                facility_id=facility_id,
                resource="facility_profile",
                environment=environment,
                actor=actor,
                records=[facility_record],
                transport="metrc_facilities",
            ))

        for local_name, resource in self.NORMALIZED_RESOURCES:
            def fetch(resource_name=resource):
                return fetch_metrc_resource(
                    state=state,
                    user_api_key=user_api_key,
                    integrator_api_key=integrator_api_key,
                    resource=resource_name,
                    environment=environment,
                    license_number=license_number,
                    page_size=100,
                    page_number=1,
                    timeout_seconds=20,
                )
            summaries.append(self._fetch_and_persist(
                organization_id=organization_id,
                facility_id=facility_id,
                resource=local_name,
                environment=environment,
                actor=actor,
                fetch=fetch,
                transport="metrc_normalized_v2",
            ))

        transport = MetrcTransport(
            state=state,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
            environment=environment,
            timeout_seconds=20,
            max_attempts=2,
        )
        for local_name, path, paginated in self.DIRECT_RESOURCES:
            params: dict[str, Any] = {}
            if local_name != "units_of_measure":
                params["licenseNumber"] = license_number
            if paginated:
                params.update({"pageSize": 100, "pageNumber": 1})

            def fetch_direct(provider_path=path, query=dict(params)):
                result = transport.get(provider_path, query)
                if result.get("ok"):
                    result["records"] = payload_rows(result.get("payload"))
                return result

            summaries.append(self._fetch_and_persist(
                organization_id=organization_id,
                facility_id=facility_id,
                resource=local_name,
                environment=environment,
                actor=actor,
                fetch=fetch_direct,
                transport="metrc_direct_v2",
            ))

        return {
            "provider": "metrc",
            "environment": environment,
            "license_number": license_number,
            "bounded_initial_sync": True,
            "resources": summaries,
            "totals": {
                "resources": len(summaries),
                "succeeded": sum(1 for row in summaries if row["status"] == "succeeded"),
                "skipped": sum(1 for row in summaries if row["status"] == "skipped"),
                "failed": sum(1 for row in summaries if row["status"] == "failed"),
                "records": sum(int(row.get("record_count") or 0) for row in summaries),
            },
        }

    def _fetch_and_persist(
        self,
        *,
        organization_id: str,
        facility_id: str,
        resource: str,
        environment: str,
        actor: str,
        fetch: Callable[[], dict[str, Any]],
        transport: str,
    ) -> dict[str, Any]:
        try:
            result = fetch()
        except Exception as exc:
            return self._failure(organization_id, facility_id, resource, environment, actor, f"{type(exc).__name__}: {exc}")

        if not result.get("ok"):
            status = str(result.get("status") or "")
            http_status = int(result.get("http_status") or 0)
            message = str(result.get("message") or "Metrc resource was unavailable.")[:512]
            if http_status in {403, 404} or status in {"forbidden", "regulatory_read_blocked"}:
                self._mark_skipped(organization_id, facility_id, resource, environment, actor, message)
                return {"resource": resource, "status": "skipped", "record_count": 0, "message": message, "http_status": http_status}
            return self._failure(organization_id, facility_id, resource, environment, actor, message, http_status=http_status)

        records = [dict(row) for row in result.get("records", []) if isinstance(row, dict)]
        summary = self._persist(
            organization_id=organization_id,
            facility_id=facility_id,
            resource=resource,
            environment=environment,
            actor=actor,
            records=records,
            transport=transport,
        )
        summary["http_status"] = int(result.get("http_status") or 200)
        return summary

    def _persist(
        self,
        *,
        organization_id: str,
        facility_id: str,
        resource: str,
        environment: str,
        actor: str,
        records: list[dict[str, Any]],
        transport: str,
    ) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        started = utc_now()
        with self.sessions.begin() as session:
            state = self._state(session, organization_id, facility_id, resource, environment, actor)
            cursor_before = state.cursor
            state.status = "running"
            state.last_started_at = started
            state.last_error = ""
            attempt = IntegrationSyncAttempt(
                organization_id=organization_id,
                facility_id=facility_id,
                provider="metrc",
                resource=resource,
                run_id=run_id,
                status="running",
                cursor_before=cursor_before,
                actor=actor,
                started_at=started,
            )
            session.add(attempt)

        accepted = 0
        duplicates = 0
        with self.sessions.begin() as session:
            for record in records:
                fingerprint = _fingerprint(record)
                existing = session.scalar(select(IntegrationSyncRecord.id).where(
                    IntegrationSyncRecord.organization_id == organization_id,
                    IntegrationSyncRecord.facility_id == facility_id,
                    IntegrationSyncRecord.provider == "metrc",
                    IntegrationSyncRecord.resource == resource,
                    IntegrationSyncRecord.fingerprint == fingerprint,
                ))
                if existing:
                    duplicates += 1
                    continue
                source = record.get("source") if isinstance(record.get("source"), dict) else record
                normalized = {
                    "provider": "metrc",
                    "environment": environment,
                    "resource": resource,
                    "external_id": _external_id(record),
                    "source": source,
                }
                session.add(IntegrationSyncRecord(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    provider="metrc",
                    resource=resource,
                    run_id=run_id,
                    external_id=_external_id(record),
                    fingerprint=fingerprint,
                    raw_payload_json=_json(record),
                    normalized_payload_json=_json(normalized),
                    status="accepted",
                    error_message="",
                    received_at=utc_now(),
                ))
                accepted += 1

            completed = utc_now()
            state = self._state(session, organization_id, facility_id, resource, environment, actor)
            state.cursor = "initial-page-1"
            state.status = "succeeded"
            state.last_completed_at = completed
            state.last_success_at = completed
            state.last_error = ""
            state.records_seen += len(records)
            state.records_written += accepted
            state.updated_by = actor
            attempt = session.scalar(select(IntegrationSyncAttempt).where(IntegrationSyncAttempt.run_id == run_id))
            attempt.status = "succeeded"
            attempt.cursor_after = "initial-page-1"
            attempt.record_count = len(records)
            attempt.accepted_count = accepted
            attempt.duplicate_count = duplicates
            attempt.error_count = 0
            attempt.error_message = ""
            attempt.completed_at = completed
        return {
            "resource": resource,
            "status": "succeeded",
            "record_count": len(records),
            "accepted_count": accepted,
            "duplicate_count": duplicates,
            "transport": transport,
        }

    def _mark_skipped(self, organization_id: str, facility_id: str, resource: str, environment: str, actor: str, message: str) -> None:
        run_id = str(uuid.uuid4())
        now = utc_now()
        with self.sessions.begin() as session:
            state = self._state(session, organization_id, facility_id, resource, environment, actor)
            state.status = "succeeded"
            state.last_started_at = now
            state.last_completed_at = now
            state.last_success_at = now
            state.last_error = ""
            state.cursor = "permission-skipped"
            state.updated_by = actor
            session.add(IntegrationSyncAttempt(
                organization_id=organization_id,
                facility_id=facility_id,
                provider="metrc",
                resource=resource,
                run_id=run_id,
                status="succeeded",
                cursor_before="",
                cursor_after="permission-skipped",
                record_count=0,
                accepted_count=0,
                duplicate_count=0,
                error_count=0,
                error_message="",
                actor=actor,
                started_at=now,
                completed_at=now,
            ))

    def _failure(self, organization_id: str, facility_id: str, resource: str, environment: str, actor: str, message: str, *, http_status: int = 0) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        now = utc_now()
        with self.sessions.begin() as session:
            state = self._state(session, organization_id, facility_id, resource, environment, actor)
            state.status = "failed"
            state.last_started_at = now
            state.last_completed_at = now
            state.last_error = message[:512]
            state.updated_by = actor
            session.add(IntegrationSyncAttempt(
                organization_id=organization_id,
                facility_id=facility_id,
                provider="metrc",
                resource=resource,
                run_id=run_id,
                status="failed",
                cursor_before=state.cursor,
                cursor_after=state.cursor,
                record_count=0,
                accepted_count=0,
                duplicate_count=0,
                error_count=1,
                error_message=message[:512],
                actor=actor,
                started_at=now,
                completed_at=now,
            ))
        return {"resource": resource, "status": "failed", "record_count": 0, "message": message, "http_status": http_status}

    @staticmethod
    def _state(session, organization_id: str, facility_id: str, resource: str, environment: str, actor: str) -> IntegrationSyncState:
        state = session.scalar(select(IntegrationSyncState).where(
            IntegrationSyncState.organization_id == organization_id,
            IntegrationSyncState.facility_id == facility_id,
            IntegrationSyncState.provider == "metrc",
            IntegrationSyncState.resource == resource,
        ))
        if state is None:
            state = IntegrationSyncState(
                organization_id=organization_id,
                facility_id=facility_id,
                provider="metrc",
                resource=resource,
                environment=environment,
                status="idle",
                cursor="",
                updated_by=actor,
            )
            session.add(state)
            session.flush()
        return state
