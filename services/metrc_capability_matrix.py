"""Operator-facing Metrc capability and module-health classification.

Metrc is the regulatory source of truth for state-tracked cannabis objects, but a
single facility license is not expected to expose every Metrc resource. This module
keeps provider transport diagnostics separate from the ERP/operator meaning of a
resource state.

A resource-specific 401/403 after an authenticated facility mapping has already been
proven is *not* evidence that the saved credential pair is globally invalid. Until an
explicit provider permission response can distinguish license capability from user
permission, that condition is rendered as ``restricted`` and remains fail-closed for
writes.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping


RESOURCE_AVAILABLE = "available"
RESOURCE_SYNCING = "syncing"
RESOURCE_RESTRICTED = "restricted"
RESOURCE_NOT_AVAILABLE = "not_available_for_license"
RESOURCE_DEGRADED = "degraded"
RESOURCE_FAILED = "failed"
RESOURCE_UNKNOWN = "unknown"


# These are ERP projection groups, not Metrc license guesses. A module is considered
# available when at least one of its provider resources is authorized for the current
# facility. Exact write capability remains separately governed by the write registry.
METRC_MODULE_RESOURCES: dict[str, tuple[str, ...]] = {
    "facility_setup": ("locations", "locations_inactive", "sublocations", "sublocations_inactive", "location_types"),
    "product_master": ("items", "items_inactive", "item_categories", "item_brands", "units_of_measure"),
    "inventory": ("packages", "package_tags", "items", "item_categories", "units_of_measure"),
    "cultivation": ("plant_batches", "plants_vegetative", "plants_flowering", "plant_tags", "strains", "harvests", "locations"),
    "post_harvest": ("harvests", "packages", "package_tags", "locations"),
    "receiving_wholesale": ("incoming_transfers", "outgoing_transfers", "rejected_transfers", "transfer_templates_outgoing", "transport_drivers", "transport_vehicles"),
    "sales": ("sales_receipts", "sales_deliveries", "packages"),
    "processing": ("processing_jobs", "processing_job_types", "processing_job_types_inactive", "processing_job_categories", "processing_job_attributes", "additive_templates", "additive_templates_inactive", "packages"),
}


_AUTH_REJECTION = re.compile(r"(?:http\s*)?(?:401|403)|permission|not\s+authorized|unauthori[sz]ed", re.IGNORECASE)
_RATE_OR_NETWORK = re.compile(r"(?:http\s*)?(?:429|5\d\d)|rate\s*limit|timeout|timed\s*out|connection|temporar", re.IGNORECASE)


@dataclass(frozen=True)
class ResourceCapability:
    resource: str
    capability: str
    operational_status: str
    reason: str
    retry_recommended: bool
    provider_status: str

    def public(self) -> dict[str, Any]:
        return {
            "resource": self.resource,
            "capability": self.capability,
            "operational_status": self.operational_status,
            "reason": self.reason,
            "retry_recommended": self.retry_recommended,
            "provider_status": self.provider_status,
        }


def classify_metrc_resource_state(
    state: Mapping[str, Any],
    *,
    authenticated_facility_access: bool,
) -> ResourceCapability:
    resource = str(state.get("resource") or "").strip()
    provider_status = str(state.get("status") or "idle").strip().casefold() or "idle"
    cursor = str(state.get("cursor") or "").strip().casefold()
    error = str(state.get("last_error") or "").strip()

    if cursor == "permission-skipped":
        return ResourceCapability(
            resource=resource,
            capability=RESOURCE_NOT_AVAILABLE,
            operational_status="healthy",
            reason="Metrc does not expose this resource to the selected facility/license scope.",
            retry_recommended=False,
            provider_status=provider_status,
        )
    if provider_status == "succeeded":
        return ResourceCapability(
            resource=resource,
            capability=RESOURCE_AVAILABLE,
            operational_status="healthy",
            reason="Authenticated Metrc read succeeded for this facility/license.",
            retry_recommended=False,
            provider_status=provider_status,
        )
    if provider_status == "running":
        return ResourceCapability(
            resource=resource,
            capability=RESOURCE_SYNCING,
            operational_status="syncing",
            reason="Metrc synchronization is in progress.",
            retry_recommended=False,
            provider_status=provider_status,
        )
    if provider_status in {"idle", ""}:
        return ResourceCapability(
            resource=resource,
            capability=RESOURCE_UNKNOWN,
            operational_status="pending",
            reason="This Metrc resource has not been proven for the selected facility/license yet.",
            retry_recommended=False,
            provider_status=provider_status,
        )
    if authenticated_facility_access and _AUTH_REJECTION.search(error):
        return ResourceCapability(
            resource=resource,
            capability=RESOURCE_RESTRICTED,
            operational_status="restricted",
            reason=(
                "The credential pair is authenticated for this facility, but Metrc rejected this specific resource. "
                "Treat it as license/user permission scope until explicit provider permissions prove otherwise."
            ),
            retry_recommended=False,
            provider_status=provider_status,
        )
    if _RATE_OR_NETWORK.search(error):
        return ResourceCapability(
            resource=resource,
            capability=RESOURCE_DEGRADED,
            operational_status="degraded",
            reason="The provider or network returned a transient condition; retry is appropriate.",
            retry_recommended=True,
            provider_status=provider_status,
        )
    return ResourceCapability(
        resource=resource,
        capability=RESOURCE_FAILED,
        operational_status="failed",
        reason=error or "Unexpected Metrc integration failure.",
        retry_recommended=True,
        provider_status=provider_status,
    )


def classify_metrc_resources(
    states: Iterable[Mapping[str, Any]],
    *,
    authenticated_facility_access: bool,
) -> list[dict[str, Any]]:
    return [
        classify_metrc_resource_state(
            state,
            authenticated_facility_access=authenticated_facility_access,
        ).public()
        for state in states
    ]


def summarize_metrc_modules(capabilities: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_resource = {
        str(row.get("resource") or ""): str(row.get("capability") or RESOURCE_UNKNOWN)
        for row in capabilities
    }
    modules: list[dict[str, Any]] = []
    for module, resources in METRC_MODULE_RESOURCES.items():
        states = [by_resource.get(resource, RESOURCE_UNKNOWN) for resource in resources]
        available = sum(state == RESOURCE_AVAILABLE for state in states)
        syncing = sum(state == RESOURCE_SYNCING for state in states)
        restricted = sum(state in {RESOURCE_RESTRICTED, RESOURCE_NOT_AVAILABLE} for state in states)
        actionable_failures = sum(state in {RESOURCE_FAILED, RESOURCE_DEGRADED} for state in states)
        unknown = sum(state == RESOURCE_UNKNOWN for state in states)

        if available:
            status = "degraded" if actionable_failures else "syncing" if syncing else "available"
        elif syncing:
            status = "syncing"
        elif restricted == len(resources):
            status = "not_available_for_license"
        elif actionable_failures:
            status = "failed"
        else:
            status = "pending"

        modules.append({
            "module": module,
            "status": status,
            "resource_count": len(resources),
            "available_resources": available,
            "restricted_resources": restricted,
            "failed_resources": actionable_failures,
            "pending_resources": unknown + syncing,
            "resources": list(resources),
        })
    return modules


def metrc_operator_summary(
    capabilities: Iterable[Mapping[str, Any]],
    modules: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    capability_rows = list(capabilities)
    module_rows = list(modules)
    available = sum(row.get("capability") == RESOURCE_AVAILABLE for row in capability_rows)
    restricted = sum(row.get("capability") in {RESOURCE_RESTRICTED, RESOURCE_NOT_AVAILABLE} for row in capability_rows)
    syncing = sum(row.get("capability") == RESOURCE_SYNCING for row in capability_rows)
    actionable_failures = sum(row.get("capability") in {RESOURCE_FAILED, RESOURCE_DEGRADED} for row in capability_rows)
    pending = sum(row.get("capability") == RESOURCE_UNKNOWN for row in capability_rows)
    return {
        "resource_count": len(capability_rows),
        "available_resources": available,
        "restricted_resources": restricted,
        "syncing_resources": syncing,
        "actionable_failures": actionable_failures,
        "pending_resources": pending,
        "available_modules": [row.get("module") for row in module_rows if row.get("status") == "available"],
        "degraded_modules": [row.get("module") for row in module_rows if row.get("status") in {"degraded", "failed"}],
        "restricted_modules": [row.get("module") for row in module_rows if row.get("status") == "not_available_for_license"],
        "healthy": actionable_failures == 0,
    }
