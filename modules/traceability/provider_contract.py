"""Provider-neutral contracts for regulated traceability adapters.

This module does not execute regulated mutations. It gives Metrc, BioTrack and
future state adapters one normalized capability/result vocabulary while the
existing durable transaction/reconciliation ledger remains authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class TraceabilityCapability:
    operation_type: str
    verification_resource: str = ""
    supports_write: bool = False
    supports_readback: bool = False


@dataclass(frozen=True)
class ProviderExecutionResult:
    provider: str
    ok: bool
    status: str
    request_sent: bool = False
    retryable: bool = False
    verified: bool = False
    http_status: int | None = None
    external_reference: str = ""
    verification_resource: str = ""
    message: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "ok": self.ok,
            "status": self.status,
            "outbound_request_sent": self.request_sent,
            "retryable": self.retryable,
            "verified": self.verified,
            "http_status": self.http_status,
            "external_reference": self.external_reference,
            "verification_resource": self.verification_resource,
            "message": self.message,
            "payload": dict(self.payload),
        }


class TraceabilityProviderAdapter(Protocol):
    provider: str

    def capabilities(self) -> Mapping[str, TraceabilityCapability]: ...

    def execute(
        self,
        *,
        operation_type: str,
        entity_id: str,
        payload: Mapping[str, Any],
        reason: str,
    ) -> ProviderExecutionResult: ...


class TraceabilityProviderRegistry:
    """Small explicit registry; registering an adapter never grants write access."""

    def __init__(self) -> None:
        self._adapters: dict[str, TraceabilityProviderAdapter] = {}

    @staticmethod
    def _key(provider: str) -> str:
        return str(provider or "").strip().casefold()

    def register(self, adapter: TraceabilityProviderAdapter) -> None:
        key = self._key(adapter.provider)
        if not key:
            raise ValueError("A provider name is required.")
        if key in self._adapters:
            raise ValueError(f"Traceability provider {key!r} is already registered.")
        self._adapters[key] = adapter

    def get(self, provider: str) -> TraceabilityProviderAdapter:
        key = self._key(provider)
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise ValueError(f"No traceability adapter is registered for {key or provider!r}.") from exc

    def capabilities(self, provider: str) -> Mapping[str, TraceabilityCapability]:
        return self.get(provider).capabilities()


def normalize_provider_result(
    provider: str,
    raw: Mapping[str, Any] | ProviderExecutionResult,
    *,
    verification_resource: str = "",
) -> ProviderExecutionResult:
    """Normalize existing adapter dictionaries without changing their semantics."""

    if isinstance(raw, ProviderExecutionResult):
        return raw
    provider_key = str(provider or raw.get("provider") or "").strip().casefold()
    status = str(raw.get("status") or ("accepted" if raw.get("ok") else "provider_error")).strip().casefold()
    payload = raw.get("payload")
    if not isinstance(payload, Mapping):
        payload = {"result": payload} if payload is not None else {}
    return ProviderExecutionResult(
        provider=provider_key,
        ok=bool(raw.get("ok")),
        status=status,
        request_sent=bool(raw.get("outbound_request_sent", raw.get("request_sent", False))),
        retryable=bool(raw.get("retryable", False)),
        verified=bool(raw.get("verified", False)),
        http_status=int(raw["http_status"]) if raw.get("http_status") is not None else None,
        external_reference=str(raw.get("external_reference") or ""),
        verification_resource=str(raw.get("verification_resource") or verification_resource or ""),
        message=str(raw.get("message") or raw.get("error_message") or ""),
        payload=dict(payload),
    )
