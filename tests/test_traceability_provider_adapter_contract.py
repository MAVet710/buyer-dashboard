from __future__ import annotations

import pytest

from modules.traceability.metrc_provider import MetrcProviderAdapter
from modules.traceability.provider_contract import ProviderExecutionResult, TraceabilityProviderRegistry
from services.metrc_native import MetrcNativeError


def _adapter(submitter):
    return MetrcProviderAdapter(
        state="MA",
        environment="sandbox",
        license_number="MP281234",
        integrator_api_key="integrator-key",
        user_api_key="user-key",
        submitter=submitter,
    )


def test_metrc_adapter_exposes_write_capability_without_granting_unverified_operations():
    adapter = _adapter(lambda **kwargs: {})
    capabilities = adapter.capabilities()

    assert capabilities["package_adjust"].supports_write is True
    assert capabilities["package_adjust"].supports_readback is True
    assert capabilities["package_move"].supports_write is False


def test_metrc_adapter_normalizes_accepted_provider_result():
    captured = {}

    def submitter(**kwargs):
        captured.update(kwargs)
        return {
            "http_status": 200,
            "payload": {"Data": [{"Id": 42}]},
            "request_sent": True,
            "external_reference": "42",
        }

    result = _adapter(submitter).execute(
        operation_type="package_adjust",
        entity_id="1A4060300000000000000001",
        payload={"quantity_delta": -1, "unit": "Grams", "reason": "Waste"},
        reason="Reviewed adjustment",
    )

    assert isinstance(result, ProviderExecutionResult)
    assert result.ok is True
    assert result.status == "accepted"
    assert result.request_sent is True
    assert result.verified is False
    assert result.verification_resource == "packages_active"
    assert result.external_reference == "42"
    assert captured["operation_type"] == "package_adjust"
    assert captured["environment"] == "sandbox"


def test_metrc_adapter_blocks_disabled_operation_before_submitter_runs():
    def should_not_run(**kwargs):
        raise AssertionError("disabled operation must never reach the provider")

    result = _adapter(should_not_run).execute(
        operation_type="package_move",
        entity_id="1A4060300000000000000001",
        payload={"destination_location": "Vault"},
        reason="Move package",
    )

    assert result.ok is False
    assert result.status == "unsupported_operation"
    assert result.request_sent is False
    assert result.verified is False


def test_metrc_adapter_preserves_uncertain_request_semantics():
    def timeout(**kwargs):
        raise MetrcNativeError(
            "Metrc request failed after transmission.",
            retryable=True,
            request_sent=True,
        )

    result = _adapter(timeout).execute(
        operation_type="package_adjust",
        entity_id="1A4060300000000000000001",
        payload={"quantity_delta": -1, "unit": "Grams", "reason": "Waste"},
        reason="Reviewed adjustment",
    )

    assert result.ok is False
    assert result.status == "retryable_provider_error"
    assert result.request_sent is True
    assert result.retryable is True
    assert result.verified is False


def test_provider_registry_fails_closed_for_unregistered_provider():
    registry = TraceabilityProviderRegistry()
    registry.register(_adapter(lambda **kwargs: {}))

    with pytest.raises(ValueError, match="No traceability adapter"):
        registry.get("biotrack")
