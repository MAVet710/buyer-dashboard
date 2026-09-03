from __future__ import annotations

import json

import pytest

from services.metrc_evaluation_sales import (
    SALES_EVALUATION_ACTIONS,
    MetrcSalesEvaluationError,
    build_sales_evaluation_payload,
    execute_sales_evaluation_action,
)


EXPECTED = {
    "sales_receipt_create": ("POST", "sales/v2/receipts"),
    "sales_receipt_update": ("PUT", "sales/v2/receipts"),
    "sales_receipt_delete": ("DELETE", "sales/v2/receipts/{id}"),
    "sales_delivery_create": ("POST", "sales/v2/deliveries"),
    "sales_delivery_update": ("PUT", "sales/v2/deliveries"),
    "sales_delivery_complete": ("PUT", "sales/v2/deliveries/complete"),
}


def _transaction():
    return {
        "package_label": "PKG-EVAL-1",
        "quantity": 1.0,
        "unit_of_measure": "Each",
        "total_amount": 25.0,
        "sales_tax": "5.00",
    }


def test_sales_workbook_surface_has_exact_method_path_pairs():
    assert set(SALES_EVALUATION_ACTIONS) == set(EXPECTED)
    for operation, expected in EXPECTED.items():
        spec = SALES_EVALUATION_ACTIONS[operation]
        assert (spec.method, spec.path) == expected


def test_unknown_operation_cannot_be_used_as_generic_metrc_writer():
    with pytest.raises(MetrcSalesEvaluationError, match="not enabled"):
        build_sales_evaluation_payload("custom", {"path": "plants/v2/harvest", "method": "PUT"})


def test_receipt_create_is_bounded_to_current_v2_fields():
    body = build_sales_evaluation_payload(
        "sales_receipt_create",
        {
            "external_receipt_number": "DL-EVAL-001",
            "identification_method": "GovernmentIssued",
            "sales_customer_type": "Consumer",
            "sales_date_time": "2026-09-03T17:30:00",
            "transactions": [_transaction()],
            "unexpected": "drop-me",
        },
    )
    assert body == [{
        "SalesCustomerType": "Consumer",
        "SalesDateTime": "2026-09-03T17:30:00",
        "Transactions": [{
            "PackageLabel": "PKG-EVAL-1",
            "Quantity": 1.0,
            "UnitOfMeasure": "Each",
            "TotalAmount": 25.0,
            "SalesTax": "5.00",
        }],
        "ExternalReceiptNumber": "DL-EVAL-001",
        "IdentificationMethod": "GovernmentIssued",
    }]
    assert "unexpected" not in json.dumps(body)


def test_update_receipt_requires_and_forwards_provider_id():
    body = build_sales_evaluation_payload(
        "sales_receipt_update",
        {
            "id": 41,
            "sales_customer_type": "Consumer",
            "sales_date_time": "2026-09-03 17:31:00",
            "transactions": [_transaction()],
        },
    )
    assert body[0]["Id"] == 41


def test_metrc_local_sales_time_rejects_zulu_or_offsets():
    for timestamp in ("2026-09-03T17:30:00Z", "2026-09-03T17:30:00-04:00", "2026-09-03T21:30:00+0000"):
        with pytest.raises(MetrcSalesEvaluationError, match="facility-local time"):
            build_sales_evaluation_payload(
                "sales_receipt_create",
                {
                    "sales_customer_type": "Consumer",
                    "sales_date_time": timestamp,
                    "transactions": [_transaction()],
                },
            )


