from __future__ import annotations

import math

import pytest

from modules.commerce_storefronts.sales_units import (
    compatible_sales_units,
    conversion_factor,
    convert_quantity,
    convert_unit_price,
    normalize_unit,
)


def test_mass_unit_aliases_and_compatible_units():
    assert normalize_unit("grams") == "g"
    assert normalize_unit("Pounds") == "lb"
    assert compatible_sales_units("g") == ["g", "oz", "lb", "kg"]
    assert compatible_sales_units("unit") == ["unit"]


def test_grams_and_pounds_round_trip_without_changing_physical_quantity():
    grams = 4535.9237
    pounds = convert_quantity(grams, "g", "lb")
    assert pounds == pytest.approx(10.0, rel=1e-9)
    assert convert_quantity(pounds, "lb", "g") == pytest.approx(grams, rel=1e-9)
    assert conversion_factor("lb", "g") == pytest.approx(453.59237, rel=1e-9)


def test_unit_price_conversion_preserves_line_total():
    quantity_g = 907.18474
    price_per_g = 2.0
    quantity_lb = convert_quantity(quantity_g, "g", "lb")
    price_per_lb = convert_unit_price(price_per_g, "g", "lb")
    assert quantity_lb == pytest.approx(2.0, rel=1e-9)
    assert price_per_lb == pytest.approx(907.18474, rel=1e-9)
    assert quantity_g * price_per_g == pytest.approx(quantity_lb * price_per_lb, rel=1e-9)


def test_switching_storefront_units_preserves_minimum_case_and_tier_economics():
    minimum_g = 453.59237
    case_g = 453.59237
    tier_g = 907.18474
    base_price_g = 1.5
    tier_price_g = 1.25

    minimum_lb = convert_quantity(minimum_g, "g", "lb")
    case_lb = convert_quantity(case_g, "g", "lb")
    tier_lb = convert_quantity(tier_g, "g", "lb")
    base_price_lb = convert_unit_price(base_price_g, "g", "lb")
    tier_price_lb = convert_unit_price(tier_price_g, "g", "lb")

    assert minimum_lb == pytest.approx(1.0)
    assert case_lb == pytest.approx(1.0)
    assert tier_lb == pytest.approx(2.0)
    assert math.isclose(base_price_lb, base_price_g * 453.59237, rel_tol=1e-9)
    assert math.isclose(tier_price_lb, tier_price_g * 453.59237, rel_tol=1e-9)
    assert tier_lb * tier_price_lb == pytest.approx(tier_g * tier_price_g)


def test_incompatible_dimensions_fail_closed():
    with pytest.raises(ValueError, match="Cannot convert storefront quantity"):
        convert_quantity(1, "unit", "lb")
