from datetime import date, datetime

from modules.coman.order_prefill import build_recommended_order_prefill


def test_optimizer_recommendation_prefills_internal_order() -> None:
    prefill = build_recommended_order_prefill(
        {
            "product": "3.5 g flower pouch",
            "format": "Pouched flower — 3.5 g",
            "units": 1200,
            "allocated_g": 4200,
            "cases": 24,
            "profit": 12500,
            "margin_pct": 61.5,
            "machine_hours": 1.4,
            "hand_labor_hours": 8.2,
        },
        "Internal / owned product",
        created_at=datetime(2026, 7, 25, 14, 30, 15),
    )

    assert prefill["order_number"] == "COM-20260725-143015"
    assert prefill["work_type"] == "Internal"
    assert prefill["requested_units"] == 1200
    assert prefill["product_name"] == "3.5 g flower pouch"
    assert prefill["due_date"] == date(2026, 8, 1)
    assert prefill["material_owner"] == "Internal"
    assert "4,200.0 g" in prefill["notes"]
    assert "hand labor: 8.2 hr" in prefill["notes"]


def test_optimizer_recommendation_prefills_external_ownership() -> None:
    prefill = build_recommended_order_prefill(
        {"product": "Customer pre-roll", "format": "Pre-roll", "units": 500},
        "External co-man service",
        created_at=datetime(2026, 7, 25, 9, 0, 0),
    )

    assert prefill["work_type"] == "External"
    assert prefill["material_owner"] == "Customer"
    assert prefill["packaging_owner"] == "Internal"
