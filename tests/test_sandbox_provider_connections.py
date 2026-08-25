from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_sandbox_providers_are_first_class_and_schema_supported():
    service = _read("modules/integrations/service.py")
    model = _read("modules/integrations/models.py")
    migration = _read("migrations/versions/0042_sandbox_provider_connections.py")
    sync_migration = _read("migrations/versions/0043_sandbox_sync.py")
    for provider in ("metrc_sandbox", "dutchie_sandbox", "biotrack_sandbox", "quickbooks_sandbox"):
        assert f'"{provider}"' in service
        assert f"'{provider}'" in model
        assert f"'{provider}'" in migration
        assert f"'{provider}'" in sync_migration
    assert 'revision = "0042_sandbox_providers"' in migration
    assert 'down_revision = "0041_integration_providers"' in migration
    assert 'revision = "0043_sandbox_sync"' in sync_migration
    assert 'down_revision = "0042_sandbox_providers"' in sync_migration


def test_sandbox_connections_are_facility_scoped_and_role_guarded():
    router = _read("backend/app/routers/sandbox_integrations.py")
    assert 'context.role not in {"dev", "admin"}' in router
    assert 'scope_type="facility"' in router
    assert 'f"{context.organization_id}:{context.facility_id}:sandbox"' in router
    assert '"production_credentials_enabled": False' in router
    assert '"production_writes_enabled": False' in router
    assert '"environment": "sandbox"' in router


def test_readiness_check_never_claims_live_provider_connectivity():
    router = _read("backend/app/routers/sandbox_integrations.py")
    assert '"configuration_ready": True' in router
    assert '"connected": False' in router
    assert '"verified": False' in router
    assert "No live provider handshake was attempted" in router


def test_sandbox_runtime_exposes_sync_retry_cursor_and_reconciliation_seams():
    router = _read("backend/app/routers/sandbox_integrations.py")
    runtime = _read("modules/integrations/sandbox_runtime.py")
    models = _read("modules/integrations/models.py")
    assert '@router.get("/{provider}/runtime")' in router
    assert '@router.post("/{provider}/sync")' in router
    assert '@router.post("/{provider}/retry")' in router
    assert "IntegrationSyncState" in models
    assert "IntegrationSyncRecord" in models
    assert "IntegrationSyncAttempt" in models
    assert "fingerprint" in runtime
    assert "cursor_before" in runtime and "cursor_after" in runtime
    assert "retry_failed" in runtime
    assert '"production_writes_enabled": False' in runtime


def test_integrations_screen_exposes_sandbox_connection_and_runtime_controls():
    app = _read("frontend/src/App.tsx")
    panel = _read("frontend/src/components/DeveloperConnectionsPanel.tsx")
    assert "DeveloperConnectionsPanel" in app
    assert "<IntegrationsPage /><DeveloperConnectionsPanel />" in app
    for provider in ("metrc", "dutchie", "biotrack", "quickbooks"):
        assert f'{provider}:' in panel
    assert "SANDBOX ONLY" in panel
    assert "Production credentials and production writes are disabled here" in panel
    assert "Run sandbox sync" in panel
    assert "Retry failed syncs" in panel
    assert "durable cursors, raw-record staging, normalization, dedupe, retry and reconciliation state" in panel


def test_steps_one_through_eight_are_documented_with_explicit_cutover_gate():
    documentation = _read("docs/SANDBOX_PROVIDER_RUNTIME.md")
    for number in range(1, 9):
        assert f"## Step {number}" in documentation
    assert "production writes remain disabled" in documentation
    assert "Sandbox credentials must never be reused as production credential rows" in documentation
