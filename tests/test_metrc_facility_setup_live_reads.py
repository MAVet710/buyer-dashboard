from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.routers import location_settings


ROOT = Path(__file__).resolve().parents[1]


class FakeTransport:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, path: str, query: dict[str, object]):
        self.calls.append((path, dict(query)))
        return {"ok": True, "payload": [{"Id": len(self.calls), "Name": path}]}


@pytest.fixture
def live_metrc(monkeypatch: pytest.MonkeyPatch):
    metrc = SimpleNamespace(
        state="MA",
        license_number="LIC-TEST",
        environment="sandbox",
    )
    transport = FakeTransport()
    monkeypatch.setattr(location_settings, "_trusted_metrc", lambda *_args, **_kwargs: (None, metrc))
    monkeypatch.setattr(location_settings, "_transport", lambda _metrc: transport)
    return metrc, transport


def test_items_live_read_uses_documented_master_data_endpoints(live_metrc):
    _, transport = live_metrc
    result = location_settings.metrc_items(context=object(), engine=object(), settings=object())

    assert [path for path, _ in transport.calls] == [
        "items/v2/active",
        "items/v2/inactive",
        "items/v2/categories",
        "items/v2/brands",
        "unitsofmeasure/v2/active",
    ]
    assert result["source"] == "metrc_live"
    assert result["license_number"] == "LIC-TEST"
    assert result["bounded"] is True
    assert len(result["items"]) == 1
    assert len(result["brands"]) == 1
    assert len(result["categories"]) == 1
    assert len(result["units_of_measure"]) == 1
    assert transport.calls[0][1] == {"licenseNumber": "LIC-TEST", "pageSize": 100, "pageNumber": 1}
    assert transport.calls[2][1] == {"licenseNumber": "LIC-TEST"}


def test_processing_setup_live_read_uses_jobtype_metadata_endpoints(live_metrc):
    _, transport = live_metrc
    result = location_settings.metrc_processing_setup(context=object(), engine=object(), settings=object())

    assert [path for path, _ in transport.calls] == [
        "processing/v2/jobtypes/active",
        "processing/v2/jobtypes/inactive",
        "processing/v2/jobtypes/attributes",
        "processing/v2/jobtypes/categories",
    ]
    assert len(result["job_types"]) == 1
    assert len(result["inactive_job_types"]) == 1
    assert len(result["attributes"]) == 1
    assert len(result["categories"]) == 1


def test_cultivation_additive_templates_are_live_read_only(live_metrc):
    _, transport = live_metrc
    result = location_settings.metrc_additive_templates(context=object(), engine=object(), settings=object())

    assert [path for path, _ in transport.calls] == [
        "additivestemplates/v2/active",
        "additivestemplates/v2/inactive",
    ]
    assert len(result["additive_templates"]) == 1
    assert len(result["inactive_additive_templates"]) == 1


def test_transportation_live_read_loads_drivers_and_vehicles(live_metrc):
    _, transport = live_metrc
    result = location_settings.metrc_transportation(context=object(), engine=object(), settings=object())

    assert [path for path, _ in transport.calls] == [
        "transporters/v2/drivers",
        "transporters/v2/vehicles",
    ]
    assert len(result["drivers"]) == 1
    assert len(result["vehicles"]) == 1
    assert all(query == {"licenseNumber": "LIC-TEST"} for _, query in transport.calls)


def test_frontend_keeps_live_provider_reads_opt_in_and_visible():
    source = (ROOT / "frontend/src/pages/LocationSettingsPage.tsx").read_text(encoding="utf-8")
    for endpoint in (
        "/api/v1/location-settings/metrc-items",
        "/api/v1/location-settings/metrc-processing-setup",
        "/api/v1/location-settings/metrc-additive-templates",
        "/api/v1/location-settings/metrc-transportation",
    ):
        assert endpoint in source
    for label in (
        "Active Metrc items",
        "Active Processing Job Types",
        "Active additive templates",
        "Transport drivers",
        "Transport vehicles",
        "Provider-changing actions",
        "Network writes remain fail-closed",
    ):
        assert label in source
    assert source.count("enabled: false") >= 7