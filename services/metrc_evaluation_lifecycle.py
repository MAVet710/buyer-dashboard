"""Bounded Massachusetts Metrc sandbox lifecycle evaluation execution.

This module covers the proficiency-evaluation lifecycle after master data:
plant batches -> plants -> harvests -> packages. It is intentionally not a
generic Metrc write client. Callers select one reviewed operation name; method,
path, payload fields and readback resource are fixed here.

Official pass evidence remains stricter than code readiness: a write must return
HTTP 200 and a fresh exact provider readback must verify the affected object (or
its exact absence for a destructive delete). Credentials never enter evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import requests

from modules.regulatory.registry import resolve_metrc_base_url
from services.metrc_client import fetch_metrc_resource


class MetrcLifecycleEvaluationError(RuntimeError):
    """Raised when a lifecycle evaluation operation cannot be proven safe."""


@dataclass(frozen=True)
class LifecycleEvaluationSpec:
    operation_type: str
    method: str
    path: str
    readback_resource: str
    identity_source: str  # response | input
    input_id_key: str = ""
    delete_verification: bool = False


LIFECYCLE_EVALUATION_ACTIONS: dict[str, LifecycleEvaluationSpec] = {
    # Plant batches
    "plant_batch_plantings": LifecycleEvaluationSpec(
        "plant_batch_plantings", "POST", "plantbatches/v2/plantings", "plant_batches_by_id", "response"
    ),
    "plant_batch_packages": LifecycleEvaluationSpec(
        "plant_batch_packages", "POST", "plantbatches/v2/packages", "packages_by_id", "response"
    ),
    "plant_batch_growthphase": LifecycleEvaluationSpec(
        "plant_batch_growthphase", "POST", "plantbatches/v2/growthphase", "plants_by_id", "response"
    ),
    "plant_batch_delete": LifecycleEvaluationSpec(
        "plant_batch_delete", "DELETE", "plantbatches/v2/", "plant_batches_by_id", "input",
        input_id_key="plant_batch_id", delete_verification=True,
    ),
    # Plants
    "plant_location": LifecycleEvaluationSpec(
        "plant_location", "PUT", "plants/v2/location", "plants_by_id", "input", input_id_key="id"
    ),
    "plant_plantings": LifecycleEvaluationSpec(
        "plant_plantings", "POST", "plants/v2/plantings", "plant_batches_by_id", "response"
    ),
    "plant_plantbatch_packages": LifecycleEvaluationSpec(
        "plant_plantbatch_packages", "POST", "plants/v2/plantbatch/packages", "packages_by_id", "response"
    ),
    "plant_delete": LifecycleEvaluationSpec(
        "plant_delete", "DELETE", "plants/v2/", "plants_by_id", "input", input_id_key="id", delete_verification=True
    ),
    "plant_manicure": LifecycleEvaluationSpec(
        "plant_manicure", "POST", "plants/v2/manicure", "harvests_by_id", "response"
    ),
    "plant_harvest": LifecycleEvaluationSpec(
        "plant_harvest", "PUT", "plants/v2/harvest", "harvests_by_id", "response"
    ),
    # Harvests
    "harvest_packages": LifecycleEvaluationSpec(
        "harvest_packages", "POST", "harvests/v2/packages", "packages_by_id", "response"
    ),
    "harvest_waste": LifecycleEvaluationSpec(
        "harvest_waste", "POST", "harvests/v2/waste", "harvests_by_id", "input", input_id_key="id"
    ),
    "harvest_finish": LifecycleEvaluationSpec(
        "harvest_finish", "PUT", "harvests/v2/finish", "harvests_by_id", "input", input_id_key="id"
    ),
    "harvest_unfinish": LifecycleEvaluationSpec(
        "harvest_unfinish", "PUT", "harvests/v2/unfinish", "harvests_by_id", "input", input_id_key="id"
    ),
    # Packages
    "package_create": LifecycleEvaluationSpec(
        "package_create", "POST", "packages/v2/", "packages_by_id", "response"
    ),
    "package_item": LifecycleEvaluationSpec(
        "package_item", "PUT", "packages/v2/item", "packages_by_id", "input", input_id_key="package_id"
    ),
    "package_adjust": LifecycleEvaluationSpec(
        "package_adjust", "PUT", "packages/v2/adjust", "packages_by_id", "input", input_id_key="package_id"
    ),
    "package_finish": LifecycleEvaluationSpec(
        "package_finish", "PUT", "packages/v2/finish", "packages_by_id", "input", input_id_key="package_id"
    ),
    "package_unfinish": LifecycleEvaluationSpec(
        "package_unfinish", "PUT", "packages/v2/unfinish", "packages_by_id", "input", input_id_key="package_id"
    ),
}


def list_lifecycle_evaluation_actions() -> tuple[LifecycleEvaluationSpec, ...]:
    return tuple(LIFECYCLE_EVALUATION_ACTIONS.values())


def _text(payload: dict[str, Any], key: str, label: str, *, optional: bool = False) -> str | None:
    if optional and key not in payload:
        return None
    value = str(payload.get(key) or "").strip()
    if not value and not optional:
        raise MetrcLifecycleEvaluationError(f"{label} is required.")
    return value or None


def _integer(payload: dict[str, Any], key: str, label: str, *, minimum: int | None = None) -> int:
    value = payload.get(key)
    if value in (None, ""):
        raise MetrcLifecycleEvaluationError(f"{label} is required.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise MetrcLifecycleEvaluationError(f"{label} must be an integer.") from exc
    if minimum is not None and number < minimum:
        raise MetrcLifecycleEvaluationError(f"{label} must be at least {minimum}.")
    return number


def _number(payload: dict[str, Any], key: str, label: str, *, minimum: float | None = None) -> float:
    value = payload.get(key)
    if value in (None, ""):
        raise MetrcLifecycleEvaluationError(f"{label} is required.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MetrcLifecycleEvaluationError(f"{label} must be numeric.") from exc
    if minimum is not None and number < minimum:
        raise MetrcLifecycleEvaluationError(f"{label} must be at least {minimum}.")
    return number


def _boolean(payload: dict[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().casefold()
        if token in {"true", "1", "yes", "y"}:
            return True
        if token in {"false", "0", "no", "n", ""}:
            return False
    return bool(value)


def _put_optional(row: dict[str, Any], field: str, value: Any) -> None:
    if value is not None and value != "":
        row[field] = value


def _common_dates(payload: dict[str, Any], row: dict[str, Any]) -> None:
    for source, target in (("expiration_date", "ExpirationDate"), ("sell_by_date", "SellByDate"), ("use_by_date", "UseByDate")):
        _put_optional(row, target, _text(payload, source, target, optional=True))


def _build_plant_batch_plantings(p: dict[str, Any]) -> list[dict[str, Any]]:
    row = {
        "Name": _text(p, "name", "Plant batch name"),
        "Type": _text(p, "type", "Plant batch type"),
        "Count": _integer(p, "count", "Plant count", minimum=1),
        "Strain": _text(p, "strain", "Strain"),
        "ActualDate": _text(p, "actual_date", "Actual date"),
    }
    for source, target in (("location", "Location"), ("sublocation", "Sublocation"), ("patient_license_number", "PatientLicenseNumber"), ("source_plant_batches", "SourcePlantBatches")):
        _put_optional(row, target, _text(p, source, target, optional=True))
    return [row]


def _build_plant_batch_packages(p: dict[str, Any]) -> list[dict[str, Any]]:
    row = {
        "PlantBatch": _text(p, "plant_batch", "Plant batch"),
        "Count": _integer(p, "count", "Plant count", minimum=1),
        "Item": _text(p, "item", "Item"),
        "Tag": _text(p, "tag", "Package tag"),
        "ActualDate": _text(p, "actual_date", "Actual date"),
        "IsTradeSample": _boolean(p, "is_trade_sample"),
        "IsDonation": _boolean(p, "is_donation"),
    }
    for source, target in (("location", "Location"), ("sublocation", "Sublocation"), ("note", "Note"), ("patient_license_number", "PatientLicenseNumber")):
        _put_optional(row, target, _text(p, source, target, optional=True))
    if p.get("id") not in (None, ""):
        row["Id"] = _integer(p, "id", "Plant batch provider ID", minimum=1)
    _common_dates(p, row)
    return [row]


def _build_plant_batch_growthphase(p: dict[str, Any]) -> list[dict[str, Any]]:
    row = {
        "Name": _text(p, "name", "Plant batch name"),
        "Count": _integer(p, "count", "Plant count", minimum=1),
        "StartingTag": _text(p, "starting_tag", "Starting plant tag"),
        "GrowthPhase": _text(p, "growth_phase", "Growth phase"),
        "NewLocation": _text(p, "new_location", "New location"),
        "GrowthDate": _text(p, "growth_date", "Growth date"),
    }
    _put_optional(row, "NewSublocation", _text(p, "new_sublocation", "New sublocation", optional=True))
    _put_optional(row, "PatientLicenseNumber", _text(p, "patient_license_number", "Patient license number", optional=True))
    return [row]


def _build_plant_batch_delete(p: dict[str, Any]) -> list[dict[str, Any]]:
    _integer(p, "plant_batch_id", "Plant batch provider ID", minimum=1)  # readback context only
    row = {
        "PlantBatch": _text(p, "plant_batch", "Plant batch"),
        "Count": _integer(p, "count", "Destroyed plant count", minimum=1),
        "ActualDate": _text(p, "actual_date", "Actual date"),
        "ReasonNote": _text(p, "reason_note", "Reason note"),
    }
    optional = {
        "waste_material_mixed": "WasteMaterialMixed",
        "waste_method_name": "WasteMethodName",
        "waste_reason_name": "WasteReasonName",
        "waste_unit_of_measure": "WasteUnitOfMeasure",
    }
    for source, target in optional.items():
        _put_optional(row, target, _text(p, source, target, optional=True))
    if p.get("waste_weight") not in (None, ""):
        row["WasteWeight"] = _number(p, "waste_weight", "Waste weight", minimum=0)
    return [row]


def _build_plant_location(p: dict[str, Any]) -> list[dict[str, Any]]:
    row = {
        "Id": _integer(p, "id", "Plant provider ID", minimum=1),
        "Location": _text(p, "location", "Location"),
        "ActualDate": _text(p, "actual_date", "Actual date"),
    }
    _put_optional(row, "Label", _text(p, "label", "Plant label", optional=True))
    _put_optional(row, "Sublocation", _text(p, "sublocation", "Sublocation", optional=True))
    return [row]


def _build_plant_plantings(p: dict[str, Any]) -> list[dict[str, Any]]:
    row = {
        "PlantBatchName": _text(p, "plant_batch_name", "Plant batch name"),
        "PlantBatchType": _text(p, "plant_batch_type", "Plant batch type"),
        "PlantCount": _integer(p, "plant_count", "Plant count", minimum=1),
        "StrainName": _text(p, "strain_name", "Strain name"),
        "ActualDate": _text(p, "actual_date", "Actual date"),
    }
    for source, target in (("plant_label", "PlantLabel"), ("location_name", "LocationName"), ("sublocation_name", "SublocationName"), ("patient_license_number", "PatientLicenseNumber")):
        _put_optional(row, target, _text(p, source, target, optional=True))
    return [row]


def _build_plant_plantbatch_packages(p: dict[str, Any]) -> list[dict[str, Any]]:
    row = {
        "PlantLabel": _text(p, "plant_label", "Plant label"),
        "PackageTag": _text(p, "package_tag", "Package tag"),
        "PlantBatchType": _text(p, "plant_batch_type", "Plant batch type"),
        "Item": _text(p, "item", "Item"),
        "Count": _integer(p, "count", "Plant count", minimum=1),
        "ActualDate": _text(p, "actual_date", "Actual date"),
        "IsTradeSample": _boolean(p, "is_trade_sample"),
        "IsDonation": _boolean(p, "is_donation"),
    }
    for source, target in (("location", "Location"), ("sublocation", "Sublocation"), ("note", "Note"), ("patient_license_number", "PatientLicenseNumber")):
        _put_optional(row, target, _text(p, source, target, optional=True))
    return [row]


def _build_plant_delete(p: dict[str, Any]) -> list[dict[str, Any]]:
    row = {
        "Id": _integer(p, "id", "Plant provider ID", minimum=1),
        "Count": _integer(p, "count", "Destroyed plant count", minimum=1),
        "ActualDate": _text(p, "actual_date", "Actual date"),
        "ReasonNote": _text(p, "reason_note", "Reason note"),
    }
    for source, target in (("label", "Label"), ("waste_material_mixed", "WasteMaterialMixed"), ("waste_method_name", "WasteMethodName"), ("waste_reason_name", "WasteReasonName"), ("waste_unit_of_measure_name", "WasteUnitOfMeasureName")):
        _put_optional(row, target, _text(p, source, target, optional=True))
    if p.get("waste_weight") not in (None, ""):
        row["WasteWeight"] = _number(p, "waste_weight", "Waste weight", minimum=0)
    return [row]


def _build_plant_manicure(p: dict[str, Any]) -> list[dict[str, Any]]:
    row = {
        "Plant": _text(p, "plant", "Plant label"),
        "PlantCount": _integer(p, "plant_count", "Plant count", minimum=1),
        "Weight": _number(p, "weight", "Weight", minimum=0),
        "UnitOfWeight": _text(p, "unit_of_weight", "Unit of weight"),
        "DryingLocation": _text(p, "drying_location", "Drying location"),
        "HarvestName": _text(p, "harvest_name", "Harvest name"),
        "ActualDate": _text(p, "actual_date", "Actual date"),
    }
    _put_optional(row, "DryingSublocation", _text(p, "drying_sublocation", "Drying sublocation", optional=True))
    _put_optional(row, "PatientLicenseNumber", _text(p, "patient_license_number", "Patient license number", optional=True))
    return [row]


def _build_plant_harvest(p: dict[str, Any]) -> list[dict[str, Any]]:
    row = {
        "Plant": _text(p, "plant", "Plant label"),
        "Weight": _number(p, "weight", "Weight", minimum=0),
        "UnitOfWeight": _text(p, "unit_of_weight", "Unit of weight"),
        "DryingLocation": _text(p, "drying_location", "Drying location"),
        "HarvestName": _text(p, "harvest_name", "Harvest name"),
        "ActualDate": _text(p, "actual_date", "Actual date"),
    }
    _put_optional(row, "DryingSublocation", _text(p, "drying_sublocation", "Drying sublocation", optional=True))
    _put_optional(row, "PatientLicenseNumber", _text(p, "patient_license_number", "Patient license number", optional=True))
    return [row]


def _harvest_ingredients(p: dict[str, Any]) -> list[dict[str, Any]]:
    raw = p.get("ingredients")
    if raw is None:
        raw = [{
            "harvest_id": p.get("harvest_id"),
            "harvest_name": p.get("harvest_name"),
            "weight": p.get("weight"),
            "unit_of_weight": p.get("unit_of_weight"),
        }]
    if not isinstance(raw, list) or not raw:
        raise MetrcLifecycleEvaluationError("Harvest package ingredients must be a non-empty list.")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise MetrcLifecycleEvaluationError(f"Harvest ingredient {index} must be an object.")
        harvest_id = item.get("harvest_id")
        harvest_name = str(item.get("harvest_name") or "").strip()
        if harvest_id in (None, "") and not harvest_name:
            raise MetrcLifecycleEvaluationError(f"Harvest ingredient {index} requires harvest_id or harvest_name.")
        row = {
            "Weight": _number(item, "weight", f"Harvest ingredient {index} weight", minimum=0),
            "UnitOfWeight": _text(item, "unit_of_weight", f"Harvest ingredient {index} unit of weight"),
        }
        if harvest_id not in (None, ""):
            row["HarvestId"] = _integer(item, "harvest_id", f"Harvest ingredient {index} provider ID", minimum=1)
        if harvest_name:
            row["HarvestName"] = harvest_name
        rows.append(row)
    return rows


def _build_harvest_packages(p: dict[str, Any]) -> list[dict[str, Any]]:
    row = {
        "Tag": _text(p, "tag", "Package tag"),
        "Item": _text(p, "item", "Item"),
        "ActualDate": _text(p, "actual_date", "Actual date"),
        "Ingredients": _harvest_ingredients(p),
        "IsProductionBatch": _boolean(p, "is_production_batch"),
        "IsTradeSample": _boolean(p, "is_trade_sample"),
        "IsDonation": _boolean(p, "is_donation"),
        "ProductRequiresRemediation": _boolean(p, "product_requires_remediation"),
        "ProductRequiresDecontamination": _boolean(p, "product_requires_decontamination"),
        "RemediateProduct": _boolean(p, "remediate_product"),
        "DecontaminateProduct": _boolean(p, "decontaminate_product"),
    }
    for source, target in (
        ("location", "Location"), ("sublocation", "Sublocation"), ("note", "Note"),
        ("patient_license_number", "PatientLicenseNumber"), ("production_batch_number", "ProductionBatchNumber"),
        ("remediation_date", "RemediationDate"), ("remediation_steps", "RemediationSteps"),
        ("decontamination_date", "DecontaminationDate"), ("decontamination_steps", "DecontaminationSteps"),
        ("unit_of_weight", "UnitOfWeight"),
    ):
        _put_optional(row, target, _text(p, source, target, optional=True))
    for source, target in (("lab_test_stage_id", "LabTestStageId"), ("processing_job_type_id", "ProcessingJobTypeId"), ("remediation_method_id", "RemediationMethodId")):
        if p.get(source) not in (None, ""):
            row[target] = _integer(p, source, target, minimum=1)
    _common_dates(p, row)
    return [row]


def _build_harvest_waste(p: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "Id": _integer(p, "id", "Harvest provider ID", minimum=1),
        "WasteType": _text(p, "waste_type", "Waste type"),
        "UnitOfWeight": _text(p, "unit_of_weight", "Unit of weight"),
        "WasteWeight": _number(p, "waste_weight", "Waste weight", minimum=0),
        "ActualDate": _text(p, "actual_date", "Actual date"),
    }]


def _build_harvest_finish(p: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"Id": _integer(p, "id", "Harvest provider ID", minimum=1), "ActualDate": _text(p, "actual_date", "Actual date")}]


def _build_harvest_unfinish(p: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"Id": _integer(p, "id", "Harvest provider ID", minimum=1)}]


def _package_ingredients(p: dict[str, Any]) -> list[dict[str, Any]]:
    raw = p.get("ingredients")
    if not isinstance(raw, list) or not raw:
        raise MetrcLifecycleEvaluationError("Package creation requires at least one source package ingredient.")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise MetrcLifecycleEvaluationError(f"Package ingredient {index} must be an object.")
        rows.append({
            "Package": _text(item, "package", f"Package ingredient {index} source package"),
            "Quantity": _number(item, "quantity", f"Package ingredient {index} quantity", minimum=0),
            "UnitOfMeasure": _text(item, "unit_of_measure", f"Package ingredient {index} unit of measure"),
        })
    return rows


def _build_package_create(p: dict[str, Any]) -> list[dict[str, Any]]:
    row = {
        "Tag": _text(p, "tag", "Package tag"),
        "Item": _text(p, "item", "Item"),
        "Quantity": _number(p, "quantity", "Package quantity", minimum=0),
        "UnitOfMeasure": _text(p, "unit_of_measure", "Unit of measure"),
        "ActualDate": _text(p, "actual_date", "Actual date"),
        "Ingredients": _package_ingredients(p),
        "IsProductionBatch": _boolean(p, "is_production_batch"),
        "IsTradeSample": _boolean(p, "is_trade_sample"),
        "IsDonation": _boolean(p, "is_donation"),
        "ProductRequiresRemediation": _boolean(p, "product_requires_remediation"),
        "RequiredLabTestBatches": _boolean(p, "required_lab_test_batches"),
        "UseSameItem": _boolean(p, "use_same_item"),
    }
    for source, target in (("location", "Location"), ("sublocation", "Sublocation"), ("note", "Note"), ("patient_license_number", "PatientLicenseNumber"), ("production_batch_number", "ProductionBatchNumber")):
        _put_optional(row, target, _text(p, source, target, optional=True))
    for source, target in (("lab_test_stage_id", "LabTestStageId"), ("processing_job_type_id", "ProcessingJobTypeId")):
        if p.get(source) not in (None, ""):
            row[target] = _integer(p, source, target, minimum=1)
    _common_dates(p, row)
    return [row]


def _build_package_item(p: dict[str, Any]) -> list[dict[str, Any]]:
    _integer(p, "package_id", "Package provider ID", minimum=1)  # readback context only
    return [{"Label": _text(p, "label", "Package label"), "Item": _text(p, "item", "Item")}]


def _build_package_adjust(p: dict[str, Any]) -> list[dict[str, Any]]:
    _integer(p, "package_id", "Package provider ID", minimum=1)  # readback context only
    row = {
        "Label": _text(p, "label", "Package label"),
        "Quantity": _number(p, "quantity", "Adjustment quantity"),
        "UnitOfMeasure": _text(p, "unit_of_measure", "Unit of measure"),
        "AdjustmentReason": _text(p, "adjustment_reason", "Adjustment reason"),
        "AdjustmentDate": _text(p, "adjustment_date", "Adjustment date"),
    }
    _put_optional(row, "ReasonNote", _text(p, "reason_note", "Reason note", optional=True))
    return [row]


def _build_package_finish(p: dict[str, Any]) -> list[dict[str, Any]]:
    _integer(p, "package_id", "Package provider ID", minimum=1)
    return [{"Label": _text(p, "label", "Package label"), "ActualDate": _text(p, "actual_date", "Actual date")}]


def _build_package_unfinish(p: dict[str, Any]) -> list[dict[str, Any]]:
    _integer(p, "package_id", "Package provider ID", minimum=1)
    return [{"Label": _text(p, "label", "Package label")}]


_BUILDERS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
    "plant_batch_plantings": _build_plant_batch_plantings,
    "plant_batch_packages": _build_plant_batch_packages,
    "plant_batch_growthphase": _build_plant_batch_growthphase,
    "plant_batch_delete": _build_plant_batch_delete,
    "plant_location": _build_plant_location,
    "plant_plantings": _build_plant_plantings,
    "plant_plantbatch_packages": _build_plant_plantbatch_packages,
    "plant_delete": _build_plant_delete,
    "plant_manicure": _build_plant_manicure,
    "plant_harvest": _build_plant_harvest,
    "harvest_packages": _build_harvest_packages,
    "harvest_waste": _build_harvest_waste,
    "harvest_finish": _build_harvest_finish,
    "harvest_unfinish": _build_harvest_unfinish,
    "package_create": _build_package_create,
    "package_item": _build_package_item,
    "package_adjust": _build_package_adjust,
    "package_finish": _build_package_finish,
    "package_unfinish": _build_package_unfinish,
}


def build_lifecycle_evaluation_payload(operation_type: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    operation = str(operation_type or "").strip().casefold()
    builder = _BUILDERS.get(operation)
    if builder is None:
        raise MetrcLifecycleEvaluationError("This operation is not enabled for the MA Metrc lifecycle evaluation.")
    if not isinstance(payload, dict):
        raise MetrcLifecycleEvaluationError("Evaluation payload must be one JSON object.")
    return builder(payload)


def _response_payload(response: Any) -> Any:
    if not getattr(response, "content", b""):
        return None
    try:
        return response.json()
    except ValueError:
        return {"message": str(getattr(response, "text", ""))[:1000]}


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _collect_ids(value: Any) -> list[str]:
    found: list[str] = []

    def add(value: Any) -> None:
        if value is None or isinstance(value, bool):
            return
        token = str(value).strip()
        if token and token not in found:
            found.append(token)

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            for key in ("Id", "id", "ExternalId", "externalId"):
                if key in node:
                    add(node.get(key))
            for key in ("Ids", "ids", "Data", "data", "Results", "results"):
                if key in node:
                    visit(node.get(key))
        elif isinstance(node, (str, int, float)):
            add(node)

    visit(value)
    return found


def _readback_id(spec: LifecycleEvaluationSpec, payload: dict[str, Any], response_payload: Any) -> str:
    if spec.identity_source == "input":
        raw = payload.get(spec.input_id_key)
        return str(raw).strip() if raw is not None else ""
    ids = _collect_ids(response_payload)
    return ids[0] if ids else ""


def _record_provider_id(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    for record in records:
        if not isinstance(record, dict):
            continue
        value = record.get("provider_id")
        if value is not None and str(value).strip():
            return str(value).strip()
        source = record.get("source")
        if isinstance(source, dict):
            value = source.get("Id") or source.get("id")
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def _last_modified(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("last_modified"):
            return str(record["last_modified"]).strip()
        source = record.get("source")
        if isinstance(source, dict):
            for key in ("LastModified", "lastModified", "LastModifiedDateTime", "Modified", "UpdatedAt"):
                if source.get(key):
                    return str(source[key]).strip()
    return ""


def _deleted_readback_verified(readback: Any, provider_id: str) -> bool:
    if not isinstance(readback, dict):
        return False
    records = readback.get("records")
    if readback.get("ok") and _record_provider_id(records) == provider_id:
        # Some Metrc resources remain addressable by ID after discontinuation.
        return True
    status = int(readback.get("http_status") or 0)
    return status in {404, 410}


def execute_lifecycle_evaluation_action(
    *,
    operation_type: str,
    payload: dict[str, Any],
    license_number: str,
    integrator_api_key: str,
    user_api_key: str,
    state: str = "MA",
    environment: str = "sandbox",
    timeout_seconds: int = 30,
    request_fn: Callable[..., Any] | None = None,
    readback_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute one reviewed lifecycle operation and capture evaluation evidence."""
    operation = str(operation_type or "").strip().casefold()
    spec = LIFECYCLE_EVALUATION_ACTIONS.get(operation)
    if spec is None:
        raise MetrcLifecycleEvaluationError("This operation is not enabled for the MA Metrc lifecycle evaluation.")

    environment = str(environment or "").strip().casefold()
    if environment != "sandbox":
        raise MetrcLifecycleEvaluationError("Lifecycle evaluation writes are restricted to the Metrc sandbox.")
    base_url, state_code = resolve_metrc_base_url(state, environment=environment)
    if state_code != "MA" or not base_url:
        raise MetrcLifecycleEvaluationError("Lifecycle evaluation writes are restricted to the verified Massachusetts sandbox.")

    license_number = str(license_number or "").strip()
    integrator_api_key = str(integrator_api_key or "").strip()
    user_api_key = str(user_api_key or "").strip()
    if not license_number:
        raise MetrcLifecycleEvaluationError("A Massachusetts sandbox facility license number is required.")
    if not integrator_api_key or not user_api_key:
        raise MetrcLifecycleEvaluationError("Both the Metrc integrator/vendor key and sandbox user API key are required.")
    if integrator_api_key == user_api_key:
        raise MetrcLifecycleEvaluationError("The Metrc integrator/vendor key and sandbox user API key must be distinct credentials.")

    body = build_lifecycle_evaluation_payload(operation, payload)
    url = f"{base_url.rstrip('/')}/{spec.path.lstrip('/')}"
    try:
        response = (request_fn or requests.request)(
            spec.method,
            url,
            auth=(integrator_api_key, user_api_key),
            params={"licenseNumber": license_number},
            json=body,
            timeout=timeout_seconds,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
    except requests.RequestException as exc:
        raise MetrcLifecycleEvaluationError(
            f"Metrc request failed before evaluation evidence could be captured: {type(exc).__name__}."
        ) from exc

    response_payload = _response_payload(response)
    http_status = int(getattr(response, "status_code", 0) or 0)
    evidence: dict[str, Any] = {
        "passed": False,
        "stage": "write",
        "operation_type": operation,
        "state": state_code,
        "environment": environment,
        "license_number": license_number,
        "http_status": http_status,
        "provider_id": "",
        "last_modified": "",
        "request": {"method": spec.method, "path": spec.path, "query": {"licenseNumber": license_number}, "body": body},
        "request_json": _json_text(body),
        "response": response_payload,
        "response_json": _json_text(response_payload),
        "readback": None,
        "message": "",
    }
    if http_status != 200:
        evidence["message"] = f"Metrc returned HTTP {http_status}; the proficiency evaluation requires HTTP 200."
        return evidence

    provider_id = _readback_id(spec, payload, response_payload)
    evidence["provider_id"] = provider_id
    if not provider_id:
        evidence["stage"] = "readback_identity"
        evidence["message"] = "Metrc accepted the write but no exact provider ID was available for fresh readback."
        return evidence

    readback = (readback_fn or fetch_metrc_resource)(
        state=state_code,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource=spec.readback_resource,
        environment=environment,
        license_number=license_number,
        path_parameters={"id": provider_id},
        timeout_seconds=timeout_seconds,
    )
    records = readback.get("records") if isinstance(readback, dict) else None
    evidence["readback"] = readback
    evidence["last_modified"] = _last_modified(records)

    if spec.delete_verification:
        verified = _deleted_readback_verified(readback, provider_id)
    else:
        verified = bool(isinstance(readback, dict) and readback.get("ok") and _record_provider_id(records) == provider_id)

    evidence["passed"] = verified
    evidence["stage"] = "complete" if verified else "readback"
    evidence["message"] = (
        "Metrc returned HTTP 200 and fresh exact provider readback verified the lifecycle mutation."
        if verified
        else "Metrc returned HTTP 200, but fresh exact provider readback did not verify the lifecycle mutation."
    )
    return evidence