def test_delivery_create_preserves_transport_and_recipient_fields():
    body = build_sales_evaluation_payload(
        "sales_delivery_create",
        {
            "sales_customer_type": "Consumer",
            "sales_date_time": "2026-09-03T17:30:00",
            "estimated_departure_date_time": "2026-09-03T17:35:00",
            "estimated_arrival_date_time": "2026-09-03T18:00:00",
            "driver_name": "Evaluation Driver",
            "drivers_license_number": "TEST-LICENSE-NUMBER",
            "vehicle_make": "Test",
            "vehicle_model": "Vehicle",
            "vehicle_license_plate_number": "EVAL",
            "recipient_name": "Evaluation Recipient",
            "recipient_address_street1": "1 Test Way",
            "recipient_address_city": "Boston",
            "recipient_address_state": "MA",
            "recipient_address_postal_code": "02108",
            "recipient_zone_id": 3,
            "transactions": [_transaction()],
        },
    )
    row = body[0]
    assert row["DriverName"] == "Evaluation Driver"
    assert row["RecipientZoneId"] == 3
    assert row["Transactions"][0]["PackageLabel"] == "PKG-EVAL-1"


def test_delivery_complete_uses_accepted_and_returned_package_contract():
    body = build_sales_evaluation_payload(
        "sales_delivery_complete",
        {
            "id": 77,
            "actual_arrival_date_time": "2026-09-03T18:05:00",
            "payment_type": "Cash",
            "accepted_packages": ["PKG-A"],
            "returned_packages": [{
                "label": "PKG-B",
                "return_quantity_verified": 1,
                "return_reason": "Customer Rejected",
                "return_reason_note": "Evaluation return",
                "return_unit_of_measure": "Each",
            }],
        },
    )
    assert body == [{
        "Id": 77,
        "ActualArrivalDateTime": "2026-09-03T18:05:00",
        "PaymentType": "Cash",
        "AcceptedPackages": ["PKG-A"],
        "ReturnedPackages": [{
            "Label": "PKG-B",
            "ReturnQuantityVerified": 1,
            "ReturnReason": "Customer Rejected",
            "ReturnUnitOfMeasure": "Each",
            "ReturnReasonNote": "Evaluation return",
        }],
    }]


def test_delivery_complete_requires_package_disposition():
    with pytest.raises(MetrcSalesEvaluationError, match="accepted or returned"):
        build_sales_evaluation_payload(
            "sales_delivery_complete",
            {"id": 77, "actual_arrival_date_time": "2026-09-03T18:05:00", "payment_type": "Cash"},
        )


class FakeResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.content = b"" if payload is None else b"json"
        self.text = "" if payload is None else json.dumps(payload)

    def json(self):
        return self._payload


def _readback(provider_id: str, resource: str):
    def fn(**kwargs):
        assert kwargs["resource"] == resource
        assert kwargs["path_parameters"] == {"id": provider_id}
        return {
            "ok": True,
            "http_status": 200,
            "records": [{
                "provider_id": provider_id,
                "last_modified": "2026-09-03T22:00:00Z",
                "source": {"Id": int(provider_id)},
            }],
        }
    return fn


def test_receipt_create_requires_http_200_and_exact_readback_without_secret_evidence():
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse(200, {"Ids": [301]})

    evidence = execute_sales_evaluation_action(
        operation_type="sales_receipt_create",
        payload={
            "sales_customer_type": "Consumer",
            "sales_date_time": "2026-09-03T17:30:00",
            "transactions": [_transaction()],
        },
        license_number="TEST-LICENSE",
        integrator_api_key="vendor-runtime-placeholder",
        user_api_key="user-runtime-placeholder",
        request_fn=request,
        readback_fn=_readback("301", "sales_receipts_by_id"),
    )
    assert evidence["passed"] is True
    assert evidence["provider_id"] == "301"
    assert evidence["last_modified"] == "2026-09-03T22:00:00Z"
    assert calls[0][0] == "POST"
    assert calls[0][1] == "https://sandbox-api-ma.metrc.com/sales/v2/receipts"
    serialized = json.dumps(evidence)
    assert "vendor-runtime-placeholder" not in serialized
    assert "user-runtime-placeholder" not in serialized


