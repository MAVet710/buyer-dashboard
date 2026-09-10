import pandas as pd

from reports.cultivation_report import _build_cultivation_executive_report_pdf


def sample_payload() -> dict:
    return {
        "summary": {
            "organization": "Example Cultivation Co.",
            "facility": "Grow 1",
            "reporting_period": "Current cultivation records",
        },
        "plants": pd.DataFrame(
            [
                {"plant_tag": "1A4001", "strain_name": "GMO", "phase": "flowering", "room_code": "FLOWER-A", "mother_plant_tag": "MOTHER-1", "planted_at": "2026-06-01", "estimated_harvest_date": "2026-09-18"},
                {"plant_tag": "1A4002", "strain_name": "GMO", "phase": "vegetative", "room_code": "VEG-A", "mother_plant_tag": "MOTHER-1", "planted_at": "2026-07-15", "estimated_harvest_date": "2026-10-15"},
                {"plant_tag": "1A4003", "strain_name": "Blue Dream", "phase": "flowering", "room_code": "FLOWER-B", "mother_plant_tag": "MOTHER-2", "planted_at": "2026-05-20", "estimated_harvest_date": "2026-09-08"},
            ]
        ),
        "rooms": pd.DataFrame(
            [
                {"room_code": "FLOWER-A", "display_name": "Flower A", "phase": "flowering", "active_plants": 1, "plant_capacity": 24, "utilization_pct": 4.2, "capacity_remaining": 23, "phase_mismatch_count": 0, "next_estimated_harvest": "2026-09-18", "total_cost_usd": 480.0, "active": True},
                {"room_code": "VEG-A", "display_name": "Veg A", "phase": "vegetative", "active_plants": 1, "plant_capacity": 36, "utilization_pct": 2.8, "capacity_remaining": 35, "phase_mismatch_count": 0, "next_estimated_harvest": "2026-10-15", "total_cost_usd": 225.0, "active": True},
            ]
        ),
        "harvests": pd.DataFrame(
            [
                {"harvest_code": "H-100", "strain_name": "GMO", "room_code": "FLOWER-A", "status": "completed", "plant_count": 12, "wet_weight": 12000.0, "dry_weight": 3000.0, "waste_weight": 500.0, "dry_yield_pct": 25.0, "labor_hours": 18.0, "total_cogs_usd": 1450.0, "cost_per_dry_unit": 0.4833},
                {"harvest_code": "H-101", "strain_name": "Blue Dream", "room_code": "FLOWER-B", "status": "drying", "plant_count": 10, "wet_weight": 10500.0, "dry_weight": 0.0, "waste_weight": 410.0, "dry_yield_pct": None, "labor_hours": 11.0, "total_cogs_usd": 900.0, "cost_per_dry_unit": None},
            ]
        ),
        "kpis": {
            "active_plants": 3,
            "flowering_plants": 2,
            "harvest_due_14_days": 1,
            "harvest_overdue": 1,
            "strain_count": 2,
            "active_rooms": 2,
            "room_capacity": 60,
            "over_capacity_rooms": 0,
            "phase_mismatch_count": 0,
            "open_harvests": 1,
            "completed_harvests": 1,
            "total_wet_weight_g": 22500.0,
            "total_dry_weight_g": 3000.0,
            "total_waste_weight_g": 910.0,
            "avg_dry_yield_pct": 13.3333,
            "total_cogs_usd": 2350.0,
            "cost_per_dry_g": 0.7833,
        },
    }


def test_every_cultivation_report_view_is_a_real_pdf():
    payload = sample_payload()
    for view in ("overview", "plants", "harvests", "rooms"):
        pdf = _build_cultivation_executive_report_pdf(payload, view=view)
        assert isinstance(pdf, bytes)
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 2_000


def test_cultivation_report_rejects_unknown_view():
    try:
        _build_cultivation_executive_report_pdf(sample_payload(), view="not-a-report")
    except ValueError as exc:
        assert "Unsupported cultivation report view" in str(exc)
    else:
        raise AssertionError("Unknown cultivation report views must be rejected.")
