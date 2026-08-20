"""Compatibility bridge between legacy Extraction UI and durable Extraction ERP.

The legacy Streamlit command center remains a compatibility surface while durable
Extraction owns run history and the shared Co-Man lot ledger owns inventory.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, MutableMapping

import pandas as pd
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import sessionmaker

from modules.coman.db import ComanDatabaseConfigurationError, create_coman_engine
from modules.coman.models import InventoryLot
from modules.extraction.models import (
    ExtractionCostEvent,
    ExtractionRun,
    ExtractionRunInput,
    ExtractionRunOutput,
    ExtractionStageEvent,
)
from modules.extraction.repository import ExtractionRepository
from modules.extraction.workflows import get_extraction_workflow


_BEFORE_ROWS = "_extraction_durable_before_rows"


def _scope(state: MutableMapping[str, Any]) -> tuple[str, str]:
    return (
        str(state.get("active_organization_id") or "").strip(),
        str(state.get("active_facility_id") or "").strip(),
    )


def _actor(state: MutableMapping[str, Any]) -> str:
    return str(
        state.get("auth_username")
        or state.get("auth_user_email")
        or state.get("display_user")
        or "legacy-extraction"
    ).strip()


def _sandbox_active(state: MutableMapping[str, Any]) -> bool:
    return bool(
        state.get("demo_mode_enabled")
        or state.get("_full_app_demo_version")
        or state.get("_sandbox_supabase_restored")
    )


def _engine_if_ready(state: MutableMapping[str, Any]):
    organization_id, facility_id = _scope(state)
    if not organization_id or not facility_id or _sandbox_active(state):
        return None
    try:
        engine = create_coman_engine()
        if not inspect(engine).has_table("extraction_runs"):
            return None
        return engine
    except (ComanDatabaseConfigurationError, Exception):
        return None


def _safe_float(value: Any) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    return float(parsed) if pd.notna(parsed) else 0.0


def _row_hash(row: pd.Series | dict[str, Any]) -> str:
    record = row.to_dict() if isinstance(row, pd.Series) else dict(row)
    keys = (
        "process_stage",
        "status",
        "qa_hold",
        "coa_status",
        "input_weight_g",
        "extraction_output_g",
        "post_process_output_g",
        "distillation_output_g",
        "final_output_g",
        "finished_output_g",
        "residual_loss_g",
        "notes",
        "raw_material_cogs_usd",
        "processing_cogs_usd",
        "packaging_cogs_usd",
        "labor_cogs_usd",
        "overhead_cogs_usd",
    )
    payload = {key: record.get(key) for key in keys}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _is_known_seed_row(row: pd.Series | dict[str, Any]) -> bool:
    record = row.to_dict() if isinstance(row, pd.Series) else dict(row)
    batch = str(record.get("batch_id_internal") or "").strip()
    license_name = str(record.get("license_name") or "").strip()
    notes = str(record.get("notes") or "").casefold()
    return bool(
        license_name == "Example Lab"
        or batch in {"BHO-0001", "ETH-0001"}
        or "sample seed record" in notes
        or "seed ethanol record" in notes
    )


def _workflow_key(record: dict[str, Any]) -> str:
    explicit = str(record.get("workflow_template") or "").strip().casefold()
    aliases = {
        "bho_live_resin": "bho_live_resin",
        "bho cured": "bho_cured",
        "bho_cured": "bho_cured",
        "ethanol": "ethanol_crude",
        "ethanol_crude": "ethanol_crude",
        "distillation": "crude_distillate",
        "crude_distillate": "crude_distillate",
        "solventless": "ice_water_hash",
        "ice_water_hash": "ice_water_hash",
        "rosin": "hash_rosin",
        "hash_rosin": "hash_rosin",
        "formulation": "rosin_vape",
        "rosin_vape": "rosin_vape",
        "co2": "co2_extract",
        "co2_extract": "co2_extract",
    }
    if explicit in aliases:
        return aliases[explicit]
    method = str(record.get("method") or "").strip().casefold()
    material = str(record.get("input_material_type") or "").strip().casefold()
    product = " ".join(
        str(record.get(key) or "")
        for key in ("product_type", "final_product_type", "finished_product_type")
    ).casefold()
    if "distill" in method or "distill" in product:
        return "crude_distillate"
    if "rosin" in method:
        return "hash_rosin"
    if "solventless" in method or "hash" in method:
        return "ice_water_hash"
    if "ethanol" in method:
        return "ethanol_crude"
    if "co2" in method:
        return "co2_extract"
    if "formulation" in method or "vape" in product:
        return "rosin_vape"
    if "bho" in method or "hydrocarbon" in method:
        return "bho_live_resin" if "fresh" in material or "live" in product else "bho_cured"
    return "bho_cured"


def _legacy_stage_key(workflow_key: str, process_stage: str) -> str:
    workflow = get_extraction_workflow(workflow_key)
    text = str(process_stage or "").strip().casefold()
    direct = text.replace(" / ", "_").replace(" ", "_").replace("-", "_")
    if workflow.has_stage(direct):
        return direct
    keyword_candidates = (
        (("qa", "coa", "awaiting qa"), "qa"),
        (("release", "complete", "final output"), "release"),
        (("fill", "packag"), "packaging"),
        (("formulat",), "formulation"),
        (("distill",), "distillation"),
        (("recover",), "recovery"),
        (("winter", "filter"), "filtration"),
        (("post", "purge", "refin", "cure"), "post_process"),
        (("press",), "press"),
        (("wash",), "wash"),
        (("collect",), "collection"),
        (("dry",), "drying"),
        (("separat",), "separation"),
        (("extract",), "extraction"),
        (("intake", "stage"), "intake"),
    )
    for terms, candidate in keyword_candidates:
        if any(term in text for term in terms) and workflow.has_stage(candidate):
            return candidate
    return workflow.first_stage


def _legacy_status(run: ExtractionRun) -> str:
    return {
        "planned": "Queued",
        "queued": "Queued",
        "active": "Processing",
        "hold": "Hold",
        "qa": "Processing",
        "complete": "Complete",
        "cancelled": "Failed",
        "failed": "Failed",
    }.get(run.status, "Processing")


def _legacy_coa(outputs: list[ExtractionRunOutput]) -> str:
    active = [output for output in outputs if output.status not in {"waste", "destroyed"}]
    if not active:
        return "Pending"
    statuses = {output.coa_status for output in active}
    if "failed" in statuses:
        return "Failed"
    if statuses <= {"passed"}:
        return "Passed"
    if statuses == {"not_submitted"}:
        return "Not Submitted"
    return "Pending"


def _durable_run_frame(engine, organization_id: str, facility_id: str) -> pd.DataFrame:
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with session_factory() as session:
        runs = list(
            session.scalars(
                select(ExtractionRun)
                .where(
                    ExtractionRun.organization_id == organization_id,
                    ExtractionRun.facility_id == facility_id,
                )
                .order_by(ExtractionRun.created_at)
            )
        )
        rows: list[dict[str, Any]] = []
        for run in runs:
            inputs = list(
                session.scalars(select(ExtractionRunInput).where(ExtractionRunInput.run_id == run.id))
            )
            outputs = list(
                session.scalars(select(ExtractionRunOutput).where(ExtractionRunOutput.run_id == run.id))
            )
            stages = list(
                session.scalars(
                    select(ExtractionStageEvent)
                    .where(ExtractionStageEvent.run_id == run.id)
                    .order_by(ExtractionStageEvent.occurred_at)
                )
            )
            cost_rows = session.execute(
                select(
                    ExtractionCostEvent.category,
                    func.coalesce(func.sum(ExtractionCostEvent.amount_usd), 0.0),
                )
                .where(ExtractionCostEvent.run_id == run.id)
                .group_by(ExtractionCostEvent.category)
            ).all()
            cost_map = {str(category): float(amount or 0.0) for category, amount in cost_rows}
            source_lots = [session.get(InventoryLot, item.lot_id) for item in inputs]
            source_lots = [lot for lot in source_lots if lot is not None]
            consumed = sum(float(item.consumed_quantity) for item in inputs)
            reserved = sum(float(item.reserved_quantity) for item in inputs)
            finished = sum(float(item.quantity) for item in outputs if item.status != "destroyed")
            yield_pct = finished / consumed * 100.0 if consumed > 0 else 0.0
            last_stage = stages[-1] if stages else None
            workflow = get_extraction_workflow(run.workflow_key)
            source_package_ids = [lot.compliance_package_id for lot in source_lots if lot.compliance_package_id]
            source_batch_ids = [lot.lot_code for lot in source_lots if lot.lot_code]
            output_package_ids = [item.compliance_package_id for item in outputs if item.compliance_package_id]
            total_cogs = sum(cost_map.values())
            rows.append(
                {
                    "run_date": (run.started_at or run.created_at).date().isoformat(),
                    "last_updated": run.updated_at.date().isoformat(),
                    "state": "MA",
                    "license_name": run.license_number,
                    "client_name": "In House",
                    "batch_id_internal": run.batch_number,
                    "method": run.method,
                    "workflow_template": run.workflow_key,
                    "strain": run.strain,
                    "product_type": run.product_family or "Other",
                    "finished_product_type": run.product_family or "Other",
                    "final_product_type": run.product_family or "Other",
                    "downstream_product": run.product_family or "N/A",
                    "process_stage": workflow.stage_label(run.current_stage_key),
                    "run_status": run.status.title(),
                    "status": _legacy_status(run),
                    "input_material_type": "Other",
                    "input_weight_g": consumed or reserved,
                    "intermediate_output_g": float(last_stage.output_weight_g or 0.0) if last_stage else 0.0,
                    "finished_output_g": finished,
                    "final_output_g": finished,
                    "residual_loss_g": max(0.0, consumed - finished),
                    "yield_pct": yield_pct,
                    "post_process_efficiency_pct": 0.0,
                    "operator": run.operator,
                    "machine_line": "",
                    "toll_processing": run.toll_processing,
                    "processing_fee_usd": 0.0,
                    "est_revenue_usd": 0.0,
                    "estimated_revenue_usd": 0.0,
                    "cogs_usd": total_cogs,
                    "total_cogs_usd": total_cogs,
                    "raw_material_cogs_usd": cost_map.get("material", 0.0),
                    "processing_cogs_usd": cost_map.get("processing", 0.0),
                    "packaging_cogs_usd": cost_map.get("packaging", 0.0),
                    "labor_cogs_usd": cost_map.get("labor", 0.0),
                    "overhead_cogs_usd": cost_map.get("overhead", 0.0),
                    "coa_status": _legacy_coa(outputs),
                    "qa_hold": run.status == "hold",
                    "notes": run.notes,
                    "source_inventory_batch_ids": json.dumps(source_batch_ids),
                    "source_inventory_metrc_ids": json.dumps(source_package_ids),
                    "source_inventory_batch_id": source_batch_ids[0] if source_batch_ids else "",
                    "source_inventory_metrc_id": source_package_ids[0] if source_package_ids else "",
                    "allocated_input_weight_g": consumed or reserved,
                    "allocated_input_cost_total": cost_map.get("material", 0.0),
                    "inventory_linked": bool(inputs),
                    "metrc_package_id_input": source_package_ids[0] if source_package_ids else "",
                    "metrc_package_id_output": output_package_ids[0] if output_package_ids else "",
                    "metrc_input_package_id": source_package_ids[0] if source_package_ids else "",
                    "metrc_final_package_id": output_package_ids[0] if output_package_ids else "",
                    "metrc_stage_input_id": source_package_ids[0] if source_package_ids else "",
                    "metrc_stage_output_id": output_package_ids[-1] if output_package_ids else "",
                    "_durable_extraction_run_id": run.id,
                }
            )
        return pd.DataFrame(rows)


def _durable_inventory_frame(engine, organization_id: str, facility_id: str) -> pd.DataFrame:
    repo = ExtractionRepository(engine)
    values: list[dict[str, Any]] = []
    for row in repo.list_available_lots(organization_id, facility_id):
        values.append(
            {
                "received_date": "",
                "material_name": row["product_name"],
                "material_type": "Shared Inventory",
                "inventory_class": "Bulk / WIP",
                "item_type": "cannabis",
                "inventory_unit": row["unit"],
                "strain": "",
                "source_vendor": "",
                "batch_id_internal": row["lot_code"],
                "metrc_package_id": row["compliance_package_id"],
                "input_category": "Cannabis Input",
                "current_weight_g": row["balance"],
                "reserved_weight_g": row["reserved"],
                "available_weight_g": row["available"],
                "cost_per_g": row["unit_cost"],
                "total_cost": row["balance"] * row["unit_cost"],
                "status": row["status"].title(),
                "lab_status": "Passed",
                "storage_location": row["location"],
                "source_extraction_batch": "",
                "facility_name": facility_id,
                "license_number": "",
                "tags": "shared-ledger;durable",
                "intended_method": "",
                "notes": "Buyer Dash shared inventory ledger",
                "_durable_lot_id": row["lot_id"],
            }
        )
    return pd.DataFrame(values)


def prepare_extraction_runtime(streamlit_module) -> None:
    state = streamlit_module.session_state
    engine = _engine_if_ready(state)
    if engine is None:
        return
    organization_id, facility_id = _scope(state)
    try:
        durable_runs = _durable_run_frame(engine, organization_id, facility_id)
        durable_inventory = _durable_inventory_frame(engine, organization_id, facility_id)
    except Exception as exc:
        state["_extraction_runtime_error"] = f"prepare:{type(exc).__name__}:{exc}"
        return

    current_runs = state.get("ecc_run_log")
    has_non_seed_current = bool(
        isinstance(current_runs, pd.DataFrame)
        and not current_runs.empty
        and any(not _is_known_seed_row(row) for _, row in current_runs.iterrows())
    )
    if not durable_runs.empty:
        state["ecc_run_log"] = durable_runs
    elif not has_non_seed_current:
        state["ecc_run_log"] = pd.DataFrame()

    state["ecc_inventory_log"] = durable_inventory
    state.setdefault("ecc_client_jobs", pd.DataFrame())
    frame = state.get("ecc_run_log")
    before: dict[str, str] = {}
    if isinstance(frame, pd.DataFrame):
        for _, row in frame.iterrows():
            batch = str(row.get("batch_id_internal") or "").strip()
            if batch:
                before[batch] = _row_hash(row)
    state[_BEFORE_ROWS] = before
    state.pop("_extraction_runtime_error", None)


def _import_costs_once(
    repository: ExtractionRepository,
    organization_id: str,
    facility_id: str,
    run_id: str,
    record: dict[str, Any],
    actor: str,
) -> None:
    if repository.list_cost_events(organization_id, facility_id, run_id):
        return
    mapping = {
        "material": "raw_material_cogs_usd",
        "processing": "processing_cogs_usd",
        "packaging": "packaging_cogs_usd",
        "labor": "labor_cogs_usd",
        "overhead": "overhead_cogs_usd",
    }
    for category, field in mapping.items():
        amount = _safe_float(record.get(field))
        if amount > 0:
            repository.add_cost_event(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run_id,
                category=category,
                amount_usd=amount,
                actor=actor,
                source_type="legacy_import",
                notes="Imported once from legacy Extraction compatibility view.",
            )


def finalize_extraction_runtime(streamlit_module) -> None:
    state = streamlit_module.session_state
    engine = _engine_if_ready(state)
    if engine is None:
        return
    organization_id, facility_id = _scope(state)
    frame = state.get("ecc_run_log")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return
    repository = ExtractionRepository(engine)
    actor = _actor(state)
    before = dict(state.get(_BEFORE_ROWS) or {})
    try:
        for _, row in frame.iterrows():
            if _is_known_seed_row(row):
                continue
            record = row.to_dict()
            batch = str(record.get("batch_id_internal") or "").strip()
            if not batch:
                continue
            run = repository.find_run_by_batch(organization_id, facility_id, batch)
            created = False
            if run is None:
                workflow_key = _workflow_key(record)
                workflow = get_extraction_workflow(workflow_key)
                run = repository.create_run(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    batch_number=batch,
                    method=workflow.method,
                    workflow_key=workflow.key,
                    actor=actor,
                    product_family=str(
                        record.get("final_product_type")
                        or record.get("finished_product_type")
                        or record.get("product_type")
                        or ""
                    ),
                    strain=str(record.get("strain") or ""),
                    operator=str(record.get("operator") or ""),
                    license_number=str(
                        record.get("license_name")
                        or state.get("metrc_license_number")
                        or ""
                    ),
                    toll_processing=bool(record.get("toll_processing") or False),
                    notes=str(record.get("notes") or ""),
                )
                created = True
                _import_costs_once(repository, organization_id, facility_id, run.id, record, actor)

            if created or before.get(batch) != _row_hash(row):
                stage_key = _legacy_stage_key(run.workflow_key, str(record.get("process_stage") or ""))
                qa_hold = bool(record.get("qa_hold") or False)
                status_text = str(record.get("status") or "").casefold()
                event_type = "hold" if qa_hold or "hold" in status_text else "measurement"
                input_weight = _safe_float(record.get("input_weight_g"))
                output_weight = next(
                    (
                        value
                        for value in (
                            _safe_float(record.get("final_output_g")),
                            _safe_float(record.get("distillation_output_g")),
                            _safe_float(record.get("post_process_output_g")),
                            _safe_float(record.get("extraction_output_g")),
                            _safe_float(record.get("finished_output_g")),
                        )
                        if value > 0
                    ),
                    0.0,
                )
                repository.record_stage_event(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    run_id=run.id,
                    stage_key=stage_key,
                    event_type=event_type,
                    actor=actor,
                    input_weight_g=input_weight if input_weight > 0 else None,
                    output_weight_g=output_weight if output_weight > 0 else None,
                    operator=str(record.get("operator") or ""),
                    notes="Captured from legacy Extraction compatibility view.",
                )
                legacy_notes = str(record.get("notes") or "")
                if legacy_notes != str(run.notes or ""):
                    repository.update_run_notes(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        run_id=run.id,
                        notes=legacy_notes,
                        actor=actor,
                    )
        state.pop("_extraction_runtime_error", None)
    except Exception as exc:
        state["_extraction_runtime_error"] = f"finalize:{type(exc).__name__}:{exc}"
