"""Small, deterministic Co-Man capacity calculations."""

from __future__ import annotations

import math


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
