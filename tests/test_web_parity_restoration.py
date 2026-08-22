from backend.app.routers.po_parity import POLine, POPdfRequest, _best_match, _pdf
from services.license_validation import validate_license_key
from services.trial_access import issue_trial_token, verify_trial_token


def test_trial_token_is_signed_scoped_and_expires():
    token, expires = issue_trial_token(
        secret="test-secret",
        organization_id="sandbox-org",
        facility_id="sandbox-facility",
        duration_seconds=300,
    )
    payload = verify_trial_token(token, secret="test-secret", now=expires - 1)
    assert payload is not None
    assert payload["organization_id"] == "sandbox-org"
    assert payload["facility_id"] == "sandbox-facility"
    assert payload["role"] == "trial"
    assert verify_trial_token(token, secret="wrong-secret", now=expires - 1) is None
    assert verify_trial_token(token, secret="test-secret", now=expires) is None


def test_trial_license_validation_is_ui_independent(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"valid": True, "plan": "trial", "features": ["retail"]}

    def fake_post(url, *, json, headers, timeout):
        captured.update(url=url, json=json, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr("services.license_validation.requests.post", fake_post)
    result = validate_license_key(
        "trial-key",
        base_url="https://doobie.example/",
        api_key="service-key",
    )
    assert result["ok"] is True
    assert result["valid"] is True
    assert result["payload"]["plan"] == "trial"
    assert captured["url"] == "https://doobie.example/api/v1/license/validate"
    assert captured["headers"]["Authorization"] == "Bearer service-key"
    assert captured["json"] == {"license_key": "trial-key"}


def test_po_inventory_cross_check_prefers_exact_sku_then_product_name():
    inventory = [
        {"sku": "SKU-100", "product_name": "Blue Dream Flower 3.5g", "packagesize": "3.5g", "onhandunits": 12},
        {"sku": "SKU-200", "product_name": "Blue Dream Pre Roll 1g", "packagesize": "1g", "onhandunits": 30},
    ]
    exact, exact_score, exact_reason = _best_match(
        POLine(sku="SKU-100", description="anything", quantity=1, price=1), inventory
    )
    assert exact["product_name"] == "Blue Dream Flower 3.5g"
    assert exact_score == 1.0
    assert exact_reason == "SKU exact match"

    fuzzy, score, _ = _best_match(
        POLine(description="Blue Dream Flower", size="3.5g", quantity=1, price=1), inventory
    )
    assert fuzzy["sku"] == "SKU-100"
    assert score >= 0.72


def test_po_pdf_keeps_original_financial_fields():
    payload = POPdfRequest(
        store_name="Buyer Dash Store",
        vendor_name="Example Vendor",
        vendor_license="LIC-123",
        po_number="PO-TEST-1",
        po_date="2026-08-22",
        terms="Net 30",
        tax_rate=6.25,
        discount=5,
        shipping=12,
        items=[POLine(sku="SKU-1", description="Example Product", strain="Hybrid", size="3.5g", quantity=10, price=20)],
    )
    pdf = _pdf(payload)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000
