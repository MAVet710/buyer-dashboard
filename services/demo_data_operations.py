"""Linked extraction and production demo data for the simulated cannabis company."""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

_SCALE_LIMITS = {"small": 8, "medium": 24, "enterprise": 72}
_METHODS = ["BHO", "Rosin", "Ethanol", "CO2"]
_OUTPUT_BY_METHOD = {
    "BHO": ("Live Resin", 15.5, 20.0),
    "Rosin": ("Hash Rosin", 7.8, 42.0),
    "Ethanol": ("Distillate", 13.5, 9.0),
    "CO2": ("CO2 Oil", 11.5, 10.0),
}


def _catalog_frame(buyer: dict[str, Any] | None) -> pd.DataFrame:
    if buyer and isinstance(buyer.get("catalog"), pd.DataFrame) and not buyer["catalog"].empty:
        return buyer["catalog"].copy()
    return pd.DataFrame([{
        "sku": "DL-FL-0001", "product_name": "Veteran Grown Blue Dream Flower 3.5g",
        "category": "flower", "size_label": "3.5g", "unit_size_g": 3.5,
        "strain": "Blue Dream", "strain_type": "hybrid", "brand": "Veteran Grown",
        "vendor": "Atlantic Cultivation", "batch": "BATCH-0001",
        "package_id": "1A406030000000100001", "coa_id": "COA-00001",
        "source_extraction_batch": "EXT-0001", "source_production_order": "CO-00001",
        "retail_price": 38.0, "unit_cost": 15.0, "on_hand": 50,
    }])


