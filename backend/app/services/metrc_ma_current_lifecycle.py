from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

import requests
from sqlalchemy import Engine

from modules.regulatory.registry import resolve_metrc_base_url
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_pagination import fetch_all_metrc_resource_pages


MA_CURRENT_LIFECYCLE_ACTIONS: dict[str, dict[str, str]] = {
    "sales_receipt_finalize": {
        "domain": "sales",
        "method": "PUT",
        "path": "sales/v2/receipts/finalize",
        "entity_type": "sales_receipt",
    },
    "sales_receipt_unfinalize": {
        "domain": "sales",
        "method": "PUT",
        "path": "sales/v2/receipts/unfinalize",
        "entity_type": "sales_receipt",
    },
    "sales_delivery_delete": {
        "domain": "sales",
        "method": "DELETE",
        "path": "sales/v2/deliveries/{id}",
        "entity_type": "sales_delivery",
    },
    "transfer_template_delete": {
        "domain": "transfers",
        "method": "DELETE",
        "path": "transfers/v2/templates/outgoing/{id}",
        "entity_type": "transfer_template",
    },
}

SALES_CURRENT_LIFECYCLE_ACTIONS = frozenset(
    name for name, spec in MA_CURRENT_LIFECYCLE_ACTIONS.items() if spec["domain"] == "sales"
)
TRANSFER_CURRENT_LIFECYCLE_ACTIONS = frozenset(
    name for name, spec in MA_CURRENT_LIFECYCLE_ACTIONS.items() if spec["domain"] == "transfers"
)


class MetrcMaCurrentLifecycleError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _scope(
    *,
    state: str,
    environment: str,
    license_number: str,
    integrator_api_key: str,
    user_api_key: str,
) -> tuple[str, str, str, str]:
    state_code = str(state or "").strip().upper()
    env = str(environment or "").strip().casefold()
    license_value = str(license_number or "").strip()
    if state_code != "MA" or env != "sandbox":
        raise MetrcMaCurrentLifecycleError(
            "Current promoted lifecycle writes are restricted to the verified Massachusetts Metrc sandbox."
        )
    base_url, resolved_state = resolve_metrc_base_url(state_code, environment=env)
    if resolved_state != "MA" or not base_url:
        raise MetrcMaCurrentLifecycleError("The verified Massachusetts Metrc sandbox host is unavailable.")
    if not license_value:
        raise MetrcMaCurrentLifecycleError("An exact Massachusetts sandbox facility license is required.")
    integrator = str(integrator_api_key or "").strip()
    user = str(user_api_key or "").strip()
    if not integrator or not user:
        raise MetrcMaCurrentLifecycleError("Both Metrc integrator/vendor and user API keys are required.")
    if integrator == user:
        raise MetrcMaCurrentLifecycleError("Metrc integrator/vendor and user API keys must be distinct credentials.")
    return state_code, env, license_value, base_url


def _provider_id(payload: dict[str, Any]) -> int:
    raw = payload.get("id", payload.get("transfer_template_id"))
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise MetrcMaCurrentLifecycleError("A numeric Metrc provider ID is required.") from exc
    if value < 1:
        raise MetrcMaCurrentLifecycleError("Metrc provider ID must be at least 1.")
    return value


def _source_record(readback: dict[str, Any], provider_id: int) -> dict[str, Any] | None:
    records = readback.get("records") if isinstance(readback, dict) else None
    if not isinstance(records, list):
        return None
    expected = str(provider_id)
    for record in records:
        if not isinstance(record, dict):
            continue
        record_id = str(record.get("provider_id") or "").strip()
        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        source_id = str(source.get("Id") or source.get("id") or "").strip()
        if expected in {record_id, source_id}:
            return source or record
    return None


def _template_record(records: list[dict[str, Any]], provider_id: int) -> dict[str, Any] | None:
    expected = str(provider_id)
    for record in records:
        if not isinstance(record, dict):
            continue
        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        ids = {
            str(record.get("provider_id") or "").strip(),
            str(source.get("Id") or "").strip(),
            str(source.get("TransferTemplateId") or "").strip(),
            str(source.get("TemplateId") or "").strip(),
        }
        if expected in ids:
            return record
    return None


