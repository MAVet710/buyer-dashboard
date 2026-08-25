from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_sandbox_providers_are_first_class_and_schema_supported():
    service = _read("modules/integrations/service.py")
    model = _read("modules/integrations/models.py")
    migration = _read("migrations/versions/0042_sandbox_provider_connections.py")
    for provider in ("metrc_sandbox", "dutchie_sandbox", "biotrack_sandbox", "quickbooks_sandbox"):
        assert f'"{provider}"' in service
        assert f"'{provider}'" in model
        assert f"'{provider}'" in migration
    assert 'down_revision = "0041_integration_providers"' in migration


def test_sandbox_connections_are_facility_scoped_and_role_guarded():
    router = _read("backend/app/routers/sandbox_integrations.py")
    assert 'context.role not in {"dev", "admin"}' in router
    assert 'scope_type="facility"' in router
    assert 'f"{context.organization_id}:{context.facility_id}:sandbox"' in router
    assert '"production_credentials_enabled": False' in router
    assert '"environment": "sandbox"' in router


def test_readiness_check_never_claims_live_provider_connectivity():
    router = _read("backend/app/routers/sandbox_integrations.py")
    assert '"configuration_ready": True' in router
    assert '"connected": False' in router
    assert '"verified": False' in router
    assert "No live provider handshake was attempted" in router


def test_integrations_screen_exposes_sandbox_connection_panel():
    app = _read("frontend/src/App.tsx")
    panel = _read("frontend/src/components/DeveloperConnectionsPanel.tsx")
    assert "DeveloperConnectionsPanel" in app
    assert "<IntegrationsPage /><DeveloperConnectionsPanel />" in app
    for provider in ("metrc", "dutchie", "biotrack", "quickbooks"):
        assert f'{provider}:' in panel
    assert "SANDBOX ONLY" in panel
    assert "Production credentials are disabled here" in panel
