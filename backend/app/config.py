from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Buyer Dash API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173"
    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("COMAN_DATABASE_URL", "DATABASE_URL"),
    )
    supabase_jwt_secret: str = ""
    supabase_jwks_url: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    integration_encryption_key: str = ""
    metrc_integrator_key: str = ""
    allowed_hosts: str = "localhost,127.0.0.1,testserver"

    @property
    def allowed_origins(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]

    @property
    def is_development(self) -> bool:
        return self.app_env.casefold() in {"development", "dev", "test"}

    @property
    def trusted_hosts(self) -> list[str]:
        return [value.strip() for value in self.allowed_hosts.split(",") if value.strip()]

    def validate_production(self) -> None:
        if self.is_development:
            return
        missing = []
        if not self.database_url: missing.append("DATABASE_URL")
        if not (self.supabase_jwt_secret or self.supabase_jwks_url): missing.append("SUPABASE_JWKS_URL or SUPABASE_JWT_SECRET")
        if not self.supabase_url: missing.append("SUPABASE_URL")
        if not self.supabase_service_role_key: missing.append("SUPABASE_SERVICE_ROLE_KEY")
        if not self.integration_encryption_key: missing.append("INTEGRATION_ENCRYPTION_KEY")
        if not self.allowed_origins: missing.append("CORS_ORIGINS")
        if missing: raise RuntimeError(f"Production configuration is incomplete: {', '.join(missing)}")
        if "*" in self.allowed_origins or "*" in self.trusted_hosts: raise RuntimeError("Production CORS and trusted hosts cannot use wildcards.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
