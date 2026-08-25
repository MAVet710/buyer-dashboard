from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.database import get_engine
from backend.app.main import app
from backend.app.routers import account as account_router
from modules.coman.models import AppUser, Base

USER_ID = "11111111-1111-1111-1111-111111111111"


def _engine(*, include_user: bool = True, active: bool = True):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    if include_user:
        with Session(engine) as session, session.begin():
            session.add(
                AppUser(
                    id=USER_ID,
                    organization_id=None,
                    username="Jwinn",
                    normalized_username="jwinn",
                    display_name="LabWizzard",
                    email="linked-user@example.com",
                    password_hash="supabase-managed",
                    role="dev",
                    active=active,
                    must_change_password=True,
                    created_by="test",
                    updated_by="test",
                )
            )
    return engine


def test_username_login_resolves_case_insensitively_and_issues_linked_supabase_session(monkeypatch):
    engine = _engine()
    observed = {}

    def fake_password_session(settings, email: str, password: str):
        observed["email"] = email
        observed["password"] = password
        return {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "auth_user_id": USER_ID,
        }

    monkeypatch.setattr(account_router, "_supabase_password_session", fake_password_session)
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/account/username-login",
            json={"username": "  JWINN  ", "password": "temporary-password-123"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert response.json() == {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
    }
    assert observed == {
        "email": "linked-user@example.com",
        "password": "temporary-password-123",
    }
    with Session(engine) as session:
        user = session.get(AppUser, USER_ID)
        assert user is not None
        assert user.last_login_at is not None


def test_unknown_username_returns_generic_error_without_calling_supabase(monkeypatch):
    engine = _engine(include_user=False)

    def should_not_call(*args, **kwargs):
        raise AssertionError("Supabase should not be called for an unknown username")

    monkeypatch.setattr(account_router, "_supabase_password_session", should_not_call)
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/account/username-login",
            json={"username": "missing-user", "password": "temporary-password-123"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid login credentials."


def test_disabled_username_returns_same_generic_error(monkeypatch):
    engine = _engine(active=False)

    def should_not_call(*args, **kwargs):
        raise AssertionError("Supabase should not be called for a disabled username")

    monkeypatch.setattr(account_router, "_supabase_password_session", should_not_call)
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/account/username-login",
            json={"username": "Jwinn", "password": "temporary-password-123"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid login credentials."


def test_username_login_rejects_supabase_identity_mismatch(monkeypatch):
    engine = _engine()

    def mismatched_password_session(settings, email: str, password: str):
        return {
            "access_token": "wrong-access-token",
            "refresh_token": "wrong-refresh-token",
            "auth_user_id": "22222222-2222-2222-2222-222222222222",
        }

    monkeypatch.setattr(account_router, "_supabase_password_session", mismatched_password_session)
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/account/username-login",
            json={"username": "Jwinn", "password": "temporary-password-123"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "authentication link is out of sync" in response.json()["detail"]
