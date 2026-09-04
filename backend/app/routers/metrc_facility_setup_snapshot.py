from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from modules.regulatory.service import RegulatoryMappingService
from services.metrc_workspace_snapshot import MetrcWorkspaceSnapshotService
from ..auth import RequestContext, get_request_context, require_any_facility_capability
from ..database import get_engine


router = APIRouter()
FACILITY_CAPABILITIES = ("retail", "production", "cultivation", "commercial")
RESOURCES = (
    "locations",
    "locations_inactive",
    "sublocations",
    "sublocations_inactive",
    "location_types",
    "strains",
    "strains_inactive",
    "items",
    "items_inactive",
    "item_categories",
    "item_brands",
    "units_of_measure",
    "processing_job_types",
    "processing_job_types_inactive",
    "processing_job_attributes",
    "processing_job_categories",
    "additive_templates",
    "additive_templates_inactive",
    "transport_drivers",
    "transport_vehicles",
)
SECTION_RESOURCES = {
    "rooms": ("locations", "locations_inactive", "sublocations", "sublocations_inactive", "location_types"),
    "strains": ("strains", "strains_inactive"),
    "items": ("items", "items_inactive", "item_categories", "item_brands", "units_of_measure"),
    "production": ("processing_job_types", "processing_job_types_inactive", "processing_job_attributes", "processing_job_categories"),
    "cultivation": ("additive_templates", "additive_templates_inactive"),
    "transportation": ("transport_drivers", "transport_vehicles"),
}


def active_metrc_mapping(engine: Engine, context: RequestContext):
    mappings = [
        row
        for row in RegulatoryMappingService(engine).list_for_facility(context.organization_id, context.facility_id)
        if row.provider == "metrc" and row.active
    ]
    if not mappings:
        return None
    if len(mappings) > 1:
        raise HTTPException(
            409,
            "Multiple active Metrc mappings exist for this DoobieLogic facility. Resolve the facility/license mapping before using synchronized Facility Setup state.",
        )
    return mappings[0]


