from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from modules.regulatory.service import RegulatoryMappingService
from services.metrc_workspace_snapshot import MetrcWorkspaceSnapshotService
from ..auth import RequestContext, get_request_context, require_facility_capability
from ..database import get_engine
from ..services.cultivation_reconciliation import CultivationMetrcReconciliationService


router = APIRouter()
RESOURCES = ("plant_batches", "plants_vegetative", "plants_flowering", "harvests")


def _active_mapping(engine: Engine, context: RequestContext):
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
            "Multiple active Metrc mappings exist for this DoobieLogic facility. Resolve the facility/license mapping before using synchronized regulatory state.",
        )
    return mappings[0]


def _resource_view(resource: dict[str, Any], *, limit: int = 100) -> dict[str, Any]:
    records = [dict(row) for row in resource.get("records") or [] if isinstance(row, dict)]
    return {
        "resource": resource.get("resource"),
        "source": resource.get("source"),
        "network_request_made": False,
        "status": resource.get("status"),
        "complete": bool(resource.get("complete")),
        "count": len(records),
        "last_synced_at": resource.get("last_synced_at"),
        "records_truncated": len(records) > limit,
        "records": [
            {
                key: row.get(key)
                for key in (
                    "provider_id",
                    "label",
                    "name",
                    "status",
                    "quantity",
                    "unit_of_measure",
                    "last_modified",
                    "source",
                )
                if row.get(key) is not None
            }
            for row in records[:limit]
        ],
    }


@router.get("/regulatory-snapshot")
def cultivation_regulatory_snapshot_from_sync(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Load current Metrc cultivation state without a provider request."""

    require_facility_capability(context, engine, "cultivation")
    mapping = _active_mapping(engine, context)
    if mapping is None:
        return {
            "configured": False,
            "ready": False,
            "provider": "metrc",
            "scope": "cultivation",
            "read_only": True,
            "source": "integration_provider_snapshots",
            "network_request_made": False,
            "message": "No verified Metrc facility mapping is active for this cultivation facility.",
            "resources": {},
            "reconciliation": None,
        }

    snapshot = MetrcWorkspaceSnapshotService(engine).read(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        environment=mapping.environment,
        resources=RESOURCES,
    )
    raw = snapshot["resources"]
    batches = raw["plant_batches"]
    vegetative = raw["plants_vegetative"]
    flowering = raw["plants_flowering"]
    harvests = raw["harvests"]
    all_complete = all(raw[name]["complete"] for name in RESOURCES)
    plant_reconciliation_safe = vegetative["complete"] and flowering["complete"]

    evidence = {
        name: {
            "source": raw[name]["source"],
            "network_request_made": False,
            "last_synced_at": raw[name]["last_synced_at"],
            "complete": raw[name]["complete"],
        }
        for name in RESOURCES
    }
    reconciliation = None
    if plant_reconciliation_safe:
        reconciliation = CultivationMetrcReconciliationService(engine).reconcile(
            context.organization_id,
            context.facility_id,
            jurisdiction_code=mapping.jurisdiction_code,
            license_number=mapping.license_number,
            environment=mapping.environment,
            vegetative_records=[dict(row) for row in vegetative["records"] if isinstance(row, dict)],
            flowering_records=[dict(row) for row in flowering["records"] if isinstance(row, dict)],
            evidence=evidence,
        )

    return {
        "configured": True,
        "ready": all_complete,
        "provider": "metrc",
        "scope": "cultivation",
        "jurisdiction_code": mapping.jurisdiction_code,
        "license_number": mapping.license_number,
        "environment": mapping.environment,
        "read_only": True,
        "source": "integration_provider_snapshots",
        "network_request_made": False,
        "last_synced_at": snapshot.get("last_synced_at"),
        "message": (
            "Last synchronized Metrc cultivation state loaded locally. No provider request was made."
            if all_complete
            else "Metrc cultivation synchronization is incomplete. Available synchronized resources are shown, but reconciliation is withheld unless both active plant-phase snapshots are complete."
        ),
        "summary": {
            "active_plant_batch_count": batches["count"],
            "vegetative_plant_count": vegetative["count"],
            "flowering_plant_count": flowering["count"],
            "active_harvest_count": harvests["count"],
        },
        "resources": {
            "plant_batches": _resource_view(batches),
            "vegetative_plants": _resource_view(vegetative),
            "flowering_plants": _resource_view(flowering),
            "harvests": _resource_view(harvests),
        },
        "reconciliation": reconciliation,
        "live_verification_endpoint": "/api/v1/inventory/production/plants/regulatory",
    }
