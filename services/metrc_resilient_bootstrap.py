from __future__ import annotations

from threading import BoundedSemaphore
from typing import Any

from modules.integrations.hydration_checkpoints import (
    IntegrationHydrationCheckpointRepository,
    page_fingerprint,
)
from modules.regulatory.metrc_resources import payload_rows
from services.metrc_client import MetrcTransport, fetch_metrc_resource
from services.metrc_facility_bootstrap import MAX_INITIAL_PAGES, PAGE_SIZE, _total_pages
from services.metrc_facility_snapshot_bootstrap import SnapshottingMetrcFacilityBootstrapService


READ_MAX_ATTEMPTS = 4
PROVIDER_CONCURRENCY = 3


class ResilientSnapshottingMetrcFacilityBootstrapService(SnapshottingMetrcFacilityBootstrapService):
    """Authenticated Metrc hydration with bounded retries and durable page resume.

    A page checkpoint is only a resume journal. It never becomes current provider
    truth by itself. The existing snapshot layer replaces current membership only
    after this service returns one complete, non-truncated collection.

    Resume is deliberately conservative:
    - at most three provider collections are read concurrently;
    - every network page gets up to four bounded transport attempts;
    - an incomplete generation is resumable for 30 minutes;
    - page 1 is re-read before resume and must have the same fingerprint and
      TotalPages value as the checkpoint anchor;
    - TotalPages must remain stable through the generation;
    - if those checks fail, the generation is restarted or rejected rather than
      promoting a potentially mixed provider snapshot.
    """

    def __init__(self, engine):
        super().__init__(engine)
        self.checkpoints = IntegrationHydrationCheckpointRepository(engine, resume_ttl_minutes=30)
        self._provider_slots = BoundedSemaphore(PROVIDER_CONCURRENCY)
        self._hydration_scope: dict[str, str] = {}

    def sync(self, **kwargs):
        self._hydration_scope = {
            "organization_id": str(kwargs.get("organization_id") or ""),
            "facility_id": str(kwargs.get("facility_id") or ""),
            "environment": str(kwargs.get("environment") or "").strip().casefold(),
            "license_number": str(kwargs.get("license_number") or "").strip(),
        }
        try:
            result = super().sync(**kwargs)
        finally:
            self._hydration_scope = {}
        result["hydration_reliability"] = {
            "page_checkpoint_resume": True,
            "resume_anchor_validation": True,
            "resume_ttl_minutes": 30,
            "provider_concurrency": PROVIDER_CONCURRENCY,
            "read_max_attempts": READ_MAX_ATTEMPTS,
            "partial_pages_promoted_to_current_snapshot": False,
        }
        return result

    def _scope(self) -> dict[str, str]:
        scope = dict(self._hydration_scope)
        if not scope.get("organization_id") or not scope.get("facility_id") or not scope.get("environment"):
            raise RuntimeError("Metrc hydration checkpoint scope is unavailable.")
        return scope

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
        with self._provider_slots:
            scope = self._scope()
            resource_key = f"normalized:{license_number}:{resource}"
            resume = self.checkpoints.latest_incomplete(
                organization_id=scope["organization_id"],
                facility_id=scope["facility_id"],
                provider="metrc",
                environment=environment,
                resource_key=resource_key,
            )
            if resume and int(resume["next_page"]) > MAX_INITIAL_PAGES:
                resume = None

            def read(page_number: int) -> dict[str, Any]:
                return fetch_metrc_resource(
                    state=state,
                    user_api_key=user_api_key,
                    integrator_api_key=integrator_api_key,
                    resource=resource,
                    environment=environment,
                    license_number=license_number,
                    page_size=PAGE_SIZE,
                    page_number=page_number,
                    timeout_seconds=10,
                    max_attempts=READ_MAX_ATTEMPTS,
                )

            return self._read_paginated(
                resource_key=resource_key,
                environment=environment,
                resume=resume,
                read=read,
                rows=lambda result: [dict(row) for row in result.get("records", []) if isinstance(row, dict)],
                total_pages=lambda result: _total_pages(result.get("payload")),
            )

    def _fetch_all_direct(
        self,
        *,
        transport: MetrcTransport,
        path: str,
        params: dict[str, Any],
        paginated: bool,
    ) -> dict[str, Any]:
        with self._provider_slots:
            resilient = MetrcTransport(
                state=transport.state,
                integrator_api_key=transport.integrator_api_key,
                user_api_key=transport.user_api_key,
                environment=transport.environment,
                timeout_seconds=transport.timeout_seconds,
                max_attempts=READ_MAX_ATTEMPTS,
                request_get=transport.request_get,
                sleeper=transport.sleeper,
            )
            if not paginated:
                result = resilient.get(path, params)
                if result.get("ok"):
                    result["records"] = payload_rows(result.get("payload"))
                    result["page_count"] = 1
                    result["truncated"] = False
                    result["checkpoint"] = {"resumed": False, "page_checkpointed": False}
                return result

            scope = self._scope()
            license_number = str(params.get("licenseNumber") or scope.get("license_number") or "").strip()
            resource_key = f"direct:{license_number}:{path}"
            resume = self.checkpoints.latest_incomplete(
                organization_id=scope["organization_id"],
                facility_id=scope["facility_id"],
                provider="metrc",
                environment=resilient.environment,
                resource_key=resource_key,
            )
            if resume and int(resume["next_page"]) > MAX_INITIAL_PAGES:
                resume = None

            def read(page_number: int) -> dict[str, Any]:
                query = dict(params)
                query.update({"pageSize": PAGE_SIZE, "pageNumber": page_number})
                return resilient.get(path, query)

            return self._read_paginated(
                resource_key=resource_key,
                environment=resilient.environment,
                resume=resume,
                read=read,
                rows=lambda result: payload_rows(result.get("payload")),
                total_pages=lambda result: _total_pages(result.get("payload")),
            )

    def _read_paginated(
        self,
        *,
        resource_key: str,
        environment: str,
        resume: dict[str, Any] | None,
        read,
        rows,
        total_pages,
    ) -> dict[str, Any]:
        scope = self._scope()
        first_result: dict[str, Any] | None = None
        records: list[dict[str, Any]] = []
        resumed = False

        # A resume generation must prove its page-1 anchor is still the same. If
        # not, start a fresh generation from the newly returned first page.
        first = read(1)
        if not first.get("ok"):
            first["checkpoint"] = {
                "status": "read_failed_before_anchor",
                "resumed": False,
                "resource_key": resource_key,
            }
            return first
        first_result = dict(first)
        first_rows = [dict(row) for row in rows(first) if isinstance(row, dict)]
        first_total = max(1, int(total_pages(first) or 1))
        first_fingerprint = page_fingerprint(first_rows)

        if resume and resume["first_page_fingerprint"] == first_fingerprint and int(resume["total_pages"]) == first_total:
            generation_id = str(resume["generation_id"])
            records = [dict(row) for row in resume["records"] if isinstance(row, dict)]
            page = int(resume["next_page"])
            expected_total = first_total
            resumed = True
        else:
            generation_id = self.checkpoints.new_generation()
            records = first_rows
            expected_total = first_total
            self.checkpoints.save_page(
                organization_id=scope["organization_id"],
                facility_id=scope["facility_id"],
                provider="metrc",
                environment=environment,
                resource_key=resource_key,
                generation_id=generation_id,
                page_number=1,
                total_pages=expected_total,
                records=first_rows,
            )
            page = 2

        while page <= min(expected_total, MAX_INITIAL_PAGES):
            result = read(page)
            if not result.get("ok"):
                result["checkpoint"] = {
                    "status": "incomplete_resumable",
                    "resumed": resumed,
                    "resource_key": resource_key,
                    "generation_id": generation_id,
                    "last_completed_page": page - 1,
                    "next_page": page,
                    "total_pages": expected_total,
                }
                return result
            page_total = max(1, int(total_pages(result) or 1))
            if page_total != expected_total:
                return {
                    "ok": False,
                    "status": "snapshot_changed_during_hydration",
                    "message": (
                        "Metrc pagination changed while the facility snapshot was being hydrated. "
                        "No partial membership was promoted; run sync again to start a fresh generation."
                    ),
                    "http_status": int(result.get("http_status") or 409),
                    "checkpoint": {
                        "status": "invalidated_provider_changed",
                        "resumed": resumed,
                        "resource_key": resource_key,
                        "generation_id": generation_id,
                        "last_completed_page": page - 1,
                        "observed_total_pages": page_total,
                        "expected_total_pages": expected_total,
                    },
                }
            page_rows = [dict(row) for row in rows(result) if isinstance(row, dict)]
            self.checkpoints.save_page(
                organization_id=scope["organization_id"],
                facility_id=scope["facility_id"],
                provider="metrc",
                environment=environment,
                resource_key=resource_key,
                generation_id=generation_id,
                page_number=page,
                total_pages=expected_total,
                records=page_rows,
            )
            records.extend(page_rows)
            page += 1

        output = first_result or {"ok": True, "status": "connected", "message": "Metrc request succeeded."}
        output["records"] = records
        output["page_count"] = min(expected_total, MAX_INITIAL_PAGES)
        output["truncated"] = expected_total > MAX_INITIAL_PAGES
        output["checkpoint"] = {
            "status": "complete" if not output["truncated"] else "bounded_incomplete",
            "resumed": resumed,
            "resource_key": resource_key,
            "generation_id": generation_id,
            "last_completed_page": min(expected_total, MAX_INITIAL_PAGES),
            "total_pages": expected_total,
        }
        return output

    def _persist_fetch_result(self, **kwargs):
        result = kwargs.get("result")
        summary = super()._persist_fetch_result(**kwargs)
        if isinstance(result, dict) and isinstance(result.get("checkpoint"), dict):
            summary["hydration_checkpoint"] = dict(result["checkpoint"])
        return summary
