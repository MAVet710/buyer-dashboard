import json

from scripts.validate_ma_metrc_sandbox import live_read


ENV = {
    "METRC_INTEGRATOR_API_KEY": "integrator-secret",
    "METRC_MA_SANDBOX_USER_API_KEY": "user-secret",
    # A stale historical license may still exist in a shell; the authentication
    # gate must not force it onto the evaluation.
    "METRC_MA_SANDBOX_LICENSE_NUMBER": "OLD-LICENSE",
}


class _Response:
    status_code = 200
    ok = True

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_live_read_verifies_existing_keys_and_discovers_all_facilities_without_echoing_secrets(monkeypatch):
    monkeypatch.setattr(
        "scripts.validate_ma_metrc_sandbox.requests.get",
        lambda *args, **kwargs: _Response(
            {
                "Data": [
                    {"Id": 1, "Name": "Cultivator", "License": {"Number": "GROW-1"}},
                    {"Id": 2, "Name": "Retailer", "License": {"Number": "SALE-1"}},
                ]
            }
        ),
    )

    report = live_read(ENV)

    assert report["ready"] is True
    assert report["status"] == "authenticated_read_verified"
    assert report["facility_count"] == 2
    assert report["license_count"] == 2
    assert report["license_required_for_authentication"] is False
    assert report["write_performed"] is False
    serialized = json.dumps(report)
    assert ENV["METRC_INTEGRATOR_API_KEY"] not in serialized
    assert ENV["METRC_MA_SANDBOX_USER_API_KEY"] not in serialized
    assert ENV["METRC_MA_SANDBOX_LICENSE_NUMBER"] not in serialized


def test_live_read_fails_closed_when_facilities_response_contains_no_license_records(monkeypatch):
    monkeypatch.setattr(
        "scripts.validate_ma_metrc_sandbox.requests.get",
        lambda *args, **kwargs: _Response({"Data": [{"Id": 1, "Name": "Unknown"}]}),
    )

    report = live_read(ENV)

    assert report["ready"] is False
    assert report["status"] == "facilities_missing"
    assert report["write_performed"] is False


def test_live_read_accepts_top_level_and_nested_license_shapes(monkeypatch):
    monkeypatch.setattr(
        "scripts.validate_ma_metrc_sandbox.requests.get",
        lambda *args, **kwargs: _Response([
            {"Id": 1, "LicenseNumber": "GROW-1"},
            {"Id": 2, "License": {"Number": "LAB-1"}},
        ]),
    )

    report = live_read(ENV)

    assert report["status"] == "authenticated_read_verified"
    assert report["facility_count"] == 2
    assert report["license_count"] == 2
