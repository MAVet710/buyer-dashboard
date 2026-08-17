import pandas as pd

from services.extraction_brief import generate_extraction_brief


def _runs(include_optional: bool = True):
    rows = [
        {
            "batch_id_internal": "EXT-001",
            "method": "BHO",
            "input_weight_g": 1000,
            "intermediate_output_g": 220,
            "finished_output_g": 180,
            "yield_pct": 18.0,
            "qa_hold": False,
            "coa_status": "Passed",
            "status": "Complete",
            "est_revenue_usd": 3600,
            "cogs_usd": 1800,
        },
        {
            "batch_id_internal": "EXT-002",
            "method": "BHO",
            "input_weight_g": 1000,
            "intermediate_output_g": 180,
            "finished_output_g": 130,
            "yield_pct": 13.0,
            "qa_hold": True,
            "coa_status": "Pending",
            "status": "Hold",
            "est_revenue_usd": 2100,
            "cogs_usd": 1900,
        },
    ]
    if include_optional:
        for index, row in enumerate(rows):
            row.update(
                {
                    "input_terpene_pct": 3.0,
                    "finished_terpene_pct": 2.2 - index * 0.4,
                    "terpene_retention_pct": 73.3 - index * 13.3,
                    "turnaround_hours": 18 + index * 10,
                    "rework_required": bool(index),
                    "residual_solvent_status": "Passed",
                    "downtime_minutes": index * 45,
                    "settings_verified": True,
                    "sop_reference": "SANDBOX-SOP-BHO-001",
                }
            )
    return rows


def test_extraction_brief_is_run_specific_and_has_no_rules_provider_noise(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = generate_extraction_brief({"runs": _runs()}, question="What needs attention?")
    rendered = "\n".join(
        [result["answer"], result["explanation"], *result["recommendations"], *result["risk_flags"]]
    ).casefold()

    assert "ext-002" in rendered
    assert "qa hold" in rendered
    assert "terpene" in rendered
    assert result["ai"]["provider"] == "deterministic"
    assert "mailto:" not in rendered
    assert "[operations:" not in rendered
    assert "department_knowledge" not in rendered
    assert "grounded source context" not in rendered
    assert result["sources"] == []


def test_extraction_brief_explicitly_blocks_missing_measurements(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = generate_extraction_brief({"runs": _runs(include_optional=False)})
    text = result["answer"].casefold()

    assert "unavailable measurements" in text
    assert "terpene retention" in text
    assert "turnaround" in text
    assert all("benchmark terpene" not in item.casefold() for item in result["recommendations"])
