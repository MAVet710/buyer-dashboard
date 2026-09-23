"""Regression guard: a sandbox-scoped Metrc read must never reach a production host.

`services.metrc_receiving._paged_resource_get` called `_metrc_get` without forwarding
`environment`, so every receiving / inventory-reconciliation read silently resolved the
production API host via `services.metrc_client._metrc_get`'s default, even when the
caller explicitly asked for sandbox.

Consequences this test locks down:

* a sandbox verification silently issued a production request, and
* the resulting 401 was reported as "Metrc rejected the saved API keys", inviting a
  needless (and forbidden) credential rotation.

Production and sandbox hosts are separate trust boundaries
(`modules/regulatory/registry.resolve_metrc_base_url`); a sandbox-scoped workflow must
never fall through to a production API host.

These tests intercept ``requests.get`` and never issue a network request.
"""

from __future__ import annotations

import requests

from services.metrc_receiving import _paged_resource_get

SANDBOX_HOST = "https://sandbox-api-ma.metrc.com/"
PRODUCTION_HOST = "https://api-ma.metrc.com/"


class _DummyResponse:
    status_code = 200
    headers: dict = {}

    def json(self):
        return {"Data": [], "Total": 0, "TotalPages": 1, "PageNumber": 1, "PageSize": 20}


def _captured_url(monkeypatch, environment):
    calls: list[str] = []

    def fake_get(url, auth=None, params=None, timeout=None, headers=None):
        calls.append(str(url))
        return _DummyResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    kwargs = {
        "state": "MA",
        "user_api_key": "user-key",
        "integrator_api_key": "integrator-key",
        "resource": "packages_active",
        "license_number": "SF-SBX-MA-4-11701",
    }
    if environment is not None:
        kwargs["environment"] = environment

    _paged_resource_get(**kwargs)

    assert calls, "expected the read to issue exactly one provider request"
    return calls[0]


def test_sandbox_read_targets_sandbox_host(monkeypatch):
    url = _captured_url(monkeypatch, "sandbox")
    assert url.startswith(SANDBOX_HOST), url


def test_sandbox_read_never_targets_production_host(monkeypatch):
    url = _captured_url(monkeypatch, "sandbox")
    assert not url.startswith(PRODUCTION_HOST), url


def test_production_read_targets_production_host(monkeypatch):
    url = _captured_url(monkeypatch, "production")
    assert url.startswith(PRODUCTION_HOST), url


def test_omitted_environment_keeps_production_default(monkeypatch):
    url = _captured_url(monkeypatch, None)
    assert url.startswith(PRODUCTION_HOST), url
