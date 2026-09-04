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
    "sublocations",
    "location_types",
    "strains",
    "items",
    "item_categories",
    "item_brands",
    "units_of_measure",
)


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
        }

    snapshot = MetrcWorkspaceSnapshotService(engine).read(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        environment=mapping.environment,
        resources=RESOURCES,
    )
    resources = snapshot["resources"]
    summary = {
        "active_location_count": resources["locations"]["count"],
        "active_sublocation_count": resources["sublocations"]["count"],
        "location_type_count": resources["location_types"]["count"],
        "active_strain_count": resources["strains"]["count"],
        "active_item_count": resources["items"]["count"],
        "item_category_count": resources["item_categories"]["count"],
        "item_brand_count": resources["item_brands"]["count"],
        "unit_of_measure_count": resources["units_of_measure"]["count"],
    }
    return {
        "configured": True,
        "ready": snapshot["all_complete"],
        "provider": "metrc",
        "jurisdiction_code": mapping.jurisdiction_code,
        "license_number": mapping.license_number,
        "environment": mapping.environment,
        "source": "integration_provider_snapshots",
        "network_request_made": False,
        "last_synced_at": snapshot.get("last_synced_at"),
        "message": (
            "Synchronized Metrc facility master data is available locally; no provider request was made."
            if snapshot["all_complete"]
            else "Some synchronized Metrc facility master-data resources are incomplete or unavailable for this license. Available current state is shown without guessing missing resources."
        ),
        "summary": summary,
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
    status = "synced" if snapshot.get("ready") else "partial-sync"
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
            "description": f"{summary.get('active_strain_count', 0)} active strains are available from the synchronized Metrc facility snapshot.{freshness}",
        },
        "items": {
            "label": f"Products & Metrc Items · {summary.get('active_item_count', 0)}",
            "description": (
                f"Synchronized Metrc master data includes {summary.get('active_item_count', 0)} active items, "
                f"{summary.get('item_brand_count', 0)} brands, {summary.get('item_category_count', 0)} categories, "
                f"and {summary.get('unit_of_measure_count', 0)} units of measure.{freshness}"
            ),
        },
    }
    sections = []
    for source in output.get("sections", []):
        row = dict(source)
        update = section_updates.get(str(row.get("key") or ""))
        if update:
            row.update(update)
            row["status"] = status
        sections.append(row)
    output["sections"] = sections

    metrc = dict(output.get("metrc") or {})
    metrc["synchronized_state"] = {
        "ready": bool(snapshot.get("ready")),
        "last_synced_at": snapshot.get("last_synced_at"),
        "source": "integration_provider_snapshots",
        "network_request_made": False,
        "summary": summary,
    }
    if snapshot.get("ready"):
        base_message = str(metrc.get("message") or "").strip()
        metrc["message"] = (
            f"{base_message} Synchronized facility structure is loaded locally; use the individual Refresh from Metrc controls only when you need a live verification."
        ).strip()
    output["metrc"] = metrc
    return output
