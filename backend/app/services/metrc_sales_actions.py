from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from sqlalchemy import Engine

from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.metrc_evaluation_sales import (
    SALES_EVALUATION_ACTIONS,
    MetrcSalesEvaluationError,
    build_sales_evaluation_payload,
    execute_sales_evaluation_action,
)


PROMOTED_SALES_ACTIONS = frozenset(SALES_EVALUATION_ACTIONS)


class MetrcSalesActionError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _scope(state: str, environment: str, license_number: str) -> tuple[str, str, str]:
    state_code = str(state or "").strip().upper()
    env = str(environment or "").strip().casefold()
    license_value = str(license_number or "").strip()
    if state_code != "MA" or env != "sandbox":
        raise MetrcSalesActionError(
            "Promoted sales writes are currently restricted to the verified Massachusetts Metrc sandbox."
        )
    if not license_value:
        raise MetrcSalesActionError("An exact Massachusetts sandbox facility license is required.")
    return state_code, env, license_value


def sales_confirmation_token(
    *,
    prepared: dict[str, Any],
    state: str,
    environment: str,
    license_number: str,
    confirmation_id: str,
) -> str:
    operation = str(prepared.get("operation_type") or "").strip().casefold()
    if operation not in PROMOTED_SALES_ACTIONS:
        raise MetrcSalesActionError("This sales action has not passed the current operator promotion gate.")
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
        raise MetrcSalesActionError("A confirmation ID is required.")
    return sha256(_canonical(document).encode("utf-8")).hexdigest()


class GovernedMetrcSalesActionService:
    """Ledger-backed MA Metrc v2 receipt/delivery actions.

    The current Massachusetts API contract is authoritative for provider paths.
    Local ``RetailSale`` rows remain an operational analytics ledger and are not
    fabricated from provider writes. Provider-owned receipt/delivery state is
    refreshed by the existing Metrc synchronization layer.
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
        spec = SALES_EVALUATION_ACTIONS.get(operation)
        if spec is None:
            raise MetrcSalesActionError("This sales action has not passed the current operator promotion gate.")
        if not isinstance(payload, dict):
            raise MetrcSalesActionError("Sales action payload must be one object.")
        try:
            body = build_sales_evaluation_payload(operation, payload)
        except MetrcSalesEvaluationError as exc:
            raise MetrcSalesActionError(str(exc)) from exc

        entity_type = "sales_delivery" if operation.startswith("sales_delivery_") else "sales_receipt"
        provider_id = str(payload.get("id") or "").strip()
        external = str(payload.get("external_receipt_number") or "").strip()
        entity_seed = provider_id or external or sha256(_canonical(payload).encode("utf-8")).hexdigest()[:24]
        transaction_count = len(payload.get("transactions") or []) if isinstance(payload.get("transactions"), list) else 0
        title = {
            "sales_receipt_create": "Create sales receipt",
            "sales_receipt_update": "Update sales receipt",
            "sales_receipt_delete": "Delete sales receipt",
            "sales_delivery_create": "Create sales delivery",
            "sales_delivery_update": "Update sales delivery",
            "sales_delivery_complete": "Complete sales delivery",
        }[operation]
        summary = {
            "title": title,
            "provider_id": provider_id,
            "external_receipt_number": external,
            "sales_date_time": str(payload.get("sales_date_time") or ""),
            "transaction_count": transaction_count,
        }
        return {
            "operation_type": operation,
            "entity_type": entity_type,
            "entity_id": entity_seed,
            "provider_payload": dict(payload),
            "provider_request_body": body,
            "provider_method": spec.method,
            "provider_path": spec.path,
            "state": state_code,
            "environment": env,
            "license_number": license_value,
            "summary": summary,
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
        expected_token = sales_confirmation_token(
            prepared=prepared,
            state=state_code,
            environment=env,
            license_number=license_value,
            confirmation_id=confirmation_id,
        )
        if str(confirmation_token or "").strip() != expected_token:
            raise MetrcSalesActionError(
                "The sales values changed after preview. Review the current action again before submitting to Metrc."
            )

        operation = prepared["operation_type"]
        transaction = self.traceability.create_transaction(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            operation_type=operation,
            entity_type=prepared["entity_type"],
            entity_id=prepared["entity_id"],
            idempotency_key=f"metrc-sales:{facility_id}:{confirmation_id}:{expected_token}",
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
            reason="Exact MA sandbox sales action, provider payload, facility scope, and confirmation fingerprint validated.",
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
            reason="Human-confirmed sales action queued for immediate controlled execution.",
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
            evidence = execute_sales_evaluation_action(
                operation_type=operation,
                payload=prepared["provider_payload"],
                license_number=license_value,
                integrator_api_key=integrator_api_key,
                user_api_key=user_api_key,
                state=state_code,
                environment=env,
            )
        except MetrcSalesEvaluationError as exc:
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
            error_message="" if http_status == 200 else str(evidence.get("message") or "Metrc rejected the sales write."),
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
                reason=str(evidence.get("message") or "Metrc did not accept the sales write."),
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
            return self._result(transaction, prepared, str(evidence.get("message") or "Metrc rejected the sales write."))

        provider_id = str(evidence.get("provider_id") or prepared["provider_payload"].get("id") or "").strip()
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="accepted",
            actor=actor,
            reason="Metrc returned HTTP 200. Fresh exact provider readback is still required before verification.",
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
            provider_state={
                "provider_id": provider_id,
                "http_status": http_status,
                "last_modified": str(evidence.get("last_modified") or ""),
            },
            readback_result=evidence.get("readback") if isinstance(evidence.get("readback"), dict) else None,
            mismatch_reason="" if provider_verified else "Fresh exact Metrc sales readback did not verify the submitted provider identity.",
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
                reason="Metrc accepted the write, but fresh exact readback did not verify it. Do not repeat the write blindly.",
                source="provider_readback",
                external_reference=provider_id,
                error_code="readback_not_verified",
                error_message="Fresh provider sales state did not verify the submitted identity.",
            )
            return self._result(transaction, prepared, "Metrc accepted the sales write, but provider verification requires reconciliation.")

        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="verified",
            actor=actor,
            reason="Fresh exact Metrc readback verified the sales mutation.",
            source="provider_readback",
            external_reference=provider_id,
        )
        return self._result(transaction, prepared, "Metrc sales state is verified. The synchronized provider mirror will refresh independently.")

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
            reason="The Metrc sales call did not produce enough evidence to classify the provider outcome. Blind retry is blocked.",
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
