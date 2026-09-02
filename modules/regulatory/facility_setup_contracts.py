"""Documented Metrc master-data actions staged for DoobieLogic Facility Setup.

This catalog is intentionally separate from the executable write registry.  It
records reviewed provider surface area and exact payload shapes that can be
shown to operators while network dispatch remains fail-closed until a real
sandbox write plus provider readback promotes the operation into
``write_registry.py``.

The first verified Facility Setup implementation is based on the current
Massachusetts v2 documentation.  Other jurisdictions must be reviewed before
these master-data actions are promoted there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FacilitySetupActionSpec:
    operation_type: str
    label: str
    resource: str
    method: str
    path: str
    required_permission: str
    entity_type: str
    dispatch_enabled: bool = False
    verification_status: str = "documented_pending_sandbox"
    note: str = "Provider dispatch remains locked until sandbox write/readback verification is complete."

    def public(self) -> dict[str, Any]:
        return {
            "operation_type": self.operation_type,
            "label": self.label,
            "resource": self.resource,
            "method": self.method,
            "path": self.path,
            "required_permission": self.required_permission,
            "entity_type": self.entity_type,
            "dispatch_enabled": self.dispatch_enabled,
            "verification_status": self.verification_status,
            "note": self.note,
        }


FACILITY_SETUP_ACTIONS: dict[str, FacilitySetupActionSpec] = {
    "location_create": FacilitySetupActionSpec("location_create", "Create room / location", "locations", "POST", "locations/v2/", "Manage Locations", "location"),
    "location_update": FacilitySetupActionSpec("location_update", "Edit room / location", "locations", "PUT", "locations/v2/", "Manage Locations", "location"),
    "location_discontinue": FacilitySetupActionSpec("location_discontinue", "Discontinue room / location", "locations", "DELETE", "locations/v2/{id}", "Manage Locations", "location"),
    "sublocation_create": FacilitySetupActionSpec("sublocation_create", "Create sublocation", "sublocations", "POST", "sublocations/v2/", "Manage Locations", "sublocation"),
    "sublocation_update": FacilitySetupActionSpec("sublocation_update", "Edit sublocation", "sublocations", "PUT", "sublocations/v2/", "Manage Locations", "sublocation"),
    "sublocation_discontinue": FacilitySetupActionSpec("sublocation_discontinue", "Discontinue sublocation", "sublocations", "DELETE", "sublocations/v2/{id}", "Manage Locations", "sublocation"),
    "strain_create": FacilitySetupActionSpec("strain_create", "Create strain", "strains", "POST", "strains/v2/", "Manage Strains", "strain"),
    "strain_update": FacilitySetupActionSpec("strain_update", "Edit strain", "strains", "PUT", "strains/v2/", "Manage Strains", "strain"),
    "strain_discontinue": FacilitySetupActionSpec("strain_discontinue", "Discontinue strain", "strains", "DELETE", "strains/v2/{id}", "Manage Strains", "strain"),
    "item_create": FacilitySetupActionSpec("item_create", "Create Metrc item", "items", "POST", "items/v2/", "Manage Items", "item"),
    "item_update": FacilitySetupActionSpec("item_update", "Edit Metrc item", "items", "PUT", "items/v2/", "Manage Items", "item"),
    "item_discontinue": FacilitySetupActionSpec("item_discontinue", "Discontinue Metrc item", "items", "DELETE", "items/v2/{id}", "Manage Items", "item"),
    "brand_create": FacilitySetupActionSpec("brand_create", "Create item brand", "brands", "POST", "items/v2/brand", "Manage Items", "brand"),
    "brand_update": FacilitySetupActionSpec("brand_update", "Edit item brand", "brands", "PUT", "items/v2/brand", "Manage Items", "brand"),
    "brand_discontinue": FacilitySetupActionSpec("brand_discontinue", "Discontinue item brand", "brands", "DELETE", "items/v2/brand/{id}", "Manage Items", "brand"),
    "processing_job_type_create": FacilitySetupActionSpec("processing_job_type_create", "Create production process", "processing_job_types", "POST", "processing/v2/jobtypes", "Manage Processing Job", "processing_job_type"),
    "processing_job_type_update": FacilitySetupActionSpec("processing_job_type_update", "Edit production process", "processing_job_types", "PUT", "processing/v2/jobtypes", "Manage Processing Job", "processing_job_type"),
    "processing_job_type_discontinue": FacilitySetupActionSpec("processing_job_type_discontinue", "Discontinue production process", "processing_job_types", "DELETE", "processing/v2/jobtypes/{id}", "Manage Processing Job", "processing_job_type"),
    "additive_template_create": FacilitySetupActionSpec("additive_template_create", "Create cultivation program", "additive_templates", "POST", "additivestemplates/v2/", "Manage Additives", "additive_template"),
    "additive_template_update": FacilitySetupActionSpec("additive_template_update", "Edit cultivation program", "additive_templates", "PUT", "additivestemplates/v2/", "Manage Additives", "additive_template"),
    "driver_create": FacilitySetupActionSpec("driver_create", "Create transport driver", "drivers", "POST", "transporters/v2/drivers", "Manage Transporters", "driver"),
    "driver_update": FacilitySetupActionSpec("driver_update", "Edit transport driver", "drivers", "PUT", "transporters/v2/drivers", "Manage Transporters", "driver"),
    "driver_discontinue": FacilitySetupActionSpec("driver_discontinue", "Discontinue transport driver", "drivers", "DELETE", "transporters/v2/drivers/{id}", "Manage Transporters", "driver"),
    "vehicle_create": FacilitySetupActionSpec("vehicle_create", "Create transport vehicle", "vehicles", "POST", "transporters/v2/vehicles", "Manage Transporters", "vehicle"),
    "vehicle_update": FacilitySetupActionSpec("vehicle_update", "Edit transport vehicle", "vehicles", "PUT", "transporters/v2/vehicles", "Manage Transporters", "vehicle"),
    "vehicle_discontinue": FacilitySetupActionSpec("vehicle_discontinue", "Discontinue transport vehicle", "vehicles", "DELETE", "transporters/v2/vehicles/{id}", "Manage Transporters", "vehicle"),
}


def list_facility_setup_actions() -> tuple[FacilitySetupActionSpec, ...]:
    return tuple(FACILITY_SETUP_ACTIONS.values())


def get_facility_setup_action(operation_type: str) -> FacilitySetupActionSpec | None:
    return FACILITY_SETUP_ACTIONS.get(str(operation_type or "").strip().casefold())


def build_facility_setup_payload(operation_type: str, payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Build reviewed request bodies for the simple MA master-data contracts.

    Complex item/job/additive/transport schemas are deliberately not guessed.
    They stay catalogued but return ``None`` until their exact payload adapter is
    promoted in a later pass.
    """

    operation = str(operation_type or "").strip().casefold()
    name = str(payload.get("name") or "").strip()
    provider_id = payload.get("id")

    if operation == "location_create":
        if not name:
            raise ValueError("Room / location name is required.")
        location_type = str(payload.get("location_type_name") or "").strip()
        if not location_type:
            raise ValueError("Metrc location type is required.")
        return [{"Name": name, "LocationTypeName": location_type}]
    if operation == "location_update":
        if provider_id in (None, "") or not name:
            raise ValueError("Location ID and name are required.")
        location_type = str(payload.get("location_type_name") or "").strip()
        if not location_type:
            raise ValueError("Metrc location type is required.")
        return [{"Id": int(provider_id), "Name": name, "LocationTypeName": location_type}]
    if operation == "location_discontinue":
        if provider_id in (None, ""):
            raise ValueError("Location ID is required.")
        return None

    if operation == "sublocation_create":
        if not name:
            raise ValueError("Sublocation name is required.")
        return [{"Name": name}]
    if operation == "sublocation_update":
        if provider_id in (None, "") or not name:
            raise ValueError("Sublocation ID and name are required.")
        return [{"Id": int(provider_id), "Name": name}]
    if operation == "sublocation_discontinue":
        if provider_id in (None, ""):
            raise ValueError("Sublocation ID is required.")
        return None

    if operation == "strain_create":
        if not name:
            raise ValueError("Strain name is required.")
        return [{
            "Name": name,
            "TestingStatus": str(payload.get("testing_status") or "").strip(),
            "ThcLevel": float(payload.get("thc_level") or 0),
            "CbdLevel": float(payload.get("cbd_level") or 0),
            "IndicaPercentage": int(payload.get("indica_percentage") or 0),
            "SativaPercentage": int(payload.get("sativa_percentage") or 0),
        }]
    if operation == "strain_update":
        if provider_id in (None, "") or not name:
            raise ValueError("Strain ID and name are required.")
        return [{
            "Id": int(provider_id),
            "Name": name,
            "TestingStatus": str(payload.get("testing_status") or "").strip(),
            "ThcLevel": float(payload.get("thc_level") or 0),
            "CbdLevel": float(payload.get("cbd_level") or 0),
            "IndicaPercentage": int(payload.get("indica_percentage") or 0),
            "SativaPercentage": int(payload.get("sativa_percentage") or 0),
        }]
    if operation == "strain_discontinue":
        if provider_id in (None, ""):
            raise ValueError("Strain ID is required.")
        return None

    return None