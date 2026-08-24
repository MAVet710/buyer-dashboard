from pathlib import Path

from sqlalchemy import CheckConstraint

from modules.integrations.models import IntegrationConfiguration


ROOT = Path(__file__).resolve().parents[1]


def test_integration_provider_constraint_matches_supported_platform_integrations():
    provider_checks = [
        str(constraint.sqltext)
        for constraint in IntegrationConfiguration.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_integration_provider"
    ]
    assert len(provider_checks) == 1
    expression = provider_checks[0]
    for provider in ("metrc", "doobie", "ai_runtime", "spacemail"):
        assert provider in expression


def test_migration_expands_existing_provider_constraint_after_ai_runtime():
    source = (ROOT / "migrations/versions/0041_integration_provider_constraint.py").read_text(encoding="utf-8")
    assert 'revision = "0041_integration_providers"' in source
    assert 'down_revision = "0040_ai_runtime"' in source
    assert "DROP CONSTRAINT IF EXISTS ck_integration_provider" in source
    assert "provider in ('metrc','doobie','ai_runtime','spacemail')" in source
