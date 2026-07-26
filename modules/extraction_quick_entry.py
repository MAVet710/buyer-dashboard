"""Small, task-focused helpers for fast extraction run capture."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Sequence


def stage_completion_flags(stages: Sequence[str], current_stage: str) -> dict[str, bool]:
    normalized = [str(stage) for stage in stages]
    current_index = normalized.index(current_stage) if current_stage in normalized else 0

    def passed_exact(stage_name: str) -> bool:
        return stage_name in normalized and current_index > normalized.index(stage_name)

    final_output = current_stage == "Final Output"
    extraction_index = next(
        (
            index
            for index, stage in enumerate(normalized)
            if any(term in stage.lower() for term in ("extract", "wash", "press"))
        ),
        1,
    )
    post_process_index = next(
        (
            index
            for index, stage in enumerate(normalized)
            if any(
                term in stage.lower()
                for term in ("post-process", "winter", "filter", "refinement", "purge")
            )
        ),
        len(normalized),
    )
    return {
        "intake_complete": current_index > 0,
        "extraction_complete": current_index > extraction_index,
        "post_process_complete": current_index > post_process_index,
        "formulation_complete": passed_exact("Formulation"),
        "filling_complete": passed_exact("Filling / Packaging"),
        "packaging_complete": final_output,
        "ready_for_transfer": final_output,
    }


def build_quick_run_record(
    *,
    run_date: date | datetime | str,
    state: str,
    client_name: str,
    batch_id_internal: str,
    method: str,
    workflow_template: str,
    product_type: str,
    input_material_type: str,
    input_weight_g: float,
    operator: str = "",
    machine_line: str = "",
    metrc_input_package_id: str = "",
    toll_processing: bool = False,
) -> dict[str, Any]:
    """Build a safe intake-stage record that the full ECC schema can enrich."""
    return {
        "run_date": str(run_date),
        "state": state,
        "license_name": "",
        "client_name": client_name.strip() or "In House",
        "batch_id_internal": batch_id_internal.strip(),
        "method": method,
        "workflow_template": workflow_template,
        "product_type": product_type,
        "finished_product_type": product_type,
        "final_product_type": product_type,
        "downstream_product": "N/A",
        "process_stage": "Intake",
        "input_material_type": input_material_type,
        "input_weight_g": float(input_weight_g),
        "intermediate_output_g": 0.0,
        "finished_output_g": 0.0,
        "residual_loss_g": 0.0,
        "yield_pct": 0.0,
        "post_process_efficiency_pct": 0.0,
        "operator": operator.strip(),
        "machine_line": machine_line.strip(),
        "metrc_package_id_input": metrc_input_package_id.strip(),
        "metrc_input_package_id": metrc_input_package_id.strip(),
        "status": "Queued",
        "toll_processing": bool(toll_processing),
        "processing_fee_usd": 0.0,
        "est_revenue_usd": 0.0,
        "cogs_usd": 0.0,
        "coa_status": "Pending",
        "qa_hold": False,
        "notes": "",
        **stage_completion_flags(["Intake"], "Intake"),
    }


def quick_stage_weight_updates(stage: str, output_weight_g: float) -> dict[str, float]:
    """Map one observed stage output into the appropriate mass-balance fields."""
    weight = float(output_weight_g)
    stage_lower = stage.lower()
    if "final" in stage_lower or "filling" in stage_lower or "packaging" in stage_lower:
        return {
            "final_output_g": weight,
            "finished_output_g": weight,
        }
    if "distill" in stage_lower:
        return {
            "distillation_output_g": weight,
            "intermediate_output_g": weight,
        }
    if any(
        term in stage_lower
        for term in (
            "post-process",
            "winter",
            "filter",
            "refinement",
            "purge",
            "solvent recovery",
            "decarb",
        )
    ):
        return {
            "post_process_output_g": weight,
            "intermediate_output_g": weight,
        }
    return {
        "extraction_output_g": weight,
        "intermediate_output_g": weight,
    }
