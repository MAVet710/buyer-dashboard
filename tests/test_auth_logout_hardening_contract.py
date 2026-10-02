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


def test_logout_synchronously_clears_workspace_trial_and_supabase_storage():
    source = (ROOT / "frontend/src/components/AppShell.tsx").read_text(
        encoding="utf-8"
    )

    assert 'localStorage.removeItem("buyer-dash-organization")' in source
    assert 'localStorage.removeItem("buyer-dash-facility")' in source
    assert 'sessionStorage.removeItem("buyer-dash-pending-page")' in source
    assert "clearTrialSession();" in source
    assert 'key?.startsWith("sb-") && key.endsWith("-auth-token")' in source
    assert 'supabase?.auth.signOut({ scope: "local" })' in source
    assert 'window.location.replace("/")' in source


def test_logout_does_not_install_or_restore_any_privileged_identity():
    source = (ROOT / "frontend/src/components/AppShell.tsx").read_text(
        encoding="utf-8"
    )
    logout = source[source.index("const signOut = () => {"):source.index(
        "\n\n  return <div className=\"app-shell\">"
    )]
    assert "web-local-developer" not in logout
    assert '"X-User-Role"' not in logout
    assert '"god"' not in logout.casefold()
    assert "setSession" not in logout