def _section_sync(resources: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for section, names in SECTION_RESOURCES.items():
        rows = [resources[name] for name in names]
        complete = [row for row in rows if row.get("complete")]
        skipped = [row for row in rows if row.get("status") == "permission_skipped"]
        output[section] = {
            "status": (
                "synced" if len(complete) == len(rows) else
                "permission-limited" if len(complete) + len(skipped) == len(rows) and skipped else
                "partial-sync" if complete else
                "not-synced"
            ),
            "complete_resource_count": len(complete),
            "requested_resource_count": len(rows),
            "permission_skipped_count": len(skipped),
            "complete": len(complete) == len(rows),
        }
    return output


def read_facility_setup_snapshot(*, context: RequestContext, engine: Engine) -> dict[str, Any]:
    mapping = active_metrc_mapping(engine, context)
    if mapping is None:
        return {
            "configured": False,
            "ready": False,
            "provider": "metrc",
            "source": "integration_provider_snapshots",
            "network_request_made": False,
            "message": "No verified Metrc facility mapping is active for this facility.",
            "resources": {},
            "summary": {},
            "sections": {},
        }

    snapshot = MetrcWorkspaceSnapshotService(engine).read(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        environment=mapping.environment,
        resources=RESOURCES,
    )
    resources = snapshot["resources"]
    sections = _section_sync(resources)
    summary = {
        "active_location_count": resources["locations"]["count"],
        "inactive_location_count": resources["locations_inactive"]["count"],
        "active_sublocation_count": resources["sublocations"]["count"],
        "inactive_sublocation_count": resources["sublocations_inactive"]["count"],
        "location_type_count": resources["location_types"]["count"],
        "active_strain_count": resources["strains"]["count"],
        "inactive_strain_count": resources["strains_inactive"]["count"],
        "active_item_count": resources["items"]["count"],
        "inactive_item_count": resources["items_inactive"]["count"],
        "item_category_count": resources["item_categories"]["count"],
        "item_brand_count": resources["item_brands"]["count"],
        "unit_of_measure_count": resources["units_of_measure"]["count"],
        "active_processing_job_type_count": resources["processing_job_types"]["count"],
        "inactive_processing_job_type_count": resources["processing_job_types_inactive"]["count"],
        "processing_job_attribute_count": resources["processing_job_attributes"]["count"],
        "processing_job_category_count": resources["processing_job_categories"]["count"],
        "active_additive_template_count": resources["additive_templates"]["count"],
        "inactive_additive_template_count": resources["additive_templates_inactive"]["count"],
        "transport_driver_count": resources["transport_drivers"]["count"],
        "transport_vehicle_count": resources["transport_vehicles"]["count"],
    }
    ready = snapshot["complete_resource_count"] > 0
    return {
        "configured": True,
        "ready": ready,
        "all_supported_complete": snapshot["all_complete"],
        "provider": "metrc",
        "jurisdiction_code": mapping.jurisdiction_code,
        "license_number": mapping.license_number,
        "environment": mapping.environment,
        "source": "integration_provider_snapshots",
        "network_request_made": False,
        "last_synced_at": snapshot.get("last_synced_at"),
        "message": (
            "Synchronized Metrc facility master data is available locally; no provider request was made."
            if ready
            else "This verified facility does not yet have a complete synchronized Facility Setup resource. Use the integration sync before relying on provider master data."
        ),
        "summary": summary,
        "sections": sections,
        "resources": resources,
    }


@router.get("/facility-setup-snapshot")
def facility_setup_snapshot(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    require_any_facility_capability(context, engine, FACILITY_CAPABILITIES)
    return read_facility_setup_snapshot(context=context, engine=engine)


def augment_facility_setup_overview(
    overview: dict[str, Any],
    *,
    context: RequestContext,
    engine: Engine,
) -> dict[str, Any]:
    """Add page-load synchronized provider visibility to the existing setup view."""

    snapshot = read_facility_setup_snapshot(context=context, engine=engine)
    output = dict(overview)
    output["sync_snapshot"] = snapshot
    if not snapshot.get("configured"):
        return output

    summary = snapshot.get("summary") or {}
    sync_sections = snapshot.get("sections") or {}
    last_synced = str(snapshot.get("last_synced_at") or "")
    freshness = f" Last synchronized {last_synced}." if last_synced else ""
    section_updates = {
        "rooms": {
            "label": f"Rooms & Locations · {summary.get('active_location_count', 0)} / {summary.get('active_sublocation_count', 0)}",
            "description": (
                f"Synchronized Metrc structure: {summary.get('active_location_count', 0)} active locations, "
                f"{summary.get('active_sublocation_count', 0)} sublocations, and {summary.get('location_type_count', 0)} location types."
                f"{freshness} Live refresh remains explicit."
            ),
        },
        "strains": {
            "label": f"Strains · {summary.get('active_strain_count', 0)}",
            "description": (
                f"Synchronized Metrc strain master: {summary.get('active_strain_count', 0)} active and "
                f"{summary.get('inactive_strain_count', 0)} inactive strains.{freshness}"
            ),
        },
        "items": {
            "label": f"Products & Metrc Items · {summary.get('active_item_count', 0)}",
            "description": (
                f"Synchronized Metrc master data includes {summary.get('active_item_count', 0)} active items, "
                f"{summary.get('inactive_item_count', 0)} inactive items, {summary.get('item_brand_count', 0)} brands, "
                f"{summary.get('item_category_count', 0)} categories, and {summary.get('unit_of_measure_count', 0)} units of measure.{freshness}"
            ),
        },
        "production": {
            "label": f"Production Processes · {summary.get('active_processing_job_type_count', 0)}",
            "description": (
                f"Synchronized Metrc Processing Job Types: {summary.get('active_processing_job_type_count', 0)} active, "
                f"{summary.get('inactive_processing_job_type_count', 0)} inactive, {summary.get('processing_job_category_count', 0)} categories, "
                f"and {summary.get('processing_job_attribute_count', 0)} attributes.{freshness}"
            ),
        },
        "cultivation": {
            "label": f"Cultivation Programs · {summary.get('active_additive_template_count', 0)}",
            "description": (
                f"Synchronized Metrc additive templates: {summary.get('active_additive_template_count', 0)} active and "
                f"{summary.get('inactive_additive_template_count', 0)} inactive.{freshness}"
            ),
        },
        "transportation": {
            "label": f"Transportation · {summary.get('transport_driver_count', 0)} / {summary.get('transport_vehicle_count', 0)}",
            "description": (
                f"Synchronized Metrc transportation reference: {summary.get('transport_driver_count', 0)} drivers and "
                f"{summary.get('transport_vehicle_count', 0)} vehicles.{freshness}"
            ),
        },
    }
    sections = []
    for source in output.get("sections", []):
        row = dict(source)
        key = str(row.get("key") or "")
        update = section_updates.get(key)
        if update:
            row.update(update)
            row["status"] = str((sync_sections.get(key) or {}).get("status") or "not-synced")
        sections.append(row)
    output["sections"] = sections

    metrc = dict(output.get("metrc") or {})
    metrc["synchronized_state"] = {
        "ready": bool(snapshot.get("ready")),
        "all_supported_complete": bool(snapshot.get("all_supported_complete")),
        "last_synced_at": snapshot.get("last_synced_at"),
        "source": "integration_provider_snapshots",
        "network_request_made": False,
        "summary": summary,
        "sections": sync_sections,
    }
    if snapshot.get("ready"):
        base_message = str(metrc.get("message") or "").strip()
        metrc["message"] = (
            f"{base_message} Synchronized facility structure is loaded locally; use the individual Refresh from Metrc controls only when you need a live verification."
        ).strip()
    output["metrc"] = metrc
    return output
