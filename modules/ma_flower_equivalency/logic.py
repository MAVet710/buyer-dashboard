"""Pure decimal-safe calculations for Massachusetts flower equivalency."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


CONCENTRATE_FACTOR = Decimal("5.6")
EDIBLE_FACTOR = Decimal("0.056")
DISPLAY_QUANTUM = Decimal("0.0001")


class EquivalencyValidationError(ValueError):
    """Raised when a calculator input is incomplete or invalid."""

    def __init__(self, field: str, message: str, *, incomplete: bool = False) -> None:
        super().__init__(message)
        self.field = field
        self.message = message
        self.incomplete = incomplete


@dataclass(frozen=True)
class EquivalencyResult:
    """Full-precision results returned by every calculator mode."""

    per_unit: Decimal
    package_total: Decimal
    quantity: int
    flower_weight_per_joint: Decimal | None = None
    infusion_equivalency_per_joint: Decimal | None = None


def _decimal(value: Any, *, field: str, label: str) -> Decimal:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise EquivalencyValidationError(
            field,
            f"Enter {label} to calculate flower equivalency.",
            incomplete=True,
        )
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        raise EquivalencyValidationError(field, f"{label} must be a valid number.") from None
    if not number.is_finite():
        raise EquivalencyValidationError(field, f"{label} must be a finite number.")
    if number < 0:
        raise EquivalencyValidationError(field, f"{label} cannot be negative.")
    return number


def _positive_whole(value: Any, *, field: str, label: str) -> int:
    number = _decimal(value, field=field, label=label)
    if number <= 0:
        raise EquivalencyValidationError(field, f"{label} must be greater than zero.")
    if number != number.to_integral_value():
        raise EquivalencyValidationError(field, f"{label} must be a positive whole number.")
    return int(number)


def calculate_concentrate_equivalency(gc: Any, quantity: Any = 1) -> EquivalencyResult:
    """Calculate concentrate/vape flower equivalency using grams x 5.6."""
    grams = _decimal(gc, field="grams", label="grams/concentration per unit")
    package_quantity = _positive_whole(
        quantity,
        field="quantity",
        label="package quantity",
    )
    per_unit = grams * CONCENTRATE_FACTOR
    return EquivalencyResult(
        per_unit=per_unit,
        package_total=per_unit * package_quantity,
        quantity=package_quantity,
    )


def calculate_edible_equivalency(active_thc_mg: Any, quantity: Any = 1) -> EquivalencyResult:
    """Calculate edible flower equivalency using active THC mg x 0.056."""
    milligrams = _decimal(
        active_thc_mg,
        field="active_thc_mg",
        label="labeled active THC in milligrams per unit",
    )
    package_quantity = _positive_whole(
        quantity,
        field="quantity",
        label="package quantity",
    )
    per_unit = milligrams * EDIBLE_FACTOR
    return EquivalencyResult(
        per_unit=per_unit,
        package_total=per_unit * package_quantity,
        quantity=package_quantity,
    )


def calculate_infused_preroll_equivalency(
    finished_grams_per_joint: Any,
    infusion_grams_per_joint: Any,
    joint_count: Any,
) -> EquivalencyResult:
    """Calculate infused pre-roll equivalency without rounding intermediates."""
    finished = _decimal(
        finished_grams_per_joint,
        field="finished_grams_per_joint",
        label="finished weight per joint in grams",
    )
    infusion = _decimal(
        infusion_grams_per_joint,
        field="infusion_grams_per_joint",
        label="infusion material per joint in grams",
    )
    count = _positive_whole(joint_count, field="joint_count", label="joint count")
    if infusion > finished:
        raise EquivalencyValidationError(
            "infusion_grams_per_joint",
            "Infusion weight cannot exceed the finished joint weight.",
        )

    flower_weight = finished - infusion
    infusion_equivalency = infusion * CONCENTRATE_FACTOR
    per_joint = flower_weight + infusion_equivalency
    return EquivalencyResult(
        per_unit=per_joint,
        package_total=per_joint * count,
        quantity=count,
        flower_weight_per_joint=flower_weight,
        infusion_equivalency_per_joint=infusion_equivalency,
    )


def format_equivalency(value: Decimal, *, max_places: int = 4) -> str:
    """Round only for display and return a plain Dutchie-ready numeric string."""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("Equivalency output must be a finite Decimal value.")
    if max_places < 0:
        raise ValueError("max_places cannot be negative.")
    quantum = Decimal(1).scaleb(-max_places) if max_places else Decimal(1)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
