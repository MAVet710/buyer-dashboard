from __future__ import annotations

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

import backend.app.auth as auth
from backend.app.config import Settings
from modules.coman.models import AppUser, AppUserFacilityRole, Base, Facility, Organization


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        organization = Organization(id="org-1", name="DoobieLogic Test", slug="doobielogic-test", active=True)
        facility = Facility(
            id="facility-1",
            organization_id="org-1",
            name="Test Facility",
            code="TEST",
            active=True,
            retail_enabled=True,
            production_enabled=True,
        )
        user = AppUser(
            id="user-1",
            organization_id="org-1",
            username="operator",
            normalized_username="operator",
            display_name="Operator One",
            email="operator@example.com",
            password_hash="$2b$12$placeholder",
            role="operator",
            active=True,
            created_by="admin",
            updated_by="admin",
        )
        assignment = AppUserFacilityRole(
            user_id="user-1",
            organization_id="org-1",
            facility_id="facility-1",
            role="qa",
        )
        session.add_all((organization, facility, user, assignment))
        session.commit()
    return engine


def _request(path: str = "/api/v1/inventory/retail/packages") -> Request:
    return Request({"type": "http", "method": "GET", "path": path, "headers": []})


def _claims() -> dict:
    return {
        "sub": "supabase-user-1",
        "email": "operator@example.com",
        "app_metadata": {
            "app_user_id": "user-1",
            "organization_id": "org-1",
            "facility_id": "facility-1",
        },
    }


def _context(engine, monkeypatch):
    monkeypatch.setattr(auth, "_decode_token", lambda *_args, **_kwargs: _claims())
    return auth.get_request_context(
        request=_request(),
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-token"),
        settings=Settings(),
        organization_id="",
        facility_id="",
        development_user="",
        development_role="",
        data_mode="Uploads",
        trial_token="",
        engine=engine,
    )


def test_authenticated_request_authorization_uses_one_select(monkeypatch):
    engine = _engine()
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _count(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    context = _context(engine, monkeypatch)

    assert context.user_id == "user-1"
    assert context.organization_id == "org-1"
    assert context.facility_id == "facility-1"
    assert context.role == "qa"
    assert {"retail", "production"}.issubset(context.capabilities)
    assert len(statements) == 1
    normalized = statements[0].casefold()
    assert "app_users" in normalized
    assert "coman_facilities" in normalized
    assert "app_user_facility_roles" in normalized


def test_missing_assignment_still_fails_closed_in_one_select(monkeypatch):
    engine = _engine()
    with Session(engine) as session:
        assignment = session.scalar(select(AppUserFacilityRole).where(AppUserFacilityRole.user_id == "user-1"))
        session.delete(assignment)
        session.commit()

    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _count(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    try:
        _context(engine, monkeypatch)
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "This account is not assigned to the selected facility."
    else:
        raise AssertionError("Missing facility assignment must fail closed.")

    assert len(statements) == 1
