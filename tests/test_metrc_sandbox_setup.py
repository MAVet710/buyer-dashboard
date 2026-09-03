from __future__ import annotations

from pathlib import Path

import pytest

from services.metrc_sandbox_setup import MetrcSandboxSetupError, provision_metrc_sandbox_user


ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, status_code: int, payload, *, headers=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload


def test_integrator_setup_uses_verified_ma_sandbox_and_special_metrc_header():
    captured = {}

    def post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse(200, {"Status": "Pending"})

    result = provision_metrc_sandbox_user(
        state="MA",
        integrator_api_key="vendor-key",
        request_post=post,
    )

    assert result["ok"] is True
    assert result["http_status"] == 200
    assert captured["url"] == "https://sandbox-api-ma.metrc.com/sandbox/v2/integrator/setup"
    assert captured["headers"]["x-metrc-key"] == "vendor-key"
    assert "Authorization" not in captured["headers"]
    assert captured["json"] == {}
    assert "contact email" in result["message"]


def test_integrator_setup_never_echoes_user_keys_from_provider_payload():
    result = provision_metrc_sandbox_user(
        state="MA",
        integrator_api_key="vendor-key",
        request_post=lambda *_args, **_kwargs: FakeResponse(200, {"userKey": "returned-secret", "Status": "Complete"}),
    )

    assert result["provider_response"]["userKey"] == "***"
    assert "returned-secret" not in str(result)


def test_integrator_setup_fails_closed_without_verified_sandbox_or_vendor_key():
    with pytest.raises(MetrcSandboxSetupError, match="verified Metrc sandbox"):
        provision_metrc_sandbox_user(state="OR", integrator_api_key="vendor-key")
    with pytest.raises(MetrcSandboxSetupError, match="Integrator / Vendor"):
        provision_metrc_sandbox_user(state="MA", integrator_api_key="")


def test_fastapi_and_react_expose_explicit_metrc_provisioning_flow():
    router = (ROOT / "backend/app/routers/sandbox_integrations.py").read_text(encoding="utf-8")
    panel = (ROOT / "frontend/src/components/DeveloperConnectionsPanel.tsx").read_text(encoding="utf-8")

    assert '@router.post("/metrc/provision-user")' in router
    assert '"required": ("state",)' in router
    assert '"sandbox_user_provisioning_enabled": True' in router
    assert "metrc_sandbox_user_provision_requested" in router
    assert "Provision sandbox user" in panel
    assert "/api/v1/integrations/sandbox/metrc/provision-user" in panel
    assert "Optional until sandbox user is provisioned" in panel
