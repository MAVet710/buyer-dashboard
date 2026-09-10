from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from sqlalchemy import Engine

from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.metrc_evaluation_transfers import (
    TRANSFER_WRITE_EVALUATION_ACTIONS,
    MetrcTransferEvaluationError,
    _validated_template_update,
    execute_transfer_template_write,
)
from services.metrc_native import MetrcNativeError, validate_metrc_action


PROMOTED_TRANSFER_ACTIONS = frozenset(TRANSFER_WRITE_EVALUATION_ACTIONS)


class MetrcTransferActionError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _scope(state: str, environment: str, license_number: str) -> tuple[str, str, str]:
    state_code = str(state or "").strip().upper()
    env = str(environment or "").strip().casefold()
    license_value = str(license_number or "").strip()
    if state_code != "MA" or env != "sandbox":
        raise MetrcTransferActionError(
            "Promoted transfer-template writes are currently restricted to the verified Massachusetts Metrc sandbox."
        )
    if not license_value:
        raise MetrcTransferActionError("An exact Massachusetts sandbox facility license is required.")
    return state_code, env, license_value


def transfer_confirmation_token(
    *,
    prepared: dict[str, Any],
    state: str,
    environment: str,
    license_number: str,
    confirmation_id: str,
) -> str:
    operation = str(prepared.get("operation_type") or "").strip().casefold()
    if operation not in PROMOTED_TRANSFER_ACTIONS:
        raise MetrcTransferActionError("This transfer action has not passed the current operator promotion gate.")
    document = {
        "confirmation_id": str(confirmation_id or "").strip(),
        "operation_type": operation,
        "state": str(state or "").strip().upper(),
        "environment": str(environment or "").strip().casefold(),
        "license_number": str(license_number or "").strip(),
        "entity_type": prepared.get("entity_type"),
        "entity_id": prepared.get("entity_id"),
        "provider_payload": prepared.get("provider_payload"),
        "provider_request_body": prepared.get("provider_request_body"),
    }
    if not document["confirmation_id"]:
        raise MetrcTransferActionError("A confirmation ID is required.")
    return sha256(_canonical(document).encode("utf-8")).hexdigest()


