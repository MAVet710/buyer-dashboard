"""Documented Metrc master-data actions staged for DoobieLogic Facility Setup.

This catalog is intentionally separate from the executable write registry. It
records reviewed provider surface area and exact request shapes that can be
shown to operators while network dispatch remains fail-closed until a real
sandbox write plus provider readback promotes the operation into
``write_registry.py``.

Request adapters are bounded to fields present in the reviewed v2 provider
documentation. Unknown input keys are never forwarded to Metrc.
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


_MISSING = object()
_ITEM_TEXT_FIELDS = {
    "global_product_name": "GlobalProductName",
    "strain": "Strain",
    "item_brand": "ItemBrand",
    "administration_method": "AdministrationMethod",
    "unit_cbd_content_unit_of_measure": "UnitCbdContentUnitOfMeasure",
    "unit_cbd_content_dose_unit_of_measure": "UnitCbdContentDoseUnitOfMeasure",
    "unit_thc_content_unit_of_measure": "UnitThcContentUnitOfMeasure",
    "unit_thc_content_dose_unit_of_measure": "UnitThcContentDoseUnitOfMeasure",
    "unit_cbda_content_unit_of_measure": "UnitCbdAContentUnitOfMeasure",
    "unit_cbda_content_dose_unit_of_measure": "UnitCbdAContentDoseUnitOfMeasure",
    "unit_thca_content_unit_of_measure": "UnitThcAContentUnitOfMeasure",
    "unit_thca_content_dose_unit_of_measure": "UnitThcAContentDoseUnitOfMeasure",
    "unit_volume_unit_of_measure": "UnitVolumeUnitOfMeasure",
    "unit_weight_unit_of_measure": "UnitWeightUnitOfMeasure",
    "public_ingredients": "PublicIngredients",
    "description": "Description",
    "allergens": "Allergens",
    "product_photo_description": "ProductPhotoDescription",
    "label_photo_description": "LabelPhotoDescription",
    "packaging_photo_description": "PackagingPhotoDescription",
    "processing_job_category_name": "ProcessingJobCategoryName",
    "processing_job_type_name": "ProcessingJobTypeName",
}
_ITEM_NUMBER_FIELDS = {
    "unit_cbd_percent": "UnitCbdPercent",
    "unit_cbd_content": "UnitCbdContent",
    "unit_cbd_content_dose": "UnitCbdContentDose",
    "unit_thc_percent": "UnitThcPercent",
    "unit_thc_content": "UnitThcContent",
    "unit_thc_content_dose": "UnitThcContentDose",
    "unit_cbda_percent": "UnitCbdAPercent",
    "unit_cbda_content": "UnitCbdAContent",
    "unit_cbda_content_dose": "UnitCbdAContentDose",
    "unit_thca_percent": "UnitThcAPercent",
    "unit_thca_content": "UnitThcAContent",
    "unit_thca_content_dose": "UnitThcAContentDose",
    "unit_volume": "UnitVolume",
    "unit_weight": "UnitWeight",
    "serving_size": "ServingSize",
    "supply_duration_days": "SupplyDurationDays",
    "number_of_doses": "NumberOfDoses",
}
_ITEM_ID_LIST_FIELDS = {
    "product_image_file_system_ids": "ProductImageFileSystemIds",
    "label_image_file_system_ids": "LabelImageFileSystemIds",
    "packaging_image_file_system_ids": "PackagingImageFileSystemIds",
    "product_pdf_file_system_ids": "ProductPDFFileSystemIds",
}


def list_facility_setup_actions() -> tuple[FacilitySetupActionSpec, ...]:
    return tuple(FACILITY_SETUP_ACTIONS.values())


def get_facility_setup_action(operation_type: str) -> FacilitySetupActionSpec | None:
    return FACILITY_SETUP_ACTIONS.get(str(operation_type or "").strip().casefold())


def _required_text(payload: dict[str, Any], key: str, label: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{label} is required.")
    return value


def _required_id(payload: dict[str, Any], label: str) -> int:
    value = payload.get("id")
    if value in (None, ""):
        raise ValueError(f"{label} ID is required.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} ID must be numeric.") from exc


def _optional_text(payload: dict[str, Any], key: str):
    if key not in payload:
        return _MISSING
    value = payload.get(key)
    if value is None:
        return None
    clean = str(value).strip()
    return clean or None


def _optional_number(payload: dict[str, Any], key: str):
    if key not in payload:
        return _MISSING
    value = payload.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key.replace('_', ' ').title()} must be numeric.") from exc


def _optional_id_list(payload: dict[str, Any], key: str):
    if key not in payload:
        return _MISSING
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{key.replace('_', ' ').title()} must be a list of numeric IDs.")
    try:
        return [int(row) for row in value]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key.replace('_', ' ').title()} must contain only numeric IDs.") from exc


def _string_list(payload: dict[str, Any], key: str, label: str) -> list[str]:
    value = payload.get(key, [])
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list.")
    clean = [str(row).strip() for row in value if str(row).strip()]
    return clean


def _active_ingredients(payload: dict[str, Any]):
    if "active_ingredients" not in payload:
        return _MISSING
    value = payload.get("active_ingredients")
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("Active ingredients must be a list.")
    rows: list[dict[str, Any]] = []
    for index, ingredient in enumerate(value, start=1):
        if not isinstance(ingredient, dict):
            raise ValueError(f"Active ingredient {index} must be an object.")
        name = _required_text(ingredient, "name", f"Active ingredient {index} name")
        percentage = ingredient.get("percentage")
        if percentage in (None, ""):
            raise ValueError(f"Active ingredient {index} percentage is required.")
        try:
            number = float(percentage)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Active ingredient {index} percentage must be numeric.") from exc
        rows.append({"Name": name, "Percentage": number})
    return rows


def _item_payload(payload: dict[str, Any], *, include_id: bool) -> dict[str, Any]:
    row: dict[str, Any] = {}
    if include_id:
        row["Id"] = _required_id(payload, "Item")
    row["Name"] = _required_text(payload, "name", "Item name")
    row["ItemCategory"] = _required_text(payload, "item_category", "Item category")
    row["UnitOfMeasure"] = _required_text(payload, "unit_of_measure", "Unit of measure")
    for source, target in _ITEM_TEXT_FIELDS.items():
        converted = _optional_text(payload, source)
        if converted is not _MISSING:
            row[target] = converted
    for source, target in _ITEM_NUMBER_FIELDS.items():
        converted = _optional_number(payload, source)
        if converted is not _MISSING:
            row[target] = converted
    for source, target in _ITEM_ID_LIST_FIELDS.items():
        converted = _optional_id_list(payload, source)
        if converted is not _MISSING:
            row[target] = converted
    return row


def _processing_job_type_payload(payload: dict[str, Any], *, include_id: bool) -> dict[str, Any]:
    row: dict[str, Any] = {}
    if include_id:
        row["Id"] = _required_id(payload, "Processing Job Type")
    row["Name"] = _required_text(payload, "name", "Process name")
    row["Description"] = _required_text(payload, "description", "Process description")
    category = _required_text(payload, "category", "Process category")
    row["CategoryName" if include_id else "Category"] = category
    row["ProcessingSteps"] = _required_text(payload, "processing_steps", "Processing steps")
    row["Attributes"] = _string_list(payload, "attributes", "Processing attributes")
    return row


def _additive_template_payload(payload: dict[str, Any], *, include_id: bool) -> dict[str, Any]:
    row: dict[str, Any] = {}
    if include_id:
        row["Id"] = _required_id(payload, "Additive template")
    row["Name"] = _required_text(payload, "name", "Additive template name")
    row["AdditiveType"] = _required_text(payload, "additive_type", "Additive type")
    row["ApplicationDevice"] = _required_text(payload, "application_device", "Application device")
    for source, target in {
        "epa_registration_number": "EpaRegistrationNumber",
        "note": "Note",
        "product_supplier": "ProductSupplier",
        "product_trade_name": "ProductTradeName",
        "restrictive_entry_interval_quantity_description": "RestrictiveEntryIntervalQuantityDescription",
        "restrictive_entry_interval_time_description": "RestrictiveEntryIntervalTimeDescription",
    }.items():
        converted = _optional_text(payload, source)
        if converted is not _MISSING:
            row[target] = converted
    ingredients = _active_ingredients(payload)
    if ingredients is not _MISSING:
        row["ActiveIngredients"] = ingredients
    return row


def _driver_payload(payload: dict[str, Any], *, include_id: bool) -> dict[str, Any]:
    row: dict[str, Any] = {}
    if include_id:
        row["Id"] = _required_id(payload, "Driver")
    row["Name"] = _required_text(payload, "name", "Driver name")
    row["DriversLicenseNumber"] = _required_text(payload, "drivers_license_number", "Driver's license number")
    row["EmployeeId"] = _required_text(payload, "employee_id", "Employee ID")
    return row


def _vehicle_payload(payload: dict[str, Any], *, include_id: bool) -> dict[str, Any]:
    row: dict[str, Any] = {}
    if include_id:
        row["Id"] = _required_id(payload, "Vehicle")
    row["Make"] = _required_text(payload, "make", "Vehicle make")
    row["Model"] = _required_text(payload, "model", "Vehicle model")
    row["LicensePlateNumber"] = _required_text(payload, "license_plate_number", "License plate number")
    registration = _optional_text(payload, "registration_number")
    if registration is not _MISSING:
        row["RegistrationNumber"] = registration
    return row


def build_facility_setup_payload(operation_type: str, payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Build bounded, reviewed request bodies for Facility Setup previews.

    DELETE operations return ``None`` because Metrc identifies the target in the
    path. Unknown keys are ignored rather than forwarded.
    """

    operation = str(operation_type or "").strip().casefold()
    name = str(payload.get("name") or "").strip()

    if operation == "location_create":
        if not name:
            raise ValueError("Room / location name is required.")
        location_type = _required_text(payload, "location_type_name", "Metrc location type")
        return [{"Name": name, "LocationTypeName": location_type}]
    if operation == "location_update":
        provider_id = _required_id(payload, "Location")
        if not name:
            raise ValueError("Location name is required.")
        location_type = _required_text(payload, "location_type_name", "Metrc location type")
        return [{"Id": provider_id, "Name": name, "LocationTypeName": location_type}]
    if operation == "location_discontinue":
        _required_id(payload, "Location")
        return None

    if operation == "sublocation_create":
        if not name:
            raise ValueError("Sublocation name is required.")
        return [{"Name": name}]
    if operation == "sublocation_update":
        provider_id = _required_id(payload, "Sublocation")
        if not name:
            raise ValueError("Sublocation name is required.")
        return [{"Id": provider_id, "Name": name}]
    if operation == "sublocation_discontinue":
        _required_id(payload, "Sublocation")
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
        provider_id = _required_id(payload, "Strain")
        if not name:
            raise ValueError("Strain name is required.")
        return [{
            "Id": provider_id,
            "Name": name,
            "TestingStatus": str(payload.get("testing_status") or "").strip(),
            "ThcLevel": float(payload.get("thc_level") or 0),
            "CbdLevel": float(payload.get("cbd_level") or 0),
            "IndicaPercentage": int(payload.get("indica_percentage") or 0),
            "SativaPercentage": int(payload.get("sativa_percentage") or 0),
        }]
    if operation == "strain_discontinue":
        _required_id(payload, "Strain")
        return None

    if operation == "item_create":
        return [_item_payload(payload, include_id=False)]
    if operation == "item_update":
        return [_item_payload(payload, include_id=True)]
    if operation == "item_discontinue":
        _required_id(payload, "Item")
        return None

    if operation == "brand_create":
        return [{"Name": _required_text(payload, "name", "Brand name")}]
    if operation == "brand_update":
        return [{"Id": _required_id(payload, "Brand"), "Name": _required_text(payload, "name", "Brand name")}]
    if operation == "brand_discontinue":
        _required_id(payload, "Brand")
        return None

    if operation == "processing_job_type_create":
        return [_processing_job_type_payload(payload, include_id=False)]
    if operation == "processing_job_type_update":
        return [_processing_job_type_payload(payload, include_id=True)]
    if operation == "processing_job_type_discontinue":
        _required_id(payload, "Processing Job Type")
        return None

    if operation == "additive_template_create":
        return [_additive_template_payload(payload, include_id=False)]
    if operation == "additive_template_update":
        return [_additive_template_payload(payload, include_id=True)]

    if operation == "driver_create":
        return [_driver_payload(payload, include_id=False)]
    if operation == "driver_update":
        return [_driver_payload(payload, include_id=True)]
    if operation == "driver_discontinue":
        _required_id(payload, "Driver")
        return None

    if operation == "vehicle_create":
        return [_vehicle_payload(payload, include_id=False)]
    if operation == "vehicle_update":
        return [_vehicle_payload(payload, include_id=True)]
    if operation == "vehicle_discontinue":
        _required_id(payload, "Vehicle")
        return None

    return None
