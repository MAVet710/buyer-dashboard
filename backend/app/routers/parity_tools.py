from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import Engine

from modules.ma_flower_equivalency.logic import (
    EquivalencyValidationError,
    calculate_concentrate_equivalency,
    calculate_edible_equivalency,
    calculate_infused_preroll_equivalency,
    format_equivalency,
)
from services.nomenclature_mapper import (
    prepare_catalog,
    prepare_manifest,
    propose_new_catalog_name,
    suggest_matches,
)
from services.nomenclature_store import NomenclatureStore
from ..auth import RequestContext, get_request_context, get_retail_context
from ..database import get_engine

router = APIRouter(prefix="/parity-tools", tags=["parity-tools"], dependencies=[Depends(get_retail_context)])


class EquivalencyRequest(BaseModel):
    mode: str
    quantity: str | int | float | None = 1
    grams: str | int | float | None = None
    active_thc_mg: str | int | float | None = None
    finished_grams_per_joint: str | int | float | None = None
    infusion_grams_per_joint: str | int | float | None = None


class MappingConfirmation(BaseModel):
    source_name: str
    correct_name: str


class MappingConfirmRequest(BaseModel):
    rows: list[MappingConfirmation]


class NomenclatureExportRequest(BaseModel):
    correct_names: list[str]


class CatalogItemInput(BaseModel):
    canonical_name: str
    sku: str = ""
    category: str = ""
    brand: str = ""


class CatalogItemsRequest(BaseModel):
    rows: list[CatalogItemInput]


