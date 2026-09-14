from __future__ import annotations

from pathlib import Path

from backend.app.config import Settings


ROOT = Path(__file__).resolve().parents[1]


def test_backend_accepts_legacy_supabase_anon_key_for_normal_auth(monkeypatch) -> None:
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "legacy-local-client-key")
    settings = Settings(_env_file=None)
    assert settings.supabase_publishable_key == "legacy-local-client-key"
    assert settings.supabase_auth_api_key == "legacy-local-client-key"


def test_current_publishable_key_takes_precedence(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "current-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "legacy-key")
    settings = Settings(_env_file=None)
    assert settings.supabase_publishable_key == "current-key"


def test_frontend_accepts_current_or_legacy_normal_auth_key_without_service_role() -> None:
    source = (ROOT / "frontend/src/lib/supabase.ts").read_text(encoding="utf-8")
    assert "VITE_SUPABASE_PUBLISHABLE_KEY" in source
    assert "VITE_SUPABASE_ANON_KEY" in source
    assert "SERVICE_ROLE" not in source.upper()
