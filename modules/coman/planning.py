"""Small, deterministic Co-Man capacity calculations."""

from __future__ import annotations

import math


GRAMS_PER_POUND = 453.59237


def weight_to_grams(weight: float, unit: str) -> float:
    """Normalize common bulk-weight inputs to grams."""
    value = max(0.0, float(weight))
    normalized = str(unit or "grams").strip().lower()
    if normalized in {"lb", "lbs", "pound", "pounds"}:
        return value * GRAMS_PER_POUND
    if normalized in {"kg", "kilogram", "kilograms"}:
        return value * 1000.0
    return value


def recommend_weight_allocation(
    input_weight_g: float,
    products: list[dict],
    *,
    loss_pct: float = 0.0,
    labor_rate: float = 0.0,
    sticker_units_per_person_hour: float = 0.0,
    case_pack_units_per_person_hour: float = 0.0,
    final_cases_per_person_hour: float = 0.0,
    optimization_goal: str = "Maximum total profit",
) -> list[dict]:
    """Rank eligible finished-product scenarios and greedily allocate usable bulk.

    Product rows are deliberately plain dictionaries so the Streamlit data editor
    can remain the operator-facing source for assumptions. Bulk cost should be
    zero when customer-owned material is supplied for an external co-man job.
    """
    input_g = max(0.0, float(input_weight_g))
    usable_g = input_g * (1.0 - min(100.0, max(0.0, float(loss_pct))) / 100.0)
    hourly_labor = max(0.0, float(labor_rate))
    candidates: list[dict] = []

    for raw in products:
        if not bool(raw.get("eligible", True)):
            continue
        unit_g = float(raw.get("unit_size_g") or 0)
        if unit_g <= 0:
            continue
        max_share = min(100.0, max(0.0, float(raw.get("max_allocation_pct") or 100.0)))
        units = math.floor((usable_g * max_share / 100.0) / unit_g)
        if units <= 0:
            continue
        units_per_case = max(1, int(raw.get("units_per_case") or 1))
        cases = math.ceil(units / units_per_case)
        machine_rate = max(0.0, float(raw.get("machine_units_per_hour") or 0.0))
        machine_hours = units / machine_rate if machine_rate else 0.0
        machine_crew = max(0, int(raw.get("machine_crew") or 0))
        hand_labor_hours = 0.0
        if sticker_units_per_person_hour > 0:
            hand_labor_hours += units / float(sticker_units_per_person_hour)
        if case_pack_units_per_person_hour > 0:
            hand_labor_hours += units / float(case_pack_units_per_person_hour)
        if final_cases_per_person_hour > 0:
            hand_labor_hours += cases / float(final_cases_per_person_hour)
        machine_labor_hours = machine_hours * machine_crew
        total_labor_hours = hand_labor_hours + machine_labor_hours
        revenue = units * max(0.0, float(raw.get("revenue_per_unit") or 0.0))
        material_cost = units * unit_g * max(0.0, float(raw.get("bulk_cost_per_g") or 0.0))
        packaging_cost = units * max(0.0, float(raw.get("packaging_cost_per_unit") or 0.0))
        other_unit_cost = units * max(0.0, float(raw.get("other_cost_per_unit") or 0.0))
        machine_cost = machine_hours * max(0.0, float(raw.get("machine_cost_per_hour") or 0.0))
        labor_cost = total_labor_hours * hourly_labor
        total_cost = material_cost + packaging_cost + other_unit_cost + machine_cost + labor_cost
        profit = revenue - total_cost
        allocated_g = units * unit_g
        margin_pct = (profit / revenue * 100.0) if revenue else 0.0
        profit_per_labor_hour = profit / total_labor_hours if total_labor_hours else profit
        candidates.append(
            {
                "product": str(raw.get("product") or raw.get("format") or "Product"),
                "format": str(raw.get("format") or "Other"),
                "units": units,
                "allocated_g": allocated_g,
                "cases": cases,
                "units_per_case": units_per_case,
                "revenue": revenue,
                "total_cost": total_cost,
                "profit": profit,
                "margin_pct": margin_pct,
                "machine_hours": machine_hours,
                "hand_labor_hours": hand_labor_hours,
                "total_labor_hours": total_labor_hours,
                "profit_per_input_lb": profit / (allocated_g / GRAMS_PER_POUND),
                "profit_per_labor_hour": profit_per_labor_hour,
                "max_allocation_pct": max_share,
            }
        )

    score_key = "profit_per_labor_hour" if "labor" in optimization_goal.lower() else "profit_per_input_lb"
    candidates.sort(key=lambda row: (row[score_key], row["profit"]), reverse=True)

    remaining_g = usable_g
    recommendations: list[dict] = []
    for candidate in candidates:
        unit_g = candidate["allocated_g"] / candidate["units"]
        allowed_g = min(remaining_g, usable_g * candidate["max_allocation_pct"] / 100.0)
        allocated_units = math.floor(allowed_g / unit_g)
        if allocated_units <= 0:
            continue
        factor = allocated_units / candidate["units"]
        recommendation = dict(candidate)
        for key in ["allocated_g", "revenue", "total_cost", "profit", "machine_hours", "hand_labor_hours", "total_labor_hours"]:
            recommendation[key] = candidate[key] * factor
        recommendation["units"] = allocated_units
        recommendation["cases"] = math.ceil(allocated_units / candidate["units_per_case"])
        recommendation["recommended"] = True
        recommendations.append(recommendation)
        remaining_g -= recommendation["allocated_g"]
        if remaining_g < min((row["allocated_g"] / row["units"] for row in candidates), default=1.0):
            break
    return recommendations


