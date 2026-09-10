from modules.regulatory.metrc_resources import build_metrc_read_plan
from modules.regulatory.registry import get_jurisdiction, resolve_metrc_base_url
from backend.app.services.metrc_ma_current_lifecycle import MA_CURRENT_LIFECYCLE_ACTIONS
from services.metrc_evaluation_sales import SALES_EVALUATION_ACTIONS
from services.metrc_evaluation_transfers import TRANSFER_WRITE_EVALUATION_ACTIONS


def test_massachusetts_uses_verified_current_api_and_separate_sandbox_host():
    profile = get_jurisdiction("MA")
    assert profile is not None
    assert profile.api_base == "https://api-ma.metrc.com"
    assert profile.api_version_preference == "v2"
    assert profile.documentation_url == "https://api-ma.metrc.com/Documentation/"
    assert resolve_metrc_base_url("MA", environment="production") == ("https://api-ma.metrc.com", "MA")
    assert resolve_metrc_base_url("MA", environment="sandbox") == ("https://sandbox-api-ma.metrc.com", "MA")


def test_current_ma_sales_write_paths_match_documented_v2_surface():
    proficiency = {
        "sales_receipt_create": ("POST", "sales/v2/receipts"),
        "sales_receipt_update": ("PUT", "sales/v2/receipts"),
        "sales_receipt_delete": ("DELETE", "sales/v2/receipts/{id}"),
        "sales_delivery_create": ("POST", "sales/v2/deliveries"),
        "sales_delivery_update": ("PUT", "sales/v2/deliveries"),
        "sales_delivery_complete": ("PUT", "sales/v2/deliveries/complete"),
    }
    assert {name: (spec.method, spec.path) for name, spec in SALES_EVALUATION_ACTIONS.items()} == proficiency
    current_lifecycle = {
        name: (spec["method"], spec["path"])
        for name, spec in MA_CURRENT_LIFECYCLE_ACTIONS.items()
        if spec["domain"] == "sales"
    }
    assert current_lifecycle == {
        "sales_receipt_finalize": ("PUT", "sales/v2/receipts/finalize"),
        "sales_receipt_unfinalize": ("PUT", "sales/v2/receipts/unfinalize"),
        "sales_delivery_delete": ("DELETE", "sales/v2/deliveries/{id}"),
    }


def test_current_ma_transfer_api_promotes_templates_not_a_fake_direct_manifest_create():
    assert TRANSFER_WRITE_EVALUATION_ACTIONS == {
        "transfer_template_create": {"method": "POST", "path": "transfers/v2/templates/outgoing"},
        "transfer_template_update": {"method": "PUT", "path": "transfers/v2/templates/outgoing"},
    }
    assert {
        name: (spec["method"], spec["path"])
        for name, spec in MA_CURRENT_LIFECYCLE_ACTIONS.items()
        if spec["domain"] == "transfers"
    } == {
        "transfer_template_delete": ("DELETE", "transfers/v2/templates/outgoing/{id}"),
    }
    outgoing = build_metrc_read_plan(
        jurisdiction="MA",
        resource="outgoing_transfers",
        environment="sandbox",
        license_number="LIC-1",
    )
    incoming = build_metrc_read_plan(
        jurisdiction="MA",
        resource="incoming_transfers",
        environment="sandbox",
        license_number="LIC-1",
    )
    templates = build_metrc_read_plan(
        jurisdiction="MA",
        resource="transfer_templates_outgoing",
        environment="sandbox",
        license_number="LIC-1",
    )
    assert outgoing.path == "transfers/v2/outgoing"
    assert incoming.path == "transfers/v2/incoming"
    assert templates.path == "transfers/v2/templates/outgoing"
