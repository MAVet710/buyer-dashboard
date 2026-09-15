from pathlib import Path
import subprocess
import sys

from scripts.run_local_metrc_execution_precheck import _healthy


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_local_doobielogic_runtime_distinguishes_app_compute_from_supabase_authority() -> None:
    vite = _read("frontend/vite.config.ts")
    env_example = _read("frontend/.env.example")
    diagnostic = _read("scripts/diagnose_local_username_login.py")
    api_env = _read("deploy/api.env.example")
    frontend_prod_env = _read("deploy/frontend.env.example")

    assert '127.0.0.1:8010' in vite
    assert '127.0.0.1:8080' not in vite
    assert 'localhost:8000' not in vite
    assert 'VITE_API_URL=http://127.0.0.1:8010' in env_example
    assert 'DEFAULT_LOCAL_API_URL = "http://127.0.0.1:8010"' in diagnostic
    assert 'EXPECTED_SUPABASE_URL = "https://fovxtygwcxubjzjgovva.supabase.co"' in diagnostic
    assert '"caddy_url": "http://127.0.0.1:8080"' in diagnostic
    assert '"fastapi_url": "http://127.0.0.1:8010"' in diagnostic
    assert '"supabase_auth_authority": EXPECTED_SUPABASE_URL' in diagnostic
    assert 'SUPABASE_URL=https://fovxtygwcxubjzjgovva.supabase.co' in api_env
    assert 'SUPABASE_JWKS_URL=https://fovxtygwcxubjzjgovva.supabase.co/auth/v1/.well-known/jwks.json' in api_env
    assert 'VITE_API_URL=' in frontend_prod_env
    assert 'VITE_SUPABASE_URL=https://fovxtygwcxubjzjgovva.supabase.co' in frontend_prod_env
    assert '127.0.0.1:54321' not in api_env


def test_windows_precheck_inherits_the_existing_pc_host_environment() -> None:
    wrapper = _read("scripts/run_local_metrc_execution_precheck.ps1")

    assert "start_local_authenticated.ps1" in wrapper
    assert ". $bootstrap" in wrapper
    assert ".pilot-venv/Scripts/python.exe" in wrapper
    assert "run_local_metrc_execution_precheck.py" in wrapper
    assert "$env:PYTHONPATH" in wrapper
    assert "METRC_INTEGRATOR_API_KEY" not in wrapper
    assert "METRC_USER_API_KEY" not in wrapper
    assert "integrator/setup" not in wrapper.casefold()


def test_precheck_script_can_be_invoked_by_file_path_from_repo_root() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_local_metrc_execution_precheck.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert "GET-only Massachusetts Metrc execution precheck" in completed.stdout
    assert "ModuleNotFoundError" not in completed.stderr


def test_local_evaluation_launcher_reuses_saved_trusted_credentials_without_printing_them() -> None:
    source = _read("scripts/run_local_ma_metrc_evaluation.py")

    assert "resolve_metrc_context" in source
    assert 'metrc.trusted_mapping' in source
    assert 'metrc.status.casefold() == "connected"' in source
    assert 'metrc.environment.casefold() == "sandbox"' in source
    assert 'metrc.state.upper() == "MA"' in source
    assert 'metrc.license_number == wanted' in source
    assert "--license-number" in source
    assert "I_APPROVE_MA_SANDBOX_WRITE" in source
    assert 'origin/main' in source
    assert 'child_env["METRC_INTEGRATOR_API_KEY"] = integrator_key' in source
    assert 'child_env["METRC_MA_SANDBOX_USER_API_KEY"] = user_key' in source
    assert 'child_env.pop("METRC_USER_API_KEY", None)' in source
    assert "integrator/setup" not in source.casefold()
    assert "print(integrator_key" not in source
    assert "print(user_key" not in source


def test_local_evaluation_launcher_can_be_invoked_by_file_path() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_local_ma_metrc_evaluation.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--license-number" in completed.stdout
    assert "--confirmation" in completed.stdout
    assert "ModuleNotFoundError" not in completed.stderr


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
