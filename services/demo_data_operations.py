"""Linked extraction and operational demo data for the simulated company."""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from typing import Any

import pandas as pd

_METHODS = ["BHO", "Rosin", "Ethanol", "CO2"]
_OUTPUTS = {"BHO": "Live Resin", "Rosin": "Hash Rosin", "Ethanol": "Distillate", "CO2": "CO2 Oil"}
_MATERIALS = {"BHO": "Fresh Frozen", "Rosin": "Fresh Frozen", "Ethanol": "Trim", "CO2": "Cured Biomass"}


def _records(catalog: Any) -> list[dict[str, Any]]:
    if isinstance(catalog, pd.DataFrame):
        return catalog.to_dict("records")
    return list(catalog or [])


def build_operations_demo(today: date, *, catalog: Any = None, scale: str = "medium",
                          seed: int = 710, company: dict[str, Any] | None = None,
                          problems: set[str] | None = None) -> dict[str, Any]:
    rng, problems = random.Random(seed + 41), set(problems or set())
    products = _records(catalog)
    company = company or {"company_name": "DoobieLogic Cannabis Group", "facility_name": "South Coast Production Campus", "license_number": "MP281999"}
    run_ids = sorted({str(p.get("source_extraction_batch") or "") for p in products if p.get("source_extraction_batch")})
    if not run_ids:
        run_ids = [f"EXT-{i:04d}" for i in range(1, 8)]

    inventory_rows, run_rows = [], []
    for idx, run_id in enumerate(run_ids):
        method = _METHODS[idx % len(_METHODS)]
        input_g = float(rng.randint(2600, 14500))
        base_yield = {"BHO": 15.5, "Rosin": 7.8, "Ethanol": 14.2, "CO2": 11.8}[method]
        yield_pct = round(max(4.0, rng.gauss(base_yield, 1.4)), 2)
        if "low_yield" in problems and idx % 4 == 0:
            yield_pct = round(max(3.0, yield_pct * 0.55), 2)
        output_g = round(input_g * yield_pct / 100.0, 2)
        received = today - timedelta(days=8 + (idx * 9) % 110)
        reserved = round(input_g * (0.20 if idx % 3 == 0 else 0.0), 2)
        if "material_shortage" in problems and idx % 5 == 0:
            input_g = float(rng.randint(180, 600))
            reserved = round(input_g * 0.75, 2)
        available = max(0.0, input_g - reserved)
        metrc_input = f"1A406030000EXT{idx + 100000:08d}"
        metrc_output = f"1A406030000OUT{idx + 100000:08d}"
        cost_per_g = round(rng.uniform(0.65, 2.25), 2)
        inventory_rows.append({
            "received_date": received.isoformat(), "material_name": f"{run_id} {_MATERIALS[method]}",
            "material_type": _MATERIALS[method], "strain": products[idx % len(products)].get("strain", "Mixed") if products else "Mixed",
            "source_vendor": products[idx % len(products)].get("vendor", "Demo Cultivation") if products else "Demo Cultivation",
            "batch_id_internal": f"MAT-{idx + 1:04d}", "metrc_package_id": metrc_input,
            "input_category": "Cannabis Input", "current_weight_g": input_g, "reserved_weight_g": reserved,
            "available_weight_g": available, "cost_per_g": cost_per_g, "total_cost": round(input_g * cost_per_g, 2),
            "status": "Quarantine" if "qa_hold" in problems and idx % 5 == 0 else ("Reserved" if reserved else "Available"),
            "storage_location": f"Freezer-{idx % 4 + 1}" if method in {"BHO", "Rosin"} else f"Vault-{idx % 3 + 1}",
            "intended_method": method, "notes": f"Synthetic demo lot linked to {run_id}",
        })
        output_value_per_g = {"Live Resin": 20.0, "Hash Rosin": 42.0, "Distillate": 9.0, "CO2 Oil": 10.0}[_OUTPUTS[method]]
        operational_cost = round(rng.uniform(240, 1150), 2)
        cogs = round(input_g * cost_per_g + operational_cost, 2)
        revenue = round(output_g * output_value_per_g, 2)
        qa_hold = "qa_hold" in problems and idx % 5 == 0
        coa_status = "Failed" if "failed_coa" in problems and idx % 7 == 0 else ("Pending" if qa_hold or idx % 6 == 0 else "Passed")
        if "negative_margin" in problems and idx % 8 == 0:
            cogs = round(revenue * 1.12, 2)
        gross_profit = revenue - cogs
        run_date = today - timedelta(days=(idx * 5) % 90)
        linked_products = [p for p in products if p.get("source_extraction_batch") == run_id]
        product_orders = sorted({p.get("source_production_order") for p in linked_products if p.get("source_production_order")})
        run_rows.append({
            "run_date": run_date.isoformat(), "state": "MA", "license_name": company["facility_name"],
            "client_name": "In House" if idx % 4 else "Atlantic Toll Processing Client",
            "batch_id_internal": run_id, "metrc_package_id_input": metrc_input, "metrc_package_id_output": metrc_output,
            "metrc_manifest_or_transfer_id": f"MAN-EXT-{idx + 1:05d}", "method": method,
            "product_type": _OUTPUTS[method], "downstream_product": _OUTPUTS[method],
            "finished_product_type": _OUTPUTS[method], "final_product_type": _OUTPUTS[method],
            "process_stage": "QA Hold" if qa_hold else ("Final Output" if idx % 3 else "Filling / Packaging"),
            "input_material_type": _MATERIALS[method], "input_weight_g": input_g,
            "intermediate_output_g": round(output_g * 1.08, 2), "finished_output_g": output_g,
            "residual_loss_g": round(max(0.0, input_g - output_g), 2), "yield_pct": yield_pct,
            "post_process_efficiency_pct": round(rng.uniform(86, 98), 2), "operator": f"Operator {idx % 6 + 1}",
            "machine_line": f"Line {idx % 3 + 1}", "status": "Hold" if qa_hold else ("Complete" if idx % 3 else "Packaging"),
            "toll_processing": idx % 4 == 0, "processing_fee_usd": 1800.0 if idx % 4 == 0 else 0.0,
            "est_revenue_usd": revenue, "estimated_revenue_usd": revenue, "cogs_usd": cogs, "total_cogs_usd": cogs,
            "raw_material_cogs_usd": round(input_g * cost_per_g, 2), "processing_cogs_usd": operational_cost,
            "packaging_cogs_usd": round(output_g * 0.18, 2), "labor_cogs_usd": round(operational_cost * 0.42, 2),
            "overhead_cogs_usd": round(operational_cost * 0.21, 2), "unit_size_g": 1.0,
            "unit_price_usd": output_value_per_g, "units_per_batch": int(output_g), "packaging_yield_loss_g": round(output_g * 0.015, 2),
            "coa_status": coa_status, "qa_hold": qa_hold, "notes": f"Feeds production orders: {', '.join(product_orders) or 'demo queue'}",
            "source_inventory_batch_id": f"MAT-{idx + 1:04d}", "source_inventory_metrc_id": metrc_input,
            "source_material_name": f"{run_id} {_MATERIALS[method]}",
            "source_inventory_batch_ids": json.dumps([f"MAT-{idx + 1:04d}"]),
            "source_inventory_metrc_ids": json.dumps([metrc_input]), "inventory_linked": True,
            "allocated_input_weight_g": input_g, "allocated_input_cost_total": round(input_g * cost_per_g, 2),
            "input_cost_total": round(input_g * cost_per_g, 2), "operational_cost_total": operational_cost,
            "total_cost": cogs, "cost_per_gram": round(cogs / output_g, 2) if output_g else 0.0,
            "market_price_per_gram": output_value_per_g, "estimated_value_usd": revenue,
            "margin_per_gram": round(gross_profit / output_g, 2) if output_g else 0.0,
            "total_profit_usd": gross_profit, "margin_pct_est": round(gross_profit / revenue * 100, 2) if revenue else 0.0,
            "value_risk_flag": "Critical" if gross_profit < 0 else ("Warning" if gross_profit / max(revenue, 1) < 0.10 else "Healthy"),
            "unmapped_output_type": False, "output_mapping_warning": "", "normalized_output_type": _OUTPUTS[method],
            "usable_output_g": round(output_g * 0.985, 2), "bulk_estimated_value_usd": revenue,
            "packaged_estimated_revenue_usd": revenue, "revenue_per_gram_realized": output_value_per_g,
            "cost_per_unit": round(cogs / max(int(output_g), 1), 2), "gross_profit_usd": gross_profit,
            "gross_margin_pct": round(gross_profit / revenue * 100, 2) if revenue else 0.0,
            "packaging_mode": "Concentrate / Dabs", "packaging_warning": "",
            "metrc_input_package_id": metrc_input, "metrc_final_package_id": metrc_output,
            "metrc_stage_input_id": metrc_input, "metrc_stage_output_id": metrc_output,
        })

    jobs = []
    for idx in range(max(4, len(run_rows) // 4)):
        promised = today + timedelta(days=idx * 3 - (2 if "late_jobs" in problems and idx == 0 else 0))
        method = _METHODS[idx % len(_METHODS)]
        jobs.append({
            "client_name": ["Atlantic Wellness", "Cape Craft", "Berkshire Brands", "Merrimack Medicinals"][idx % 4],
            "state": "MA", "license_or_registration": f"MC281{idx + 100:03d}",
            "metrc_transfer_id": f"XFER-{idx + 1:05d}", "material_received_date": (today - timedelta(days=8 + idx)).isoformat(),
            "promised_completion_date": promised.isoformat(), "method": method, "input_weight_g": 4500 + idx * 500,
            "expected_output_g": 650 + idx * 60, "actual_output_g": 0 if idx % 3 == 0 else 620 + idx * 55,
            "sla_status": "At Risk" if promised < today or ("late_jobs" in problems and idx == 0) else "On Track",
            "invoice_status": "Overdue" if "overdue_invoice" in problems and idx == 1 else ("Paid" if idx % 3 == 2 else "Sent"),
            "payment_status": "Pending" if idx % 3 == 0 else "Paid", "coa_status": "Pending" if idx % 3 == 0 else "Passed",
            "job_status": "Processing" if idx % 3 == 0 else "Complete",
        })

    return {
        "extraction_inventory": pd.DataFrame(inventory_rows),
        "extraction_runs": pd.DataFrame(run_rows),
        "extraction_jobs": pd.DataFrame(jobs),
    }
