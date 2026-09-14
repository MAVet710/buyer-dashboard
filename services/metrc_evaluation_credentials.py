from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


class MetrcEvaluationCredentialError(ValueError):
    """Raised when MA sandbox evaluation credential aliases are missing or conflict."""


@dataclass(frozen=True)
class MaSandboxEvaluationCredentials:
    integrator_api_key: str
    user_api_key: str
    license_number: str
    user_key_source: str
    license_source: str


def _clean(values: Mapping[str, str], name: str) -> str:
    return str(values.get(name) or "").strip()


def _aliased_value(
    values: Mapping[str, str],
    *,
    scoped_name: str,
    generic_name: str,
    label: str,
) -> tuple[str, str]:
    scoped = _clean(values, scoped_name)
    generic = _clean(values, generic_name)
    if scoped and generic and scoped != generic:
        raise MetrcEvaluationCredentialError(
            f"Conflicting {label}: {scoped_name} and {generic_name} are both set but do not match. "
            "Clear the stale value before running any MA sandbox evaluation request."
        )
    if scoped:
        return scoped, scoped_name
    if generic:
        return generic, generic_name
    return "", ""


def resolve_ma_sandbox_evaluation_credentials(
    environ: Mapping[str, str] | None = None,
    *,
    require_license: bool = True,
) -> MaSandboxEvaluationCredentials:
    """Resolve one unambiguous credential set for all local MA evaluation tooling.

    Historical tooling used both generic evaluation names and MA-specific sandbox
    names. GitHub workflows alias them to the same secret, but local shells may
    retain different stale values. Never choose silently when both are populated
    differently; an ambiguous credential pair is less safe than refusing to run.
    """

    values = environ if environ is not None else os.environ
    integrator = _clean(values, "METRC_INTEGRATOR_API_KEY")
    user_key, user_source = _aliased_value(
        values,
        scoped_name="METRC_MA_SANDBOX_USER_API_KEY",
        generic_name="METRC_USER_API_KEY",
        label="MA sandbox user API key environment variables",
    )
    license_number, license_source = _aliased_value(
        values,
        scoped_name="METRC_MA_SANDBOX_LICENSE_NUMBER",
        generic_name="METRC_LICENSE_NUMBER",
        label="MA sandbox license environment variables",
    )

    missing: list[str] = []
    if not integrator:
        missing.append("METRC_INTEGRATOR_API_KEY")
    if not user_key:
        missing.append("METRC_MA_SANDBOX_USER_API_KEY or METRC_USER_API_KEY")
    if require_license and not license_number:
        missing.append("METRC_MA_SANDBOX_LICENSE_NUMBER or METRC_LICENSE_NUMBER")
    if missing:
        raise MetrcEvaluationCredentialError(
            "Missing required MA sandbox evaluation environment variable(s): " + ", ".join(missing)
        )

    return MaSandboxEvaluationCredentials(
        integrator_api_key=integrator,
        user_api_key=user_key,
        license_number=license_number,
        user_key_source=user_source,
        license_source=license_source,
    )
