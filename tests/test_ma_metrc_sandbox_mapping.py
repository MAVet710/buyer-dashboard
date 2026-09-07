import json

from scripts.validate_ma_metrc_sandbox import live_read


ENV = {
    "METRC_INTEGRATOR_API_KEY": "integrator-secret",
    "METRC_MA_SANDBOX_USER_API_KEY": "user-secret",
    "METRC_MA_SANDBOX_LICENSE_NUMBER": "MP281234",
}


class _Response:
    status_code = 200
    ok = True

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_live_read_verifies_nested_facility_license_without_echoing_it(monkeypatch):
    monkeypatch.setattr(
        "scripts.validate_ma_metrc_sandbox.requests.get",
        lambda *args, **kwargs: _Response(
            {
                "Data": [
                    {"Id": 1, "Name": "MA Sandbox Facility", "License": {"Number": "MP281234"}},
                    {"Id": 2, "Name": "Other Facility", "License": {"Number": "MP289999"}},
                ]
            }
        ),
    )

    report = live_read(ENV)

    assert report["ready"] is True
    assert report["status"] == "authenticated_read_verified"
    assert report["facility_count"] == 2
    assert report["matched_facility_count"] == 1
    assert report["license_mapping_verified"] is True
    assert report["write_performed"] is False
    serialized = json.dumps(report)
    assert ENV["METRC_INTEGRATOR_API_KEY"] not in serialized
    assert ENV["METRC_MA_SANDBOX_USER_API_KEY"] not in serialized
    assert ENV["METRC_MA_SANDBOX_LICENSE_NUMBER"] not in serialized


def test_live_read_fails_closed_when_configured_license_is_not_returned(monkeypatch):
    monkeypatch.setattr(
        "scripts.validate_ma_metrc_sandbox.requests.get",
        lambda *args, **kwargs: _Response(
            {"Data": [{"Id": 1, "LicenseNumber": "MP289999"}]}
        ),
    )

    report = live_read(ENV)

    assert report["ready"] is False
    assert report["status"] == "license_mapping_not_found"
    assert report["facility_count"] == 1
    assert report["matched_facility_count"] == 0
    assert report["license_mapping_verified"] is False
    assert report["write_performed"] is False
    assert ENV["METRC_MA_SANDBOX_LICENSE_NUMBER"] not in json.dumps(report)


def test_live_read_accepts_top_level_license_number_shape(monkeypatch):
    monkeypatch.setattr(
        "scripts.validate_ma_metrc_sandbox.requests.get",
        lambda *args, **kwargs: _Response(
            [{"Id": 1, "LicenseNumber": "mp281234"}]
        ),
    )

    report = live_read(ENV)

    assert report["status"] == "authenticated_read_verified"
    assert report["license_mapping_verified"] is True
    assert report["matched_facility_count"] == 1
