from __future__ import annotations

import pytest

from services import metrc_evaluation_master_data as subject


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.content = b"{}" if payload is not None else b""
        self.text = ""

    def json(self):
        return self._payload


def test_location_create_uses_only_reviewed_ma_sandbox_contract(monkeypatch):
    monkeypatch.setattr(subject, "resolve_metrc_base_url", lambda state, environment: ("https://sandbox-api-ma.metrc.com", "MA"))
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse(200, [{"Id": 101}])

    def readback(**kwargs):
        assert kwargs["resource"] == "locations_by_id"
        assert kwargs["path_parameters"] == {"id": "101"}
        return {"ok": True, "http_status": 200, "records": [{"provider_id": "101", "last_modified": "2026-09-03T21:00:00Z", "source": {"Id": 101}}]}

    result = subject.execute_master_data_evaluation_action(
        operation_type="location_create",
        payload={"name": "Evaluation Flower", "location_type_name": "Default", "unexpected": "drop"},
        license_number="LIC-TEST",
        integrator_api_key="vendor-key",
        user_api_key="user-key",
        request_fn=request,
        readback_fn=readback,
    )

    assert result["passed"] is True
    assert result["provider_id"] == "101"
    assert result["http_status"] == 200
    assert result["request"]["body"] == [{"Name": "Evaluation Flower", "LocationTypeName": "Default"}]
    assert calls[0][0:2] == ("POST", "https://sandbox-api-ma.metrc.com/locations/v2/")
    assert calls[0][2]["auth"] == ("vendor-key", "user-key")
    assert calls[0][2]["params"] == {"licenseNumber": "LIC-TEST"}


def test_update_readback_uses_payload_provider_id(monkeypatch):
    monkeypatch.setattr(subject, "resolve_metrc_base_url", lambda state, environment: ("https://sandbox-api-ma.metrc.com", "MA"))

    def readback(**kwargs):
        assert kwargs["resource"] == "strains_by_id"
        assert kwargs["path_parameters"] == {"id": "77"}
        return {"ok": True, "records": [{"provider_id": "77", "source": {"Id": 77}}]}

    result = subject.execute_master_data_evaluation_action(
        operation_type="strain_update",
        payload={"id": 77, "name": "GMO", "testing_status": "None", "thc_level": 25, "cbd_level": 0, "indica_percentage": 70, "sativa_percentage": 30},
        license_number="LIC-TEST",
        integrator_api_key="vendor-key",
        user_api_key="user-key",
        request_fn=lambda *args, **kwargs: FakeResponse(200, None),
        readback_fn=readback,
    )
    assert result["passed"] is True
    assert result["provider_id"] == "77"


def test_non_200_write_never_claims_evaluation_pass(monkeypatch):
    monkeypatch.setattr(subject, "resolve_metrc_base_url", lambda state, environment: ("https://sandbox-api-ma.metrc.com", "MA"))
    result = subject.execute_master_data_evaluation_action(
        operation_type="item_create",
        payload={"name": "GMO 3.5g", "item_category": "Buds", "unit_of_measure": "Each"},
        license_number="LIC-TEST",
        integrator_api_key="vendor-key",
        user_api_key="user-key",
        request_fn=lambda *args, **kwargs: FakeResponse(400, {"Message": "bad request"}),
        readback_fn=lambda **kwargs: pytest.fail("readback must not run after a failed write"),
    )
    assert result["passed"] is False
    assert result["stage"] == "write"
    assert result["http_status"] == 400


def test_runner_rejects_production_and_unknown_operations(monkeypatch):
    monkeypatch.setattr(subject, "resolve_metrc_base_url", lambda state, environment: ("https://api-ma.metrc.com", "MA"))
    with pytest.raises(subject.MetrcEvaluationError, match="restricted to the Metrc sandbox"):
        subject.execute_master_data_evaluation_action(
            operation_type="location_create",
            payload={"name": "Room", "location_type_name": "Default"},
            license_number="LIC",
            integrator_api_key="vendor",
            user_api_key="user",
            environment="production",
        )
    with pytest.raises(subject.MetrcEvaluationError, match="not enabled"):
        subject.execute_master_data_evaluation_action(
            operation_type="brand_create",
            payload={"name": "Brand"},
            license_number="LIC",
            integrator_api_key="vendor",
            user_api_key="user",
        )


def test_runner_rejects_reusing_same_credential_for_both_roles(monkeypatch):
    monkeypatch.setattr(subject, "resolve_metrc_base_url", lambda state, environment: ("https://sandbox-api-ma.metrc.com", "MA"))
    with pytest.raises(subject.MetrcEvaluationError, match="distinct credentials"):
        subject.execute_master_data_evaluation_action(
            operation_type="location_create",
            payload={"name": "Room", "location_type_name": "Default"},
            license_number="LIC",
            integrator_api_key="same",
            user_api_key="same",
        )
