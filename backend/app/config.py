from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Buyer Dash API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173"
    database_url: str = Field(default="", validation_alias=AliasChoices("COMAN_DATABASE_URL", "DATABASE_URL"))
    supabase_jwt_secret: str = ""
    supabase_jwks_url: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    integration_encryption_key: str = ""
    metrc_integrator_key: str = ""
    allowed_hosts: str = "localhost,127.0.0.1,testserver"

    # Spacemail SMTP. The primary mailbox authenticates to SMTP while the
    # support alias is used as the visible sender. Keep the mailbox password in
    # a server-side secret only; it must never be exposed to the browser.
    spacemail_smtp_host: str = "mail.spacemail.com"
    spacemail_smtp_port: int = 465
    spacemail_smtp_username: str = "nelson@doobielogic.io"
    spacemail_smtp_password: str = ""
    spacemail_smtp_timeout_seconds: float = 12.0
    spacemail_from_email: str = "support@doobielogic.io"
    spacemail_from_name: str = "DoobieLogic Support"
    spacemail_support_email: str = "support@doobielogic.io"
    spacemail_help_email: str = "help@doobielogic.io"
    spacemail_info_email: str = "info@doobielogic.io"
    spacemail_login_url: str = "https://ops.doobielogic.io/"
    spacemail_welcome_email_enabled: bool = True

    # DoobieLogic AI Runtime. Inference services remain external to the API image.
    ai_provider_mode: str = "local_first"
    ai_provider_order: str = "local,gemini,openai,doobie"
    ai_allow_cloud_fallback: bool = True
    local_llm_base_url: str = ""
    local_llm_api_key: str = ""
    local_llm_model: str = ""
    local_llm_timeout_seconds: float = 30.0
    local_llm_max_tokens: int = 1400
    local_llm_temperature: float = 0.2
    local_embedding_base_url: str = ""
    local_embedding_api_key: str = ""
    local_embedding_model: str = ""
    local_embedding_timeout_seconds: float = 20.0
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    openai_api_key: str = ""
    openai_model: str = ""
    openai_base_url: str = "https://api.openai.com"
    doobie_ai_model: str = "doobie-cloud"
    ai_gemini_input_cost_per_million: float = 0.0
    ai_gemini_output_cost_per_million: float = 0.0
    ai_openai_input_cost_per_million: float = 0.0
    ai_openai_output_cost_per_million: float = 0.0

    @property
    def allowed_origins(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]

    @property
    def is_development(self) -> bool:
        return self.app_env.casefold() in {"development", "dev", "test"}

    @property
    def trusted_hosts(self) -> list[str]:
        return [value.strip() for value in self.allowed_hosts.split(",") if value.strip()]

    @property
    def provider_order(self) -> list[str]:
        values = [value.strip().casefold() for value in self.ai_provider_order.split(",") if value.strip()]
        if self.ai_provider_mode.casefold() == "local_only":
            return ["local"]
        return values or ["local", "gemini", "openai", "doobie"]

    @property
    def spacemail_is_configured(self) -> bool:
        return bool(
            self.spacemail_welcome_email_enabled
            and self.spacemail_smtp_host.strip()
            and self.spacemail_smtp_username.strip()
            and self.spacemail_smtp_password
            and self.spacemail_from_email.strip()
        )

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