def _response_payload(response: Any) -> Any:
    if not getattr(response, "content", b""):
        return None
    try:
        return response.json()
    except ValueError:
        return {"message": str(getattr(response, "text", ""))[:1000]}


def lifecycle_confirmation_token(
    *,
    prepared: dict[str, Any],
    state: str,
    environment: str,
    license_number: str,
    confirmation_id: str,
) -> str:
    confirmation = str(confirmation_id or "").strip()
    if not confirmation:
        raise MetrcMaCurrentLifecycleError("A confirmation ID is required.")
    operation = str(prepared.get("operation_type") or "").strip().casefold()
    if operation not in MA_CURRENT_LIFECYCLE_ACTIONS:
        raise MetrcMaCurrentLifecycleError("This current MA lifecycle action is not promoted.")
    document = {
        "confirmation_id": confirmation,
        "operation_type": operation,
        "state": str(state or "").strip().upper(),
        "environment": str(environment or "").strip().casefold(),
        "license_number": str(license_number or "").strip(),
        "entity_type": prepared.get("entity_type"),
        "entity_id": prepared.get("entity_id"),
        "provider_method": prepared.get("provider_method"),
        "provider_path": prepared.get("provider_path"),
        "provider_request_body": prepared.get("provider_request_body"),
        "provider_prestate": prepared.get("provider_prestate"),
    }
    return sha256(_canonical(document).encode("utf-8")).hexdigest()


