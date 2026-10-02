from pathlib import Path

import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.app.auth import get_authorization_engine, get_request_context
from backend.app.config import Settings, get_settings


ROOT = Path(__file__).resolve().parents[1]


def _context_client(settings: Settings) -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    api = FastAPI()
    api.dependency_overrides[get_settings] = lambda: settings
    api.dependency_overrides[get_authorization_engine] = lambda: engine

    @api.get("/probe")
    def probe(context=Depends(get_request_context)):
        return {"user_id": context.user_id, "role": context.role}

    return TestClient(api)


def test_production_rejects_legacy_developer_headers_without_authentication():
    settings = Settings(_env_file=None, app_env="production")
    with _context_client(settings) as client:
        response = client.get(
            "/probe",
            headers={
                "X-User-Id": "web-local-developer",
                "X-User-Role": "admin",
                "X-Organization-Id": "forged-org",
                "X-Facility-Id": "forged-facility",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token required."


def test_development_keeps_explicit_local_header_fallback_available():
    settings = Settings(_env_file=None, app_env="development")
    with _context_client(settings) as client:
        response = client.get(
            "/probe",
            headers={
                "X-User-Id": "local-regression-user",
                "X-User-Role": "admin",
                "X-Organization-Id": "local-org",
                "X-Facility-Id": "local-facility",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "local-regression-user",
        "role": "admin",
    }


def test_expired_production_token_fails_closed_even_with_privileged_headers():
    secret = "fixture-secret-that-is-long-enough-for-hs256-regression-tests"
    settings = Settings(
        _env_file=None,
        app_env="production",
        supabase_url="https://auth-regression.invalid",
        supabase_jwt_secret=secret,
    )
    token = jwt.encode(
        {
            "sub": "expired-user",
            "aud": settings.supabase_jwt_audience,
            "iss": "https://auth-regression.invalid/auth/v1",
            "iat": 1,
            "exp": 2,
        },
        secret,
        algorithm="HS256",
    )
    with _context_client(settings) as client:
        response = client.get(
            "/probe",
            headers={
                "Authorization": f"Bearer {token}",
                "X-User-Role": "dev",
                "X-Organization-Id": "forged-org",
                "X-Facility-Id": "forged-facility",
            },
        )

    assert response.status_code == 401


def test_frontend_production_fallback_is_dev_gated():
    source = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")
    assert (
        'token || trial || !import.meta.env.DEV'
        in source
    )
    assert (
        '"X-User-Id": "web-local-developer", "X-User-Role": "admin"'
        in source
    )


def test_logout_runs_before_react_and_clears_all_auth_storage():
    source = (ROOT / "frontend/src/main.tsx").read_text(encoding="utf-8")
    logout_start = source.index('if (/^\\/logout')
    react_start = source.index('const App = lazy(')
    assert logout_start < react_start

    assert 'localStorage.removeItem("buyer-dash-organization")' in source
    assert 'localStorage.removeItem("buyer-dash-facility")' in source
    assert 'localStorage.removeItem("buyer-dash-operation")' in source
    assert 'sessionStorage.removeItem("buyer-dash-pending-page")' in source
    assert 'sessionStorage.removeItem("buyer-dash-trial-token")' in source
    assert 'sessionStorage.removeItem("buyer-dash-trial-expires")' in source
    assert 'key.startsWith("sb-") && key.includes("-auth-token")' in source
    assert 'key.startsWith("supabase.auth.")' in source
    assert "clearAuthStorage(localStorage);" in source
    assert "clearAuthStorage(sessionStorage);" in source
    assert 'window.location.replace("/?signed_out=1")' in source


def test_every_signout_surface_uses_the_hard_logout_route():
    app_shell = (ROOT / "frontend/src/components/AppShell.tsx").read_text(encoding="utf-8")
    assert 'href="/logout"' in app_shell
    assert "auth.signOut" not in app_shell

    for relative in (
        "frontend/src/components/AuthGate.tsx",
        "frontend/src/components/LegalGate.tsx",
        "frontend/src/components/PasswordGate.tsx",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "auth.signOut" not in source
        assert 'window.location.replace("/logout")' in source


def test_logout_does_not_install_or_restore_any_privileged_identity():
    source = (ROOT / "frontend/src/main.tsx").read_text(encoding="utf-8")
    start = source.index('if (/^\\/logout')
    end = source.index("const App = lazy(")
    logout = source[start:end]
    assert "web-local-developer" not in logout
    assert '"X-User-Role"' not in logout
    assert '"god"' not in logout.casefold()
    assert "setSession" not in logout


def test_logout_cache_version_forces_clients_off_the_old_shell():
    worker = (ROOT / "frontend/public/service-worker.js").read_text(encoding="utf-8")
    assert 'const CACHE_VERSION = "doobielogic-shell-v3";' in worker
