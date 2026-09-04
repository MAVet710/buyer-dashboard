from __future__ import annotations

import json

from modules.regulatory.metrc_resources import build_metrc_read_plan
from services.metrc_evaluation_lab import build_lab_evaluation_payload, execute_lab_evaluation_action
from services.metrc_evaluation_pagination import fetch_all_metrc_resource_pages
from services.metrc_evaluation_transfers import (
    execute_transfer_evaluation_read,
    execute_transfer_template_write,
)
from services.metrc_evaluation_workbook import (
    MA_NA_SHEETS,
    MA_WORKBOOK_TASKS,
    WORKBOOK_SHEETS,
    ma_workbook_plan,
)


LICENSE = "MP281234"
INTEGRATOR = "integrator-key"
USER = "user-key"


def test_ma_workbook_map_covers_all_22_sheets_and_47_applicable_task_rows():
    plan = ma_workbook_plan()
    assert plan["sheet_count"] == 22
    assert len(WORKBOOK_SHEETS) == 22
    assert plan["applicable_task_count"] == 47
    assert len(MA_WORKBOOK_TASKS) == 47
    assert [task.number for task in MA_WORKBOOK_TASKS] == list(range(1, 48))
    assert all(task.operation_type and task.current_endpoint and task.execution_kind for task in MA_WORKBOOK_TASKS)
    assert set(MA_NA_SHEETS) == {
        "Closed Loop Environment",
        "Closed Loop States PlantBatches",
        "CA ONLY Labs",
        "Sales with Patient Look Up",
        "CA- SalesRetailDeliveries",
        "Transfer External Incoming",
    }


def test_ma_workbook_preserves_template_and_transfer_legacy_labels_but_executes_current_v2_paths():
    by_number = {task.number: task for task in MA_WORKBOOK_TASKS}
    assert by_number[35].workbook_endpoint == "PUT /sales/v2/deliveries/complete"
    assert by_number[35].current_endpoint == "PUT /sales/v2/deliveries"
    assert by_number[41].workbook_endpoint == "GET /transfers/v2/delivery/{id}/packages"
    assert by_number[41].current_endpoint == "GET /transfers/v2/deliveries/{id}/packages"
    assert by_number[42].current_endpoint == "GET /transfers/v2/deliveries/{id}/packages/wholesale"
    assert by_number[45].workbook_endpoint == "GET /transfers/v2/templates"
    assert by_number[45].current_endpoint == "GET /transfers/v2/templates/outgoing"
    assert by_number[46].current_endpoint == "GET /transfers/v2/templates/outgoing/{id}/deliveries"


def test_evaluation_pagination_walks_every_reported_page():
    calls: list[int] = []

    def fake_fetch(**kwargs):
        page = kwargs["page_number"]
        calls.append(page)
        return {
            "ok": True,
            "http_status": 200,
            "payload": {"TotalPages": 3, "Data": [{"Id": page}]},
            "records": [{"provider_id": str(page), "source": {"Id": page}}],
            "correlation_id": f"page-{page}",
        }

    result = fetch_all_metrc_resource_pages(
        state="MA",
        user_api_key=USER,
        integrator_api_key=INTEGRATOR,
        resource="incoming_transfers",
        environment="sandbox",
        license_number=LICENSE,
        fetch_fn=fake_fetch,
    )
    assert result["passed"] is True
    assert result["page_count"] == 3
    assert result["total_pages"] == 3
    assert calls == [1, 2, 3]
    assert [row["provider_id"] for row in result["records"]] == ["1", "2", "3"]


def test_evaluation_pagination_fails_entire_read_when_later_page_fails():
    def fake_fetch(**kwargs):
        page = kwargs["page_number"]
        if page == 2:
            return {"ok": False, "http_status": 429, "status": "rate_limited", "message": "retry later"}
        return {
            "ok": True,
            "http_status": 200,
            "payload": {"TotalPages": 3, "Data": [{"Id": 1}]},
            "records": [{"provider_id": "1", "source": {"Id": 1}}],
        }

    result = fetch_all_metrc_resource_pages(
        state="MA",
        user_api_key=USER,
        integrator_api_key=INTEGRATOR,
        resource="incoming_transfers",
        environment="sandbox",
        license_number=LICENSE,
        fetch_fn=fake_fetch,
    )
    assert result["passed"] is False
    assert result["failed_page"] == 2
    assert result["page_count"] == 2


def test_current_template_delivery_read_plan_uses_outgoing_v2_path_and_pagination():
    plan = build_metrc_read_plan(
        jurisdiction="MA",
        resource="transfer_template_deliveries",
        environment="sandbox",
        path_parameters={"template_id": 123},
        page_number=4,
        page_size=20,
    )
    assert plan.path == "transfers/v2/templates/outgoing/123/deliveries"
    assert plan.params == {"pageSize": 20, "pageNumber": 4}


