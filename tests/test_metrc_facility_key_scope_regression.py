from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_doobie_dispatch_uses_resolved_facility_integrator_key() -> None:
    source = _read("backend/app/routers/doobie.py")

    assert source.count("metrc_integrator_api_key=metrc.integrator_api_key") >= 2
    assert "metrc_integrator_api_key=settings.metrc_integrator_key" not in source


def test_typed_traceability_dispatch_uses_resolved_facility_integrator_key() -> None:
    source = _read("backend/app/routers/traceability_actions.py")

    assert "resolve_metrc_context(engine, settings, context)" in source
    assert "metrc_integrator_api_key=metrc.integrator_api_key" in source
    assert "metrc_integrator_api_key=settings.metrc_integrator_key" not in source


def test_sandbox_context_fails_closed_when_vendor_scope_does_not_match() -> None:
    source = _read("backend/app/services/metrc_context.py")

    assert 'status="sandbox_vendor_scope_mismatch"' in source
    assert "if configured_environment != \"sandbox\" and not sandbox_matches:" in source
    assert "if not sandbox_matches or not str(sandbox_vendor_key or \"\").strip():" in source
    assert "integrator_api_key = str(sandbox_vendor_key).strip()" in source
    assert "if configured_environment == \"sandbox\" or sandbox_matches:" not in source


def test_context_documents_why_global_fallback_is_unsafe_for_bound_sandbox_user() -> None:
    source = _read("backend/app/services/metrc_context.py")

    assert "pair a valid user key with the wrong vendor key" in source
    assert "facility-scoped Metrc sandbox connection" in source
