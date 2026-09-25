"""Truthful release readiness for each configured regulatory jurisdiction.

Documentation, provider-host discovery, sandbox execution, regulator acceptance,
and production release are deliberately separate gates. The registry must never
turn documentation availability into an implication that DoobieLogic may write
to a state system.
"""

from __future__ import annotations

from typing import Any

from .registry import get_jurisdiction, list_jurisdictions, resolve_metrc_base_url


# External acceptance is intentionally empty in source control. A jurisdiction
# reaches these sets only after the corresponding regulator/provider evidence
# has been reviewed and deliberately committed as a release decision. Runtime
# sandbox success does not silently mutate code policy.
GENERIC_EVALUATION_APPROVED: frozenset[str] = frozenset()
PRODUCTION_WRITE_APPROVED: frozenset[str] = frozenset()


def jurisdiction_readiness(value: str) -> dict[str, Any]:
    profile = get_jurisdiction(value)
    if profile is None:
        return {
            "code": str(value or "").strip().upper(),
            "known_market": False,
            "documentation_verified": False,
            "production_host_verified": False,
            "sandbox_host_verified": False,
            "evaluation_approved": False,
            "production_write_approved": False,
            "release_stage": "unknown_market",
            "next_gate": "Verify the market/provider relationship before configuring any regulatory connection.",
        }

    sandbox_base, _ = resolve_metrc_base_url(profile.code, environment="sandbox")
    production_base, _ = resolve_metrc_base_url(profile.code, environment="production")
    documentation_verified = bool(profile.documentation_verified)
    sandbox_host_verified = bool(sandbox_base)
    evaluation_approved = profile.code in GENERIC_EVALUATION_APPROVED
    production_write_approved = profile.code in PRODUCTION_WRITE_APPROVED

    if production_write_approved:
        stage = "production_write_approved"
        next_gate = "Production release policy is approved; operator actions must still pass exact license, permission, payload, confirmation and readback gates."
    elif evaluation_approved:
        stage = "evaluation_approved"
        next_gate = "Complete jurisdiction-specific production authorization and controlled production release review."
    elif sandbox_host_verified:
        stage = "sandbox_ready_for_evidence"
        next_gate = "Execute the jurisdiction-specific sandbox acceptance suite and retain exact provider readback evidence; do not infer regulator approval from code readiness."
    elif documentation_verified:
        stage = "documentation_verified"
        next_gate = "Obtain and verify the provider-issued sandbox deployment/access before promoting any sandbox write workflow."
    else:
        stage = "market_known"
        next_gate = "Verify the jurisdiction's current official API documentation and exact endpoint families before implementing write contracts."

    return {
        "code": profile.code,
        "name": profile.name,
        "provider": profile.provider,
        "known_market": True,
        "documentation_verified": documentation_verified,
        "production_host_verified": bool(production_base),
        "sandbox_host_verified": sandbox_host_verified,
        "evaluation_approved": evaluation_approved,
        "production_write_approved": production_write_approved,
        "release_stage": stage,
        "next_gate": next_gate,
        "documentation_url": profile.documentation_url,
        "verified_on": profile.verified_on,
        "capabilities": {key: status.value for key, status in profile.capabilities.items()},
        "safety": {
            "documentation_is_not_permission": True,
            "sandbox_success_is_not_regulator_approval": True,
            "production_writes_default_locked": not production_write_approved,
        },
    }


def list_jurisdiction_readiness() -> list[dict[str, Any]]:
    return [jurisdiction_readiness(profile.code) for profile in list_jurisdictions()]


def require_sandbox_execution_ready(value: str) -> dict[str, Any]:
    readiness = jurisdiction_readiness(value)
    if not readiness.get("known_market"):
        raise ValueError("The regulatory jurisdiction is not verified in the active registry.")
    if not readiness.get("documentation_verified"):
        raise ValueError(f"Official API documentation has not been verified for {readiness['code']}.")
    if not readiness.get("sandbox_host_verified"):
        raise ValueError(f"A provider-issued sandbox API deployment has not been verified for {readiness['code']}.")
    return readiness


def require_production_write_approved(value: str) -> dict[str, Any]:
    readiness = jurisdiction_readiness(value)
    if not readiness.get("production_write_approved"):
        raise ValueError(
            f"Production regulatory writes are not release-approved for {readiness.get('code') or str(value).upper()}. "
            "Documentation or sandbox evidence alone cannot unlock production writes."
        )
    return readiness
