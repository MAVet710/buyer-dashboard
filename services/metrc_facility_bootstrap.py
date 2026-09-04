from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
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
from services.metrc_facility_materialization import MetrcCanonicalInventorySeeder


PAGE_SIZE = 100
MAX_INITIAL_PAGES = 100


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


def _total_pages(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 1
    try:
        return max(1, int(payload.get("TotalPages") or payload.get("totalPages") or 1))
    except (TypeError, ValueError):
        return 1


class MetrcFacilityBootstrapService:
    """Hydrate one mapped facility with provider-owned Metrc state.

    Discovery remains fast and mapping-only. This explicit initial-sync step walks
    every available page, up to a defensive 100-page ceiling per collection,
    stores the lossless provider mirror, and then seeds only unambiguous new Metrc
    packages into the canonical DoobieLogic inventory ledger.

    Existing local package/product state is never overwritten. Differences remain
    visible to the existing reconciliation layer. Permission-specific 403/404
    results are recorded as skipped capabilities because not every license exposes
    every cultivation, retail, tag, or transport resource.
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
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def _fetch_all_normalized(
        self,
        *,
        resource: str,
        state: str,
        user_api_key: str,
        integrator_api_key: str,
        license_number: str,
        environment: str,
    ) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        first_result: dict[str, Any] | None = None
        total_pages = 1
        page = 1
        while page <= min(total_pages, MAX_INITIAL_PAGES):
            result = fetch_metrc_resource(
                state=state,
                user_api_key=user_api_key,
                integrator_api_key=integrator_api_key,
                resource=resource,
                environment=environment,
                license_number=license_number,
                page_size=PAGE_SIZE,
                page_number=page,
                timeout_seconds=10,
                max_attempts=1,
            )
            if first_result is None:
                first_result = dict(result)
            if not result.get("ok"):
                return result
            records.extend(dict(row) for row in result.get("records", []) if isinstance(row, dict))
            total_pages = _total_pages(result.get("payload"))
            page += 1
        output = first_result or {"ok": True, "status": "connected", "message": "Metrc request succeeded."}
        output["records"] = records
        output["page_count"] = min(total_pages, MAX_INITIAL_PAGES)
        output["truncated"] = total_pages > MAX_INITIAL_PAGES
        return output

    @staticmethod
    def _fetch_all_direct(
        *,
        transport: MetrcTransport,
        path: str,
        params: dict[str, Any],
        paginated: bool,
    ) -> dict[str, Any]:
        if not paginated:
            result = transport.get(path, params)
            if result.get("ok"):
                result["records"] = payload_rows(result.get("payload"))
                result["page_count"] = 1
                result["truncated"] = False
            return result

        records: list[dict[str, Any]] = []
        first_result: dict[str, Any] | None = None
        total_pages = 1
        page = 1
        while page <= min(total_pages, MAX_INITIAL_PAGES):
            query = dict(params)
            query.update({"pageSize": PAGE_SIZE, "pageNumber": page})
            result = transport.get(path, query)
            if first_result is None:
                first_result = dict(result)
            if not result.get("ok"):
                return result
            records.extend(payload_rows(result.get("payload")))
            total_pages = _total_pages(result.get("payload"))
            page += 1
        output = first_result or {"ok": True, "status": "connected", "message": "Metrc request succeeded."}
        output["records"] = records
        output["page_count"] = min(total_pages, MAX_INITIAL_PAGES)
        output["truncated"] = total_pages > MAX_INITIAL_PAGES
        return output

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

        transport = MetrcTransport(
            state=state,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
            environment=environment,
            timeout_seconds=10,
            max_attempts=1,
        )
        jobs: list[tuple[str, str, Callable[[], dict[str, Any]]]] = []
        for local_name, resource in self.NORMALIZED_RESOURCES:
            def fetch(resource_name=resource):
                return self._fetch_all_normalized(
                    resource=resource_name,
                    state=state,
                    user_api_key=user_api_key,
                    integrator_api_key=integrator_api_key,
                    license_number=license_number,
                    environment=environment,
                )
            jobs.append((local_name, "metrc_normalized_v2", fetch))

        for local_name, path, paginated in self.DIRECT_RESOURCES:
            params: dict[str, Any] = {}
            if local_name != "units_of_measure":
                params["licenseNumber"] = license_number

            def fetch_direct(provider_path=path, query=dict(params), provider_paginated=paginated):
                return self._fetch_all_direct(
                    transport=transport,
                    path=provider_path,
                    params=query,
                    paginated=provider_paginated,
                )
            jobs.append((local_name, "metrc_direct_v2", fetch_direct))

        results: dict[str, tuple[str, dict[str, Any] | Exception]] = {}
        worker_count = max(1, min(5, len(jobs)))
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="metrc-bootstrap") as pool:
            future_map = {
                pool.submit(fetch): (resource, transport_name)
                for resource, transport_name, fetch in jobs
            }
            for future in as_completed(future_map):
                resource, transport_name = future_map[future]
                try:
                    results[resource] = (transport_name, future.result())
                except Exception as exc:
                    results[resource] = (transport_name, exc)

        # Persist in deterministic order even though provider reads ran concurrently.
        for resource, transport_name, _ in jobs:
            _, result = results[resource]
            summaries.append(self._persist_fetch_result(
                organization_id=organization_id,
                facility_id=facility_id,
                resource=resource,
                environment=environment,
                actor=actor,
                result=result,
                transport=transport_name,
            ))

        package_result = results.get("packages", ("", RuntimeError("Package snapshot unavailable.")))[1]
        if isinstance(package_result, dict) and package_result.get("ok") and not package_result.get("truncated"):
            materialization = MetrcCanonicalInventorySeeder(self.engine).seed(
                organization_id=organization_id,
                facility_id=facility_id,
                state=state,
                environment=environment,
                license_number=license_number,
                actor=actor,
                packages=[dict(row) for row in package_result.get("records", []) if isinstance(row, dict)],
            )
            materialization["status"] = "completed"
        else:
            materialization = {
                "provider": "metrc",
                "status": "blocked",
                "created_products": 0,
                "created_inventory_lots": 0,
                "created_inventory_transactions": 0,
                "conflict_count": 0,
                "warning_count": 0,
                "overwrite_existing": False,
                "message": (
                    "Canonical inventory materialization was blocked because the active-package snapshot was incomplete."
                    if isinstance(package_result, dict) and package_result.get("truncated")
                    else "Canonical inventory materialization was skipped because the active-package read did not complete successfully."
                ),
            }

        return {
            "provider": "metrc",
            "environment": environment,
            "license_number": license_number,
            "bounded_initial_sync": False,
            "full_initial_sync": True,
            "page_size": PAGE_SIZE,
            "max_pages_per_resource": MAX_INITIAL_PAGES,
            "resources": summaries,
            "materialization": materialization,
            "totals": {
                "resources": len(summaries),
                "succeeded": sum(1 for row in summaries if row["status"] == "succeeded"),
                "skipped": sum(1 for row in summaries if row["status"] == "skipped"),
                "failed": sum(1 for row in summaries if row["status"] == "failed"),
                "records": sum(int(row.get("record_count") or 0) for row in summaries),
            },
        }

    def _persist_fetch_result(
        self,
        *,
        organization_id: str,
        facility_id: str,
        resource: str,
        environment: str,
        actor: str,
        result: dict[str, Any] | Exception,
        transport: str,
    ) -> dict[str, Any]:
        if isinstance(result, Exception):
            return self._failure(
                organization_id,
                facility_id,
                resource,
                environment,
                actor,
                f"{type(result).__name__}: {result}",
            )
        if not result.get("ok"):
            status = str(result.get("status") or "")
            http_status = int(result.get("http_status") or 0)
            message = str(result.get("message") or "Metrc resource was unavailable.")[:512]
            if http_status in {403, 404} or status in {"forbidden", "regulatory_read_blocked"}:
                self._mark_skipped(organization_id, facility_id, resource, environment, actor, message)
                return {
                    "resource": resource,
                    "status": "skipped",
                    "record_count": 0,
                    "message": message,
                    "http_status": http_status,
                    "page_count": int(result.get("page_count") or 0),
                    "truncated": bool(result.get("truncated")),
                }
            return self._failure(
                organization_id,
                facility_id,
                resource,
                environment,
                actor,
                message,
                http_status=http_status,
            )

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
        summary["page_count"] = int(result.get("page_count") or 1)
        summary["truncated"] = bool(result.get("truncated"))
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
            session.add(IntegrationSyncAttempt(
                organization_id=organization_id,
                facility_id=facility_id,
                provider="metrc",
                resource=resource,
                run_id=run_id,
                status="running",
                cursor_before=cursor_before,
                actor=actor,
                started_at=started,
            ))

        accepted = 0
        duplicates = 0
        with self.sessions.begin() as session:
            fingerprints = {_fingerprint(record) for record in records}
            existing_fingerprints = set(session.scalars(select(IntegrationSyncRecord.fingerprint).where(
                IntegrationSyncRecord.organization_id == organization_id,
                IntegrationSyncRecord.facility_id == facility_id,
                IntegrationSyncRecord.provider == "metrc",
                IntegrationSyncRecord.resource == resource,
                IntegrationSyncRecord.fingerprint.in_(fingerprints),
            ))) if fingerprints else set()
            for record in records:
                fingerprint = _fingerprint(record)
                if fingerprint in existing_fingerprints:
                    duplicates += 1
                    continue
                existing_fingerprints.add(fingerprint)
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
            state.cursor = "initial-full"
            state.status = "succeeded"
            state.last_completed_at = completed
            state.last_success_at = completed
            state.last_error = ""
            state.records_seen += len(records)
            state.records_written += accepted
            state.updated_by = actor
            attempt = session.scalar(select(IntegrationSyncAttempt).where(IntegrationSyncAttempt.run_id == run_id))
            attempt.status = "succeeded"
            attempt.cursor_after = "initial-full"
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

    def _mark_skipped(
        self,
        organization_id: str,
        facility_id: str,
        resource: str,
        environment: str,
        actor: str,
        message: str,
    ) -> None:
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

    def _failure(
        self,
        organization_id: str,
        facility_id: str,
        resource: str,
        environment: str,
        actor: str,
        message: str,
        *,
        http_status: int = 0,
    ) -> dict[str, Any]:
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
        return {
            "resource": resource,
            "status": "failed",
            "record_count": 0,
            "message": message,
            "http_status": http_status,
        }

    @staticmethod
    def _state(
        session,
        organization_id: str,
        facility_id: str,
        resource: str,
        environment: str,
        actor: str,
    ) -> IntegrationSyncState:
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
