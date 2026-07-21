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
