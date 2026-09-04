from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import json
import uuid
from typing import Any

from sqlalchemy import Engine, select

from modules.integrations.models import IntegrationSyncState
from modules.integrations.provider_snapshot import IntegrationProviderSnapshotRepository
from services import metrc_facility_bootstrap as base_bootstrap
from services.metrc_facility_bootstrap import MAX_INITIAL_PAGES, PAGE_SIZE, _total_pages
from services.metrc_workspace_hydration import MetrcWorkspaceHydrationService


LAST_MODIFIED_OVERLAP = timedelta(minutes=5)
READ_MAX_ATTEMPTS = 4
PROVIDER_CONCURRENCY = 3
CULTIVATION_RESOURCES = (
    "locations",
    "plant_batches",
    "plants_vegetative",
    "plants_flowering",
    "harvests",
)

# These are normalized active/current resources for which the Metrc v2 read
# planner accepts query parameters and the provider's LastModified filtering can
# reduce routine sync volume. Direct reference tables/tags stay on periodic full
# hydration until their exact change-filter contract is separately proven.
INCREMENTAL_RESOURCES: tuple[tuple[str, str], ...] = (
    ("locations", "locations_active"),
    ("strains", "strains_active"),
    ("items", "items_active"),
    ("packages", "packages_active"),
    ("plant_batches", "plant_batches_active"),
    ("plants_vegetative", "plants_vegetative"),
    ("plants_flowering", "plants_flowering"),
    ("harvests", "harvests_active"),
    ("incoming_transfers", "incoming_transfers"),
    ("outgoing_transfers", "outgoing_transfers"),
    ("rejected_transfers", "rejected_transfers"),
    ("processing_jobs", "processing_active"),
    ("sales_receipts", "sales_receipts_active"),
    ("sales_deliveries", "sales_deliveries_active"),
)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _provider_timestamp(value: datetime) -> str:
    current = _aware(value) or datetime.now(timezone.utc)
    # requests will URL-encode the + offset correctly. Seconds precision avoids
    # generating needless distinct cursors from microseconds.
    return current.astimezone(timezone.utc).replace(microsecond=0).isoformat()


