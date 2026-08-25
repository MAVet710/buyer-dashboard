"""Service-account authentication for DoobieLogic's external operational API."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import utc_now
from .models import ServiceAccount


@dataclass(frozen=True)
class ServiceAccountContext:
    id: str
    organization_id: str
    facility_id: str | None
    name: str
    scopes: frozenset[str]


def authenticate_service_account(engine: Engine, token: str, required_scope: str) -> ServiceAccountContext:
    raw = str(token or "").strip()
    if not raw.startswith("dla_") or len(raw) < 20:
        raise ValueError("Invalid service-account token.")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    with Session(engine) as session:
        row = session.scalar(select(ServiceAccount).where(ServiceAccount.token_hash == digest, ServiceAccount.active.is_(True)))
        if not row:
            raise ValueError("Invalid or disabled service-account token.")
        try:
            scopes = frozenset(str(value) for value in json.loads(row.scopes_json or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            scopes = frozenset()
        if required_scope not in scopes and "*" not in scopes:
            raise PermissionError(f"Service account does not include {required_scope} scope.")
        row.last_used_at = utc_now()
        session.commit()
        return ServiceAccountContext(id=row.id, organization_id=row.organization_id, facility_id=row.facility_id, name=row.name, scopes=scopes)
