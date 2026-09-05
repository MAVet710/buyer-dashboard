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


class PagedFakeTransport:
    def __init__(self, *, full_pages: int, tail_count: int):
        self.full_pages = full_pages
        self.tail_count = tail_count
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, path: str, query: dict[str, object]):
        self.calls.append((path, dict(query)))
        page = int(query.get("pageNumber") or 1)
        page_size = int(query.get("pageSize") or 20)
        if page <= self.full_pages:
            count = page_size
        elif page == self.full_pages + 1:
            count = self.tail_count
        else:
            count = 0
        start = (page - 1) * page_size
        return {
            "ok": True,
            "payload": [{"Id": start + index + 1, "Name": f"row-{start + index + 1}"} for index in range(count)],
        }


class RestrictedBrandsTransport(FakeTransport):
    def get(self, path: str, query: dict[str, object]):
        self.calls.append((path, dict(query)))
        if path == "items/v2/brands":
            return {
                "ok": False,
                "http_status": 401,
                "status": "auth_failed",
                "message": "Metrc rejected the saved API keys.",
            }
        return {"ok": True, "http_status": 200, "payload": [{"Id": len(self.calls), "Name": path}]}


@pytest.fixture
def live_metrc(monkeypatch: pytest.MonkeyPatch):
    metrc = SimpleNamespace(
        state="MA",
        license_number="LIC-TEST",
        environment="sandbox",
        configured=True,
        status="connected",
        trusted_mapping=True,
        user_api_key="user-key",
        integrator_api_key="integrator-key",
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
    assert result["pagination"]["items"] == {
        "page_size": 20,
        "pages_loaded": 1,
        "records_loaded": 1,
        "truncated": False,
        "max_pages": 20,
    }
    assert result["verification_status"] == "complete"
    assert result["warnings"] == []


def test_items_live_read_keeps_verified_data_when_brands_are_restricted(monkeypatch: pytest.MonkeyPatch):
    metrc = SimpleNamespace(
        state="MA",
        license_number="LIC-TEST",
        environment="sandbox",
        configured=True,
        status="connected",
        trusted_mapping=True,
        user_api_key="user-key",
        integrator_api_key="integrator-key",
    )
    transport = RestrictedBrandsTransport()
    monkeypatch.setattr(location_settings, "_trusted_metrc", lambda *_args, **_kwargs: (None, metrc))
    monkeypatch.setattr(location_settings, "_transport", lambda _metrc: transport)

    result = location_settings.metrc_items(context=object(), engine=object(), settings=object())

    assert [path for path, _ in transport.calls] == [
        "items/v2/active",
        "items/v2/inactive",
        "items/v2/categories",
        "items/v2/brands",
        "unitsofmeasure/v2/active",
    ]
    assert len(result["items"]) == 1
    assert len(result["inactive_items"]) == 1
    assert len(result["categories"]) == 1
    assert len(result["units_of_measure"]) == 1
    assert result["brands"] == []
    assert result["verification_status"] == "partial"
    assert result["warnings"] == [{
        "resource": "brands",
        "label": "item brands",
        "status": "restricted",
        "provider_status": "auth_failed",
        "http_status": 401,
        "message": "Metrc did not authorize item brands for this facility or user. Other verified item data remains available.",
    }]
    assert result["pagination"]["brands"]["complete"] is False
    assert result["pagination"]["brands"]["failed_page"] == 1
    assert result["pagination"]["brands"]["http_status"] == 401


def test_master_data_paging_reaches_records_beyond_first_page():
    metrc = SimpleNamespace(license_number="LIC-TEST")
    transport = PagedFakeTransport(full_pages=1, tail_count=3)

    rows, page = location_settings._paged_provider_rows(
        transport,
        metrc,
        "items/v2/active",
        "active items",
    )

    assert len(rows) == 23
    assert [query["pageNumber"] for _, query in transport.calls] == [1, 2]
    assert all(query["pageSize"] == 20 for _, query in transport.calls)
    assert page["pages_loaded"] == 2
    assert page["records_loaded"] == 23
    assert page["truncated"] is False


def test_master_data_paging_has_a_hard_provider_call_bound():
    metrc = SimpleNamespace(license_number="LIC-TEST")
    transport = PagedFakeTransport(full_pages=20, tail_count=0)

    rows, page = location_settings._paged_provider_rows(
        transport,
        metrc,
        "locations/v2/active",
        "active locations",
        max_pages=2,
    )

    assert len(rows) == 40
    assert len(transport.calls) == 2
    assert page["max_pages"] == 2
    assert page["truncated"] is True


def test_initial_facility_reads_stay_within_metrc_page_limit(live_metrc):
    _, transport = live_metrc
    location_settings.metrc_rooms(context=object(), engine=object(), settings=object())
    location_settings.metrc_strains(context=object(), engine=object(), settings=object())
    assert transport.calls
    for _, query in transport.calls:
        assert query["licenseNumber"] == "LIC-TEST"
        if "pageSize" in query:
            assert 1 <= query["pageSize"] <= 20
            assert query["pageNumber"] == 1


def test_master_data_page_size_is_clamped_to_reviewed_metrc_v2_limit():
    metrc = SimpleNamespace(license_number="LIC-TEST")
    transport = PagedFakeTransport(full_pages=0, tail_count=1)

    rows, page = location_settings._paged_provider_rows(
        transport,
        metrc,
        "locations/v2/active",
        "active locations",
        page_size=50,
    )

    assert len(rows) == 1
    assert transport.calls == [
        ("locations/v2/active", {"licenseNumber": "LIC-TEST", "pageSize": 20, "pageNumber": 1})
    ]
    assert page["page_size"] == 20


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


def test_preview_accepts_documentation_verified_jurisdiction_but_never_dispatches_unpromoted_action(live_metrc):
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
    assert result["confirmation_id"] == ""
    assert result["confirmation_token"] == ""
    assert result["requires_human_confirmation"] is True


def test_ma_master_data_preview_promotes_exact_write_and_binds_confirmation(live_metrc):
    request = location_settings.MetrcActionPreview(
        operation_type="location_create",
        payload={"name": "Flower Room 2", "location_type_name": "Default", "unexpected": "drop"},
    )
    result = location_settings.metrc_action_preview(
        request=request,
        context=SimpleNamespace(role="admin"),
        engine=object(),
        settings=object(),
    )

    assert result["dispatch_enabled"] is True
    assert result["operation"]["dispatch_enabled"] is True
    assert result["operation"]["verification_status"] == "ma_sandbox_write_readback_promoted"
    assert result["provider_request"] == {
        "method": "POST",
        "path": "locations/v2/",
        "query": {"licenseNumber": "LIC-TEST"},
        "body": [{"Name": "Flower Room 2", "LocationTypeName": "Default"}],
    }
    assert result["confirmation_id"]
    assert len(result["confirmation_token"]) == 64
    assert "fresh exact by-ID readback" in result["message"]


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
        "reconciliation instead of blind retry",
    ):
        assert label in source
    assert "items.data.warnings.map" in source
    assert 'itemBrandsWarning ? "—" : items.data.brands.length' in source
    assert source.count("enabled: false") >= 7