class MetrcIncrementalSyncService:
    """Apply LastModified deltas without treating omissions as provider removals.

    Metrc guidance recommends a five-minute overlap to absorb clock drift. Every
    resource therefore starts at the previous successful sync time minus five
    minutes. The current-provider mirror is updated non-destructively: rows in the
    delta are created/updated, while omitted rows remain current until a complete
    full snapshot proves their absence.

    Newly changed provider objects pass through the same safe natural-workspace
    materializers. Existing local operational state is never silently overwritten.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.snapshots = IntegrationProviderSnapshotRepository(engine)

    def sync(
        self,
        *,
        organization_id: str,
        facility_id: str,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
        actor: str,
    ) -> dict[str, Any]:
        baselines = self._baselines(
            organization_id=organization_id,
            facility_id=facility_id,
            environment=environment,
        )
        permission_skipped = self._permission_skipped_resources(
            organization_id=organization_id,
            facility_id=facility_id,
            environment=environment,
        )
        resources: list[dict[str, Any]] = []
        deltas: dict[str, list[dict[str, Any]]] = {}

        eligible = [(local, provider, baselines.get(local)) for local, provider in INCREMENTAL_RESOURCES]
        to_read = [
            (local, provider, baseline)
            for local, provider, baseline in eligible
            if baseline is not None and local not in permission_skipped
        ]
        for local, provider, baseline in eligible:
            if local in permission_skipped:
                resources.append({
                    "resource": local,
                    "provider_resource": provider,
                    "status": "skipped",
                    "record_count": 0,
                    "message": "This resource was permission-skipped during the verified full baseline; incremental sync will not repeatedly treat it as missing.",
                    "current_snapshot_changed": False,
                })
            elif baseline is None:
                resources.append({
                    "resource": local,
                    "provider_resource": provider,
                    "status": "full_sync_required",
                    "record_count": 0,
                    "message": "No completed full/incremental baseline exists for this resource; run full facility hydration first.",
                    "current_snapshot_changed": False,
                })

        results: dict[str, dict[str, Any] | Exception] = {}
        with ThreadPoolExecutor(max_workers=max(1, min(PROVIDER_CONCURRENCY, len(to_read) or 1)), thread_name_prefix="metrc-delta") as pool:
            future_map = {
                pool.submit(
                    self._fetch_delta,
                    provider_resource=provider,
                    baseline=baseline,
                    state=state,
                    environment=environment,
                    license_number=license_number,
                    integrator_api_key=integrator_api_key,
                    user_api_key=user_api_key,
                ): local
                for local, provider, baseline in to_read
            }
            for future in as_completed(future_map):
                local = future_map[future]
                try:
                    results[local] = future.result()
                except Exception as exc:  # transport/runtime boundary; sanitized below
                    results[local] = exc

        core = base_bootstrap.MetrcFacilityBootstrapService(self.engine)
        # The application composes the resilient subclass into the base module.
        # We only need its stable immutable persistence contract here; if composed,
        # call the core ancestor method explicitly to avoid checkpoint scope needs.
        persist_method = None
        for cls in type(core).mro():
            if cls.__name__ == "MetrcFacilityBootstrapService" and cls.__module__ == "services.metrc_facility_bootstrap":
                persist_method = cls._persist
                break
        if persist_method is None:
            persist_method = base_bootstrap.MetrcFacilityBootstrapService._persist

        by_name = {name: provider for name, provider in INCREMENTAL_RESOURCES}
        for local, _provider, baseline in to_read:
            result = results.get(local)
            if isinstance(result, Exception):
                resources.append({
                    "resource": local,
                    "provider_resource": by_name[local],
                    "status": "failed",
                    "record_count": 0,
                    "message": f"{type(result).__name__}: incremental provider read failed.",
                    "current_snapshot_changed": False,
                })
                continue
            if not isinstance(result, dict) or not result.get("ok"):
                result = result if isinstance(result, dict) else {}
                http_status = int(result.get("http_status") or 0)
                status = str(result.get("status") or "failed")
                if http_status in {403, 404} or status in {"forbidden", "regulatory_read_blocked"}:
                    outcome = "skipped"
                elif http_status == 400:
                    outcome = "full_sync_required"
                else:
                    outcome = "failed"
                resources.append({
                    "resource": local,
                    "provider_resource": by_name[local],
                    "status": outcome,
                    "record_count": 0,
                    "http_status": http_status,
                    "message": str(result.get("message") or "Incremental Metrc read failed."),
                    "current_snapshot_changed": False,
                })
                continue
            if result.get("truncated"):
                resources.append({
                    "resource": local,
                    "provider_resource": by_name[local],
                    "status": "full_sync_required",
                    "record_count": len(result.get("records") or []),
                    "message": "The incremental change window exceeded the defensive page ceiling; partial delta was not applied.",
                    "current_snapshot_changed": False,
                })
                continue

            records = [dict(row) for row in result.get("records") or [] if isinstance(row, dict)]
            # Preserve immutable audit evidence before updating current shadow state.
            persist_summary = persist_method(
                core,
                organization_id=organization_id,
                facility_id=facility_id,
                resource=local,
                environment=environment,
                actor=actor,
                records=records,
                transport="metrc_last_modified_delta",
            )
            completed_at = datetime.now(timezone.utc)
            self._mark_incremental_cursor(
                organization_id=organization_id,
                facility_id=facility_id,
                resource=local,
                environment=environment,
                actor=actor,
                completed_at=completed_at,
            )
            snapshot_stats = self.snapshots.upsert_delta(
                organization_id=organization_id,
                facility_id=facility_id,
                provider="metrc",
                environment=environment,
                resource=local,
                run_id=str(uuid.uuid4()),
                records=records,
            )
            deltas[local] = records
            resources.append({
                "resource": local,
                "provider_resource": by_name[local],
                "status": "succeeded",
                "record_count": len(records),
                "page_count": int(result.get("page_count") or 1),
                "last_modified_start": result.get("last_modified_start"),
                "overlap_minutes": 5,
                "audit": persist_summary,
                "current_snapshot": snapshot_stats,
                "current_snapshot_changed": bool(records),
                "omitted_rows_marked_absent": False,
            })

        workspace_snapshots: dict[str, list[dict[str, Any]]] = {
            "items": deltas.get("items", []),
            "packages": deltas.get("packages", []),
        }
        cultivation_changed = any(deltas.get(resource) for resource in CULTIVATION_RESOURCES)
        cultivation_baseline_complete = all(baselines.get(resource) is not None for resource in CULTIVATION_RESOURCES)
        if cultivation_changed and cultivation_baseline_complete:
            # Changed plants/harvests need the already-current location and batch
            # dependencies even when those master records were not part of this
            # LastModified window. Read them from DoobieLogic's local snapshot,
            # never by making a second provider request.
            workspace_snapshots.update({
                "locations": self._current_snapshot_records(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    environment=environment,
                    resource="locations",
                ),
                "plant_batches": self._current_snapshot_records(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    environment=environment,
                    resource="plant_batches",
                ),
                "plants_vegetative": deltas.get("plants_vegetative", []),
                "plants_flowering": deltas.get("plants_flowering", []),
                "harvests": deltas.get("harvests", []),
            })

        workspace = MetrcWorkspaceHydrationService(self.engine).hydrate(
            organization_id=organization_id,
            facility_id=facility_id,
            state=state,
            environment=environment,
            license_number=license_number,
            actor=actor,
            resource_snapshots=workspace_snapshots,
        )
        if cultivation_changed:
            workspace.setdefault("workspace_gates", {})["cultivation"] = {
                "status": "current_delta_applied" if cultivation_baseline_complete else "withheld_incomplete_baseline",
                "required_resources": list(CULTIVATION_RESOURCES),
                "network_request_made_for_dependencies": False,
            }

        ordered = sorted(resources, key=lambda row: row["resource"])
        return {
            "provider": "metrc",
            "environment": environment,
            "license_number": license_number,
            "mode": "last_modified_delta",
            "overlap_minutes": 5,
            "destructive_membership_replacement": False,
            "periodic_full_snapshot_required_for_absence": True,
            "resources": ordered,
            "workspace_hydration": workspace,
            "totals": {
                "resources": len(ordered),
                "succeeded": sum(row["status"] == "succeeded" for row in ordered),
                "skipped": sum(row["status"] == "skipped" for row in ordered),
                "full_sync_required": sum(row["status"] == "full_sync_required" for row in ordered),
                "failed": sum(row["status"] == "failed" for row in ordered),
                "records": sum(int(row.get("record_count") or 0) for row in ordered if row["status"] == "succeeded"),
            },
        }

    def _baselines(self, *, organization_id: str, facility_id: str, environment: str) -> dict[str, datetime | None]:
        resource_names = tuple(name for name, _provider in INCREMENTAL_RESOURCES)
        with self.engine.connect() as connection:
            rows = list(connection.execute(
                select(
                    IntegrationSyncState.resource,
                    IntegrationSyncState.cursor,
                    IntegrationSyncState.last_success_at,
                ).where(
                    IntegrationSyncState.organization_id == organization_id,
                    IntegrationSyncState.facility_id == facility_id,
                    IntegrationSyncState.provider == "metrc",
                    IntegrationSyncState.environment == environment,
                    IntegrationSyncState.resource.in_(resource_names),
                    IntegrationSyncState.status == "succeeded",
                )
            ))
        output: dict[str, datetime | None] = {name: None for name in resource_names}
        for resource, cursor, last_success_at in rows:
            cursor_value = str(cursor or "")
            baseline = _aware(last_success_at)
            if baseline is not None and (cursor_value.startswith("initial-full") or cursor_value.startswith("incremental:")):
                output[str(resource)] = baseline
        return output

    def _permission_skipped_resources(self, *, organization_id: str, facility_id: str, environment: str) -> set[str]:
        resource_names = tuple(name for name, _provider in INCREMENTAL_RESOURCES)
        with self.engine.connect() as connection:
            rows = list(connection.execute(
                select(IntegrationSyncState.resource, IntegrationSyncState.cursor).where(
                    IntegrationSyncState.organization_id == organization_id,
                    IntegrationSyncState.facility_id == facility_id,
                    IntegrationSyncState.provider == "metrc",
                    IntegrationSyncState.environment == environment,
                    IntegrationSyncState.resource.in_(resource_names),
                    IntegrationSyncState.status == "succeeded",
                )
            ))
        return {
            str(resource)
            for resource, cursor in rows
            if str(cursor or "").startswith("permission-skipped")
        }

    def _current_snapshot_records(
        self,
        *,
        organization_id: str,
        facility_id: str,
        environment: str,
        resource: str,
    ) -> list[dict[str, Any]]:
        rows = self.snapshots.current(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            resources=(resource,),
            environment=environment,
            limit=10000,
        )
        records: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row.raw_payload_json or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                records.append(payload)
        return records

    def _fetch_delta(
        self,
        *,
        provider_resource: str,
        baseline: datetime,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        start = (_aware(baseline) or datetime.now(timezone.utc)) - LAST_MODIFIED_OVERLAP
        start_value = _provider_timestamp(start)
        page = 1
        total_pages = 1
        records: list[dict[str, Any]] = []
        first: dict[str, Any] | None = None
        while page <= min(total_pages, MAX_INITIAL_PAGES):
            result = base_bootstrap.fetch_metrc_resource(
                state=state,
                user_api_key=user_api_key,
                integrator_api_key=integrator_api_key,
                resource=provider_resource,
                environment=environment,
                license_number=license_number,
                query={"lastModifiedStart": start_value},
                page_size=PAGE_SIZE,
                page_number=page,
                timeout_seconds=10,
                max_attempts=READ_MAX_ATTEMPTS,
            )
            if first is None:
                first = dict(result)
            if not result.get("ok"):
                result["last_modified_start"] = start_value
                return result
            records.extend(dict(row) for row in result.get("records") or [] if isinstance(row, dict))
            total_pages = _total_pages(result.get("payload"))
            page += 1
        output = first or {"ok": True, "status": "connected", "message": "Metrc incremental read succeeded."}
        output["records"] = records
        output["page_count"] = min(total_pages, MAX_INITIAL_PAGES)
        output["truncated"] = total_pages > MAX_INITIAL_PAGES
        output["last_modified_start"] = start_value
        return output

    def _mark_incremental_cursor(
        self,
        *,
        organization_id: str,
        facility_id: str,
        resource: str,
        environment: str,
        actor: str,
        completed_at: datetime,
    ) -> None:
        from sqlalchemy.orm import Session

        with Session(self.engine) as session, session.begin():
            state = session.scalar(select(IntegrationSyncState).where(
                IntegrationSyncState.organization_id == organization_id,
                IntegrationSyncState.facility_id == facility_id,
                IntegrationSyncState.provider == "metrc",
                IntegrationSyncState.environment == environment,
                IntegrationSyncState.resource == resource,
            ))
            if state is None:
                return
            state.cursor = f"incremental:{_provider_timestamp(completed_at)}"
            state.status = "succeeded"
            state.last_completed_at = completed_at
            state.last_success_at = completed_at
            state.last_error = ""
            state.updated_by = actor
