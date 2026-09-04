"""Auditable provider dispatcher for queued traceability transactions."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import Engine

from modules.alpha_mode import AlphaOperatingModeService
from modules.coman.models import utc_now
from modules.integrations import IntegrationConfigurationService
from modules.regulatory import RegulatoryMappingService, require_metrc_write_contract
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.metrc_native import MetrcNativeError, submit_metrc_action, validate_metrc_action


class TraceabilityDispatchError(RuntimeError):
    pass


def _json_dict(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class TraceabilityDispatcher:
    """Dispatch only explicitly reviewed provider operations.

    Queue status is never treated as external success. The dispatcher requires
    an exact trusted tenant/facility mapping and an operation-specific write
    contract before a provider request can leave DoobieLogic. Every attempt is
    durable and uncertain outcomes reconcile instead of being blindly retried.
    """

    def __init__(self, engine: Engine, *, encryption_key: str, metrc_integrator_api_key: str):
        self.engine = engine
        self.integrations = IntegrationConfigurationService(engine, encryption_key)
        self.traceability = TraceabilityBackofficeRepository(engine)
        self.metrc_integrator_api_key = str(metrc_integrator_api_key or "").strip()

    def dispatch(self, *, organization_id: str, facility_id: str, transaction_id: str, actor: str) -> dict[str, Any]:
        tx = self.traceability.get_transaction(organization_id, facility_id, transaction_id)
        if tx.status != "queued":
            raise TraceabilityDispatchError(f"Only queued transactions can dispatch; current status is {tx.status}.")
        payload = _json_dict(tx.request_payload_json)
        if tx.provider == "metrc":
            return self._dispatch_metrc(tx, payload, actor)
        if tx.provider == "biotrack":
            self.traceability.record_attempt(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=tx.id,
                request_payload={"operation_type": tx.operation_type, "entity_id": tx.entity_id},
                error_code="unsupported_operation",
                error_message="BioTrack mutation adapter is not enabled for this state contract.",
            )
            self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=tx.id,
                new_status="reconciliation_required",
                actor=actor,
                reason="BioTrack state-specific mutation adapter is not enabled; no external request was sent.",
                source="provider_worker",
            )
            return {"ok": False, "status": "reconciliation_required", "provider": "biotrack", "outbound_request_sent": False}
        raise TraceabilityDispatchError(f"Automatic dispatch is not implemented for provider '{tx.provider}'.")

    def _no_request(self, tx, actor: str, *, code: str, message: str) -> dict[str, Any]:
        self.traceability.record_attempt(
            organization_id=tx.organization_id,
            facility_id=tx.facility_id,
            transaction_id=tx.id,
            error_code=code,
            error_message=message,
        )
        self.traceability.transition_logged(
            organization_id=tx.organization_id,
            facility_id=tx.facility_id,
            transaction_id=tx.id,
            new_status="reconciliation_required",
            actor=actor,
            reason=f"{message} No external request was sent.",
            source="provider_worker",
        )
        return {
            "ok": False,
            "status": "reconciliation_required",
            "provider": "metrc",
            "outbound_request_sent": False,
            "retryable": False,
        }

    def _dispatch_metrc(self, tx, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        try:
            mode = AlphaOperatingModeService(self.engine).current(tx.organization_id, tx.facility_id)
        except ValueError as exc:
            return self._no_request(
                tx,
                actor,
                code="facility_mode_unavailable",
                message=str(exc),
            )
        if not mode.metrc_enabled:
            return self._no_request(
                tx,
                actor,
                code="alpha_mode_doobielogic_sandbox",
                message=(
                    "DoobieLogic Sandbox is active for this facility. Metrc dispatch is disabled until an administrator selects Metrc Sandbox."
                ),
            )

        scope_key = f"{tx.requested_by}|{tx.facility_id}"
        row = self.integrations.get("user", scope_key, "metrc")
        if row is None:
            legacy = self.integrations.get("user", tx.requested_by, "metrc")
            if legacy is not None and str(legacy.facility_id or "") == str(tx.facility_id):
                row = legacy
        if row is None or row.status != "connected":
            return self._no_request(
                tx,
                actor,
                code="provider_not_connected",
                message="The requesting user's Metrc connection is not validated for this facility.",
            )
        if str(row.organization_id or "") != str(tx.organization_id) or str(row.facility_id or "") != str(tx.facility_id):
            return self._no_request(
                tx,
                actor,
                code="credential_scope_mismatch",
                message="The validated Metrc credential does not belong to this exact organization and facility.",
            )

        config = self.integrations.public(row).get("configuration", {})
        state = str(config.get("state") or "").strip().upper()
        configured_license = str(config.get("license_number") or "").strip()
        environment = str(config.get("environment") or "").strip().casefold()
        if environment not in {"sandbox", "production"}:
            return self._no_request(
                tx,
                actor,
                code="environment_not_verified",
                message="The Metrc write environment must be explicitly saved as sandbox or production.",
            )
        if environment != "sandbox":
            return self._no_request(
                tx,
                actor,
                code="alpha_mode_production_blocked",
                message=(
                    "Metrc Sandbox is the only provider mode enabled during alpha. A production-configured credential cannot dispatch from this operating mode."
                ),
            )
        if not state or not configured_license:
            return self._no_request(
                tx,
                actor,
                code="facility_mapping_incomplete",
                message="The Metrc jurisdiction and facility license must be saved before a write can dispatch.",
            )
        license_number = str(tx.license_number or configured_license).strip()
        if tx.license_number and configured_license and tx.license_number != configured_license:
            raise TraceabilityDispatchError("Transaction license does not match the validated Metrc facility credential.")

        mapping = RegulatoryMappingService(self.engine).get(
            organization_id=tx.organization_id,
            facility_id=tx.facility_id,
            provider="metrc",
            license_number=configured_license,
            environment=environment,
        )
        trusted_mapping = bool(
            mapping
            and mapping.integration_configuration_id == row.id
            and str(mapping.jurisdiction_code or "").strip().upper() == state
        )
        if not trusted_mapping:
            return self._no_request(
                tx,
                actor,
                code="trusted_mapping_required",
                message="An administrator must verify the exact Metrc facility, license, jurisdiction, credential, and environment mapping before writes can dispatch.",
            )

        try:
            contract = require_metrc_write_contract(
                operation_type=tx.operation_type,
                jurisdiction=state,
                environment=environment,
            )
        except ValueError as exc:
            return self._no_request(
                tx,
                actor,
                code="write_contract_blocked",
                message=str(exc),
            )

        user_api_key = self.integrations.secret(row)
        try:
            validate_metrc_action(
                operation_type=tx.operation_type,
                entity_id=tx.entity_id,
                payload=payload,
                reason=tx.reason,
            )
        except MetrcNativeError as exc:
            self.traceability.record_attempt(
                organization_id=tx.organization_id,
                facility_id=tx.facility_id,
                transaction_id=tx.id,
                request_payload={"operation_type": tx.operation_type, "entity_id": tx.entity_id, "payload": payload},
                error_code="validation_failed",
                error_message=str(exc),
            )
            self.traceability.transition_logged(
                organization_id=tx.organization_id,
                facility_id=tx.facility_id,
                transaction_id=tx.id,
                new_status="reconciliation_required",
                actor=actor,
                reason=f"Provider dispatch validation failed before any external request: {exc}",
                source="provider_worker",
            )
            return {"ok": False, "status": "reconciliation_required", "provider": "metrc", "outbound_request_sent": False, "retryable": False}

        self.traceability.transition_logged(
            organization_id=tx.organization_id,
            facility_id=tx.facility_id,
            transaction_id=tx.id,
            new_status="submitted",
            actor=actor,
            reason=f"Provider worker began the authenticated Metrc {environment} {contract.operation_type} request.",
            source="provider_worker",
        )
        try:
            result = submit_metrc_action(
                state=state,
                environment=environment,
                license_number=license_number,
                integrator_api_key=self.metrc_integrator_api_key,
                user_api_key=user_api_key,
                operation_type=tx.operation_type,
                entity_id=tx.entity_id,
                payload=payload,
                reason=tx.reason,
            )
        except MetrcNativeError as exc:
            self.traceability.record_attempt(
                organization_id=tx.organization_id,
                facility_id=tx.facility_id,
                transaction_id=tx.id,
                request_payload={"operation_type": tx.operation_type, "entity_id": tx.entity_id, "payload": payload},
                response_payload=exc.response if isinstance(exc.response, dict) else None,
                http_status=exc.http_status,
                error_code="retryable_provider_error" if exc.retryable else "provider_rejected",
                error_message=str(exc),
            )
            target = "reconciliation_required" if exc.retryable or not exc.request_sent else "rejected"
            self.traceability.transition_logged(
                organization_id=tx.organization_id,
                facility_id=tx.facility_id,
                transaction_id=tx.id,
                new_status=target,
                actor=actor,
                reason=str(exc),
                source="provider_worker",
                next_attempt_at=utc_now() + timedelta(minutes=5) if exc.retryable else None,
            )
            return {
                "ok": False,
                "status": target,
                "provider": "metrc",
                "outbound_request_sent": exc.request_sent,
                "retryable": exc.retryable,
                "blind_retry_allowed": False,
            }
        self.traceability.record_attempt(
            organization_id=tx.organization_id,
            facility_id=tx.facility_id,
            transaction_id=tx.id,
            request_payload={"operation_type": tx.operation_type, "entity_id": tx.entity_id, "payload": payload},
            response_payload=result.get("payload") if isinstance(result.get("payload"), dict) else {"result": result.get("payload")},
            http_status=int(result.get("http_status") or 0),
        )
        accepted = self.traceability.transition_logged(
            organization_id=tx.organization_id,
            facility_id=tx.facility_id,
            transaction_id=tx.id,
            new_status="accepted",
            actor=actor,
            reason="Metrc accepted the authenticated request. Verification remains a separate reconciliation step.",
            source="provider_worker",
            external_reference=str(result.get("external_reference") or ""),
        )
        return {
            "ok": True,
            "status": accepted.status,
            "provider": "metrc",
            "environment": environment,
            "operation_type": contract.operation_type,
            "verification_resource": contract.verification_resource,
            "outbound_request_sent": True,
            "verified": False,
            "external_reference": str(result.get("external_reference") or ""),
        }