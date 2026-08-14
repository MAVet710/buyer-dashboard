"""Fail-closed organization and facility checks for tenant-owned workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from services.workspace_navigation import (
    COMAN_WORKSPACE,
    COMMERCIAL_WORKSPACE,
    EXTRACTION_WORKSPACE,
)


FACILITY_SCOPED_WORKSPACES = frozenset(
    {COMAN_WORKSPACE, COMMERCIAL_WORKSPACE, EXTRACTION_WORKSPACE}
)


@dataclass(frozen=True)
class TenantContext:
    organization_id: str = ""
    organization_name: str = ""
    facility_id: str = ""
    facility_name: str = ""

    @property
    def complete(self) -> bool:
        return bool(self.organization_id and self.facility_id)


def resolve_tenant_context(state: Mapping[str, Any]) -> TenantContext:
    return TenantContext(
        organization_id=str(state.get("active_organization_id") or "").strip(),
        organization_name=str(state.get("active_organization_name") or "").strip(),
        facility_id=str(state.get("active_facility_id") or "").strip(),
        facility_name=str(state.get("active_facility_name") or "").strip(),
    )


def tenant_access_issue(workspace: str, context: TenantContext) -> str:
    """Return a user-facing blocker for a tenant-owned workspace, if any."""

    if workspace not in FACILITY_SCOPED_WORKSPACES:
        return ""
    if not context.organization_id:
        return "Select an organization before opening this workspace."
    if not context.facility_id:
        return "Select a facility before opening this workspace."
    return ""
