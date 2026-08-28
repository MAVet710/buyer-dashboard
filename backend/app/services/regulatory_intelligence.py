from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from modules.coman.models import Facility
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.metrc_production import (
    fetch_all_active_harvests,
    fetch_all_active_plant_batches,
    fetch_all_active_processing_jobs,
    fetch_all_flowering_plants,
    fetch_all_vegetative_plants,
)
from services.metrc_receiving import fetch_all_transfer_deliveries
from services.metrc_reconciliation import fetch_all_active_metrc_packages
from services.metrc_wholesale import (
    fetch_all_outgoing_transfers,
    fetch_all_transporter_drivers,
    fetch_all_transporter_vehicles,
    fetch_all_wholesale_delivery_packages,
)

from ..auth import RequestContext
from ..config import Settings
from .cultivation_reconciliation import CultivationMetrcReconciliationService
from .inventory_reconciliation import InventoryMetrcReconciliationService
from .metrc_context import MetrcContext, resolve_metrc_context


SEVERITY_RANK = {"high": 0, "medium": 1, "info": 2}


class RegulatoryIntelligenceService:
    """Build one read-only, evidence-backed regulatory attention model.

    This service is deliberately deterministic. It never changes Metrc or local
    operational state and it never asks a model to decide whether something is
    compliant. It only surfaces observable mismatches, provider states, and
    traceability exceptions so Compliance and Doobie Agent consume the same
    facility-scoped evidence.
    """

    def __init__(self, engine: Engine, settings: Settings):
        self.engine = engine
        self.settings = settings

    def collect(self, context: RequestContext) -> dict[str, Any]:
        capabilities = self._capabilities(context)
        findings: list[dict[str, Any]] = []
        warnings: list[str] = []
        snapshots: dict[str, Any] = {}

        self._traceability_findings(context, findings, snapshots)

        try:
            _, metrc = resolve_metrc_context(self.engine, self.settings, context)
        except RuntimeError as exc:
            metrc = MetrcContext(configured=False, message=str(exc))

        scope = {
            "organization_id": context.organization_id,
            "facility_id": context.facility_id,
            "capabilities": sorted(capabilities),
            "provider": "metrc",
            "jurisdiction_code": metrc.state.upper() if metrc.state else "",
            "license_number": metrc.license_number,
            "environment": metrc.environment,
        }

        if not metrc.configured:
            warnings.append(metrc.message or "Metrc is not configured for this facility.")
            return self._report(
                configured=False,
                ready=False,
                scope=scope,
                findings=findings,
                warnings=warnings,
                snapshots=snapshots,
                message=metrc.message or "Metrc is not configured for this facility.",
            )
        if metrc.status != "connected":
            warnings.append("Validate the Metrc connection for this exact facility before loading live regulatory intelligence.")
            findings.append(self._finding(
                severity="high",
                domain="integration",
                code="metrc_connection_not_validated",
                title="Metrc connection needs validation",
                message="The saved Metrc connection is not in a validated connected state, so no live regulatory reads were attempted.",
                source="trusted_mapping_gate",
                recommended_review="Validate this facility's Metrc connection before relying on live regulatory state.",
                metrc=metrc,
            ))
            return self._report(True, False, scope, findings, warnings, snapshots, "Metrc connection validation is required.")
        if not metrc.trusted_mapping:
            warnings.append("The exact facility/license/jurisdiction/credential/environment mapping is not trusted yet.")
            findings.append(self._finding(
                severity="high",
                domain="integration",
                code="metrc_mapping_not_trusted",
                title="Metrc facility mapping is not verified",
                message="Live regulatory reads are blocked until an administrator verifies the exact facility, license, jurisdiction, credential, and environment mapping.",
                source="trusted_mapping_gate",
                recommended_review="Verify the saved Metrc mapping for this facility before live regulatory reads are enabled.",
                metrc=metrc,
            ))
            return self._report(True, False, scope, findings, warnings, snapshots, "Trusted Metrc mapping is required.")

        common = {
            "state": metrc.state,
            "user_api_key": metrc.user_api_key,
            "integrator_api_key": metrc.integrator_api_key,
            "license_number": metrc.license_number,
            "environment": metrc.environment,
        }

        if capabilities & {"retail", "production", "cultivation"}:
            self._inventory_findings(context, metrc, common, findings, warnings, snapshots)
        if "production" in capabilities:
            self._manufacturing_findings(metrc, common, findings, warnings, snapshots)
        if "cultivation" in capabilities:
            self._cultivation_findings(context, metrc, common, findings, warnings, snapshots)
        if "commercial" in capabilities:
            self._wholesale_findings(metrc, common, findings, warnings, snapshots)

        return self._report(
            configured=True,
            ready=True,
            scope=scope,
            findings=findings,
            warnings=warnings,
            snapshots=snapshots,
            message="Regulatory intelligence was built from the exact trusted facility mapping and local audit ledgers.",
        )

    def _capabilities(self, context: RequestContext) -> set[str]:
        with Session(self.engine) as session:
            facility = session.get(Facility, context.facility_id)
        if not facility or facility.organization_id != context.organization_id:
            return set()
        output = set()
        if facility.retail_enabled:
            output.add("retail")
        if facility.production_enabled:
            output.add("production")
        if facility.cultivation_enabled:
            output.add("cultivation")
        if facility.commercial_enabled:
            output.add("commercial")
        return output

    def _traceability_findings(self, context: RequestContext, findings: list[dict[str, Any]], snapshots: dict[str, Any]) -> None:
        repo = TraceabilityBackofficeRepository(self.engine)
        summary = repo.summary(context.organization_id, context.facility_id)
        rows = repo.list_transactions(context.organization_id, context.facility_id, statuses=())
        exception_rows = [row for row in rows if str(row.status).casefold() in {"rejected", "reconciliation_required", "failed"}]
        snapshots["traceability"] = {
            "summary": summary,
            "exception_count": len(exception_rows),
        }
        for row in exception_rows[:100]:
            findings.append(self._finding(
                severity="high",
                domain="traceability",
                code=f"traceability_{str(row.status).casefold()}",
                title=f"Traceability action {str(row.status).replace('_', ' ')}",
                message=str(row.error_message or row.error_code or row.reason or "This traceability action requires reconciliation review."),
                entity_type=str(row.entity_type or "traceability_transaction"),
                entity_id=str(row.entity_id or row.id),
                source="local_traceability_ledger",
                recommended_review="Open Queue & Reconciliation, compare the provider state, and document the evidence before changing lifecycle status.",
                extra={"transaction_id": row.id, "operation_type": row.operation_type, "external_reference": row.external_reference},
            ))

    def _inventory_findings(
        self,
        context: RequestContext,
        metrc: MetrcContext,
        common: dict[str, Any],
        findings: list[dict[str, Any]],
        warnings: list[str],
        snapshots: dict[str, Any],
    ) -> None:
        result = fetch_all_active_metrc_packages(**common)
        if not result.get("ok"):
            self._resource_failure("inventory", "packages_active", result, metrc, findings, warnings)
            return
        records = [dict(row) for row in result.get("records") or [] if isinstance(row, dict)]
        read_plan = result.get("read_plan") if isinstance(result.get("read_plan"), dict) else {}
        report = InventoryMetrcReconciliationService(self.engine).reconcile(
            context.organization_id,
            context.facility_id,
            jurisdiction_code=metrc.state.upper(),
            license_number=metrc.license_number,
            environment=metrc.environment,
            metrc_records=records,
            evidence=read_plan.get("evidence") if isinstance(read_plan.get("evidence"), dict) else None,
        )
        snapshots["inventory"] = {
            "summary": report.get("summary") or {},
            "page_count": int(result.get("page_count") or 1),
            "truncated": bool(result.get("truncated")),
        }
        for row in report.get("discrepancies") or []:
            if not isinstance(row, dict):
                continue
            package = str(row.get("package_id") or row.get("metrc_label") or row.get("local_package_id") or "")
            findings.append(self._finding(
                severity=str(row.get("severity") or "medium"),
                domain="inventory",
                code=str(row.get("code") or "package_mismatch"),
                title=self._title(str(row.get("code") or "package mismatch")),
                message=str(row.get("message") or "DoobieLogic and Metrc package state require reconciliation."),
                entity_type="package",
                entity_id=package,
                source="metrc_package_reconciliation",
                recommended_review="Review the physical/local lot and the exact Metrc package before making any adjustment.",
                metrc=metrc,
            ))

        for record in records[:500]:
            status = str(record.get("status") or "").strip()
            token = status.casefold()
            if any(value in token for value in ("fail", "hold", "quarantine")):
                severity = "high"
                code = "package_regulatory_hold"
                review = "Verify the package testing/hold state and do not treat the package as released until the authoritative state is resolved."
            elif any(value in token for value in ("pending", "testing", "submitted", "not tested", "not_tested")):
                severity = "medium"
                code = "package_testing_pending"
                review = "Verify the current lab/testing state before downstream release, production, or sale decisions."
            else:
                continue
            findings.append(self._finding(
                severity=severity,
                domain="inventory",
                code=code,
                title=self._title(code),
                message=f"Metrc returned package testing/status state '{status}'.",
                entity_type="package",
                entity_id=str(record.get("label") or record.get("provider_id") or ""),
                source="metrc_packages_active",
                recommended_review=review,
                metrc=metrc,
            ))

    def _manufacturing_findings(
        self,
        metrc: MetrcContext,
        common: dict[str, Any],
        findings: list[dict[str, Any]],
        warnings: list[str],
        snapshots: dict[str, Any],
    ) -> None:
        result = fetch_all_active_processing_jobs(**common)
        if not result.get("ok"):
            self._resource_failure("manufacturing", "processing_active", result, metrc, findings, warnings)
            return
        records = [dict(row) for row in result.get("records") or [] if isinstance(row, dict)]
        snapshots["manufacturing"] = {"active_processing_job_count": len(records), "truncated": bool(result.get("truncated"))}
        for record in records[:500]:
            status = str(record.get("status") or "").strip()
            token = status.casefold()
            if not any(value in token for value in ("fail", "hold", "error", "quarantine")):
                continue
            findings.append(self._finding(
                severity="high" if any(value in token for value in ("fail", "error")) else "medium",
                domain="manufacturing",
                code="processing_job_exception",
                title="Processing job needs regulatory review",
                message=f"Metrc returned active processing job status '{status}'.",
                entity_type="processing_job",
                entity_id=str(record.get("provider_id") or record.get("name") or ""),
                source="metrc_processing_active",
                recommended_review="Compare the processing job to the production run and resolve the provider state before closing or advancing the run.",
                metrc=metrc,
            ))

    def _cultivation_findings(
        self,
        context: RequestContext,
        metrc: MetrcContext,
        common: dict[str, Any],
        findings: list[dict[str, Any]],
        warnings: list[str],
        snapshots: dict[str, Any],
    ) -> None:
        batches = fetch_all_active_plant_batches(**common)
        vegetative = fetch_all_vegetative_plants(**common)
        flowering = fetch_all_flowering_plants(**common)
        harvests = fetch_all_active_harvests(**common)
        results = {
            "plant_batches": batches,
            "vegetative_plants": vegetative,
            "flowering_plants": flowering,
            "harvests": harvests,
        }
        for name, result in results.items():
            if not result.get("ok"):
                self._resource_failure("cultivation", name, result, metrc, findings, warnings)
        if not vegetative.get("ok") or not flowering.get("ok"):
            snapshots["cultivation"] = {"available": False}
            return
        veg_records = [dict(row) for row in vegetative.get("records") or [] if isinstance(row, dict)]
        flower_records = [dict(row) for row in flowering.get("records") or [] if isinstance(row, dict)]
        veg_plan = vegetative.get("read_plan") if isinstance(vegetative.get("read_plan"), dict) else {}
        report = CultivationMetrcReconciliationService(self.engine).reconcile(
            context.organization_id,
            context.facility_id,
            jurisdiction_code=metrc.state.upper(),
            license_number=metrc.license_number,
            environment=metrc.environment,
            vegetative_records=veg_records,
            flowering_records=flower_records,
            evidence=veg_plan.get("evidence") if isinstance(veg_plan.get("evidence"), dict) else None,
        )
        snapshots["cultivation"] = {
            "summary": report.get("summary") or {},
            "plant_batch_count": len([row for row in batches.get("records") or [] if isinstance(row, dict)]) if batches.get("ok") else None,
            "harvest_count": len([row for row in harvests.get("records") or [] if isinstance(row, dict)]) if harvests.get("ok") else None,
        }
        for row in report.get("discrepancies") or []:
            if not isinstance(row, dict):
                continue
            findings.append(self._finding(
                severity=str(row.get("severity") or "medium"),
                domain="cultivation",
                code=str(row.get("code") or "plant_mismatch"),
                title=self._title(str(row.get("code") or "plant mismatch")),
                message=str(row.get("message") or "DoobieLogic and Metrc plant state require reconciliation."),
                entity_type="plant",
                entity_id=str(row.get("plant_tag") or ""),
                source="metrc_plant_reconciliation",
                recommended_review="Verify the physical plant tag, room, lifecycle phase, and Metrc plant record before recording a lifecycle correction.",
                metrc=metrc,
            ))

    def _wholesale_findings(
        self,
        metrc: MetrcContext,
        common: dict[str, Any],
        findings: list[dict[str, Any]],
        warnings: list[str],
        snapshots: dict[str, Any],
    ) -> None:
        outgoing = fetch_all_outgoing_transfers(**common)
        if not outgoing.get("ok"):
            self._resource_failure("wholesale", "outgoing_transfers", outgoing, metrc, findings, warnings)
            return
        drivers = fetch_all_transporter_drivers(**common)
        vehicles = fetch_all_transporter_vehicles(**common)
        transfer_rows = [dict(row) for row in outgoing.get("rows") or [] if isinstance(row, dict)]
        expanded = transfer_rows[:50]
        delivery_count = 0
        package_count = 0

        for transfer in expanded:
            transfer_id = self._source_string(transfer, "Id", "TransferId")
            manifest = self._source_string(transfer, "ManifestNumber", "Manifest", "ManifestNo")
            recipient_license = self._source_string(
                transfer,
                "DestFacilityLicenseNumber",
                "RecipientFacilityLicenseNumber",
                "ReceiverFacilityLicenseNumber",
            )
            if not manifest:
                findings.append(self._finding(
                    severity="medium",
                    domain="wholesale",
                    code="transfer_manifest_reference_missing",
                    title="Outgoing transfer has no manifest reference",
                    message="The active outgoing Metrc transfer did not return a manifest reference in the provider payload.",
                    entity_type="transfer",
                    entity_id=transfer_id,
                    source="metrc_outgoing_transfers",
                    recommended_review="Verify the transfer/manifest state before shipment. This signal does not by itself determine whether the transfer is legally incomplete.",
                    metrc=metrc,
                ))
            if not recipient_license:
                findings.append(self._finding(
                    severity="medium",
                    domain="wholesale",
                    code="transfer_recipient_license_missing",
                    title="Recipient license is not visible on outgoing transfer",
                    message="The outgoing transfer payload did not return a recipient facility license number.",
                    entity_type="transfer",
                    entity_id=transfer_id,
                    source="metrc_outgoing_transfers",
                    recommended_review="Verify the destination license and transfer details before fulfillment or shipment.",
                    metrc=metrc,
                ))
            if not transfer_id:
                findings.append(self._finding(
                    severity="medium",
                    domain="wholesale",
                    code="transfer_id_missing",
                    title="Outgoing transfer could not be expanded",
                    message="One Metrc outgoing transfer did not return an id, so deliveries and wholesale packages could not be inspected.",
                    entity_type="transfer",
                    source="metrc_outgoing_transfers",
                    recommended_review="Inspect the provider transfer record directly before shipment.",
                    metrc=metrc,
                ))
                continue
            deliveries = fetch_all_transfer_deliveries(
                state=metrc.state,
                user_api_key=metrc.user_api_key,
                integrator_api_key=metrc.integrator_api_key,
                transfer_id=transfer_id,
                environment=metrc.environment,
            )
            if not deliveries.get("ok"):
                self._resource_failure("wholesale", f"transfer_{transfer_id}_deliveries", deliveries, metrc, findings, warnings, entity_id=transfer_id)
                continue
            delivery_rows = [dict(row) for row in deliveries.get("rows") or [] if isinstance(row, dict)]
            delivery_count += len(delivery_rows)
            for delivery in delivery_rows:
                delivery_id = self._source_string(delivery, "Id", "DeliveryId")
                if not delivery_id:
                    findings.append(self._finding(
                        severity="medium",
                        domain="wholesale",
                        code="delivery_id_missing",
                        title="Transfer delivery could not be expanded",
                        message=f"Transfer {transfer_id} included a delivery without an id.",
                        entity_type="transfer",
                        entity_id=transfer_id,
                        source="metrc_transfer_deliveries",
                        recommended_review="Inspect the provider delivery before shipment.",
                        metrc=metrc,
                    ))
                    continue
                packages = fetch_all_wholesale_delivery_packages(
                    state=metrc.state,
                    user_api_key=metrc.user_api_key,
                    integrator_api_key=metrc.integrator_api_key,
                    delivery_id=delivery_id,
                    environment=metrc.environment,
                )
                if not packages.get("ok"):
                    self._resource_failure("wholesale", f"delivery_{delivery_id}_packages", packages, metrc, findings, warnings, entity_id=delivery_id)
                    continue
                package_count += len([row for row in packages.get("rows") or [] if isinstance(row, dict)])

        if len(transfer_rows) > 50:
            findings.append(self._finding(
                severity="info",
                domain="wholesale",
                code="transfer_expansion_limited",
                title="Transfer detail expansion was capped",
                message=f"{len(transfer_rows)} outgoing transfers were returned; only the first 50 were expanded into deliveries and wholesale packages.",
                source="metrc_outgoing_transfers",
                recommended_review="Use Wholesale Regulatory Health to inspect additional transfer detail if needed.",
                metrc=metrc,
            ))

        driver_count = len([row for row in drivers.get("records") or [] if isinstance(row, dict)]) if drivers.get("ok") else None
        vehicle_count = len([row for row in vehicles.get("records") or [] if isinstance(row, dict)]) if vehicles.get("ok") else None
        if transfer_rows and drivers.get("ok") and driver_count == 0:
            findings.append(self._finding(
                severity="medium",
                domain="wholesale",
                code="no_transporter_drivers_returned",
                title="No transporter drivers returned",
                message="Metrc returned active outgoing transfers but no transporter driver records for this credential.",
                source="metrc_transporter_drivers",
                recommended_review="Verify transporter assignment and credential scope before shipment; this signal does not assert a jurisdiction-specific staffing requirement.",
                metrc=metrc,
            ))
        if transfer_rows and vehicles.get("ok") and vehicle_count == 0:
            findings.append(self._finding(
                severity="medium",
                domain="wholesale",
                code="no_transporter_vehicles_returned",
                title="No transporter vehicles returned",
                message="Metrc returned active outgoing transfers but no transporter vehicle records for this credential.",
                source="metrc_transporter_vehicles",
                recommended_review="Verify vehicle assignment and credential scope before shipment; this signal does not assert a jurisdiction-specific vehicle requirement.",
                metrc=metrc,
            ))
        if not drivers.get("ok"):
            warnings.append(str(drivers.get("message") or "Metrc transporter drivers were unavailable for this credential."))
        if not vehicles.get("ok"):
            warnings.append(str(vehicles.get("message") or "Metrc transporter vehicles were unavailable for this credential."))

        snapshots["wholesale"] = {
            "outgoing_transfer_count": len(transfer_rows),
            "expanded_transfer_count": len(expanded),
            "delivery_count": delivery_count,
            "wholesale_package_count": package_count,
            "transporter_driver_count": driver_count,
            "transporter_vehicle_count": vehicle_count,
            "expansion_limited": len(transfer_rows) > 50,
        }

    def _resource_failure(
        self,
        domain: str,
        resource: str,
        result: dict[str, Any],
        metrc: MetrcContext,
        findings: list[dict[str, Any]],
        warnings: list[str],
        *,
        entity_id: str = "",
    ) -> None:
        message = str(result.get("message") or f"Metrc resource {resource} could not be loaded.")
        warnings.append(message)
        findings.append(self._finding(
            severity="medium",
            domain=domain,
            code="regulatory_resource_unavailable",
            title=f"{self._title(resource)} is unavailable",
            message=message,
            entity_type="regulatory_resource",
            entity_id=entity_id or resource,
            source=resource,
            recommended_review="Verify provider capability, credential scope, and connectivity before relying on this resource.",
            metrc=metrc,
        ))

    def _report(
        self,
        configured: bool,
        ready: bool,
        scope: dict[str, Any],
        findings: list[dict[str, Any]],
        warnings: list[str],
        snapshots: dict[str, Any],
        message: str,
    ) -> dict[str, Any]:
        findings.sort(key=lambda row: (SEVERITY_RANK.get(str(row.get("severity")), 9), str(row.get("domain")), str(row.get("code")), str(row.get("entity_id"))))
        counts = {"high": 0, "medium": 0, "info": 0}
        domains: dict[str, int] = {}
        for row in findings:
            severity = str(row.get("severity") or "info")
            counts[severity] = counts.get(severity, 0) + 1
            domain = str(row.get("domain") or "other")
            domains[domain] = domains.get(domain, 0) + 1
        score = min(100, counts.get("high", 0) * 20 + counts.get("medium", 0) * 7 + counts.get("info", 0))
        status = "unavailable" if not ready else "attention" if counts.get("high", 0) or counts.get("medium", 0) else "clean"
        return {
            "configured": configured,
            "ready": ready,
            "provider": "metrc",
            "read_only": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "message": message,
            "scope": scope,
            "summary": {
                "status": status,
                "attention_score": score,
                "finding_count": len(findings),
                "high_count": counts.get("high", 0),
                "medium_count": counts.get("medium", 0),
                "info_count": counts.get("info", 0),
                "by_domain": domains,
            },
            "findings": findings[:500],
            "warnings": list(dict.fromkeys(warnings))[:100],
            "snapshots": snapshots,
        }

    @staticmethod
    def _finding(
        *,
        severity: str,
        domain: str,
        code: str,
        title: str,
        message: str,
        entity_type: str = "",
        entity_id: str = "",
        source: str,
        recommended_review: str,
        metrc: MetrcContext | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        output = {
            "severity": severity if severity in SEVERITY_RANK else "info",
            "domain": domain,
            "code": code,
            "title": title,
            "message": message,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "source": source,
            "recommended_review": recommended_review,
            "jurisdiction_code": metrc.state.upper() if metrc and metrc.state else "",
            "license_number": metrc.license_number if metrc else "",
            "environment": metrc.environment if metrc else "",
        }
        if extra:
            output["evidence"] = extra
        return output

    @staticmethod
    def _source_string(row: dict[str, Any], *keys: str) -> str:
        source = row.get("source") if isinstance(row.get("source"), dict) else row
        for key in keys:
            value = source.get(key) if isinstance(source, dict) else None
            if value is not None and str(value).strip():
                if isinstance(value, dict):
                    value = value.get("Name") or value.get("name") or ""
                return str(value).strip()
        return ""

    @staticmethod
    def _title(value: str) -> str:
        return " ".join(part.capitalize() for part in str(value or "").replace("-", "_").split("_") if part)
