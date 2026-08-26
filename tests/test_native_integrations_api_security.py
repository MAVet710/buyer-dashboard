from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_native_provider_credentials_are_admin_only_and_facility_scoped():
    source = read("backend/app/routers/native_integrations.py")
    assert 'ADMIN_ROLES = {"dev", "admin"}' in source
    assert 'scope_type="facility"' in source
    assert 'scope_key=_scope(context)' in source
    assert "context.organization_id" in source
    assert "context.facility_id" in source
    assert "_require_admin(context)" in source
    assert "confirm_production" in source


def test_metrc_dispatch_keeps_human_approval_boundary_and_no_generic_escape_hatch():
    actions = read("backend/app/routers/traceability_actions.py")
    dispatcher = read("services/traceability_dispatcher.py")
    native = read("services/metrc_native.py")
    assert "DISPATCH_ROLES" in actions
    assert "Supervisor, QA, Admin, or DEV" in actions
    assert 'tx.status != "queued"' in dispatcher
    assert 'tx.provider == "metrc"' in dispatcher
    assert 'tx.provider == "biotrack"' in dispatcher
    assert "no external request was sent" in dispatcher
    assert "not enabled for automatic dispatch" in native
    assert "packages/v2/finish" in native
    assert "packages/v2/adjust" in native


def test_external_printing_stays_service_account_authenticated():
    source = read("backend/app/routers/printing_external.py")
    assert "authenticate_service_account" in source
    assert "Authorization: Bearer" not in source or "_token" in source
    assert '"printing:read"' in source
    assert '"printing:write"' in source
    assert "_facility(engine, context, x_facility_id)" in source


def test_native_receiving_preview_never_mutates_inventory():
    source = read("backend/app/routers/native_integrations.py")
    assert '"mutation_performed": False' in source
    assert '"already_received"' in source
    assert '"new_packages"' in source
