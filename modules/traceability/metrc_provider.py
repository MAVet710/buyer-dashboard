"""Provider-contract adapter for reviewed Metrc mutations.

The adapter is deliberately narrower than the durable dispatcher. It owns the
provider-specific execution/result vocabulary, but it does not grant permission
to write. Tenant scope, operating mode, credential scope, trusted facility
mapping, approval and durable lifecycle gates remain the dispatcher's job.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from modules.regulatory import list_metrc_write_contracts
from services.metrc_native import MetrcNativeError, submit_metrc_action

from .provider_contract import ProviderExecutionResult, TraceabilityCapability


class MetrcProviderAdapter:
    """Execute only registry-promoted Metrc operations through one contract."""

    provider = "metrc"

    def __init__(
        self,
        *,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
        submitter: Callable[..., dict[str, Any]] = submit_metrc_action,
    ) -> None:
        self.state = str(state or "").strip().upper()
        self.environment = str(environment or "").strip().casefold()
        self.license_number = str(license_number or "").strip()
        self._integrator_api_key = str(integrator_api_key or "").strip()
        self._user_api_key = str(user_api_key or "").strip()
        self._submitter = submitter

    def capabilities(self) -> Mapping[str, TraceabilityCapability]:
        capabilities: dict[str, TraceabilityCapability] = {}
        for contract in list_metrc_write_contracts(
            jurisdiction=self.state,
            environment=self.environment,
        ):
            public = contract.public(
                jurisdiction=self.state,
                environment=self.environment,
            )
            capabilities[contract.operation_type] = TraceabilityCapability(
                operation_type=contract.operation_type,
                verification_resource=str(contract.verification_resource or ""),
                supports_write=bool(public.get("dispatch_enabled")),
                supports_readback=bool(contract.verification_resource),
            )
        return capabilities

    def execute(
        self,
        *,
        operation_type: str,
        entity_id: str,
        payload: Mapping[str, Any],
        reason: str,
    ) -> ProviderExecutionResult:
        operation = str(operation_type or "").strip().casefold()
        capability = self.capabilities().get(operation)
        if capability is None or not capability.supports_write:
            return ProviderExecutionResult(
                provider=self.provider,
                ok=False,
                status="unsupported_operation",
                request_sent=False,
                verified=False,
                verification_resource=(capability.verification_resource if capability else ""),
                message=f"Metrc operation {operation!r} is not enabled for this jurisdiction/environment contract.",
            )

        try:
            raw = self._submitter(
                state=self.state,
                environment=self.environment,
                license_number=self.license_number,
                integrator_api_key=self._integrator_api_key,
                user_api_key=self._user_api_key,
                operation_type=operation,
                entity_id=str(entity_id or "").strip(),
                payload=dict(payload),
                reason=str(reason or ""),
            )
        except MetrcNativeError as exc:
            response_payload = exc.response if isinstance(exc.response, Mapping) else {}
            return ProviderExecutionResult(
                provider=self.provider,
                ok=False,
                status="retryable_provider_error" if exc.retryable else "provider_rejected",
                request_sent=bool(exc.request_sent),
                retryable=bool(exc.retryable),
                verified=False,
                http_status=exc.http_status,
                verification_resource=capability.verification_resource,
                message=str(exc),
                payload=dict(response_payload),
            )

        raw_payload = raw.get("payload")
        if isinstance(raw_payload, Mapping):
            response_payload = dict(raw_payload)
        elif raw_payload is None:
            response_payload = {}
        else:
            response_payload = {"result": raw_payload}
        return ProviderExecutionResult(
            provider=self.provider,
            ok=True,
            status="accepted",
            request_sent=bool(raw.get("request_sent", True)),
            retryable=False,
            verified=False,
            http_status=int(raw.get("http_status") or 0) or None,
            external_reference=str(raw.get("external_reference") or ""),
            verification_resource=capability.verification_resource,
            payload=response_payload,
        )
