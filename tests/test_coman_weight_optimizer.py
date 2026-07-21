import pytest

from modules.coman.planning import GRAMS_PER_POUND, recommend_weight_allocation, weight_to_grams


def _product(name, unit_g, revenue, max_pct=100, machine_rate=100):
    return {
        "eligible": True,
        "product": name,
        "format": "Pre-roll",
        "unit_size_g": unit_g,
        "revenue_per_unit": revenue,
        "bulk_cost_per_g": 1.0,
        "packaging_cost_per_unit": 0.25,
        "other_cost_per_unit": 0,
        "machine_units_per_hour": machine_rate,
        "machine_crew": 1,
        "machine_cost_per_hour": 10,
        "units_per_case": 50,
        "max_allocation_pct": max_pct,
    }


def test_weight_to_grams_supports_pounds_and_kilograms():
    assert weight_to_grams(1, "Pounds") == pytest.approx(GRAMS_PER_POUND)
    assert weight_to_grams(2, "Kilograms") == pytest.approx(2000)
    assert weight_to_grams(125, "Grams") == pytest.approx(125)


def test_optimizer_applies_loss_and_ranks_profit_per_input_weight():
    rows = recommend_weight_allocation(
        1000,
        [_product("Lower value", 1, 3), _product("Higher value", 1, 5)],
        loss_pct=10,
        labor_rate=0,
        optimization_goal="Maximum total profit",
    )
    assert rows[0]["product"] == "Higher value"
    assert rows[0]["units"] == 900
    assert rows[0]["allocated_g"] == pytest.approx(900)


def test_optimizer_uses_allocation_caps_to_make_a_mix():
    rows = recommend_weight_allocation(
        1000,
        [_product("Premium", 1, 8, max_pct=60), _product("Value", 1, 4, max_pct=100)],
        labor_rate=0,
    )
    assert [row["product"] for row in rows] == ["Premium", "Value"]
    assert rows[0]["units"] == 600
    assert rows[1]["units"] == 400
    assert sum(row["allocated_g"] for row in rows) == pytest.approx(1000)


def test_customer_owned_bulk_can_have_zero_material_cost():
    product = _product("External service", 1, 2)
    product["bulk_cost_per_g"] = 0
    product["machine_cost_per_hour"] = 0
    rows = recommend_weight_allocation(100, [product], labor_rate=0)
    assert rows[0]["total_cost"] == pytest.approx(25)
    assert rows[0]["profit"] == pytest.approx(175)