def test_delivery_update_reads_back_the_input_provider_id():
    def request(method, url, **kwargs):
        assert method == "PUT"
        assert url.endswith("/sales/v2/deliveries")
        return FakeResponse(200, {"Ids": []})

    evidence = execute_sales_evaluation_action(
        operation_type="sales_delivery_update",
        payload={
            "id": 55,
            "sales_customer_type": "Consumer",
            "sales_date_time": "2026-09-03T17:30:00",
            "transactions": [_transaction()],
        },
        license_number="TEST-LICENSE",
        integrator_api_key="vendor-runtime-placeholder",
        user_api_key="user-runtime-placeholder",
        request_fn=request,
        readback_fn=_readback("55", "sales_deliveries_by_id"),
    )
    assert evidence["passed"] is True
    assert evidence["provider_id"] == "55"


def test_receipt_delete_formats_id_in_path_sends_no_json_and_accepts_archived_readback():
    captured = {}

    def request(method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return FakeResponse(200)

    evidence = execute_sales_evaluation_action(
        operation_type="sales_receipt_delete",
        payload={"id": 99},
        license_number="TEST-LICENSE",
        integrator_api_key="vendor-runtime-placeholder",
        user_api_key="user-runtime-placeholder",
        request_fn=request,
        readback_fn=_readback("99", "sales_receipts_by_id"),
    )
    assert evidence["passed"] is True
    assert captured["method"] == "DELETE"
    assert captured["url"].endswith("/sales/v2/receipts/99")
    assert "json" not in captured
    assert evidence["request"]["body"] is None


def test_non_200_never_becomes_proficiency_pass():
    evidence = execute_sales_evaluation_action(
        operation_type="sales_receipt_create",
        payload={
            "sales_customer_type": "Consumer",
            "sales_date_time": "2026-09-03T17:30:00",
            "transactions": [_transaction()],
        },
        license_number="TEST-LICENSE",
        integrator_api_key="vendor-runtime-placeholder",
        user_api_key="user-runtime-placeholder",
        request_fn=lambda *args, **kwargs: FakeResponse(201, {"Ids": [1]}),
        readback_fn=lambda **kwargs: pytest.fail("readback must not run after non-200"),
    )
    assert evidence["passed"] is False
    assert evidence["http_status"] == 201
    assert evidence["stage"] == "write"


def test_create_response_without_provider_id_does_not_fake_pass():
    evidence = execute_sales_evaluation_action(
        operation_type="sales_delivery_create",
        payload={
            "sales_customer_type": "Consumer",
            "sales_date_time": "2026-09-03T17:30:00",
            "transactions": [_transaction()],
        },
        license_number="TEST-LICENSE",
        integrator_api_key="vendor-runtime-placeholder",
        user_api_key="user-runtime-placeholder",
        request_fn=lambda *args, **kwargs: FakeResponse(200, {}),
        readback_fn=lambda **kwargs: pytest.fail("readback must not run without provider identity"),
    )
    assert evidence["passed"] is False
    assert evidence["stage"] == "readback_identity"


def test_production_sales_execution_is_blocked_before_dispatch():
    with pytest.raises(MetrcSalesEvaluationError, match="restricted to the Metrc sandbox"):
        execute_sales_evaluation_action(
            operation_type="sales_receipt_delete",
            payload={"id": 1},
            license_number="TEST-LICENSE",
            integrator_api_key="vendor-runtime-placeholder",
            user_api_key="user-runtime-placeholder",
            environment="production",
            request_fn=lambda *args, **kwargs: pytest.fail("must not dispatch"),
        )


def test_duplicate_credential_roles_fail_closed():
    with pytest.raises(MetrcSalesEvaluationError, match="must be distinct"):
        execute_sales_evaluation_action(
            operation_type="sales_receipt_delete",
            payload={"id": 1},
            license_number="TEST-LICENSE",
            integrator_api_key="same-placeholder",
            user_api_key="same-placeholder",
            request_fn=lambda *args, **kwargs: pytest.fail("must not dispatch"),
        )
