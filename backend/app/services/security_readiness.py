"""Local configuration evidence only, without provider calls or secret values."""
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent
from modules.coman.permissions import AppUserPermissionOverride


def readiness_snapshot(context, engine, settings):
    controls = []

    def add(key, label, status, detail):
        controls.append(dict(key=key, label=label, status=status, detail=detail))

    auth_configured = bool(settings.supabase_url.strip() and settings.supabase_auth_api_key
                           and (settings.supabase_jwt_secret.strip() or settings.supabase_jwks_url.strip()))
    add("supabase_auth", "Supabase authentication", "configured" if auth_configured else "not_configured",
        "Server Auth URL, API key and JWT verification configuration are present." if auth_configured else
        "Server Auth URL, API key or JWT verification configuration is missing.")
    add("passwords", "Password requirements", "supported",
        "App account creation and password change require at least 12 characters. Provider password policy is not inspected.")
    add("sessions", "Session behavior", "supported",
        "Supabase tokens require expiry, audience, issuer and subject verification. Provider session lifetime, idle timeout and revocation settings are not inspected.")
    for key, label, model in (
        ("permission_overrides", "Facility permission overrides", AppUserPermissionOverride),
        ("audit_logging", "Operational audit logging", AuditEvent),
    ):
        try:
            with Session(engine) as session:
                observed = session.scalar(select(model.id).where(
                    model.organization_id == context.organization_id,
                    model.facility_id == context.facility_id,
                ).limit(1)) is not None
            add(key, label, "observed" if observed else "available",
                "Records observed in the active organization and facility." if observed else
                "Storage is available; no records observed in the active organization and facility.")
        except SQLAlchemyError:
            add(key, label, "unavailable", "Storage could not be verified. Check database connectivity and migrations.")
    add("integration_encryption", "Integration secret encryption",
        "configured" if settings.integration_encryption_key.strip() else "not_configured",
        "The integration service uses Fernet encryption when a server encryption key is configured. Existing ciphertext and key recovery are not verified here.")
    for key, label in (("mfa", "MFA enforcement"), ("sso", "Enterprise SSO"), ("scim", "SCIM provisioning")):
        add(key, label, "unsupported", "This app does not implement this control. Provider capabilities or settings are not evidence of app enforcement.")
    return {"organization_id": context.organization_id, "facility_id": context.facility_id,
            "scope": "Local configuration and scoped storage evidence, not a security certification or provider health check.",
            "controls": controls}
