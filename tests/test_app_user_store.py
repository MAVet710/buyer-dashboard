from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from modules.coman.models import Base
from services.app_user_store import AppUserStore


def _store() -> AppUserStore:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return AppUserStore(engine=engine)


def _hash(password: str) -> str:
    # Store validation only needs a syntactically bcrypt-shaped value. Actual
    # bcrypt verification is covered by the application's auth tests/runtime.
    return "$2b$12$" + (password.replace("-", "") + "x" * 53)[:53]


def test_admin_can_create_durable_user_without_plaintext_password():
    store = _store()
    user = store.create_user(
        username="production.user",
        password_hash=_hash("temporary-password"),
        role="operator",
        created_by="admin",
    )
    loaded = store.get_user("PRODUCTION.USER")
    assert loaded is not None
    assert loaded.id == user.id
    assert loaded.password_hash != "temporary-password"
    assert loaded.must_change_password is True


def test_duplicate_username_is_case_insensitive():
    store = _store()
    store.create_user(
        username="BuyerOne",
        password_hash=_hash("first-password"),
        role="buyer",
        created_by="admin",
    )
    with pytest.raises(ValueError, match="already exists"):
        store.create_user(
            username="buyerone",
            password_hash=_hash("second-password"),
            role="buyer",
            created_by="admin",
        )


def test_user_can_be_disabled_and_password_reset():
    store = _store()
    user = store.create_user(
        username="qa.user",
        password_hash=_hash("first-password"),
        role="qa",
        created_by="admin",
    )
    assert store.set_active(user.id, False, "admin") is True
    assert store.get_user("qa.user").active is False
    replacement = _hash("replacement-password")
    assert store.reset_password(user.id, replacement, "admin") is True
    assert store.get_user("qa.user").password_hash == replacement


def test_active_user_can_complete_required_password_change():
    store = _store()
    user = store.create_user(
        username="new.operator",
        password_hash=_hash("temporary-password"),
        role="operator",
        created_by="admin",
    )
    replacement = _hash("private-new-password")
    assert store.change_password(user.id, replacement) is True
    loaded = store.get_user("new.operator")
    assert loaded.password_hash == replacement
    assert loaded.must_change_password is False
