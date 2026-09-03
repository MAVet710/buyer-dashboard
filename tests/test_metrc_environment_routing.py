from __future__ import annotations

from services import metrc_inventory_adjustments, metrc_packages
from modules.regulatory.registry import resolve_metrc_base_url


class _Response:
    status_code = 200
    content = b""
    headers = {}

    @property
    def ok(self):
        return True

    def json(self):
        return None


def test_ma_sandbox_and_production_hosts_are_strictly_separate():
    assert resolve_metrc_base_url("MA", environment="production") == ("https://api-ma.metrc.com", "MA")
    assert resolve_metrc_base_url("MA", environment="sandbox") == ("https://sandbox-api-ma.metrc.com", "MA")
    assert resolve_metrc_base_url("OR", environment="sandbox") == ("", "OR")


def test_package_adjustment_targets_ma_sandbox(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return _Response()

    monkeypatch.setattr(metrc_inventory_adjustments.requests, "request", fake_request)
    result = metrc_inventory_adjustments.submit_package_adjustment(
        state="MA",
        environment="sandbox",
        user_api_key="user",
        integrator_api_key="integrator",
        license_number="LIC-1",
        package_label="1A4000000000000000000001",
        adjustment_type="absolute",
        quantity=3.5,
        unit="g",
        reason="Inventory Audit",
    )

    assert result["ok"] is True
    assert calls[0][1] == "https://sandbox-api-ma.metrc.com/packages/v2/adjust"


def test_package_creation_targets_ma_sandbox(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return _Response()

    monkeypatch.setattr(metrc_inventory_adjustments.requests, "request", fake_request)
    result = metrc_packages.submit_package_creation(
        state="MA",
        environment="sandbox",
        user_api_key="user",
        integrator_api_key="integrator",
        license_number="LIC-1",
        tag="1A4000000000000000000099",
        item="Finished Flower 3.5g",
        quantity=3.5,
        unit="g",
        ingredients=[{"package_label": "1A4000000000000000000001", "quantity": 3.5, "unit": "g"}],
    )

    assert result["ok"] is True
    assert calls[0][1] == "https://sandbox-api-ma.metrc.com/packages/v2/"
