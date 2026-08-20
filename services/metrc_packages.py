"""Minimal Metrc v2 package-creation adapter for approved traceability workers."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from services.metrc_inventory_adjustments import _request, normalize_metrc_unit


def submit_package_creation(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str,
    tag: str,
    item: str,
    quantity: float,
    unit: str,
    ingredients: Sequence[Mapping[str, Any]],
    actual_date: date | None = None,
    location: str | None = None,
    note: str = "",
    production_batch_number: str = "",
    is_finished_good: bool | None = None,
    expiration_date: date | None = None,
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    """Create one Metrc package from one or more source-package ingredients.

    Credentials are runtime-only. The caller should persist only the sanitized
    business payload through Buyer Dash's traceability transaction ledger.
    """

    license_number = str(license_number or "").strip()
    tag = str(tag or "").strip()
    item = str(item or "").strip()
    if not license_number:
        return {"ok": False, "status": "missing_license", "message": "A Metrc facility license is required."}
    if not tag:
        return {"ok": False, "status": "missing_tag", "message": "A new Metrc package tag is required."}
    if not item:
        return {"ok": False, "status": "missing_item", "message": "A Metrc Item name is required."}
    if float(quantity or 0.0) <= 0:
        return {"ok": False, "status": "invalid_quantity", "message": "Package quantity must be greater than zero."}

    normalized_ingredients: list[dict[str, Any]] = []
    for ingredient in ingredients or []:
        package_label = str(ingredient.get("package_label") or ingredient.get("Package") or "").strip()
        ingredient_quantity = float(ingredient.get("quantity") or ingredient.get("Quantity") or 0.0)
        ingredient_unit = str(ingredient.get("unit") or ingredient.get("UnitOfMeasure") or unit or "").strip()
        if not package_label or ingredient_quantity <= 0 or not ingredient_unit:
            return {
                "ok": False,
                "status": "invalid_ingredient",
                "message": "Every package ingredient requires a source package label, positive quantity, and unit.",
            }
        normalized_ingredients.append(
            {
                "Package": package_label,
                "Quantity": ingredient_quantity,
                "UnitOfMeasure": normalize_metrc_unit(ingredient_unit),
            }
        )
    if not normalized_ingredients:
        return {
            "ok": False,
            "status": "missing_ingredients",
            "message": "At least one source Metrc package is required for an extraction output package.",
        }

    payload = [
        {
            "Tag": tag,
            "Location": str(location or "").strip() or None,
            "Sublocation": None,
            "Item": item,
            "Quantity": float(quantity),
            "UnitOfMeasure": normalize_metrc_unit(unit),
            "PatientLicenseNumber": None,
            "Note": str(note or "").strip() or None,
            "IsProductionBatch": bool(production_batch_number),
            "ProductionBatchNumber": str(production_batch_number or "").strip() or None,
            "IsDonation": False,
            "IsTradeSample": False,
            "IsFinishedGood": is_finished_good,
            "ProductRequiresRemediation": False,
            "UseSameItem": False,
            "ActualDate": (actual_date or date.today()).isoformat(),
            "ExpirationDate": expiration_date.isoformat() if expiration_date else None,
            "SellByDate": None,
            "UseByDate": None,
            "Ingredients": normalized_ingredients,
        }
    ]
    result = _request(
        "POST",
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        path="packages/v2/",
        params={"licenseNumber": license_number},
        json_payload=payload,
        timeout_seconds=timeout_seconds,
    )
    if result.get("ok"):
        result["message"] = "Metrc package creation succeeded."
        payload_result = result.get("payload")
        if isinstance(payload_result, dict):
            ids = payload_result.get("Ids")
            if isinstance(ids, list) and ids:
                result["external_reference"] = str(ids[0])
    return result
