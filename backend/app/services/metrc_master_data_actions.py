from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from sqlalchemy import Engine

from modules.regulatory.facility_setup_contracts import build_facility_setup_payload
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.metrc_evaluation_master_data import (
    MASTER_DATA_EVALUATION_ACTIONS,
    MetrcEvaluationError,
    execute_master_data_evaluation_action,
)
from .metrc_master_data_readback import compare_master_data_readback


PROMOTED_MASTER_DATA_ACTIONS = frozenset(MASTER_DATA_EVALUATION_ACTIONS)

_ENTITY_TYPES = {
    "location_create": "location",
    "location_update": "location",
    "strain_create": "strain",
    "strain_update": "strain",
    "item_create": "item",
    "item_update": "item",
}


class MetrcMasterDataActionError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def master_data_confirmation_token(
    *,
    operation_type: str,
    payload: dict[str, Any],
    state: str,
    environment: str,
    license_number: str,
    confirmation_id: str,
) -> str:
    """Bind one human confirmation to the exact reviewed provider request.

    The token is an integrity/fingerprint guard, not a credential. Authorization,
    tenant scope, trusted facility mapping, and Metrc credentials are re-resolved
    server-side at execution time.
    """

    operation = str(operation_type or "").strip().casefold()
    spec = MASTER_DATA_EVALUATION_ACTIONS.get(operation)
    if spec is None:
        raise MetrcMasterDataActionError("This Facility Setup action has not been promoted for operator execution.")
    try:
        body = build_facility_setup_payload(operation, payload)
    except (TypeError, ValueError) as exc:
        raise MetrcMasterDataActionError(str(exc)) from exc
    document = {
        "confirmation_id": str(confirmation_id or "").strip(),
        "operation_type": operation,
        "method": spec.method,
        "path": spec.path,
        "state": str(state or "").strip().upper(),
        "environment": str(environment or "").strip().casefold(),
        "license_number": str(license_number or "").strip(),
        "body": body,
    }
    if not document["confirmation_id"]:
        raise MetrcMasterDataActionError("A confirmation ID is required.")
    return sha256(_canonical(document).encode("utf-8")).hexdigest()


def master_data_action_summary(operation_type: str, payload: dict[str, Any]) -> dict[str, str]:
    operation = str(operation_type or "").strip().casefold()
    entity_type = _ENTITY_TYPES.get(operation)
    if entity_type is None:
        raise MetrcMasterDataActionError("This Facility Setup action has not been promoted for operator execution.")
    action = "Create" if operation.endswith("_create") else "Edit"
    provider_id = str(payload.get("id") or "").strip()
    name = str(payload.get("name") or "").strip()
    return {
        "action": action,
        "entity_type": entity_type,
        "entity_id": provider_id or name or "new",
        "label": f"{action} {entity_type}",
        "name": name,
    }