def test_lab_payload_is_bounded_to_reviewed_v2_record_schema():
    body = build_lab_evaluation_payload({
        "package_label": "1A4FF0100000000000000999",
        "result_date": "2026-09-04",
        "results": [{
            "lab_test_type_name": "THC",
            "quantity": 22.1,
            "passed": True,
            "notes": "evaluation",
            "unexpected": "drop-me",
        }],
        "unexpected": "drop-me",
    })
    assert body == [{
        "Label": "1A4FF0100000000000000999",
        "ResultDate": "2026-09-04",
        "Results": [{"LabTestTypeName": "THC", "Quantity": 22.1, "Passed": True, "Notes": "evaluation"}],
    }]


def test_lab_evaluation_requires_http_200_and_exact_paginated_package_test_readback():
    calls = []

    class Response:
        status_code = 200
        content = b"{}"
        text = "{}"
        def json(self):
            return {}

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return Response()

    def fake_paged(**kwargs):
        assert kwargs["resource"] == "lab_results"
        assert kwargs["query"] == {"packageId": "991"}
        return {
            "passed": True,
            "records": [{
                "provider_id": "1",
                "last_modified": "2026-09-04T12:00:00",
                "source": {
                    "Id": 1,
                    "PackageId": 991,
                    "PackageLabel": "1A4FF0100000000000000999",
                    "LabTestTypeName": "THC",
                },
            }],
            "page_count": 2,
            "total_pages": 2,
        }

    result = execute_lab_evaluation_action(
        operation_type="lab_test_record",
        payload={
            "package_id": 991,
            "package_label": "1A4FF0100000000000000999",
            "result_date": "2026-09-04",
            "results": [{"lab_test_type_name": "THC", "quantity": 22.1, "passed": True}],
        },
        license_number=LICENSE,
        integrator_api_key=INTEGRATOR,
        user_api_key=USER,
        request_fn=fake_request,
        paged_read_fn=fake_paged,
    )
    assert result["passed"] is True
    assert result["http_status"] == 200
    assert result["last_modified"] == "2026-09-04T12:00:00"
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/labtests/v2/record")


def test_transfer_template_deliveries_executor_uses_current_resource_and_all_page_helper():
    captured = {}

    def fake_paged(**kwargs):
        captured.update(kwargs)
        return {"passed": True, "records": [{"provider_id": "88"}], "page_count": 4, "total_pages": 4}

    result = execute_transfer_evaluation_read(
        operation_type="transfer_template_deliveries",
        payload={"template_id": 123},
        license_number=LICENSE,
        integrator_api_key=INTEGRATOR,
        user_api_key=USER,
        paged_read_fn=fake_paged,
    )
    assert result["passed"] is True
    assert result["page_count"] == 4
    assert captured["resource"] == "transfer_template_deliveries"
    assert captured["path_parameters"] == {"template_id": "123"}


def test_transfer_template_update_uses_current_put_path_and_exact_id_readback():
    calls = []

    class Response:
        status_code = 200
        content = b"{}"
        text = "{}"
        def json(self):
            return {}

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return Response()

    def fake_paged(**kwargs):
        assert kwargs["resource"] == "transfer_templates_outgoing"
        assert kwargs["query"] == {
            "lastModifiedStart": "2026-09-04T00:00:00",
            "lastModifiedEnd": "2026-09-05T00:00:00",
        }
        return {
            "passed": True,
            "page_count": 3,
            "total_pages": 3,
            "records": [{
                "provider_id": "123",
                "name": "Template A Updated",
                "last_modified": "2026-09-04T13:00:00",
                "source": {"Id": 123, "Name": "Template A Updated"},
            }],
        }

    payload = {
        "transfer_template_id": 123,
        "last_modified_start": "2026-09-04T00:00:00",
        "last_modified_end": "2026-09-05T00:00:00",
        "template": {
            "TransferTemplateId": 123,
            "Name": "Template A Updated",
            "Destinations": [{
                "TransferDestinationId": 456,
                "RecipientLicenseNumber": "MR281111",
                "TransferTypeName": "Transfer",
                "PlannedRoute": "Licensed route",
                "EstimatedDepartureDateTime": "2026-09-04T09:00:00-04:00",
                "EstimatedArrivalDateTime": "2026-09-04T11:00:00-04:00",
                "Packages": [{"PackageLabel": "1A406030000MA00001"}],
            }],
        },
    }
    result = execute_transfer_template_write(
        operation_type="transfer_template_update",
        payload=payload,
        license_number=LICENSE,
        integrator_api_key=INTEGRATOR,
        user_api_key=USER,
        request_fn=fake_request,
        paged_read_fn=fake_paged,
    )
    assert result["passed"] is True
    assert result["provider_id"] == "123"
    assert calls[0][0] == "PUT"
    assert calls[0][1].endswith("/transfers/v2/templates/outgoing")
    sent = calls[0][2]["json"]
    assert sent[0]["TransferTemplateId"] == 123
    assert sent[0]["Destinations"][0]["TransferDestinationId"] == 456
    assert "unexpected" not in json.dumps(sent)
