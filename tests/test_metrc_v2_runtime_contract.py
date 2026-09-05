from __future__ import annotations

from modules.regulatory.metrc_resources import METRC_V2_MAX_PAGE_SIZE
from services import metrc_production
from services.metrc_evaluation_pagination import fetch_all_metrc_resource_pages
from services.metrc_resilient_bootstrap import PAGE_SIZE as HYDRATION_PAGE_SIZE


def test_runtime_hydration_uses_metrc_v2_page_ceiling():
    assert METRC_V2_MAX_PAGE_SIZE == 20
    assert HYDRATION_PAGE_SIZE == 20


def test_evaluation_page_helper_caps_requested_page_size_to_metrc_v2_limit():
    seen: list[int] = []

    def fake_fetch(**kwargs):
        seen.append(int(kwargs["page_size"]))
        return {
            "ok": True,
            "http_status": 200,
            "status": "connected",
            "records": [{"provider_id": "1"}],
            "payload": {"TotalPages": 1, "Data": [{"Id": 1}]},
            "correlation_id": "corr-1",
        }

    result = fetch_all_metrc_resource_pages(
        state="MA",
        user_api_key="user",
        integrator_api_key="integrator",
        resource="incoming_transfers",
        environment="sandbox",
        license_number="MA-SANDBOX-LIC",
        page_size=100,
        fetch_fn=fake_fetch,
    )

    assert result["passed"] is True
    assert seen == [20]


def test_production_resource_401_does_not_claim_saved_keys_are_globally_invalid(monkeypatch):
    monkeypatch.setattr(
        metrc_production,
        "_paged_resource_get",
        lambda **_kwargs: {
            "ok": False,
            "http_status": 401,
            "status": "auth_failed",
            "message": "Metrc rejected the saved API keys.",
        },
    )

    result = metrc_production.fetch_all_active_plant_batches(
        state="MA",
        user_api_key="user",
        integrator_api_key="integrator",
        license_number="MA-SANDBOX-LIC",
        environment="sandbox",
    )

    assert result["ok"] is False
    assert result["status"] == "authentication_or_permission_rejected"
    assert "resource request" in result["message"]
    assert "permission" in result["message"]
    assert "globally invalid" in result["message"]