def estimate_machine_job(
    requested_units: int,
    effective_units_per_hour: float,
    crew_size: int,
    setup_minutes: int = 0,
    cleanup_minutes: int = 0,
    shift_hours: float = 8.0,
) -> dict[str, float | int]:
    """Estimate elapsed hours, labor hours, and shifts using a facility's observed rate."""
    units = max(0, int(requested_units))
    rate = float(effective_units_per_hour)
    crew = max(1, int(crew_size))
    shift = float(shift_hours)
    if rate <= 0:
        raise ValueError("Effective rate must be greater than zero.")
    if shift <= 0:
        raise ValueError("Shift hours must be greater than zero.")
    run_hours = units / rate
    fixed_hours = (max(0, int(setup_minutes)) + max(0, int(cleanup_minutes))) / 60
    elapsed_hours = run_hours + fixed_hours
    return {
        "run_hours": run_hours,
        "elapsed_hours": elapsed_hours,
        "labor_hours": elapsed_hours * crew,
        "shifts": math.ceil(elapsed_hours / shift) if elapsed_hours else 0,
    }


def estimate_hand_labor_job(requested_units: int, crew_size: int, sticker_units_per_person_hour: float, case_pack_units_per_person_hour: float, final_cases_per_person_hour: float, units_per_case: int, setup_minutes: int = 0, cleanup_minutes: int = 0) -> dict[str, float | str]:
    """Estimate universal downstream stickering, case packing, and final case packing."""
    units, crew, case_size = max(0, int(requested_units)), max(1, int(crew_size)), max(1, int(units_per_case))
    rates = {"Stickering": float(sticker_units_per_person_hour), "Case packing": float(case_pack_units_per_person_hour), "Final case packing": float(final_cases_per_person_hour)}
    if any(rate <= 0 for rate in rates.values()):
        raise ValueError("All hand-labor rates must be greater than zero.")
    cases = math.ceil(units / case_size) if units else 0
    stages = {"Stickering": units / (rates["Stickering"] * crew), "Case packing": units / (rates["Case packing"] * crew), "Final case packing": cases / (rates["Final case packing"] * crew)}
    elapsed = sum(stages.values()) + (max(0, int(setup_minutes)) + max(0, int(cleanup_minutes))) / 60
    return {"cases": cases, "sticker_hours": stages["Stickering"], "case_pack_hours": stages["Case packing"], "final_case_hours": stages["Final case packing"], "elapsed_hours": elapsed, "labor_hours": elapsed * crew, "bottleneck": max(stages, key=stages.get)}

