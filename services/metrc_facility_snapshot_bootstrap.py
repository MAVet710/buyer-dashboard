from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Engine

from modules.integrations.provider_snapshot import IntegrationProviderSnapshotRepository
from services.metrc_facility_bootstrap import MetrcFacilityBootstrapService as BaseMetrcFacilityBootstrapService


class SnapshottingMetrcFacilityBootstrapService(BaseMetrcFacilityBootstrapService):
    """Persist complete authenticated Metrc reads into the current provider mirror.

    The base bootstrap remains responsible for provider access, immutable sync
    history, cursor/attempt evidence and canonical package materialization. This
    composition layer adds the separate answer to "what does Metrc say exists
    now?" without changing those audit semantics.

    Only complete successful resource reads replace current membership. A
    truncated, permission-skipped, failed or transport-uncertain read never marks
    previously known provider objects absent.
    """

    def __init__(self, engine: Engine):
        super().__init__(engine)
        self.provider_snapshots = IntegrationProviderSnapshotRepository(engine)

    def _replace_current_snapshot(
        self,
        *,
        organization_id: str,
        facility_id: str,
        environment: str,
        resource: str,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        stats = self.provider_snapshots.replace(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            environment=environment,
            resource=resource,
            run_id=run_id,
            records=records,
        )
        return {"status": "current", "snapshot_run_id": run_id, **stats}

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
        # Discovery persists only a fully returned single facility profile through
        # this direct method. Normal paginated resources are handled by the
        # completeness-aware _persist_fetch_result override below.
        summary = super()._persist(
            organization_id=organization_id,
            facility_id=facility_id,
            resource=resource,
            environment=environment,
            actor=actor,
            records=records,
            transport=transport,
        )
        if resource == "facility_profile":
            summary["current_snapshot"] = self._replace_current_snapshot(
                organization_id=organization_id,
                facility_id=facility_id,
                environment=environment,
                resource=resource,
                records=records,
            )
        return summary

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
                    "current_snapshot": {"status": "unchanged_permission_skipped"},
                }
            failure = self._failure(
                organization_id,
                facility_id,
                resource,
                environment,
                actor,
                message,
                http_status=http_status,
            )
            failure["current_snapshot"] = {"status": "unchanged_failed_read"}
            return failure

        records = [dict(row) for row in result.get("records", []) if isinstance(row, dict)]
        # Call the base implementation directly so normal resources do not pass
        # through the facility-profile-only _persist override above.
        summary = BaseMetrcFacilityBootstrapService._persist(
            self,
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

        if summary["truncated"]:
            summary["current_snapshot"] = {
                "status": "unchanged_incomplete_read",
                "reason": "The provider collection exceeded the defensive bootstrap page ceiling.",
            }
        else:
            summary["current_snapshot"] = self._replace_current_snapshot(
                organization_id=organization_id,
                facility_id=facility_id,
                environment=environment,
                resource=resource,
                records=records,
            )
        return summary
