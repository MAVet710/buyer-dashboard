from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import AuditEvent
from .models import IntegrationConfiguration


class IntegrationConfigurationService:
    def __init__(self, engine: Engine, encryption_key: str):
        if not str(encryption_key or "").strip(): raise RuntimeError("Integration credential encryption is not configured.")
        digest = hashlib.sha256(str(encryption_key).encode()).digest(); self.cipher = Fernet(base64.urlsafe_b64encode(digest)); self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def get(self, scope_type: str, scope_key: str, provider: str) -> IntegrationConfiguration | None:
        with self.sessions() as session: return session.scalar(select(IntegrationConfiguration).where(IntegrationConfiguration.scope_type == scope_type, IntegrationConfiguration.scope_key == scope_key, IntegrationConfiguration.provider == provider))

    def save(self, *, scope_type: str, scope_key: str, provider: str, organization_id: str | None, facility_id: str | None, configuration: dict, secret: str | None, actor: str, audit_organization_id: str | None = None, audit_facility_id: str | None = None) -> IntegrationConfiguration:
        if scope_type not in {"user", "facility", "platform"} or provider not in {"metrc", "doobie"}: raise ValueError("Unsupported integration scope or provider.")
        if not (audit_organization_id or organization_id): raise ValueError("An audit organization is required for integration changes.")
        with self.sessions.begin() as session:
            row = session.scalar(select(IntegrationConfiguration).where(IntegrationConfiguration.scope_type == scope_type, IntegrationConfiguration.scope_key == scope_key, IntegrationConfiguration.provider == provider))
            if row is None:
                row = IntegrationConfiguration(scope_type=scope_type, scope_key=scope_key, provider=provider, organization_id=organization_id, facility_id=facility_id, updated_by=actor); session.add(row)
            row.organization_id = organization_id; row.facility_id = facility_id; row.configuration_json = json.dumps(configuration, sort_keys=True); row.updated_by = actor
            if secret is not None:
                clean = str(secret).strip(); row.encrypted_secret = self.cipher.encrypt(clean.encode()).decode() if clean else ""; row.secret_hint = f"••••{clean[-4:]}" if clean else ""
            row.status = "configured" if row.encrypted_secret else "not_connected"; row.last_error = ""; session.flush()
            session.add(AuditEvent(organization_id=audit_organization_id or organization_id, facility_id=audit_facility_id if audit_facility_id is not None else facility_id, entity_type="integration_configuration", entity_id=row.id, action="configuration_saved", actor=actor, changes_json=json.dumps({"provider": provider, "scope_type": scope_type, "configuration_keys": sorted(configuration), "secret_changed": secret is not None}, sort_keys=True)))
        return row

    def clear(self, *, scope_type: str, scope_key: str, provider: str, actor: str, audit_organization_id: str, audit_facility_id: str | None = None) -> None:
        """Clear one saved integration while retaining an auditable reset event."""
        with self.sessions.begin() as session:
            row = session.scalar(select(IntegrationConfiguration).where(IntegrationConfiguration.scope_type == scope_type, IntegrationConfiguration.scope_key == scope_key, IntegrationConfiguration.provider == provider))
            if row is not None:
                entity_id = row.id
                session.delete(row)
            else:
                entity_id = f"{scope_type}:{scope_key}:{provider}"
            session.add(AuditEvent(organization_id=audit_organization_id, facility_id=audit_facility_id, entity_type="integration_configuration", entity_id=entity_id, action="configuration_cleared", actor=actor, changes_json=json.dumps({"provider": provider, "scope_type": scope_type}, sort_keys=True)))

    def secret(self, row: IntegrationConfiguration) -> str:
        if not row.encrypted_secret: return ""
        try: return self.cipher.decrypt(row.encrypted_secret.encode()).decode()
        except InvalidToken as exc: raise RuntimeError("Stored integration credential cannot be decrypted with the active key.") from exc

    def validation_result(self, row_id: str, *, ok: bool, error: str = "") -> IntegrationConfiguration:
        with self.sessions.begin() as session:
            row = session.get(IntegrationConfiguration, row_id)
            if not row: raise ValueError("Integration configuration was not found.")
            row.status = "connected" if ok else "failed"; row.last_validated_at = datetime.now(timezone.utc); row.last_error = str(error or "")[:512]
        return row

    @staticmethod
    def public(row: IntegrationConfiguration | None) -> dict:
        if row is None: return {"configured": False, "status": "not_connected", "secret_hint": "", "configuration": {}, "last_validated_at": None, "last_error": ""}
        return {"configured": bool(row.encrypted_secret), "status": row.status, "secret_hint": row.secret_hint, "configuration": json.loads(row.configuration_json or "{}"), "last_validated_at": row.last_validated_at, "last_error": row.last_error}
