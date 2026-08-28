from __future__ import annotations

import requests

from services.metrc_receiving import (
    fetch_all_delivery_packages,
    fetch_all_incoming_transfers,
    fetch_metrc_lab_results,
)


class _DummyResponse:
    def __init__(self, status_code: int, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"Data": [], "TotalPages": 1}
        self.headers = headers or {}

    def json(self):
        return self._payload


def test_incoming_transfers_reads_every_metrc_page(monkeypatch):
    calls = []

    def fake_get(url, auth=None, params=None, timeout=None, headers=None):
        calls.append({"url": url, "auth": auth, "params": dict(params or {})})
        page = int((params or {}).get("pageNumber") or 1)
        return _DummyResponse(
            200,
            {
                "Data": [{"Id": page, "ManifestNumber": f"M-{page}"}],
                "Total": 2,
                "TotalPages": 2,
                "PageNumber": page,
                "PageSize": 20,
            },
        )

    monkeypatch.setattr(requests, "get", fake_get)
    result = fetch_all_incoming_transfers(
        state="MA",
        user_api_key="user-key",
        integrator_api_key="integrator-key",
        license_number="LIC-123",
    )

    assert result["ok"] is True
    assert [item["Id"] for item in result["transfers"]] == [1, 2]
    assert len(calls) == 2
    assert calls[0]["url"] == "https://api-ma.metrc.com/transfers/v2/incoming"
    assert calls[0]["auth"] == ("integrator-key", "user-key")
    assert calls[0]["params"] == {
        "licenseNumber": "LIC-123",
        "pageSize": 20,
        "pageNumber": 1,
    }
    assert calls[1]["params"]["pageNumber"] == 2


def test_delivery_packages_reads_every_page(monkeypatch):
    calls = []

    def fake_get(url, auth=None, params=None, timeout=None, headers=None):
        calls.append({"url": url, "params": dict(params or {})})
        page = int((params or {}).get("pageNumber") or 1)
        return _DummyResponse(
            200,
            {
                "Data": [
                    {
                        "PackageId": 500 + page,
                        "PackageLabel": f"TAG-{page}",
                        "ItemId": 100 + page,
                    }
                ],
                "Total": 2,
                "TotalPages": 2,
                "PageNumber": page,
                "PageSize": 20,
            },
        )

    monkeypatch.setattr(requests, "get", fake_get)
    result = fetch_all_delivery_packages(
        state="MA",
        user_api_key="user-key",
        integrator_api_key="integrator-key",
        delivery_id=77,
    )

    assert result["ok"] is True
    assert [item["PackageLabel"] for item in result["packages"]] == ["TAG-1", "TAG-2"]
    assert calls[0]["url"] == "https://api-ma.metrc.com/transfers/v2/deliveries/77/packages"
    assert [call["params"]["pageNumber"] for call in calls] == [1, 2]


def test_lab_result_lookup_is_read_only_get_with_package_and_license(monkeypatch):
    calls = []

    def fake_get(url, auth=None, params=None, timeout=None, headers=None):
        calls.append(
            {
                "url": url,
                "auth": auth,
                "params": dict(params or {}),
                "headers": headers,
            }
        )
        return _DummyResponse(
            200,
            {
                "Data": [
                    {
                        "TestTypeName": "Total THC",
                        "TestResultLevel": 25.4,
                        "TestPassed": True,
                        "OverallPassed": True,
                    }
                ],
                "Total": 1,
                "TotalPages": 1,
                "PageNumber": 1,
                "PageSize": 20,
            },
        )

    monkeypatch.setattr(requests, "get", fake_get)
    result = fetch_metrc_lab_results(
        state="MA",
        user_api_key="user-key",
        integrator_api_key="integrator-key",
        license_number="LIC-123",
        package_id=501,
    )

    assert result["ok"] is True
    assert len(result["lab_results"]) == 1
    assert len(calls) == 1
    assert calls[0]["url"] == "https://api-ma.metrc.com/labtests/v2/results"
    assert calls[0]["auth"] == ("integrator-key", "user-key")
    assert calls[0]["params"] == {
        "packageId": "501",
        "licenseNumber": "LIC-123",
        "pageSize": 20,
        "pageNumber": 1,
    }
    assert calls[0]["headers"]["Accept"] == "application/json"
    assert calls[0]["headers"]["X-Correlation-ID"]


def test_metrc_receive_reads_stop_on_auth_failure(monkeypatch):
    calls = []

    def fake_get(url, auth=None, params=None, timeout=None, headers=None):
        calls.append(url)
        return _DummyResponse(401, {"message": "unauthorized"})

    monkeypatch.setattr(requests, "get", fake_get)
    result = fetch_all_incoming_transfers(
        state="MA",
        user_api_key="bad-key",
        integrator_api_key="integrator-key",
        license_number="LIC-123",
    )

    assert result["ok"] is False
    assert result["status"] == "auth_failed"
    assert len(calls) == 1
