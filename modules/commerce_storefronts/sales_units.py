"""Storefront-facing sales units that preserve base inventory truth."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id


_MASS_TO_GRAMS = {
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.349523125,
    "lb": 453.59237,
}
_ALIASES = {
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "unit": "unit", "units": "unit", "each": "unit", "ea": "unit",
}


class StorefrontProductSalesUnit(TimestampMixin, Base):
    __tablename__ = "commerce_storefront_product_sales_units"
    __table_args__ = (
        UniqueConstraint("storefront_id", "product_id", name="uq_storefront_product_sales_unit"),
        Index("ix_storefront_product_sales_unit_scope", "organization_id", "storefront_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    storefront_id: Mapped[str] = mapped_column(ForeignKey("commerce_storefronts.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("coman_products.id", ondelete="CASCADE"), nullable=False, index=True)
    sales_unit: Mapped[str] = mapped_column(String(24), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)


def normalize_unit(value: str) -> str:
    raw = str(value or "").strip().casefold()
    return _ALIASES.get(raw, raw)


def compatible_sales_units(base_unit: str) -> list[str]:
    normalized = normalize_unit(base_unit)
    if normalized in _MASS_TO_GRAMS:
        return ["g", "oz", "lb", "kg"]
    return [normalized] if normalized else []


def conversion_factor(from_unit: str, to_unit: str) -> float:
    """Return how many target units equal one source unit."""
    source = normalize_unit(from_unit)
    target = normalize_unit(to_unit)
    if source == target:
        return 1.0
    if source in _MASS_TO_GRAMS and target in _MASS_TO_GRAMS:
        return _MASS_TO_GRAMS[source] / _MASS_TO_GRAMS[target]
    raise ValueError(f"Cannot convert storefront quantity from {from_unit or 'unknown'} to {to_unit or 'unknown'}.")


def convert_quantity(quantity: float, from_unit: str, to_unit: str) -> float:
    return float(quantity) * conversion_factor(from_unit, to_unit)


def convert_unit_price(price: float, from_unit: str, to_unit: str) -> float:
    """Convert price-per-source-unit to an equivalent price-per-target-unit."""
    factor = conversion_factor(to_unit, from_unit)
    return float(price) * factor
