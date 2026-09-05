from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import Engine

from modules.data_hub_repository import DataHubRepository


DATASET_KEY = "metrc_permission_evidence"
DATASET_LABEL = "Metrc Permission Evidence"
CACHE_KEY = "_cache_metrc_permission_evidence"
FILENAME = "metrc_permission_evidence.json"


def normalize_permissions(value: Any) -> list[str]:
    """Return a stable, de-duplicated permission list without guessing semantics."""

    found: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, str):
            clean = node.strip()
            if clean:
                found.add(clean)
            return
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if isinstance(node, dict):
            for key, item in node.items():
                folded = str(key).strip().casefold()
                if isinstance(item, bool):
                    if item:
                        found.add(str(key).strip())
                elif folded in {"name", "permission", "permissionname", "displayname"} and isinstance(item, str):
                    visit(item)
                else:
                    visit(item)

    visit(value)
    return sorted(permission for permission in found if permission)


class MetrcPermissionEvidenceStore:
    """Persist non-secret Metrc permission introspection as optional audit evidence.

    Permission introspection is never a prerequisite for facility discovery, initial
    regulatory hydration, or normal provider reads. Metrc continues to enforce the
    authenticated user's permissions on every provider request. This store only
    captures explicit evidence when the employee permissions endpoint is available.
    """

    def __init__(self, engine: Engine):
        self.repository = DataHubRepository(engine)

    def persist(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        jurisdiction_code: str,
        environment: str,
        license_number: str,
        employee_license_number: str,
        permissions: Any,
    ) -> dict[str, Any]:
        normalized = normalize_permissions(permissions)
        observed_at = datetime.now(timezone.utc).isoformat()
        evidence = {
            "provider": "metrc",
            "evidence_type": "employee_permissions",
            "jurisdiction_code": str(jurisdiction_code or "").strip().upper(),
            "environment": str(environment or "").strip().casefold(),
            "license_number": str(license_number or "").strip(),
            "employee_license_number": str(employee_license_number or "").strip(),
            "permissions": normalized,
            "permission_count": len(normalized),
            "observed_at": observed_at,
            "authoritative_scope": "provider_reported_employee_permissions",
            "optional": True,
        }
        payload = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
        fingerprint = sha256(payload).hexdigest()
        row = self.repository.publish_source(
            organization_id=organization_id,
            facility_id=facility_id,
            dataset_key=DATASET_KEY,
            dataset_label=DATASET_LABEL,
            cache_key=CACHE_KEY,
            filename=FILENAME,
            fingerprint=fingerprint,
            payload=payload,
            inspection={
                "rows": len(normalized),
                "columns": len(evidence),
                "quality": "Provider evidence",
                "matches": {},
                "missing": [],
            },
            content_type="application/json",
            imported_by_user_id=actor,
            imported_by=actor,
            retain_versions=10,
        )
        return {
            "dataset_key": DATASET_KEY,
            "source_id": str(row.id),
            "permission_count": len(normalized),
            "observed_at": observed_at,
        }
