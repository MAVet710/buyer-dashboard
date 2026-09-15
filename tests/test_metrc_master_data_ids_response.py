from __future__ import annotations

from services import metrc_evaluation_master_data as subject


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.content = b"{}" if payload is not None else b""
        self.text = ""

    def json(self):
        return self._payload


def test_master_data_create_accepts_metrc_v2_ids_wrapper(monkeypatch):
    monkeypatch.setattr(
        subject,
        "resolve_metrc_base_url",
        lambda state, environment: ("https://sandbox-api-ma.metrc.com", "MA"),
    )

    def readback(**kwargs):
        assert kwargs["resource"] == "strains_by_id"
        assert kwargs["path_parameters"] == {"id": "14301"}
        return {
            "ok": True,
            "http_status": 200,
            "records": [{
                "provider_id": "14301",
                "source": {"Id": 14301, "Name": "DL-EVAL-Strain"},
            }],
        }

    result = subject.execute_master_data_evaluation_action(
        operation_type="strain_create",
        payload={
            "name": "DL-EVAL-Strain",
            "testing_status": "None",
            "thc_level": 24.1,
            "cbd_level": 0.2,
            "indica_percentage": 70,
            "sativa_percentage": 30,
        },
        license_number="LIC-TEST",
        integrator_api_key="vendor-key",
        user_api_key="user-key",
        request_fn=lambda *args, **kwargs: FakeResponse(200, {"Ids": [14301], "Warnings": None}),
        readback_fn=readback,
    )

    assert result["passed"] is True
    assert result["stage"] == "complete"
    assert result["provider_id"] == "14301"
