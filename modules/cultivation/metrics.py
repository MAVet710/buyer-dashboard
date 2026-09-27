from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    unit: str
    kind: str = "continuous"
    minimum: float | None = None
    maximum: float | None = None
    aliases: tuple[str, ...] = ()


_DEFINITIONS = (
    MetricDefinition("temperature", "C", minimum=-273.15, aliases=("air_temperature",)),
    MetricDefinition("relative_humidity", "%", minimum=0, maximum=100, aliases=("rh",)),
    MetricDefinition("vpd", "kPa", minimum=0),
    MetricDefinition("co2", "ppm", minimum=0, aliases=("co2_ppm",)),
    MetricDefinition("ppfd", "umol/m2/s", minimum=0),
    MetricDefinition("dli", "mol/m2/day", minimum=0),
    MetricDefinition("substrate_vwc", "%", minimum=0, maximum=100),
    MetricDefinition("substrate_ec", "mS/cm", minimum=0),
    MetricDefinition("substrate_temperature", "C", minimum=-273.15),
    MetricDefinition("dryback_pct", "%", minimum=0, maximum=100),
    MetricDefinition("feed_ec", "mS/cm", minimum=0),
    MetricDefinition("feed_ph", "pH", minimum=0, maximum=14),
    MetricDefinition("runoff_ec", "mS/cm", minimum=0),
    MetricDefinition("runoff_ph", "pH", minimum=0, maximum=14),
    MetricDefinition("runoff_pct", "%", minimum=0, maximum=100),
    MetricDefinition("irrigation_volume", "L", kind="volume", minimum=0),
    MetricDefinition("irrigation_duration", "s", kind="duration", minimum=0),
    MetricDefinition("irrigation_event", "count", kind="event", minimum=1, maximum=1),
    MetricDefinition("water_flow", "L/min", minimum=0),
    MetricDefinition("tank_level", "%", minimum=0, maximum=100),
    MetricDefinition("hvac_state", "state", kind="state", minimum=0, maximum=1),
    MetricDefinition("dehumidifier_state", "state", kind="state", minimum=0, maximum=1),
    MetricDefinition("light_output_pct", "%", minimum=0, maximum=100),
    MetricDefinition("co2_state", "state", kind="state", minimum=0, maximum=1),
)

METRIC_REGISTRY = {row.key: row for row in _DEFINITIONS}
ALIASES = {alias: row.key for row in _DEFINITIONS for alias in row.aliases}
CANONICAL_UNITS = {key: row.unit for key, row in METRIC_REGISTRY.items()}


def canonical_metric(value: str) -> str:
    key = str(value or "").strip().casefold().replace(" ", "_")
    key = ALIASES.get(key, key)
    if key not in METRIC_REGISTRY:
        raise ValueError(f"Unsupported cultivation telemetry metric: {value}.")
    return key


def normalize_metric_value(metric: str, value: float, unit: str) -> tuple[str, float, str]:
    key = canonical_metric(metric)
    definition = METRIC_REGISTRY[key]
    original_unit = str(unit or "").strip()
    if isinstance(value, bool):
        raise ValueError("Boolean values are not measurements.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("Measurement must be finite.")

    if definition.unit == "C" and original_unit in {"F", "Â°F"}:
        numeric = (numeric - 32) * 5 / 9
    elif definition.unit == "C" and original_unit in {"C", "Â°C"}:
        pass
    elif definition.unit == "mS/cm" and original_unit in {"uS/cm", "ÂµS/cm"}:
        numeric /= 1000
    elif definition.unit == "mS/cm" and original_unit == "dS/m":
        pass  # Both units equal 0.1 siemens per meter.
    elif definition.unit == "L" and original_unit == "mL":
        numeric /= 1000
    elif definition.unit == "L" and original_unit == "US gal":
        numeric *= 3.785411784
    elif definition.unit == "L" and original_unit == "imperial gal":
        numeric *= 4.54609
    elif definition.unit == "s" and original_unit in {"min", "minute", "minutes"}:
        numeric *= 60
    elif definition.unit == "L/min" and original_unit == "US gal/min":
        numeric *= 3.785411784
    elif definition.unit == "umol/m2/s" and original_unit in {"Âµmol/mÂ²/s", "umol/mÂ²/s", "Âµmol/m2/s"}:
        pass
    elif definition.unit == "mol/m2/day" and original_unit in {"mol/mÂ²/day", "mol/mÂ²/d", "mol/m2/d"}:
        pass
    elif definition.unit == "state" and original_unit in {"bool", "boolean"}:
        pass
    elif original_unit != definition.unit:
        raise ValueError(f"Unsupported unit for {key}; use {definition.unit}.")

    if definition.kind == "state" and numeric not in (0, 1):
        raise ValueError("State must be zero or one.")
    if definition.minimum is not None and numeric < definition.minimum:
        raise ValueError(f"{key} is below the supported measurement range.")
    if definition.maximum is not None and numeric > definition.maximum:
        raise ValueError(f"{key} is above the supported measurement range.")
    if key == "irrigation_event" and numeric != 1:
        raise ValueError("An irrigation event has a count of 1.")
    return key, round(numeric, 6), definition.unit


def public_registry() -> list[dict]:
    return [
        {
            "metric": row.key,
            "unit": row.unit,
            "kind": row.kind,
            "aliases": list(row.aliases),
        }
        for row in _DEFINITIONS
    ]
