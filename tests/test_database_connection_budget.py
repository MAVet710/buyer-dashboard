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


def test_render_free_api_reserves_supabase_session_headroom():
    blueprint = Path("render.yaml").read_text(encoding="utf-8")
    api = blueprint.split("name: doobielogic-api-rc", 1)[1].split("name: doobielogic-web-prod", 1)[0]

    # The free API runs one Uvicorn worker and may open only one pooled database
    # connection. No overflow means a traffic spike queues instead of exhausting
    # the Supabase Free session budget.
    assert "plan: free" in api
    assert '- key: DATABASE_POOL_SIZE\n        value: "1"' in api
    assert '- key: DATABASE_MAX_OVERFLOW\n        value: "0"' in api
    assert '- key: DATABASE_POOL_TIMEOUT\n        value: "30"' in api
    assert "exec uvicorn backend.app.main:app" in api
    assert "--workers" not in api
    assert "autoDeployTrigger: checksPass" in api