def _decimal(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _catalog_records(frame: pd.DataFrame, *, limit: int | None = None) -> list[dict[str, str]]:
    selected = frame if limit is None else frame.head(limit)
    rows: list[dict[str, str]] = []
    for row in selected.to_dict("records"):
        rows.append(
            {
                "canonical_name": str(row.get("canonical_name") or ""),
                "sku": str(row.get("sku") or ""),
                "category": str(row.get("category") or ""),
                "brand": str(row.get("brand") or ""),
            }
        )
    return rows


@router.post("/ma-flower-equivalency")
def ma_flower_equivalency(payload: EquivalencyRequest):
    try:
        mode = payload.mode.strip().casefold()
        if mode in {"concentrate", "vape", "concentrate_vape"}:
            result = calculate_concentrate_equivalency(payload.grams, payload.quantity)
        elif mode in {"edible", "beverage"}:
            result = calculate_edible_equivalency(payload.active_thc_mg, payload.quantity)
        elif mode in {"infused_preroll", "infused pre-roll", "infused pre roll"}:
            result = calculate_infused_preroll_equivalency(
                payload.finished_grams_per_joint,
                payload.infusion_grams_per_joint,
                payload.quantity,
            )
        else:
            raise HTTPException(422, "Choose concentrate/vape, edible/beverage, or infused pre-roll.")
    except EquivalencyValidationError as exc:
        raise HTTPException(422, exc.message) from exc
    return {
        "mode": mode,
        "quantity": result.quantity,
        "per_unit": _decimal(result.per_unit),
        "package_total": _decimal(result.package_total),
        "per_unit_display": format_equivalency(result.per_unit),
        "package_total_display": format_equivalency(result.package_total),
        "flower_weight_per_joint": _decimal(result.flower_weight_per_joint),
        "infusion_equivalency_per_joint": _decimal(result.infusion_equivalency_per_joint),
        "flower_weight_display": format_equivalency(result.flower_weight_per_joint) if result.flower_weight_per_joint is not None else None,
        "infusion_equivalency_display": format_equivalency(result.infusion_equivalency_per_joint) if result.infusion_equivalency_per_joint is not None else None,
    }


def _store(engine: Engine) -> NomenclatureStore:
    store = NomenclatureStore(engine=engine)
    if not store.configured:
        raise HTTPException(503, "Nomenclature storage is unavailable.")
    return store


@router.get("/nomenclature")
def nomenclature_status(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    store = _store(engine)
    catalog = store.list_catalog(context.organization_id)
    learned = store.learned_mappings(context.organization_id)
    return {
        "catalog_count": len(catalog),
        "mapping_count": len(learned),
        "catalog": [
            {"id": row.id, "canonical_name": row.canonical_name, "sku": row.sku, "category": row.category, "brand": row.brand}
            for row in catalog
        ],
    }


@router.post("/nomenclature/catalog/preview")
async def nomenclature_catalog_preview(file: UploadFile = File(...)):
    payload = await file.read()
    if len(payload) > 10 * 1024 * 1024:
        raise HTTPException(413, "Catalog files must be 10 MB or smaller.")
    try:
        frame = prepare_catalog(payload, file.filename or "catalog.csv")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "detected": len(frame),
        "preview": _catalog_records(frame, limit=100),
    }


@router.post("/nomenclature/catalog")
async def nomenclature_catalog(
    file: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    payload = await file.read()
    if len(payload) > 10 * 1024 * 1024:
        raise HTTPException(413, "Catalog files must be 10 MB or smaller.")
    try:
        frame = prepare_catalog(payload, file.filename or "catalog.csv")
        saved = _store(engine).replace_catalog(context.organization_id, frame.to_dict("records"), context.user_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"saved": saved, "preview": _catalog_records(frame, limit=100)}


@router.post("/nomenclature/catalog/items")
def nomenclature_catalog_items(
    payload: CatalogItemsRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    try:
        saved = _store(engine).add_catalog_items(
            context.organization_id,
            [row.model_dump() for row in payload.rows],
            context.user_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"saved": saved}


@router.post("/nomenclature/manifest")
async def nomenclature_manifest(
    file: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "Manifest files must be 10 MB or smaller.")
    store = _store(engine)
    records = store.list_catalog(context.organization_id)
    if not records:
        raise HTTPException(422, "Save this organization's Dutchie catalog before mapping a METRC manifest.")
    catalog = pd.DataFrame(
        [
            {
                "id": row.id,
                "canonical_name": row.canonical_name,
                "normalized_name": row.normalized_name,
                "sku": row.sku,
                "category": row.category,
                "brand": row.brand,
            }
            for row in records
        ]
    )
    try:
        manifest, item_column = prepare_manifest(raw, file.filename or "manifest.csv")
        suggestions = suggest_matches(
            manifest[item_column].fillna("").astype(str),
            catalog,
            learned_mappings=store.learned_mappings(context.organization_id),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    by_source = {row.source_name: row for row in suggestions}
    manifest_rows = []
    for source in manifest[item_column].fillna("").astype(str):
        match = by_source.get(source)
        manifest_rows.append(
            {
                "source_name": source,
                "correct_name": match.correct_name if match else "",
                "status": match.status if match else "Unmatched",
                "confidence": round(float(match.confidence) * 100, 1) if match else 0,
                "match_basis": match.match_basis if match else "",
            }
        )
    return {
        "filename": file.filename or "manifest",
        "row_count": len(manifest_rows),
        "rows": manifest_rows,
        "unique_suggestions": [
            {
                "source_name": row.source_name,
                "correct_name": row.correct_name,
                "confidence": round(float(row.confidence) * 100, 1),
                "status": row.status,
                "match_basis": row.match_basis,
                "proposed_new_name": propose_new_catalog_name(row.source_name, catalog),
            }
            for row in suggestions
        ],
    }


@router.post("/nomenclature/confirm")
def nomenclature_confirm(
    payload: MappingConfirmRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    rows = [
        {"Original METRC Item": row.source_name, "Correct Item Name": row.correct_name}
        for row in payload.rows
    ]
    try:
        saved = _store(engine).confirm_mappings(context.organization_id, rows, context.user_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"saved": saved}


@router.post("/nomenclature/export")
def nomenclature_export(payload: NomenclatureExportRequest):
    if not payload.correct_names or any(not value.strip() for value in payload.correct_names):
        raise HTTPException(422, "Every manifest row needs a confirmed Correct Item Name before export.")
    output = BytesIO()
    frame = pd.DataFrame({"Correct Item Name": payload.correct_names})
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Correct Item Names")
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Correct_METRC_Item_Names.xlsx"'},
    )
