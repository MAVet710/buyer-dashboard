from pathlib import Path

import pytest

from modules.integrations.accounting_links import AccountingSyncLink
from services.metrc_native import MetrcNativeError, validate_metrc_action
from services.quickbooks_client import QuickBooksError, quickbooks_api_request


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_native_integration_schema_has_one_accounting_link_ledger_and_signed_webhook_material():
    migration = read("migrations/versions/0045_native_integrations.py")
    assert 'revision = "0045_native_integrations"' in migration
    assert '"accounting_sync_links"' in migration
    assert "'customer','vendor','item','invoice','payment','purchase_order','bill'" in migration
    assert 'batch.add_column(sa.Column("encrypted_secret"' in migration
    assert 'batch.add_column(sa.Column("secret_hint"' in migration
    assert '"printer_profiles"' in migration
    assert '"label_print_jobs"' in migration
    assert AccountingSyncLink.__tablename__ == "accounting_sync_links"


def test_metrc_automatic_dispatch_is_explicit_and_validates_before_network():
    finish = validate_metrc_action(operation_type="package_finish", entity_id="1A400000000000000001", payload={})
    assert finish["operation"] == "package_finish"
    assert finish["body"][0]["Label"] == "1A400000000000000001"

    adjust = validate_metrc_action(
        operation_type="package_adjust",
        entity_id="1A400000000000000001",
        payload={"quantity_delta": -1, "unit": "Grams", "reason": "Waste"},
    )
    assert adjust["body"][0]["Quantity"] == -1.0

    with pytest.raises(MetrcNativeError, match="not enabled for automatic dispatch"):
        validate_metrc_action(operation_type="transfer_create", entity_id="transfer-1", payload={})


def test_quickbooks_client_rejects_unregistered_accounting_entities_before_network():
    with pytest.raises(QuickBooksError, match="not enabled for native sync"):
        quickbooks_api_request(
            access_token="not-used",
            realm_id="realm-1",
            environment="sandbox",
            entity="journalentry",
            payload={},
        )


def test_quickbooks_sync_is_idempotent_and_requires_item_mapping():
    source = read("services/quickbooks_sync.py")
    assert "payload_hash == payload_hash" in source
    assert "Synchronize the invoice customer to QuickBooks before posting this invoice." in source
    assert "QuickBooks Item mapping is required before invoice sync" in source
    assert 'entity_type="item"' in source
    assert 'entity="customer"' in source
    assert 'entity="invoice"' in source


def test_edge_printing_and_secure_webhook_compatibility_are_mounted():
    main = read("backend/app/main.py")
    printing = read("backend/app/routers/printing_external.py")
    webhooks = read("backend/app/routers/webhooks.py")

    assert "printing_external_router" in main
    assert "app.include_router(printing_external_router" in main
    assert '"printing:read"' in printing
    assert '"printing:write"' in printing

    secure_position = main.index("app.include_router(legacy_webhooks_router")
    old_position = main.index("app.include_router(control_tower_router")
    assert secure_position < old_position
    assert 'legacy_router = APIRouter(prefix="/control-tower/enterprise"' in webhooks
    assert "create_subscription" in webhooks
    assert "deprecated_route" in webhooks


def test_signed_webhooks_have_hmac_retry_and_dead_letter_contracts():
    source = read("modules/operational_moats/webhook_delivery.py")
    assert "hmac.new" in source
    assert "X-DoobieLogic-Signature" in source
    assert "MAX_ATTEMPTS = 5" in source
    assert 'delivery.status = "dead_letter"' in source
    assert "encrypted_secret" in source


def test_native_provider_ui_keeps_parity_and_adds_biotrack_quickbooks():
    source = read("frontend/src/pages/IntegrationsPage.tsx")
    for legacy in ("AI & METRC Integrations", "METRC Integrations", "METRC User API Key", "Doobie Service API Key"):
        assert legacy in source
    for native in ("State & Accounting Connections", "BioTrack", "QuickBooks Online", "Company Realm ID"):
        assert native in source
    assert 'apiGet<NativePayload>("/api/v1/native-integrations"' in source
    assert "/api/v1/native-integrations/biotrack" in source
    assert "/api/v1/native-integrations/quickbooks" in source
