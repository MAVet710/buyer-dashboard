"""Real JWT lookup must not select a blank-email or conflicting user identity."""
import secrets
import time
from uuid import uuid4

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import get_authorization_engine, get_request_context
from backend.app.config import Settings, get_settings
from modules.coman.models import Base, Organization, Facility, AppUser, AppUserFacilityRole


@pytest.fixture
def identity_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[Organization.__table__, Facility.__table__,
                                           AppUser.__table__, AppUserFacilityRole.__table__])
    org, other, facility, reader, blank, conflicting = [str(uuid4()) for _ in range(6)]
    with Session(engine) as session, session.begin():
        session.add_all([Organization(id=org, name="Own", slug=org), Organization(id=other, name="Other", slug=other)])
        session.flush()
        session.add(Facility(id=facility, organization_id=org, name="Own", code="OWN", cultivation_enabled=True))
        # Unrelated privileged rows precede the correct identity deliberately.
        for uid, tenant, email, role in [(blank, other, "", "dev"),
                                         (conflicting, other, "other@example.test", "dev"),
                                         (reader, org, "reader@example.test", "read_only")]:
            session.add(AppUser(id=uid, organization_id=tenant, username=uid, normalized_username=uid,
                                email=email, role=role, password_hash="unusable-fixture", active=True, must_change_password=False))
        session.flush()
        session.add(AppUserFacilityRole(user_id=reader, organization_id=org, facility_id=facility, role="read_only"))
    secret = secrets.token_urlsafe(48)
    settings = Settings(_env_file=None, app_env="production", supabase_url="https://identity.example.test",
                        supabase_jwks_url="", supabase_jwt_secret=secret)
    api = FastAPI()
    api.dependency_overrides[get_settings] = lambda: settings
    api.dependency_overrides[get_authorization_engine] = lambda: engine
    @api.get("/identity")
    def identity(context=Depends(get_request_context)):
        return {"user_id": context.user_id, "role": context.role, "organization_id": context.organization_id}
    def headers(sub=reader, **extra):
        now = int(time.time())
        token = jwt.encode({"sub": sub, "iss": settings.supabase_url + "/auth/v1", "aud": "authenticated",
                            "iat": now, "exp": now + 300, **extra}, secret, algorithm="HS256")
        return {"Authorization": "Bearer " + token, "X-Organization-Id": org, "X-Facility-Id": facility, "X-User-Role": "dev"}
    with TestClient(api) as client:
        yield client, headers, engine, reader, org
    engine.dispose()


@pytest.mark.parametrize("claims", [{}, {"email": ""}, {"email": "other@example.test"}])
def test_exact_identity_precedes_email_matches(identity_client, claims):
    client, headers, engine, reader, org = identity_client
    result = client.get("/identity", headers=headers(**claims))
    assert result.status_code == 200
    assert result.json() == {"user_id": reader, "role": "read_only", "organization_id": org}


def test_unknown_identity_without_email_cannot_match_blank_account(identity_client):
    client, headers, *_ = identity_client
    assert client.get("/identity", headers=headers(sub=str(uuid4()))).status_code == 403


def test_inactive_exact_identity_cannot_fall_back_to_another_email(identity_client):
    client, headers, engine, reader, org = identity_client
    with Session(engine) as session, session.begin():
        session.get(AppUser, reader).active = False
    assert client.get("/identity", headers=headers(email="other@example.test")).status_code == 403


def test_existing_unique_legacy_email_link_remains_supported(identity_client):
    client, headers, engine, reader, org = identity_client
    result = client.get("/identity", headers=headers(sub=str(uuid4()), email="reader@example.test"))
    assert result.status_code == 200 and result.json()["user_id"] == reader


def test_ambiguous_legacy_email_never_selects_an_arbitrary_account(identity_client):
    client, headers, engine, reader, org = identity_client
    with Session(engine) as session, session.begin():
        uid = str(uuid4())
        session.add(AppUser(id=uid, organization_id=org, username=uid, normalized_username=uid,
                            email="reader@example.test", role="admin", password_hash="unusable-fixture",
                            active=True, must_change_password=False))
    assert client.get("/identity", headers=headers(sub=str(uuid4()), email="reader@example.test")).status_code == 403
    exact = client.get("/identity", headers=headers(email="reader@example.test"))
    assert exact.status_code == 200 and exact.json()["role"] == "read_only"
