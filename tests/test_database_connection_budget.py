from pathlib import Path

from backend.app import auth


def test_authorization_reuses_shared_database_engine(monkeypatch):
    sentinel = object()
    calls = 0

    def shared_engine():
        nonlocal calls
        calls += 1
        return sentinel

    monkeypatch.setattr(auth, "get_database_engine", shared_engine)

    assert auth.get_authorization_engine() is sentinel
    assert auth.get_authorization_engine() is sentinel
    assert calls == 2
    source = Path("backend/app/auth.py").read_text(encoding="utf-8")
    assert "create_coman_engine" not in source


def test_pc_hosted_api_keeps_supabase_connection_pool_bounded():
    source = Path("modules/coman/db.py").read_text(encoding="utf-8")

    assert 'options["pool_size"] = _int_setting("DATABASE_POOL_SIZE", 2, minimum=1)' in source
    assert 'options["max_overflow"] = _int_setting("DATABASE_MAX_OVERFLOW", 0, minimum=0)' in source
    assert 'options["pool_timeout"] = _int_setting("DATABASE_POOL_TIMEOUT", 30, minimum=1)' in source
    assert 'options["pool_use_lifo"] = True' in source
    assert 'options["pool_recycle"] = 300' in source
