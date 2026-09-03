from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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
    assert result["page_size"] == 20
    assert len(result["items"]) == 1
    assert len(result["brands"]) == 1
    assert len(result["categories"]) == 1
    assert len(result["units_of_measure"]) == 1
    paged = {"licenseNumber": "LIC-TEST", "pageSize": 20, "pageNumber": 1}
    assert all(query == paged for _, query in transport.calls[:4])
    assert transport.calls[4][1] == {}


def test_initial_facility_reads_stay_within_metrc_page_limit(live_metrc):
    _, transport = live_metrc
    location_settings.metrc_rooms(context=object(), engine=object(), settings=object())
    location_settings.metrc_strains(context=object(), engine=object(), settings=object())
    assert transport.calls
    for _, query in transport.calls:
        assert query["licenseNumber"] == "LIC-TEST"
        if "pageSize" in query:
            assert 1 <= query["pageSize"] <= 50
            assert query["pageNumber"] == 1


def test_provider_failure_identifies_the_failing_resource():
    with pytest.raises(HTTPException) as error:
        location_settings._provider_rows(
            {"ok": False, "status": "auth_failed", "message": "Metrc rejected the saved API keys."},
            "item brands",
        )
    assert error.value.status_code == 502
    assert error.value.detail == "Metrc item brands: Metrc rejected the saved API keys."


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
    assert transport.calls[0][1] == {"licenseNumber": "LIC-TEST", "pageSize": 20, "pageNumber": 1}
    assert transport.calls[1][1] == {"licenseNumber": "LIC-TEST", "pageSize": 20, "pageNumber": 1}
    assert transport.calls[2][1] == {"licenseNumber": "LIC-TEST"}
    assert transport.calls[3][1] == {"licenseNumber": "LIC-TEST"}


def test_cultivation_additive_templates_are_live_read_only(live_metrc):
    _, transport = live_metrc
    result = location_settings.metrc_additive_templates(context=object(), engine=object(), settings=object())

    assert [path for path, _ in transport.calls] == [
        "additivestemplates/v2/active",
        "additivestemplates/v2/inactive",
    ]
    assert len(result["additive_templates"]) == 1
    assert len(result["inactive_additive_templates"]) == 1
    assert all(query == {"licenseNumber": "LIC-TEST", "pageSize": 20, "pageNumber": 1} for _, query in transport.calls)


def test_transportation_live_read_loads_drivers_and_vehicles(live_metrc):
    _, transport = live_metrc
    result = location_settings.metrc_transportation(context=object(), engine=object(), settings=object())

    assert [path for path, _ in transport.calls] == [
        "transporters/v2/drivers",
        "transporters/v2/vehicles",
    ]
    assert len(result["drivers"]) == 1
    assert len(result["vehicles"]) == 1
    assert all(query == {"licenseNumber": "LIC-TEST", "pageSize": 20, "pageNumber": 1} for _, query in transport.calls)


def test_preview_accepts_documentation_verified_jurisdiction_but_never_dispatches(live_metrc):
    metrc, _ = live_metrc
    metrc.state = "RI"
    request = location_settings.MetrcActionPreview(
        operation_type="brand_create",
        payload={"name": "Reserve", "unexpected": "drop"},
    )
    result = location_settings.metrc_action_preview(
        request=request,
        context=SimpleNamespace(role="admin"),
        engine=object(),
        settings=object(),
    )

    assert result["jurisdiction"]["code"] == "RI"
    assert result["jurisdiction"]["documentation_verified"] is True
    assert result["provider_request"] == {
        "method": "POST",
        "path": "items/v2/brand",
        "query": {"licenseNumber": "LIC-TEST"},
        "body": [{"Name": "Reserve"}],
    }
    assert result["dispatch_enabled"] is False
    assert result["requires_human_confirmation"] is True


def test_preview_rejects_jurisdiction_without_direct_documentation_verification(live_metrc):
    metrc, _ = live_metrc
    metrc.state = "VA"
    request = location_settings.MetrcActionPreview(
        operation_type="brand_create",
        payload={"name": "Reserve"},
    )

    with pytest.raises(HTTPException) as exc_info:
        location_settings.metrc_action_preview(
            request=request,
            context=SimpleNamespace(role="admin"),
            engine=object(),
            settings=object(),
        )
    assert exc_info.value.status_code == 409
    assert "documentation-verified Metrc jurisdiction" in str(exc_info.value.detail)


def test_preview_rejects_non_manager_role_before_provider_work(live_metrc):
    request = location_settings.MetrcActionPreview(
        operation_type="brand_create",
        payload={"name": "Reserve"},
    )
    with pytest.raises(HTTPException) as exc_info:
        location_settings.metrc_action_preview(
            request=request,
            context=SimpleNamespace(role="operator"),
            engine=object(),
            settings=object(),
        )
    assert exc_info.value.status_code == 403


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


def test_frontend_exposes_bounded_preview_forms_without_execute_controls():
    source = (ROOT / "frontend/src/pages/LocationSettingsPage.tsx").read_text(encoding="utf-8")
    for label in (
        "Prepare a Metrc item",
        "Advanced item fields",
        "Prepare item request",
        "Prepare an item brand",
        "Prepare brand request",
        "Prepare a Processing Job Type",
        "Prepare process request",
        "Prepare an additive template",
        "Prepare additive request",
        "Prepare a transport driver",
        "Prepare driver request",
        "Prepare a transport vehicle",
        "Prepare vehicle request",
        "Metrc request preview",
    ):
        assert label in source
    for operation in (
        'operation_type: "item_create"',
        'operation_type: "brand_create"',
        'operation_type: "processing_job_type_create"',
        'operation_type: "additive_template_create"',
        'operation_type: "driver_create"',
        'operation_type: "vehicle_create"',
    ):
        assert operation in source
    assert "Execute Metrc" not in source
    assert "Submit to Metrc" not in source