def _extraction_inventory(catalog: pd.DataFrame, today: date, rng: random.Random,
                          problems: set[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for idx, (run_id, group) in enumerate(catalog.groupby("source_extraction_batch", sort=True)):
        first = group.iloc[0]
        current = float(rng.randint(2400, 18000))
        reserved = round(current * rng.uniform(0.0, 0.28), 1)
        status = "Available"
        if "material_shortage" in problems and idx % 5 == 0:
            current, reserved, status = float(rng.randint(120, 520)), round(current * 0.75, 1), "Reserved"
        if "qa_hold" in problems and idx % 9 == 0:
            status = "Quarantine"
        input_batch = f"MAT-{idx + 1:04d}"
        input_metrc = f"1A406030000{idx + 500000:09d}"
        rows.append({
            "received_date": (today - timedelta(days=8 + (idx * 7) % 95)).isoformat(),
            "material_name": f"{first['strain']} cured biomass",
            "material_type": "Cured Biomass" if idx % 4 else "Fresh Frozen",
            "strain": first["strain"], "source_vendor": first["vendor"],
            "batch_id_internal": input_batch, "metrc_package_id": input_metrc,
            "input_category": "Cannabis", "current_weight_g": current,
            "reserved_weight_g": reserved, "available_weight_g": max(current - reserved, 0.0),
            "cost_per_g": round(rng.uniform(0.65, 1.85), 2), "total_cost": 0.0,
            "status": status, "storage_location": "Freezer A" if idx % 4 == 0 else "Secure Bulk Vault",
            "intended_method": _METHODS[idx % len(_METHODS)],
            "notes": f"Feeds extraction run {run_id}; synthetic demo traceability record.",
            "linked_extraction_run": run_id,
        })
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["total_cost"] = frame["current_weight_g"] * frame["cost_per_g"]
    return frame


def _extraction_runs(catalog: pd.DataFrame, inventory: pd.DataFrame, today: date,
                     rng: random.Random, problems: set[str], run_limit: int,
                     profile: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped = list(catalog.groupby("source_extraction_batch", sort=True))[:run_limit]
    for idx, (run_id, group) in enumerate(grouped):
        first, inv = group.iloc[0], inventory.iloc[idx % len(inventory)]
        method = _METHODS[idx % len(_METHODS)]
        output_type, expected_yield, market_price = _OUTPUT_BY_METHOD[method]
        input_weight = float(min(inv["current_weight_g"] * 0.35, rng.randint(1400, 7200)))
        yield_pct = max(3.0, expected_yield + rng.uniform(-2.4, 2.1))
        if "low_yield" in problems and idx % 4 == 0:
            yield_pct = max(3.0, expected_yield * 0.55)
        finished = round(input_weight * yield_pct / 100.0, 1)
        qa_hold = bool("qa_hold" in problems and idx % 6 == 0)
        failed = bool("failed_coa" in problems and idx % 8 == 0)
        coa_status = "Failed" if failed else ("Pending" if qa_hold or idx % 7 == 0 else "Passed")
        status = "Hold" if qa_hold or failed else ("Complete" if idx % 5 != 0 else "Processing")
        processing_cost = round(rng.uniform(260, 950), 2)
        raw_cost = round(input_weight * float(inv["cost_per_g"]), 2)
        packaging_cost = round(max(finished, 1.0) * rng.uniform(0.12, 0.55), 2)
        labor_cost, overhead = round(rng.uniform(180, 620), 2), round(rng.uniform(90, 340), 2)
        total_cogs = raw_cost + processing_cost + packaging_cost + labor_cost + overhead
        revenue = round(finished * market_price, 2)
        gross_profit = revenue - total_cogs
        final_package = str(first["package_id"])
        rows.append({
            "run_date": (today - timedelta(days=(idx * 4) % 70)).isoformat(),
            "state": profile.get("state", "MA"),
            "license_name": profile.get("facility_name", "South Coast Production Campus"),
            "client_name": "In House", "batch_id_internal": run_id,
            "metrc_package_id_input": inv["metrc_package_id"], "metrc_package_id_output": final_package,
            "metrc_manifest_or_transfer_id": f"TR-{idx + 2000:06d}", "method": method,
            "workflow_template": "Hydrocarbon" if method == "BHO" else method,
            "product_type": output_type, "finished_product_type": output_type,
            "intermediate_product_type": "Crude Oil" if method in {"BHO", "Ethanol", "CO2"} else "Bubble Hash",
            "final_product_type": output_type, "downstream_product": output_type,
            "packaging_mode": "Concentrate / Dabs",
            "process_stage": "Final Output" if status == "Complete" else "Post-Process",
            "input_material_type": inv["material_type"], "input_weight_g": input_weight,
            "intermediate_output_g": round(finished * 1.12, 1), "finished_output_g": finished,
            "residual_loss_g": max(0.0, round(input_weight - finished, 1)), "yield_pct": round(yield_pct, 2),
            "post_process_efficiency_pct": round(rng.uniform(88.0, 98.0), 2),
            "operator": ["A. Rivera", "J. Santos", "M. Costa", "T. Nguyen"][idx % 4],
            "machine_line": f"Extraction Line {idx % 3 + 1}", "status": status,
            "toll_processing": False, "processing_fee_usd": 0.0,
            "est_revenue_usd": revenue, "estimated_revenue_usd": revenue,
            "cogs_usd": round(total_cogs, 2), "total_cogs_usd": round(total_cogs, 2),
            "raw_material_cogs_usd": raw_cost, "processing_cogs_usd": processing_cost,
            "packaging_cogs_usd": packaging_cost, "labor_cogs_usd": labor_cost,
            "overhead_cogs_usd": overhead, "unit_size_g": 1.0, "unit_price_usd": market_price,
            "units_per_batch": int(finished), "usable_output_g": finished,
            "cost_per_gram": round(total_cogs / max(finished, 1.0), 2),
            "market_price_per_gram": market_price, "gross_profit_usd": round(gross_profit, 2),
            "gross_margin_pct": round(gross_profit / revenue * 100.0, 2) if revenue else 0.0,
            "coa_status": coa_status, "qa_hold": qa_hold, "ready_for_transfer": coa_status == "Passed",
            "source_inventory_batch_id": inv["batch_id_internal"],
            "source_inventory_metrc_id": inv["metrc_package_id"],
            "source_material_name": inv["material_name"],
            "source_inventory_batch_ids": json.dumps([inv["batch_id_internal"]]),
            "source_inventory_metrc_ids": json.dumps([inv["metrc_package_id"]]),
            "allocated_input_weight_g": input_weight, "allocated_input_cost_total": raw_cost,
            "inventory_linked": True, "metrc_input_package_id": inv["metrc_package_id"],
            "metrc_final_package_id": final_package, "metrc_stage_input_id": inv["metrc_package_id"],
            "metrc_stage_output_id": final_package,
            "extraction_output_g": round(finished * 1.20, 1),
            "post_process_output_g": round(finished * 1.08, 1),
            "final_output_g": finished, "final_yield_pct": round(yield_pct, 2),
            "notes": f"Creates products: {', '.join(group['sku'].astype(str).head(5))}",
        })
    return pd.DataFrame(rows)


def _jobs(runs: pd.DataFrame, today: date, problems: set[str]) -> pd.DataFrame:
    rows = []
    for idx, client in enumerate(["Harbor Wellness", "Berkshire Brands", "Cape Select", "Pioneer Processing"]):
        at_risk = "late_po" in problems and idx == 0
        rows.append({
            "client_name": client, "state": "MA", "license_or_registration": f"MP28{2100 + idx}",
            "metrc_transfer_id": f"TR-TOLL-{4100 + idx}",
            "material_received_date": (today - timedelta(days=10 + idx)).isoformat(),
            "promised_completion_date": (today - timedelta(days=1) if at_risk else today + timedelta(days=3 + idx)).isoformat(),
            "method": _METHODS[idx % len(_METHODS)], "input_weight_g": 2400 + idx * 800,
            "expected_output_g": 310 + idx * 85, "actual_output_g": 0 if idx < 2 else 360 + idx * 70,
            "sla_status": "At Risk" if at_risk else "On Track",
            "invoice_status": "Overdue" if at_risk else ("Sent" if idx < 2 else "Paid"),
            "payment_status": "Pending" if idx < 2 else "Paid", "coa_status": "Pending" if idx < 2 else "Passed",
            "job_status": "Processing" if idx == 0 else ("Queued" if idx == 1 else "Complete"),
            "linked_run": str(runs.iloc[idx % len(runs)]["batch_id_internal"]) if not runs.empty else "",
        })
    return pd.DataFrame(rows)


def _coman_blueprint(catalog: pd.DataFrame, inventory: pd.DataFrame, runs: pd.DataFrame,
                     today: date, problems: set[str], profile: dict[str, Any], scale: str) -> dict[str, Any]:
    product_limit = {"small": 8, "medium": 24, "enterprise": 60}.get(scale, 24)
    products = catalog.head(product_limit).to_dict("records")
    unique_orders = [group.iloc[0].to_dict() for _, group in catalog.head(product_limit).groupby("source_production_order", sort=True)]
    statuses = ["complete", "scheduled", "in_progress", "on_hold", "draft"]
    orders = []
    for idx, p in enumerate(unique_orders):
        status = "on_hold" if "machine_downtime" in problems and idx == 1 else statuses[idx % len(statuses)]
        due = today - timedelta(days=5) if "late_po" in problems and idx == 0 else today + timedelta(days=(idx - 2) * 2)
        if "late_po" in problems and idx == 0:
            status = "scheduled"
        requested = max(100, int(1600 / max(float(p.get("unit_size_g") or 1.0), 0.5)))
        orders.append({
            "order_number": p["source_production_order"], "work_type": "external" if idx % 4 == 0 else "internal",
            "customer_name": ["Harbor Wellness", "Cape Select", "Berkshire Brands"][idx % 3],
            "product_name": p["product_name"], "sku": p["sku"], "product_format": p["category"],
            "requested_units": requested, "actual_units": int(requested * 0.97) if status == "complete" else 0,
            "scrap_units": int(requested * 0.018) if status == "complete" else 0,
            "rework_units": int(requested * 0.008) if status == "complete" else 0,
            "status": status, "priority": "urgent" if due < today else "normal",
            "due_at": datetime.combine(due, datetime.min.time(), tzinfo=timezone.utc),
            "source_lot_reference": p["source_extraction_batch"],
            "finished_package_id": p["package_id"], "coa_id": p["coa_id"],
            "notes": "Synthetic interconnected demo production order.",
        })
    return {
        "profile": profile,
        "customers": [
            {"name": "Harbor Wellness", "license_or_registration": "MR281101", "contact_name": "Maya Chen", "contact_email": "maya@example.invalid"},
            {"name": "Cape Select", "license_or_registration": "MR281102", "contact_name": "Luis Pereira", "contact_email": "luis@example.invalid"},
            {"name": "Berkshire Brands", "license_or_registration": "MR281103", "contact_name": "Jordan Reed", "contact_email": "jordan@example.invalid"},
        ],
        "products": products, "orders": orders,
        "input_inventory": inventory.to_dict("records"), "extraction_runs": runs.to_dict("records"),
        "machines": [
            {"manufacturer": "DemoWorks", "model": "PouchPro 900", "category": "Packaging", "asset_code": "PKG-01", "display_name": "Pouch Line 1", "rate": 720.0, "crew": 3, "active": "machine_downtime" not in problems},
            {"manufacturer": "DemoWorks", "model": "RollMaster 1200", "category": "Pre-Roll", "asset_code": "PR-01", "display_name": "Pre-Roll Line 1", "rate": 980.0, "crew": 4, "active": True},
        ],
        "crew": [{"work_date": today + timedelta(days=i), "shift_name": "Day", "available_people": 5 if i % 5 else 3, "shift_hours": 8.0, "notes": "Demo capacity plan"} for i in range(14)],
        "problems": sorted(problems), "scale": scale,
    }


def build_operations_demo(today: date, *, buyer: dict[str, Any] | None = None,
                          scale: str = "medium", seed: int = 710,
                          history_seed: int | None = None,
                          problems: set[str] | None = None) -> dict[str, Any]:
    problems = set(problems or set())
    rng = random.Random(seed + 303 if history_seed is None else history_seed)
    catalog = _catalog_frame(buyer)
    profile = dict((buyer or {}).get("company_profile") or {})
    inventory = _extraction_inventory(catalog, today, rng, problems)
    runs = _extraction_runs(catalog, inventory, today, rng, problems, _SCALE_LIMITS.get(scale, 24), profile)
    jobs = _jobs(runs, today, problems)
    return {
        "extraction_inventory": inventory, "extraction_runs": runs,
        "extraction_jobs": jobs,
        "coman_blueprint": _coman_blueprint(catalog, inventory, runs, today, problems, profile, scale),
    }