class MetrcMasterDataActionService:
    """Execute only the six #452-reviewed MA sandbox master-data actions.

    This service deliberately reuses the official evaluation executor rather
    than introducing a second request schema. The durable traceability ledger
    records lifecycle status and sanitized attempt/readback evidence around that
    exact write+readback operation.
    """

    def __init__(self, engine: Engine):
        self.traceability = TraceabilityBackofficeRepository(engine)

    def execute(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        operation_type: str,
        payload: dict[str, Any],
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
        confirmation_id: str,
        confirmation_token: str,
    ) -> dict[str, Any]:
        operation = str(operation_type or "").strip().casefold()
        state_code = str(state or "").strip().upper()
        env = str(environment or "").strip().casefold()
        license_value = str(license_number or "").strip()
        if state_code != "MA" or env != "sandbox":
            raise MetrcMasterDataActionError(
                "Promoted Facility Setup writes are currently restricted to the verified Massachusetts Metrc sandbox."
            )
        if operation not in PROMOTED_MASTER_DATA_ACTIONS:
            raise MetrcMasterDataActionError("This Facility Setup action has not passed the current master-data promotion gate.")

        expected_token = master_data_confirmation_token(
            operation_type=operation,
            payload=payload,
            state=state_code,
            environment=env,
            license_number=license_value,
            confirmation_id=confirmation_id,
        )
        if str(confirmation_token or "").strip() != expected_token:
            raise MetrcMasterDataActionError(
                "The Facility Setup request changed after preview. Review the current request again before submitting it to Metrc."
            )

        summary = master_data_action_summary(operation, payload)
        spec = MASTER_DATA_EVALUATION_ACTIONS[operation]
        body = build_facility_setup_payload(operation, payload)
        idempotency_key = f"metrc-master:{facility_id}:{confirmation_id}:{expected_token}"
        transaction = self.traceability.create_transaction(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            operation_type=operation,
            entity_type=summary["entity_type"],
            entity_id=summary["entity_id"],
            idempotency_key=idempotency_key,
            actor=actor,
            license_number=license_value,
            jurisdiction=state_code,
            environment=env,
            request_payload={
                "operator_payload": payload,
                "provider_request": {
                    "method": spec.method,
                    "path": spec.path,
                    "query": {"licenseNumber": license_value},
                    "body": body,
                },
                "confirmation_id": confirmation_id,
            },
            reason=f"Authorized operator confirmed {summary['label'].lower()} from Facility Setup.",
        )

        # A confirmation is an execution lease, not only an idempotency label.
        # Exactly one concurrent request may claim requested -> validated.
        # Every loser returns the durable transaction without calling Metrc.
        transaction, claimed = self.traceability.claim_transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            expected_status="requested",
            new_status="validated",
            actor=actor,
            reason="Exact MA sandbox operation, facility/license scope, bounded payload, and confirmation fingerprint validated.",
            source="system",
        )
        if not claimed:
            return self._existing(transaction, summary)

        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="queued",
            actor=actor,
            reason="Human-confirmed Facility Setup action queued for immediate controlled execution.",
            source="system",
        )
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="submitted",
            actor=actor,
            reason=f"Beginning authenticated {spec.method} /{spec.path} against the trusted Massachusetts sandbox mapping.",
            source="provider_worker",
        )

        try:
            evidence = execute_master_data_evaluation_action(
                operation_type=operation,
                payload=payload,
                license_number=license_value,
                integrator_api_key=integrator_api_key,
                user_api_key=user_api_key,
                state=state_code,
                environment=env,
            )
        except MetrcEvaluationError as exc:
            self.traceability.record_attempt(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                request_payload={"operation_type": operation, "payload": payload},
                error_code="provider_outcome_unknown",
                error_message=str(exc),
            )
            transaction = self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                new_status="reconciliation_required",
                actor=actor,
                reason="The controlled Metrc call did not produce evidence sufficient to classify the provider outcome. Blind retry is blocked.",
                source="provider_worker",
                error_code="provider_outcome_unknown",
                error_message=str(exc),
            )
            self.traceability.record_reconciliation(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                actor=actor,
                mismatch_reason=str(exc),
                evidence={"operation_type": operation, "stage": "execution_exception", "blind_retry_allowed": False},
                retry_eligible=False,
            )
            return self._result(transaction, summary, None, str(exc))

        http_status = int(evidence.get("http_status") or 0)
        provider_id = str(evidence.get("provider_id") or "").strip()
        self.traceability.record_attempt(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            request_payload=evidence.get("request") if isinstance(evidence.get("request"), dict) else {"operation_type": operation},
            response_payload=evidence.get("response") if isinstance(evidence.get("response"), dict) else {"response": evidence.get("response")},
            http_status=http_status or None,
            error_code="" if http_status == 200 else "provider_rejected",
            error_message="" if http_status == 200 else str(evidence.get("message") or "Metrc rejected the write."),
        )

        if http_status != 200:
            uncertain = http_status == 429 or http_status >= 500 or http_status == 0
            target = "reconciliation_required" if uncertain else "rejected"
            transaction = self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                new_status=target,
                actor=actor,
                reason=str(evidence.get("message") or "Metrc did not accept the Facility Setup write."),
                source="provider_worker",
                error_code="provider_outcome_unknown" if uncertain else "provider_rejected",
                error_message=str(evidence.get("message") or ""),
            )
            self.traceability.record_reconciliation(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                actor=actor,
                provider_state={"http_status": http_status, "response": evidence.get("response")},
                readback_result=evidence.get("readback") if isinstance(evidence.get("readback"), dict) else None,
                mismatch_reason=str(evidence.get("message") or "Provider write was not accepted."),
                evidence={"operation_type": operation, "stage": evidence.get("stage"), "blind_retry_allowed": False},
                retry_eligible=False,
            )
            return self._result(transaction, summary, evidence, str(evidence.get("message") or "Metrc rejected the write."))

        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="accepted",
            actor=actor,
            reason="Metrc returned HTTP 200. Exact provider readback and reviewed-field equality are still required before this action is verified.",
            source="provider_worker",
            external_reference=provider_id,
            response_payload=evidence.get("response") if isinstance(evidence.get("response"), dict) else {"response": evidence.get("response")},
        )

        readback = evidence.get("readback") if isinstance(evidence.get("readback"), dict) else None
        field_verification = compare_master_data_readback(
            provider_request_body=body,
            readback=readback,
            provider_id=provider_id,
        )
        verified = bool(evidence.get("passed")) and bool(field_verification.get("matched"))
        mismatch_message = ""
        if not evidence.get("passed"):
            mismatch_message = str(evidence.get("message") or "Exact readback did not verify the provider object.")
        elif not field_verification.get("matched"):
            mismatch_message = "Fresh Metrc readback found the object, but one or more reviewed business fields do not match the confirmed request."

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
            readback_result=readback,
            mismatch_reason=mismatch_message,
            evidence={
                "operation_type": operation,
                "stage": evidence.get("stage"),
                "evaluator_passed": bool(evidence.get("passed")),
                "field_verification": field_verification,
                "verified": verified,
                "provider_id": provider_id,
                "last_modified": str(evidence.get("last_modified") or ""),
                "blind_retry_allowed": False,
            },
            retry_eligible=False,
        )

        if verified:
            transaction = self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                new_status="verified",
                actor=actor,
                reason="Fresh exact by-ID Metrc readback verified both provider identity and every reviewed master-data field after HTTP 200.",
                source="provider_readback",
                external_reference=provider_id,
            )
            return self._result(transaction, summary, evidence, "Metrc confirmed the change and fresh readback verified every reviewed field.")

        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="reconciliation_required",
            actor=actor,
            reason="Metrc accepted the write, but exact readback did not verify the confirmed business state. Do not repeat the write blindly.",
            source="provider_readback",
            external_reference=provider_id,
            error_code="readback_not_verified",
            error_message=mismatch_message or "Exact provider readback did not verify the confirmed business state.",
        )
        return self._result(transaction, summary, evidence, mismatch_message or "Verification requires reconciliation.")

    @staticmethod
    def _existing(transaction, summary: dict[str, str]) -> dict[str, Any]:
        return {
            "ok": transaction.status == "verified",
            "transaction_id": transaction.id,
            "status": transaction.status,
            "verified": transaction.status == "verified",
            "already_submitted": True,
            "external_reference": transaction.external_reference,
            "summary": summary,
            "message": (
                "This exact confirmation was already verified."
                if transaction.status == "verified"
                else "This exact confirmation already has a durable traceability transaction. Review its current status before any new action."
            ),
        }

    @staticmethod
    def _result(transaction, summary: dict[str, str], evidence: dict[str, Any] | None, message: str) -> dict[str, Any]:
        return {
            "ok": transaction.status == "verified",
            "transaction_id": transaction.id,
            "status": transaction.status,
            "verified": transaction.status == "verified",
            "external_reference": transaction.external_reference,
            "summary": summary,
            "http_status": int((evidence or {}).get("http_status") or 0),
            "last_modified": str((evidence or {}).get("last_modified") or ""),
            "stage": str((evidence or {}).get("stage") or ""),
            "message": message,
        }
