from backend.app.config import Settings


def _production_settings(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "database_url": "postgresql+psycopg://example",
        "supabase_url": "https://project.supabase.co",
        "supabase_jwks_url": "https://project.supabase.co/auth/v1/.well-known/jwks.json",
        "supabase_publishable_key": "test-publishable",
        "integration_encryption_key": "stable-secret",
        "cors_origins": "https://ops.doobielogic.io",
    }
    values.update(overrides)
    return Settings(**values)


def test_default_trusted_hosts_cover_public_storefront_subdomains() -> None:
    settings = Settings()
    assert "doobielogic.io" in settings.trusted_hosts
    assert "*.doobielogic.io" in settings.trusted_hosts


def test_production_allows_scoped_doobielogic_subdomain_wildcard() -> None:
    settings = _production_settings(allowed_hosts="doobielogic.io,*.doobielogic.io,localhost,127.0.0.1")
    settings.validate_production()
