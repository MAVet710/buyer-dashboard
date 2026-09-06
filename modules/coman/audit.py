"""Canonical operational audit envelope backed by the existing AuditEvent table.

The existing ``coman_audit_events`` table remains authoritative. New writers can
add structured provenance/correlation metadata while legacy readers continue to
see their familiar top-level ``changes_json`` keys.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from sqlalchemy.orm import Session

from modules.canonical_cannabis import canonical_entity_type

from .models import AuditEvent


AUDIT_ENVELOPE_KEY = "_event"
AUDIT_SCHEMA_VERSION = 1
AUDIT_SOURCES = frozenset(
    {
        "user",
        "api",
        "import",
        "system",
        "ai_agent",
        "rfid",
        "scanner",
        "provider",
        "provider_worker",
        "migration",
    }
)


def build_audit_payload(
    changes: Mapping[str, Any] | None = None,
    *,
    source: str = "user",
    reason: str = "",
    correlation_id: str = "",
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    provider: str = "",
    device: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a backward-compatible payload with structured event provenance."""

    source_key = str(source or "user").strip().casefold().replace("-", "_")
    if source_key not in AUDIT_SOURCES:
        raise ValueError(f"Unsupported audit source: {source}.")

    payload = dict(changes or {})
    envelope: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "source": source_key,
    }
    if reason:
        envelope["reason"] = str(reason).strip()
    if correlation_id:
        envelope["correlation_id"] = str(correlation_id).strip()
    if before is not None:
        envelope["before"] = dict(before)
    if after is not None:
        envelope["after"] = dict(after)
    if provider:
        envelope["provider"] = str(provider).strip().casefold()
    if device:
        envelope["device"] = dict(device)
    if metadata:
        envelope["metadata"] = dict(metadata)
    payload[AUDIT_ENVELOPE_KEY] = envelope
    return payload


def parse_audit_payload(raw: str | Mapping[str, Any] | None) -> dict[str, Any]:
    """Read both legacy flat payloads and the canonical structured envelope."""

    if isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        try:
            parsed = json.loads(str(raw or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = {}
        payload = dict(parsed) if isinstance(parsed, Mapping) else {}

    event = payload.get(AUDIT_ENVELOPE_KEY)
    if not isinstance(event, Mapping):
        payload[AUDIT_ENVELOPE_KEY] = {
            "schema_version": 0,
            "source": "system",
            "legacy": True,
        }
    return payload


def record_audit_event(
    session: Session,
    *,
    organization_id: str,
    facility_id: str | None,
    entity_type: str,
    entity_id: str,
    action: str,
    actor: str,
    changes: Mapping[str, Any] | None = None,
    source: str = "user",
    reason: str = "",
    correlation_id: str = "",
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    provider: str = "",
    device: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> AuditEvent:
    """Append one normalized event to the existing durable audit ledger."""

    clean_actor = str(actor or "").strip()
    clean_entity_id = str(entity_id or "").strip()
    clean_action = str(action or "").strip()
    if not clean_actor:
        raise ValueError("An actor is required for an audit event.")
    if not clean_entity_id:
        raise ValueError("An entity id is required for an audit event.")
    if not clean_action:
        raise ValueError("An action is required for an audit event.")

    payload = build_audit_payload(
        changes,
        source=source,
        reason=reason,
        correlation_id=correlation_id,
        before=before,
        after=after,
        provider=provider,
        device=device,
        metadata=metadata,
    )
    row = AuditEvent(
        organization_id=organization_id,
        facility_id=facility_id,
        entity_type=canonical_entity_type(entity_type),
        entity_id=clean_entity_id,
        action=clean_action,
        actor=clean_actor,
        changes_json=json.dumps(payload, sort_keys=True, default=str),
    )
    session.add(row)
    return row
