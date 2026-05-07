from user_integrations_store import UserIntegrationsStore


def test_admin_can_create_user_with_password_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_INTEGRATIONS_DB_PATH", str(tmp_path / "users.db"))
    store = UserIntegrationsStore()
    assert store.available
    ok = store.save_user_integrations(
        username="new_user",
        is_admin=False,
        values={"password_hash": "$2b$12$examplehash", "user_status": "active", "email": "a@b.com"},
    )
    assert ok is True
    record = store.get_user("new_user")
    assert record is not None
    assert record.password_hash.startswith("$2")


def test_existing_admin_flag_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_INTEGRATIONS_DB_PATH", str(tmp_path / "admins.db"))
    store = UserIntegrationsStore()
    store.ensure_user("admin_1", is_admin=True)
    rec = store.get_user("admin_1")
    assert rec is not None
    assert rec.is_admin is True
