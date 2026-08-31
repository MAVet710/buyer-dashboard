from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select

from backend.app.config import get_settings
from backend.app.database import get_engine
from backend.app.main import app
from modules.coman.models import AppUser, Base, Organization

ROOT = Path(__file__).resolve().parents[1]


def test_backend_health_endpoint_reports_runtime():
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "buyer-dash-api"


def test_backend_root_endpoint_reports_product_identity():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "DoobieLogic API"
    assert payload["docs"] == "/docs"


def test_settings_default_to_safe_web_runtime(monkeypatch):
    for key in ("COMAN_DATABASE_URL", "BUYER_DASH_ENV", "BUYER_DASH_AUTH_MODE", "BUYER_DASH_CORS_ORIGINS"):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.environment == "development"
    assert settings.auth_mode == "jwt"
    assert settings.cors_origins == ()
    get_settings.cache_clear()


def test_production_rejects_unsafe_auth_mode(monkeypatch):
    monkeypatch.setenv("BUYER_DASH_ENV", "production")
    monkeypatch.setenv("BUYER_DASH_AUTH_MODE", "dev_headers")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="dev_headers"):
        get_settings()
    get_settings.cache_clear()


def test_create_all_imports_complete_durable_schema(tmp_path):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'create-all.db').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    expected = {
        "coman_organizations",
        "coman_app_users",
        "coman_inventory_lots",
        "product_master_profiles",
        "extraction_runs",
        "production_run_outputs",
        "commercial_orders",
    }
    assert expected.issubset(tables)
    engine.dispose()


def test_get_engine_uses_configured_database_url(monkeypatch, tmp_path):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'configured.db').as_posix()}"
    monkeypatch.setenv("COMAN_DATABASE_URL", database_url)
    get_settings.cache_clear()
    engine = get_engine()
    assert str(engine.url) == database_url
    engine.dispose()
    get_settings.cache_clear()


def test_supabase_acl_hardening_covers_functions_and_future_app_objects():
    migration = (ROOT / "migrations/versions/0037_supabase_function_acl_hardening.py").read_text(encoding="utf-8")
    assert "REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC" in migration
    assert "REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM %I" in migration
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES" in migration
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES" in migration
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON FUNCTIONS" in migration
    assert "Public Data API must therefore also be disabled" in migration


def test_fresh_database_migrates_to_head_and_latest_revision_rolls_back(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'migration-gate.db').as_posix()}"
    monkeypatch.setenv("COMAN_DATABASE_URL", database_url)
    config = Config(str(ROOT / "alembic.ini"))

    command.upgrade(config, "head")
    engine = create_engine(database_url, future=True)
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0060_vertical_saleability"

    command.downgrade(config, "-1")
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0059_material_transformations"

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0060_vertical_saleability"
    engine.dispose()
