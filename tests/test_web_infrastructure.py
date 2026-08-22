from pathlib import Path
from datetime import datetime, timedelta, timezone

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
import pytest
import jwt
from sqlalchemy import create_engine

from backend.app.config import Settings
from backend.app.auth import _decode_token

ROOT = Path(__file__).resolve().parents[1]


def production_settings(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "database_url": "postgresql+psycopg://example",
        "supabase_url": "https://project.supabase.co",
        "supabase_jwks_url": "https://project.supabase.co/auth/v1/.well-known/jwks.json",
        "supabase_service_role_key": "server-secret",
        "integration_encryption_key": "stable-secret",
        "cors_origins": "https://ops.doobielogic.io",
        "allowed_hosts": "api.doobielogic.io,*.run.app",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_configuration_fails_closed_when_secrets_are_missing():
    with pytest.raises(RuntimeError, match="Production configuration is incomplete"):
        Settings(app_env="production", cors_origins="https://ops.doobielogic.io", allowed_hosts="api.doobielogic.io").validate_production()


def test_production_configuration_rejects_wildcard_origins_and_hosts():
    production_settings().validate_production()
    with pytest.raises(RuntimeError, match="cannot use wildcards"):
        production_settings(cors_origins="*").validate_production()
    with pytest.raises(RuntimeError, match="cannot use wildcards"):
        production_settings(allowed_hosts="*").validate_production()


def test_supabase_tokens_require_the_configured_project_issuer():
    secret = "test-secret-with-at-least-thirty-two-bytes"
    settings = production_settings(supabase_jwks_url="", supabase_jwt_secret=secret)
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "user-1",
        "aud": "authenticated",
        "iss": "https://project.supabase.co/auth/v1",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    valid = jwt.encode(claims, secret, algorithm="HS256")
    assert _decode_token(valid, settings)["sub"] == "user-1"

    wrong_issuer = jwt.encode({**claims, "iss": "https://attacker.supabase.co/auth/v1"}, secret, algorithm="HS256")
    with pytest.raises(jwt.InvalidIssuerError):
        _decode_token(wrong_issuer, settings)

    missing_issuer = jwt.encode({key: value for key, value in claims.items() if key != "iss"}, secret, algorithm="HS256")
    with pytest.raises(jwt.MissingRequiredClaimError):
        _decode_token(missing_issuer, settings)


def test_deployment_artifacts_use_correct_io_domains_and_server_only_secrets():
    files = [ROOT / "deploy/cloudbuild-api.yaml", ROOT / "deploy/api.env.example", ROOT / "deploy/frontend.env.example", ROOT / "docs/PRODUCTION_DEPLOYMENT.md"]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    api_deployment = (ROOT / "deploy/cloudbuild-api.yaml").read_text(encoding="utf-8")
    assert "ops.doobielogic.io" in combined
    assert "api.doobielogic.io" in combined
    assert "ops.doobielogic.com" not in combined
    assert "api.doobielogic.com" not in combined
    assert "^@^APP_ENV=production@CORS_ORIGINS=https://ops.doobielogic.io@ALLOWED_HOSTS=" in api_deployment
    assert "^:^APP_ENV=" not in api_deployment
    assert "SUPABASE_SERVICE_ROLE_KEY" not in (ROOT / "deploy/frontend.env.example").read_text(encoding="utf-8")


def test_api_container_is_non_root_and_frontend_supports_spa_fallback():
    api = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")
    api_requirements = (ROOT / "backend/requirements.txt").read_text(encoding="utf-8")
    migration_build = (ROOT / "deploy/cloudbuild-migrate.yaml").read_text(encoding="utf-8")
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    assert "USER buyer" in api
    assert "--proxy-headers" in api
    assert "alembic>=" in api_requirements
    assert "- alembic" in migration_build
    assert "try_files $uri $uri/ /index.html" in nginx


def test_fastapi_routes_use_ui_independent_shared_modules():
    data_hub_router = (ROOT / "backend/app/routers/data_hub.py").read_text(encoding="utf-8")
    integrations_router = (ROOT / "backend/app/routers/integrations.py").read_text(encoding="utf-8")
    assert "modules.data_hub_core" in data_hub_router
    assert "modules.data_hub import" not in data_hub_router
    assert "services.doobie_connection" in integrations_router
    assert "services.doobie_config" not in integrations_router


def test_fresh_database_migrates_to_head_and_latest_revision_rolls_back(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'migration-gate.db').as_posix()}"
    monkeypatch.setenv("COMAN_DATABASE_URL", database_url)
    config = Config(str(ROOT / "alembic.ini"))

    command.upgrade(config, "head")
    engine = create_engine(database_url, future=True)
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0036_supabase_data_api_hardening"

    command.downgrade(config, "0035_facility_capabilities")
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0035_facility_capabilities"

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0036_supabase_data_api_hardening"
    engine.dispose()
