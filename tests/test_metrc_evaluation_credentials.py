from __future__ import annotations

import pytest

from services.metrc_evaluation_credentials import (
    MetrcEvaluationCredentialError,
    resolve_ma_sandbox_evaluation_credentials,
)


def _name(*parts: str) -> str:
    return "".join(parts)


def _env(*, scoped_user: str = "", generic_user: str = "", scoped_license: str = "", generic_license: str = ""):
    values = {
        _name("METRC_", "INTEGRATOR_", "API_KEY"): "i",
    }
    if scoped_user:
        values[_name("METRC_MA_", "SANDBOX_USER_", "API_KEY")] = scoped_user
    if generic_user:
        values[_name("METRC_", "USER_", "API_KEY")] = generic_user
    if scoped_license:
        values[_name("METRC_MA_", "SANDBOX_LICENSE_", "NUMBER")] = scoped_license
    if generic_license:
        values[_name("METRC_", "LICENSE_", "NUMBER")] = generic_license
    return values


def test_scoped_and_generic_aliases_may_match_when_fixed_license_is_required() -> None:
    credentials = resolve_ma_sandbox_evaluation_credentials(
        _env(scoped_user="u", generic_user="u", scoped_license="L", generic_license="L")
    )

    assert credentials.user_api_key == "u"
    assert credentials.license_number == "L"
    assert credentials.user_key_source == "METRC_MA_SANDBOX_USER_API_KEY"
    assert credentials.license_source == "METRC_MA_SANDBOX_LICENSE_NUMBER"


def test_generic_evaluation_names_remain_supported_for_fixed_license_callers() -> None:
    credentials = resolve_ma_sandbox_evaluation_credentials(
        _env(generic_user="u", generic_license="L")
    )

    assert credentials.user_api_key == "u"
    assert credentials.license_number == "L"
    assert credentials.user_key_source == "METRC_USER_API_KEY"
    assert credentials.license_source == "METRC_LICENSE_NUMBER"


def test_conflicting_user_aliases_always_fail_closed() -> None:
    with pytest.raises(MetrcEvaluationCredentialError, match="do not match"):
        resolve_ma_sandbox_evaluation_credentials(
            _env(scoped_user="u1", generic_user="u2", scoped_license="L"),
            require_license=False,
        )


def test_conflicting_license_aliases_fail_closed_when_fixed_license_is_required() -> None:
    with pytest.raises(MetrcEvaluationCredentialError, match="do not match"):
        resolve_ma_sandbox_evaluation_credentials(
            _env(scoped_user="u", scoped_license="L1", generic_license="L2")
        )


def test_discovery_driven_runner_does_not_inherit_or_compare_global_license_aliases() -> None:
    credentials = resolve_ma_sandbox_evaluation_credentials(
        _env(scoped_user="u", scoped_license="OLD-L1", generic_license="STALE-L2"),
        require_license=False,
    )

    assert credentials.user_api_key == "u"
    assert credentials.license_number == ""
    assert credentials.license_source == ""


def test_facilities_read_does_not_require_license() -> None:
    credentials = resolve_ma_sandbox_evaluation_credentials(
        _env(scoped_user="u"),
        require_license=False,
    )

    assert credentials.user_api_key == "u"
    assert credentials.license_number == ""
