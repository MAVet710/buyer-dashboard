from decimal import Decimal

import pytest

from modules.ma_flower_equivalency.logic import (
    EquivalencyValidationError,
    calculate_concentrate_equivalency,
    calculate_edible_equivalency,
    calculate_infused_preroll_equivalency,
    format_equivalency,
)


@pytest.mark.parametrize(
    ("grams", "expected"),
    [
        ("1", Decimal("5.6")),
        ("2", Decimal("11.2")),
        ("0.5", Decimal("2.80")),
    ],
)
def test_concentrate_cart_and_disposable_examples(grams, expected):
    result = calculate_concentrate_equivalency(grams, 1)

    assert result.per_unit == expected
    assert result.package_total == expected


@pytest.mark.parametrize(
    ("milligrams", "expected"),
    [
        ("100", Decimal("5.600")),
        ("200", Decimal("11.200")),
    ],
)
def test_edible_examples_use_active_thc_milligrams(milligrams, expected):
    result = calculate_edible_equivalency(milligrams, 1)

    assert result.per_unit == expected
    assert result.package_total == expected


def test_infused_preroll_example_totals_10_75():
    result = calculate_infused_preroll_equivalency("1", "0.25", 5)

    assert result.flower_weight_per_joint == Decimal("0.75")
    assert result.infusion_equivalency_per_joint == Decimal("1.400")
    assert result.per_unit == Decimal("2.150")
    assert result.package_total == Decimal("10.750")


def test_infused_weight_equal_to_finished_weight_is_valid():
    result = calculate_infused_preroll_equivalency("1", "1", 2)

    assert result.flower_weight_per_joint == Decimal("0")
    assert result.package_total == Decimal("11.2")


def test_infused_weight_cannot_exceed_finished_weight():
    with pytest.raises(EquivalencyValidationError, match="cannot exceed") as error:
        calculate_infused_preroll_equivalency("1", "1.01", 1)

    assert error.value.field == "infusion_grams_per_joint"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_blank_required_measurements_are_incomplete_not_zero(value):
    with pytest.raises(EquivalencyValidationError) as error:
        calculate_edible_equivalency(value, 1)

    assert error.value.incomplete is True


@pytest.mark.parametrize("value", ["abc", "NaN", "Infinity", "-1"])
def test_invalid_nonfinite_and_negative_measurements_are_rejected(value):
    with pytest.raises(EquivalencyValidationError):
        calculate_concentrate_equivalency(value, 1)


def test_zero_measurement_is_valid_and_distinct_from_blank():
    result = calculate_concentrate_equivalency("0", 1)

    assert result.package_total == Decimal("0.0")


@pytest.mark.parametrize("quantity", [0, -1, "1.5", "bad", ""])
def test_quantity_must_be_a_positive_whole_number(quantity):
    with pytest.raises(EquivalencyValidationError):
        calculate_edible_equivalency(100, quantity)


def test_quantity_multiplies_without_rounding_the_per_unit_result():
    result = calculate_edible_equivalency("10.125", 3)

    assert result.per_unit == Decimal("0.567000")
    assert result.package_total == Decimal("1.701000")


def test_decimal_measurements_preserve_precision_and_display_rounds_only_at_end():
    result = calculate_concentrate_equivalency("0.123456789", 7)

    assert result.per_unit == Decimal("0.6913580184")
    assert result.package_total == Decimal("4.8395061288")
    assert format_equivalency(result.per_unit) == "0.6914"
    assert format_equivalency(result.package_total) == "4.8395"


def test_display_format_is_plain_numeric_and_uses_at_most_four_places():
    assert format_equivalency(Decimal("10.750000")) == "10.75"
    assert format_equivalency(Decimal("5.6000")) == "5.6"
    assert format_equivalency(Decimal("0")) == "0"
