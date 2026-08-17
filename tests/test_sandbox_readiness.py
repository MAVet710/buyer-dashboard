from datetime import date

from services.demo_data import build_demo_payload
from services.sandbox_readiness import validate_sandbox_payload


def test_generated_dev_sandbox_is_ready_across_workspaces():
    payload = build_demo_payload(date(2026, 8, 17), scale="small")
    report = validate_sandbox_payload(payload)

    assert report["ready"] is True, report["issues"]
    assert report["organization"] == "DEV Sandbox"
    assert report["facility"] == "Sandbox Facility"
    assert report["facility_code"] == "SANDBOX"
    assert report["timezone"] == "America/New_York"


def test_extraction_sandbox_has_measurements_the_agent_is_allowed_to_discuss():
    payload = build_demo_payload(date(2026, 8, 17), scale="small")
    runs = payload["extraction_runs"]

    required = {
        "input_terpene_pct",
        "finished_terpene_pct",
        "terpene_retention_pct",
        "turnaround_hours",
        "rework_required",
        "residual_solvent_status",
        "downtime_minutes",
        "settings_verified",
        "sop_reference",
    }
    assert required.issubset(set(runs.columns))
    assert runs["license_name"].eq("Sandbox Facility").all()
    assert payload["sales"]["Store"].eq("Sandbox Facility").all()
