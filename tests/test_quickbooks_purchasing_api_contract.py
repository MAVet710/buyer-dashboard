from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_quickbooks_purchasing_router_is_explicitly_registered_at_app_composition():
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    router = (ROOT / "backend/app/routers/quickbooks_purchasing.py").read_text(encoding="utf-8")

    assert "from .routers.quickbooks_purchasing import router as quickbooks_purchasing_router" in main
    assert "app.include_router(quickbooks_purchasing_router, prefix=settings.api_prefix)" in main
    assert 'APIRouter(prefix="/native-integrations/quickbooks"' in router
    assert '@router.post("/vendors/{partner_id}/sync")' in router
    assert '@router.post("/purchase-orders/{order_id}/sync")' in router
    assert '@router.get("/reconciliation")' in router
    assert "_require_admin(context)" in router


def test_purchase_order_sync_keeps_human_confirmation_and_explicit_mapping_boundaries():
    source = (ROOT / "services/quickbooks_purchasing.py").read_text(encoding="utf-8")

    assert 'order.order_type != "purchase"' in source
    assert 'order.status not in {"confirmed", "fulfilled"}' in source
    assert "Confirm the purchase order in DoobieLogic before synchronizing it to QuickBooks." in source
    assert "Synchronize the purchase-order vendor to QuickBooks before posting this purchase order." in source
    assert "QuickBooks Item mapping is required before purchase-order sync" in source
    assert 'entity="purchaseorder"' in source
    assert 'entity_type="purchase_order"' in source
    assert 'entity="vendor"' in source
    assert 'entity_type="vendor"' in source


def test_reconciliation_is_explicitly_local_and_never_claims_remote_qbo_verification():
    source = (ROOT / "services/quickbooks_purchasing.py").read_text(encoding="utf-8")

    marker = "def reconciliation_snapshot"
    assert marker in source
    reconciliation = source[source.index(marker):]
    assert "quickbooks_api_request(" not in reconciliation
    assert '"read_only": True' in reconciliation
    assert "does not claim remote provider verification" in reconciliation
    assert '"awaiting_confirmation"' in reconciliation
    assert '"blocked_vendor_mapping"' in reconciliation
    assert '"blocked_item_mapping"' in reconciliation
    assert '"local_changes_pending"' in reconciliation