class GovernedMetrcTransferActionService:
    """Ledger-backed MA Metrc outgoing transfer-template actions.

    The current Massachusetts v2 API exposes outgoing transfer-template writes,
    not a generic direct outgoing-manifest creation endpoint. This service keeps
    that provider boundary explicit so DoobieLogic never claims a regulatory
    transfer exists merely because a local physical transfer was prepared.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.traceability = TraceabilityBackofficeRepository(engine)

    def prepare(
        self,
        *,
        operation_type: str,
        payload: dict[str, Any],
        state: str,
        environment: str,
        license_number: str,
    ) -> dict[str, Any]:
        state_code, env, license_value = _scope(state, environment, license_number)
        operation = str(operation_type or "").strip().casefold()
        spec = TRANSFER_WRITE_EVALUATION_ACTIONS.get(operation)
        if spec is None:
            raise MetrcTransferActionError("This transfer action has not passed the current operator promotion gate.")
        if not isinstance(payload, dict):
            raise MetrcTransferActionError("Transfer action payload must be one object.")

        start = str(payload.get("last_modified_start") or payload.get("lastModifiedStart") or "").strip()
        end = str(payload.get("last_modified_end") or payload.get("lastModifiedEnd") or "").strip()
        if not start or not end:
            raise MetrcTransferActionError(
                "Transfer-template verification requires a bounded last-modified readback window."
            )

        try:
            if operation == "transfer_template_create":
                template = payload.get("template")
                if not isinstance(template, dict):
                    raise MetrcTransferActionError("Transfer template create requires a template object.")
                entity = str(payload.get("entity_id") or template.get("Name") or "transfer-template").strip()
                body = validate_metrc_action(
                    operation_type="transfer_template_create",
                    entity_id=entity,
                    payload={"template": template},
                )["body"]
            else:
                body = _validated_template_update(payload)
        except (MetrcNativeError, MetrcTransferEvaluationError) as exc:
            raise MetrcTransferActionError(str(exc)) from exc

        template = body[0]
        provider_id = str(template.get("TransferTemplateId") or payload.get("transfer_template_id") or "").strip()
        name = str(template.get("Name") or "").strip()
        destinations = template.get("Destinations") if isinstance(template.get("Destinations"), list) else []
        package_count = sum(
            len(row.get("Packages") or [])
            for row in destinations
            if isinstance(row, dict) and isinstance(row.get("Packages"), list)
        )
        entity_seed = provider_id or sha256(_canonical(body).encode("utf-8")).hexdigest()[:24]
        return {
            "operation_type": operation,
            "entity_type": "transfer_template",
            "entity_id": entity_seed,
            "provider_payload": dict(payload),
            "provider_request_body": body,
            "provider_method": spec["method"],
            "provider_path": spec["path"],
            "state": state_code,
            "environment": env,
            "license_number": license_value,
            "summary": {
                "title": "Create transfer template" if operation == "transfer_template_create" else "Update transfer template",
                "template_name": name,
                "provider_id": provider_id,
                "destination_count": len(destinations),
                "package_count": package_count,
                "note": "A Metrc transfer template is not itself proof that an outgoing regulatory manifest has been created.",
            },
        }

    def execute(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        operation_type: str,
        payload: dict[str, Any],
        confirmation_id: str,
        confirmation_token: str,
        reason: str,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        prepared = self.prepare(
            operation_type=operation_type,
            payload=payload,
            state=state,
            environment=environment,
            license_number=license_number,
        )
        state_code, env, license_value = _scope(state, environment, license_number)
        expected_token = transfer_confirmation_token(
            prepared=prepared,
            state=state_code,
            environment=env,
            license_number=license_value,
            confirmation_id=confirmation_id,
        )
        if str(confirmation_token or "").strip() != expected_token:
            raise MetrcTransferActionError(
                "The transfer-template values changed after preview. Review the current action again before submitting to Metrc."
            )

        operation = prepared["operation_type"]
        transaction = self.traceability.create_transaction(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            operation_type=operation,
            entity_type="transfer_template",
            entity_id=prepared["entity_id"],
            idempotency_key=f"metrc-transfer:{facility_id}:{confirmation_id}:{expected_token}",
            actor=actor,
            license_number=license_value,
            jurisdiction=state_code,
            environment=env,
            request_payload={
                "operator_payload": prepared["provider_payload"],
                "provider_request": {
                    "method": prepared["provider_method"],
                    "path": prepared["provider_path"],
                    "query": {"licenseNumber": license_value},
                    "body": prepared["provider_request_body"],
                },
                "confirmation_id": confirmation_id,
            },
            reason=str(reason or prepared["summary"]["title"]),
        )
        transaction, claimed = self.traceability.claim_transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            expected_status="requested",
            new_status="validated",
            actor=actor,
            reason="Exact MA sandbox transfer-template payload, facility scope, and confirmation fingerprint validated.",
            source="system",
        )
        if not claimed:
            return self._existing(transaction, prepared)
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="queued",
            actor=actor,
            reason="Human-confirmed transfer-template action queued for immediate controlled execution.",
            source="system",
        )
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="submitted",
            actor=actor,
            reason=f"Beginning authenticated {prepared['provider_method']} /{prepared['provider_path']} against the trusted Massachusetts sandbox mapping.",
            source="provider_worker",
        )

        try:
            evidence = execute_transfer_template_write(
                operation_type=operation,
                payload=prepared["provider_payload"],
                license_number=license_value,
                integrator_api_key=integrator_api_key,
                user_api_key=user_api_key,
                state=state_code,
                environment=env,
            )
        except MetrcTransferEvaluationError as exc:
            return self._unknown(transaction, prepared, actor, organization_id, facility_id, str(exc))

        http_status = int(evidence.get("http_status") or 0)
        self.traceability.record_attempt(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            request_payload=evidence.get("request") if isinstance(evidence.get("request"), dict) else {"operation_type": operation},
            response_payload=evidence.get("response") if isinstance(evidence.get("response"), dict) else {"response": evidence.get("response")},
            http_status=http_status or None,
            error_code="" if http_status == 200 else "provider_rejected",
            error_message="" if http_status == 200 else str(evidence.get("message") or "Metrc rejected the transfer-template write."),
        )
        if http_status != 200:
            uncertain = http_status == 0 or http_status == 429 or http_status >= 500
            target = "reconciliation_required" if uncertain else "rejected"
            transaction = self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                new_status=target,
                actor=actor,
                reason=str(evidence.get("message") or "Metrc did not accept the transfer-template write."),
                source="provider_worker",
                error_code="provider_outcome_unknown" if uncertain else "provider_rejected",
                error_message=str(evidence.get("message") or ""),
            )
            if uncertain:
                self.traceability.record_reconciliation(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    transaction_id=transaction.id,
                    actor=actor,
                    mismatch_reason=str(evidence.get("message") or "Provider outcome is unknown."),
                    evidence={"operation_type": operation, "blind_retry_allowed": False},
                    retry_eligible=False,
                )
            return self._result(transaction, prepared, str(evidence.get("message") or "Metrc rejected the transfer-template write."))

        provider_id = str(evidence.get("provider_id") or prepared["provider_payload"].get("transfer_template_id") or "").strip()
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="accepted",
            actor=actor,
            reason="Metrc returned HTTP 200. Full paginated readback must still verify the exact template before completion.",
            source="provider_worker",
            external_reference=provider_id,
            response_payload=evidence.get("response") if isinstance(evidence.get("response"), dict) else {"response": evidence.get("response")},
        )
        provider_verified = bool(evidence.get("passed")) and bool(provider_id)
        self.traceability.record_reconciliation(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            actor=actor,
            provider_state={"provider_id": provider_id, "http_status": http_status, "last_modified": str(evidence.get("last_modified") or "")},
            readback_result=evidence.get("readback") if isinstance(evidence.get("readback"), dict) else None,
            mismatch_reason="" if provider_verified else "Full paginated Metrc transfer-template readback did not verify the submitted object.",
            evidence={"operation_type": operation, "provider_verified": provider_verified, "blind_retry_allowed": False},
            retry_eligible=False,
        )
        if not provider_verified:
            transaction = self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                new_status="reconciliation_required",
                actor=actor,
                reason="Metrc accepted the write, but provider readback did not verify the expected template. Do not repeat the write blindly.",
                source="provider_readback",
                external_reference=provider_id,
                error_code="readback_not_verified",
                error_message="Fresh provider transfer-template state did not verify the submitted object.",
            )
            return self._result(transaction, prepared, "Metrc accepted the transfer-template write, but provider verification requires reconciliation.")

        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="verified",
            actor=actor,
            reason="Full paginated Metrc readback verified the outgoing transfer template.",
            source="provider_readback",
            external_reference=provider_id,
        )
        return self._result(transaction, prepared, "Metrc transfer template is verified. Regulatory manifest creation remains a separate provider lifecycle step.")

    def _unknown(self, transaction, prepared: dict[str, Any], actor: str, organization_id: str, facility_id: str, message: str) -> dict[str, Any]:
        self.traceability.record_attempt(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            request_payload={"operation_type": prepared["operation_type"], "payload": prepared["provider_payload"]},
            error_code="provider_outcome_unknown",
            error_message=message,
        )
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="reconciliation_required",
            actor=actor,
            reason="The Metrc transfer-template call did not produce enough evidence to classify the provider outcome. Blind retry is blocked.",
            source="provider_worker",
            error_code="provider_outcome_unknown",
            error_message=message,
        )
        self.traceability.record_reconciliation(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            actor=actor,
            mismatch_reason=message,
            evidence={"operation_type": prepared["operation_type"], "blind_retry_allowed": False},
            retry_eligible=False,
        )
        return self._result(transaction, prepared, message)

    @staticmethod
    def _existing(transaction, prepared: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": transaction.status == "verified",
            "verified": transaction.status == "verified",
            "status": transaction.status,
            "transaction_id": transaction.id,
            "external_reference": transaction.external_reference,
            "already_submitted": True,
            "summary": prepared["summary"],
            "message": "This exact confirmation already has a durable traceability transaction. Review its current status before any new action.",
        }

    @staticmethod
    def _result(transaction, prepared: dict[str, Any], message: str) -> dict[str, Any]:
        return {
            "ok": transaction.status == "verified",
            "verified": transaction.status == "verified",
            "status": transaction.status,
            "transaction_id": transaction.id,
            "external_reference": transaction.external_reference,
            "summary": prepared["summary"],
            "message": message,
        }
