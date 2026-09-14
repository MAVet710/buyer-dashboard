from pathlib import Path

from scripts.run_local_metrc_execution_precheck import _healthy


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_local_doobielogic_runtime_uses_fastapi_8080_not_8000() -> None:
    vite = _read("frontend/vite.config.ts")
    env_example = _read("frontend/.env.example")
    diagnostic = _read("scripts/diagnose_local_username_login.py")
    policy = _read("docs/PROJECT_INVARIANTS.md")

    assert '127.0.0.1:8080' in vite
    assert 'localhost:8000' not in vite
    assert 'VITE_API_URL=http://127.0.0.1:8080' in env_example
    assert 'DEFAULT_LOCAL_API_URL = "http://127.0.0.1:8080"' in diagnostic
    assert '127.0.0.1:8080' in policy
    assert 'Cloudflare/Cloudflare Tunnel' in policy
    assert 'Port `8000` is not part of the active DoobieLogic application-hosting contract' in policy


def test_metrc_local_precheck_is_independent_from_doobielogic_login() -> None:
    source = _read("scripts/run_local_metrc_execution_precheck.py")

    assert 'scope": "metrc_evaluation_only"' in source
    assert 'doobielogic_login_checked": False' in source
    assert 'doobielogic_login_required_for_precheck": False' in source
    assert 'run_server_evaluation_rebaseline' in source
    assert 'run_server_resume_diagnostic' in source
    assert 'diagnose_local_username_login' in source  # documentation-only reference
    assert 'from scripts.diagnose_local_username_login import' not in source
    assert 'provider_mutations_sent": 0' in source
    assert 'metrc_credentials_changed": False' in source
    assert 'integrator_setup_called": False' in source
    assert '"transfer_types": True' in source
    assert '"outgoing_transfer_templates": True' in source
    assert '"incoming_outgoing_rejected_transfers": True' in source
    assert '"active_and_lab_packages": True' in source


def test_metrc_precheck_requires_fresh_facility_evidence() -> None:
    assert _healthy({"read_only": True, "mutations_sent": 0, "facility_count": 1}) is True
    assert _healthy({"read_only": True, "mutations_sent": 0, "facility_count": 0}) is False
    assert _healthy({"read_only": True, "mutations_sent": 0, "status": "already_completed"}) is False


def test_project_invariants_keep_god_and_metrc_strictly_separate() -> None:
    policy = _read("docs/PROJECT_INVARIANTS.md")

    assert "`God` is Nelson's DoobieLogic application username" in policy
    assert "unrelated to Metrc credentials" in policy
    assert "local Windows" in policy
