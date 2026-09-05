from services import metrc_facility_bootstrap as bootstrap_module
from modules.regulatory.metrc_resources import METRC_V2_MAX_PAGE_SIZE
from services.metrc_facility_bootstrap import MetrcFacilityBootstrapService


def test_base_facility_bootstrap_uses_shared_metrc_v2_page_cap():
    assert METRC_V2_MAX_PAGE_SIZE == 20
    assert bootstrap_module.PAGE_SIZE == METRC_V2_MAX_PAGE_SIZE


def test_normalized_bootstrap_never_requests_more_than_metrc_v2_page_cap(monkeypatch):
    calls: list[dict] = []

    def fake_fetch(**kwargs):
        calls.append(dict(kwargs))
        page = int(kwargs["page_number"])
        return {
            "ok": True,
            "http_status": 200,
            "payload": {"Data": [{"Id": page}], "TotalPages": 3},
            "records": [{"provider_id": str(page), "source": {"Id": page}}],
        }

    monkeypatch.setattr(bootstrap_module, "fetch_metrc_resource", fake_fetch)

    result = object.__new__(MetrcFacilityBootstrapService)._fetch_all_normalized(
        resource="packages_active",
        state="MA",
        user_api_key="user",
        integrator_api_key="vendor",
        license_number="LIC-20",
        environment="sandbox",
    )

    assert [call["page_number"] for call in calls] == [1, 2, 3]
    assert all(call["page_size"] == METRC_V2_MAX_PAGE_SIZE for call in calls)
    assert result["page_count"] == 3
    assert result["truncated"] is False


def test_direct_paginated_bootstrap_never_requests_more_than_metrc_v2_page_cap():
    class Transport:
        def __init__(self):
            self.calls: list[tuple[str, dict]] = []

        def get(self, path, params):
            query = dict(params)
            self.calls.append((path, query))
            page = int(query["pageNumber"])
            return {
                "ok": True,
                "http_status": 200,
                "payload": {"Data": [{"Id": page}], "TotalPages": 2},
            }

    transport = Transport()
    result = MetrcFacilityBootstrapService._fetch_all_direct(
        transport=transport,
        path="items/v2/categories",
        params={"licenseNumber": "LIC-20"},
        paginated=True,
    )

    assert [query["pageNumber"] for _path, query in transport.calls] == [1, 2]
    assert all(query["pageSize"] == METRC_V2_MAX_PAGE_SIZE for _path, query in transport.calls)
    assert result["page_count"] == 2
    assert result["truncated"] is False


def test_direct_nonpaginated_bootstrap_does_not_inject_page_parameters():
    class Transport:
        def __init__(self):
            self.calls: list[tuple[str, dict]] = []

        def get(self, path, params):
            query = dict(params)
            self.calls.append((path, query))
            return {"ok": True, "http_status": 200, "payload": [{"Name": "Grams"}]}

    transport = Transport()
    result = MetrcFacilityBootstrapService._fetch_all_direct(
        transport=transport,
        path="unitsofmeasure/v2/active",
        params={},
        paginated=False,
    )

    assert transport.calls == [("unitsofmeasure/v2/active", {})]
    assert result["page_count"] == 1
    assert result["truncated"] is False