class GovernedMetrcMaCurrentLifecycleService:
    """Current MA v2 lifecycle writes that are not part of the proficiency workbook.

    The operation registry is closed and MA-sandbox-only. Preview performs fresh
    provider preflight, the confirmation fingerprint binds that provider state,
    and execute performs exactly one provider write. HTTP 200 is not treated as
    completion until a fresh semantic readback proves the target state.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.traceability = TraceabilityBackofficeRepository(engine)

    def _receipt_state(
        self,
        *,
        provider_id: int,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        readback = fetch_metrc_resource(
            state=state,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            resource="sales_receipts_by_id",
            environment=environment,
            license_number=license_number,
            path_parameters={"id": provider_id},
        )
        source = _source_record(readback, provider_id)
        if not readback.get("ok") or source is None:
            raise MetrcMaCurrentLifecycleError(
                "Fresh Metrc readback could not verify the exact sales receipt before this action."
            )
        if "IsFinal" not in source or not isinstance(source.get("IsFinal"), bool):
            raise MetrcMaCurrentLifecycleError(
                "Fresh Metrc receipt state did not expose an explicit IsFinal value; refusing to infer finalization state."
            )
        return {
            "provider_id": str(provider_id),
            "is_final": bool(source["IsFinal"]),
            "archived_date": source.get("ArchivedDate"),
            "last_modified": source.get("LastModified") or source.get("lastModified") or "",
        }

    def _delivery_state(
        self,
        *,
        provider_id: int,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
        allow_missing: bool = False,
    ) -> dict[str, Any]:
        readback = fetch_metrc_resource(
            state=state,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            resource="sales_deliveries_by_id",
            environment=environment,
            license_number=license_number,
            path_parameters={"id": provider_id},
        )
        if int(readback.get("http_status") or 0) in {404, 410} and allow_missing:
            return {"provider_id": str(provider_id), "missing": True, "voided_date": None, "last_modified": ""}
        source = _source_record(readback, provider_id)
        if not readback.get("ok") or source is None:
            raise MetrcMaCurrentLifecycleError(
                "Fresh Metrc readback could not verify the exact sales delivery."
            )
        if "VoidedDate" not in source:
            raise MetrcMaCurrentLifecycleError(
                "Fresh Metrc delivery state did not expose VoidedDate; refusing to infer whether the delivery is active or voided."
            )
        return {
            "provider_id": str(provider_id),
            "missing": False,
            "voided_date": source.get("VoidedDate"),
            "sales_delivery_state": source.get("SalesDeliveryState"),
            "last_modified": source.get("LastModified") or source.get("lastModified") or "",
        }

    def _template_state(
        self,
        *,
        provider_id: int,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        readback = fetch_all_metrc_resource_pages(
            state=state,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            resource="transfer_templates_outgoing",
            environment=environment,
            license_number=license_number,
            query=None,
            page_size=20,
        )
        if not readback.get("passed"):
            raise MetrcMaCurrentLifecycleError(
                "A complete paginated Metrc outgoing-template readback is required before changing template state."
            )
        records = [row for row in (readback.get("records") or []) if isinstance(row, dict)]
        match = _template_record(records, provider_id)
        source = match.get("source") if isinstance(match, dict) and isinstance(match.get("source"), dict) else {}
        return {
            "provider_id": str(provider_id),
            "present": match is not None,
            "name": str((source or {}).get("Name") or (match or {}).get("name") or "").strip(),
            "last_modified": str((source or {}).get("LastModified") or (match or {}).get("last_modified") or "").strip(),
            "page_count": int(readback.get("page_count") or 0),
            "total_pages": int(readback.get("total_pages") or 0),
        }

    def prepare(
        self,
        *,
        operation_type: str,
        payload: dict[str, Any],
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        state_code, env, license_value, _base_url = _scope(
            state=state,
            environment=environment,
            license_number=license_number,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        operation = str(operation_type or "").strip().casefold()
        spec = MA_CURRENT_LIFECYCLE_ACTIONS.get(operation)
        if spec is None:
            raise MetrcMaCurrentLifecycleError("This current Massachusetts lifecycle action is not promoted.")
        if not isinstance(payload, dict):
            raise MetrcMaCurrentLifecycleError("Lifecycle action payload must be one object.")
        provider_id = _provider_id(payload)
        body: list[dict[str, int]] | None = None
        path = spec["path"].replace("{id}", str(provider_id))

        if operation in {"sales_receipt_finalize", "sales_receipt_unfinalize"}:
            prestate = self._receipt_state(
                provider_id=provider_id,
                state=state_code,
                environment=env,
                license_number=license_value,
                integrator_api_key=integrator_api_key,
                user_api_key=user_api_key,
            )
            target_final = operation == "sales_receipt_finalize"
            if prestate["is_final"] is target_final:
                raise MetrcMaCurrentLifecycleError(
                    "Metrc already reports this sales receipt in the requested finalization state."
                )
            body = [{"Id": provider_id}]
            title = "Finalize sales receipt" if target_final else "Unfinalize sales receipt"
            summary = {
                "title": title,
                "provider_id": str(provider_id),
                "current_is_final": prestate["is_final"],
                "target_is_final": target_final,
            }
        elif operation == "sales_delivery_delete":
            prestate = self._delivery_state(
                provider_id=provider_id,
                state=state_code,
                environment=env,
                license_number=license_value,
                integrator_api_key=integrator_api_key,
                user_api_key=user_api_key,
            )
            if prestate["voided_date"]:
                raise MetrcMaCurrentLifecycleError("Metrc already reports this sales delivery as voided.")
            summary = {
                "title": "Void sales delivery",
                "provider_id": str(provider_id),
                "sales_delivery_state": prestate.get("sales_delivery_state"),
            }
        else:
            prestate = self._template_state(
                provider_id=provider_id,
                state=state_code,
                environment=env,
                license_number=license_value,
                integrator_api_key=integrator_api_key,
                user_api_key=user_api_key,
            )
            if not prestate["present"]:
                raise MetrcMaCurrentLifecycleError(
                    "The outgoing transfer template is not present in a complete current Metrc readback."
                )
            summary = {
                "title": "Archive transfer template",
                "provider_id": str(provider_id),
                "template_name": prestate.get("name"),
                "note": "Archiving a transfer template is not a regulatory manifest cancellation.",
            }

        return {
            "operation_type": operation,
            "domain": spec["domain"],
            "entity_type": spec["entity_type"],
            "entity_id": str(provider_id),
            "provider_method": spec["method"],
            "provider_path": path,
            "provider_request_body": body,
            "provider_prestate": prestate,
            "summary": summary,
            "state": state_code,
            "environment": env,
            "license_number": license_value,
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
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        state_code, env, license_value, base_url = _scope(
            state=state,
            environment=environment,
            license_number=license_number,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        expected_token = lifecycle_confirmation_token(
            prepared=prepared,
            state=state_code,
            environment=env,
            license_number=license_value,
            confirmation_id=confirmation_id,
        )
        if str(confirmation_token or "").strip() != expected_token:
            raise MetrcMaCurrentLifecycleError(
                "The Metrc provider state changed after preview. Review the action again before submitting."
            )

        transaction = self.traceability.create_transaction(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            operation_type=prepared["operation_type"],
            entity_type=prepared["entity_type"],
            entity_id=prepared["entity_id"],
            idempotency_key=f"metrc-ma-current:{facility_id}:{confirmation_id}:{expected_token}",
            actor=actor,
            license_number=license_value,
            jurisdiction=state_code,
            environment=env,
            request_payload={
                "provider_request": {
                    "method": prepared["provider_method"],
                    "path": prepared["provider_path"],
                    "query": {"licenseNumber": license_value},
                    "body": prepared["provider_request_body"],
                },
                "provider_prestate": prepared["provider_prestate"],
                "confirmation_id": confirmation_id,
            },
            local_state=prepared["provider_prestate"],
            reason=str(reason or prepared["summary"]["title"]),
        )
        transaction, claimed = self.traceability.claim_transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            expected_status="requested",
            new_status="validated",
            actor=actor,
            reason="Fresh exact MA provider prestate, facility scope, closed operation contract, and confirmation fingerprint validated.",
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
            reason="Human-confirmed MA lifecycle action queued for immediate controlled execution.",
            source="system",
        )
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="submitted",
            actor=actor,
            reason=f"Beginning one authenticated {prepared['provider_method']} /{prepared['provider_path']} against the trusted MA sandbox mapping.",
            source="provider_worker",
        )

        request_kwargs: dict[str, Any] = {
            "auth": (str(integrator_api_key).strip(), str(user_api_key).strip()),
            "params": {"licenseNumber": license_value},
            "timeout": 30,
            "headers": {"Accept": "application/json", "Content-Type": "application/json"},
        }
        if prepared["provider_request_body"] is not None:
            request_kwargs["json"] = prepared["provider_request_body"]
        try:
            response = requests.request(
                prepared["provider_method"],
                f"{base_url.rstrip('/')}/{prepared['provider_path'].lstrip('/')}",
                **request_kwargs,
            )
        except requests.RequestException as exc:
            return self._unknown(
                transaction,
                prepared,
                actor,
                organization_id,
                facility_id,
                f"Metrc request outcome is unknown after {type(exc).__name__}.",
            )

        http_status = int(getattr(response, "status_code", 0) or 0)
        response_payload = _response_payload(response)
        self.traceability.record_attempt(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            request_payload={
                "method": prepared["provider_method"],
                "path": prepared["provider_path"],
                "query": {"licenseNumber": license_value},
                "body": prepared["provider_request_body"],
            },
            response_payload=response_payload if isinstance(response_payload, dict) else {"response": response_payload},
            http_status=http_status or None,
            error_code="" if http_status == 200 else "provider_rejected",
            error_message="" if http_status == 200 else f"Metrc returned HTTP {http_status}.",
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
                reason=f"Metrc returned HTTP {http_status}; provider outcome {'requires reconciliation' if uncertain else 'was rejected'}.",
                source="provider_worker",
                error_code="provider_outcome_unknown" if uncertain else "provider_rejected",
                error_message=f"Metrc returned HTTP {http_status}.",
            )
            if uncertain:
                self.traceability.record_reconciliation(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    transaction_id=transaction.id,
                    actor=actor,
                    mismatch_reason=f"Metrc returned HTTP {http_status}; do not repeat the write blindly.",
                    evidence={"operation_type": prepared["operation_type"], "blind_retry_allowed": False},
                    retry_eligible=False,
                )
            return self._result(transaction, prepared, f"Metrc returned HTTP {http_status}.")

        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="accepted",
            actor=actor,
            reason="Metrc returned HTTP 200. Fresh semantic readback is still required before verification.",
            source="provider_worker",
            external_reference=prepared["entity_id"],
            response_payload=response_payload if isinstance(response_payload, dict) else {"response": response_payload},
        )

        try:
            poststate, verified = self._verify_poststate(
                prepared=prepared,
                state=state_code,
                environment=env,
                license_number=license_value,
                integrator_api_key=integrator_api_key,
                user_api_key=user_api_key,
            )
        except MetrcMaCurrentLifecycleError as exc:
            poststate, verified = {"verification_error": str(exc)}, False

        self.traceability.record_reconciliation(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            actor=actor,
            local_state=prepared["provider_prestate"],
            provider_state=poststate,
            readback_result=poststate,
            mismatch_reason="" if verified else "Fresh semantic provider readback did not prove the confirmed target state.",
            evidence={
                "operation_type": prepared["operation_type"],
                "provider_verified": verified,
                "blind_retry_allowed": False,
            },
            retry_eligible=False,
        )
        if not verified:
            transaction = self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                new_status="reconciliation_required",
                actor=actor,
                reason="Metrc accepted the write, but fresh semantic readback did not prove the target state. Do not repeat the write blindly.",
                source="provider_readback",
                external_reference=prepared["entity_id"],
                error_code="readback_not_verified",
                error_message="Fresh provider state did not prove the requested lifecycle transition.",
            )
            return self._result(
                transaction,
                prepared,
                "Metrc accepted the write, but semantic verification requires reconciliation.",
            )

        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="verified",
            actor=actor,
            reason="Fresh semantic Metrc readback proved the confirmed lifecycle target state.",
            source="provider_readback",
            external_reference=prepared["entity_id"],
        )
        return self._result(transaction, prepared, "Metrc lifecycle state is verified. The synchronized provider mirror will refresh independently.")

    def _verify_poststate(
        self,
        *,
        prepared: dict[str, Any],
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> tuple[dict[str, Any], bool]:
        provider_id = int(prepared["entity_id"])
        operation = prepared["operation_type"]
        if operation in {"sales_receipt_finalize", "sales_receipt_unfinalize"}:
            poststate = self._receipt_state(
                provider_id=provider_id,
                state=state,
                environment=environment,
                license_number=license_number,
                integrator_api_key=integrator_api_key,
                user_api_key=user_api_key,
            )
            target = operation == "sales_receipt_finalize"
            return poststate, poststate["is_final"] is target
        if operation == "sales_delivery_delete":
            poststate = self._delivery_state(
                provider_id=provider_id,
                state=state,
                environment=environment,
                license_number=license_number,
                integrator_api_key=integrator_api_key,
                user_api_key=user_api_key,
                allow_missing=True,
            )
            return poststate, bool(poststate.get("missing") or poststate.get("voided_date"))
        poststate = self._template_state(
            provider_id=provider_id,
            state=state,
            environment=environment,
            license_number=license_number,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        return poststate, not bool(poststate["present"])

    def _unknown(
        self,
        transaction,
        prepared: dict[str, Any],
        actor: str,
        organization_id: str,
        facility_id: str,
        message: str,
    ) -> dict[str, Any]:
        self.traceability.record_attempt(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            request_payload={"operation_type": prepared["operation_type"], "path": prepared["provider_path"]},
            error_code="provider_outcome_unknown",
            error_message=message,
        )
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="reconciliation_required",
            actor=actor,
            reason="The provider call ended without enough evidence to classify the outcome. Blind retry is blocked.",
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