def test_frontend_exposes_simple_master_data_actions_and_governed_confirmation():
    source = (ROOT / "frontend/src/pages/LocationSettingsPage.tsx").read_text(encoding="utf-8")
    for label in (
        "Create room",
        "Edit an existing room",
        "Create strain",
        "Edit an existing strain",
        "Create a Metrc item",
        "Edit an existing Metrc item",
        "Review Metrc change",
        "Business values to submit",
        "Confirm & submit to Metrc",
        "Compliance evidence details",
        "Verified in Metrc",
        "Clear / none",
    ):
        assert label in source
    for operation in (
        'operation_type: "location_create"',
        'operation_type: "location_update"',
        'operation_type: "strain_create"',
        'operation_type: "strain_update"',
        'operation_type: "item_create"',
        'operation_type: "item_update"',
    ):
        assert operation in source
    for explicit_clear in (
        "item_brand: brand.trim() || null",
        "strain: strain.trim() || null",
        "description: description.trim() || null",
    ):
        assert explicit_clear in source
    assert "/api/v1/location-settings/metrc-action-preview" in source
    assert "/api/v1/location-settings/metrc-action-execute" in source


def test_frontend_keeps_unpromoted_provider_actions_review_only():
    source = (ROOT / "frontend/src/pages/LocationSettingsPage.tsx").read_text(encoding="utf-8")
    for label in (
        "Review sublocation request",
        "Review brand request",
        "Review process request",
        "Review additive request",
        "Review driver request",
        "Review vehicle request",
        "Preview only",
    ):
        assert label in source
    for operation in (
        'operation_type: "brand_create"',
        'operation_type: "processing_job_type_create"',
        'operation_type: "additive_template_create"',
        'operation_type: "driver_create"',
        'operation_type: "vehicle_create"',
    ):
        assert operation in source
