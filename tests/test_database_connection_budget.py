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


def test_production_deploy_reserves_supabase_session_headroom():
    workflow = Path(".github/workflows/deploy.yml").read_text(encoding="utf-8")
    assert "API_MAX_INSTANCES: 3" in workflow
    assert "DATABASE_POOL_SIZE: 2" in workflow
    assert "SUPABASE_SESSION_LIMIT: 15" in workflow
    assert "SUPABASE_SESSION_HEADROOM: 3" in workflow
    assert "Verify Supabase session budget" in workflow
    assert "--max-instances \"${{ env.API_MAX_INSTANCES }}\"" in workflow
    assert "DATABASE_POOL_SIZE=${{ env.DATABASE_POOL_SIZE }}" in workflow
