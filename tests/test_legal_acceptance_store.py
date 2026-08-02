from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

import pytest
from sqlalchemy import create_engine

from modules.coman.models import Base
from services.app_user_store import AppUserStore
from services.legal_acceptance_store import LegalAcceptanceStore, PolicyDocument


def _hash(password: str) -> str:
    return "$2b$12$" + (password.replace("-", "") + "x" * 53)[:53]


def _stores():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return AppUserStore(engine=engine), LegalAcceptanceStore(engine=engine)


def _policy(policy_type: str, version: str, text: str) -> PolicyDocument:
    return PolicyDocument(
        policy_type=policy_type,
        version=version,
        effective_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
        document_sha256=sha256(text.encode("utf-8")).hexdigest(),
        document_url=f"in-app://legal/{policy_type}",
    )


def _user(user_store: AppUserStore):
    return user_store.create_user(
        username="buyer.user",
        password_hash=_hash("temporary-password"),
        role="buyer",
        created_by="dev",
    )


def test_acceptance_is_durable_and_idempotent():
    user_store, acceptance_store = _stores()
    user = _user(user_store)
    terms = _policy("terms", "v1", "terms v1")
    privacy = _policy("privacy", "v1", "privacy v1")

    first = acceptance_store.record_acceptance(
        user_id=user.id,
        organization_id=None,
        terms=terms,
        privacy=privacy,
        statement_version="statement-v1",
    )
    second = acceptance_store.record_acceptance(
        user_id=user.id,
        organization_id=None,
        terms=terms,
        privacy=privacy,
        statement_version="statement-v1",
    )

    assert first.id == second.id
    assert acceptance_store.has_accepted(
        user_id=user.id,
        terms_version="v1",
        privacy_version="v1",
    )


def test_new_policy_version_requires_new_acceptance():
    user_store, acceptance_store = _stores()
    user = _user(user_store)
    acceptance_store.record_acceptance(
        user_id=user.id,
        organization_id=None,
        terms=_policy("terms", "v1", "terms v1"),
        privacy=_policy("privacy", "v1", "privacy v1"),
        statement_version="statement-v1",
    )

    assert not acceptance_store.has_accepted(
        user_id=user.id,
        terms_version="v2",
        privacy_version="v1",
    )


def test_published_policy_version_cannot_change_in_place():
    user_store, acceptance_store = _stores()
    first_user = _user(user_store)
    second_user = user_store.create_user(
        username="second.user",
        password_hash=_hash("temporary-password"),
        role="buyer",
        created_by="dev",
    )
    privacy = _policy("privacy", "v1", "privacy v1")
    acceptance_store.record_acceptance(
        user_id=first_user.id,
        organization_id=None,
        terms=_policy("terms", "v1", "original terms"),
        privacy=privacy,
        statement_version="statement-v1",
    )

    with pytest.raises(ValueError, match="cannot be changed"):
        acceptance_store.record_acceptance(
            user_id=second_user.id,
            organization_id=None,
            terms=_policy("terms", "v1", "modified terms"),
            privacy=privacy,
            statement_version="statement-v1",
        )


@pytest.mark.parametrize("method", ["silent", "assumed", "admin_override"])
def test_invalid_acceptance_methods_are_rejected(method):
    user_store, acceptance_store = _stores()
    user = _user(user_store)

    with pytest.raises(ValueError, match="Invalid acceptance method"):
        acceptance_store.record_acceptance(
            user_id=user.id,
            organization_id=None,
            terms=_policy("terms", "v1", "terms"),
            privacy=_policy("privacy", "v1", "privacy"),
            statement_version="statement-v1",
            acceptance_method=method,
        )


