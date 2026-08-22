import json

import pandas as pd
from fastapi.testclient import TestClient

from backend.app.database import get_engine
from backend.app.main import app
from services.extraction_partner_import import apply_mapping, normalize_workbook, suggestions
from tests.test_web_inventory_api import _engine


HEADERS = {
    "X-Organization-Id": "org-1",
    "X-Facility-Id": "facility-1",
    "X-User-Id": "extractor@example.com",
    "X-User-Role": "qa",
}


def test_partner_service_normalizes_maps_defaults_and_calculates_yields():
    payload = b"Run Date,Batch Number,Input Weight,Intermediate Output,Finished Output\n2026-08-20,BATCH-7,100,80,72\n"
    frame, diagnostics = normalize_workbook(payload, "partner-runs.csv")
    proposed = suggestions(list(frame.columns))
    mapped = apply_mapping(
        frame,
        {
            "run_date": "run date",
            "batch_id_internal": "batch number",
            "input_weight_g": "input weight",
            "intermediate_output_g": "intermediate output",
            "finished_output_g": "finished output",
        },
        {"method": "Rosin", "state": "MA", "client_name": "In House"},
    )

    assert diagnostics["rows_extracted"] == 1
    assert proposed["run_date"]["source"] == "run date"
    assert proposed["batch_id_internal"]["source"] == "batch number"
    assert mapped.iloc[0]["batch_id_internal"] == "BATCH-7"
    assert mapped.iloc[0]["method"] == "Rosin"
    assert mapped.iloc[0]["yield_pct"] == 72
    assert mapped.iloc[0]["post_process_efficiency_pct"] == 90


def test_partner_suggestions_prefer_known_aliases_and_do_not_confuse_date_with_state():
    proposed = suggestions(["date", "batch", "input", "intermediate", "output", "operator"])
    assert proposed["run_date"] == {"source": "date", "score": 1.0}
    assert proposed["batch_id_internal"] == {"source": "batch", "score": 1.0}
    assert proposed["state"]["source"] == "IGNORE"


def test_partner_import_inspects_publishes_deduplicates_and_isolates_runs():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    csv = b"Date,Batch,Input,Intermediate,Output,Operator\n2026-08-21,PARTNER-42,200,100,75,Operator P\n"
    mapping = {
        "run_date": "date",
        "batch_id_internal": "batch",
        "input_weight_g": "input",
        "intermediate_output_g": "intermediate",
        "finished_output_g": "output",
        "operator": "operator",
    }
    defaults = {"method": "BHO", "state": "MA", "client_name": "Partner One", "status": "Complete", "coa_status": "Pending"}
    try:
        inspected = client.post(
            "/api/v1/extraction-parity/partner-import/inspect",
            headers=HEADERS,
            files={"file": ("partner.csv", csv, "text/csv")},
        )
        published = client.post(
            "/api/v1/extraction-parity/partner-import/publish",
            headers=HEADERS,
            data={"mapping_json": json.dumps(mapping), "defaults_json": json.dumps(defaults)},
            files={"file": ("partner.csv", csv, "text/csv")},
        )
        duplicate = client.post(
            "/api/v1/extraction-parity/partner-import/publish",
            headers=HEADERS,
            data={"mapping_json": json.dumps(mapping), "defaults_json": json.dumps(defaults)},
            files={"file": ("partner.csv", csv, "text/csv")},
        )
        overview = client.get("/api/v1/extraction-parity/overview", headers=HEADERS)
        isolated = client.get("/api/v1/extraction-parity/overview", headers={**HEADERS, "X-Facility-Id": "other-facility"})
    finally:
        app.dependency_overrides.clear()

    assert inspected.status_code == 200
    assert inspected.json()["columns"] == ["date", "batch", "input", "intermediate", "output", "operator", "__source_sheet"]
    assert inspected.json()["defaults"]["method"] == "BHO"
    assert published.status_code == 200
    assert published.json() == {"added": 1, "duplicates": 0, "rows": 1, "filename": "partner.csv"}
    assert duplicate.json()["added"] == 0 and duplicate.json()["duplicates"] == 1
    row = next(value for value in overview.json()["runs"] if value["batch_id_internal"] == "PARTNER-42")
    assert row["input_weight_g"] == 200
    assert row["finished_output_g"] == 75
    assert row["yield_pct"] == 37.5
    assert row["post_process_efficiency_pct"] == 75
    assert row["status"] == "Complete"
    assert isolated.status_code == 403


def test_partner_mapping_rejects_columns_that_are_not_in_the_file():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/extraction-parity/partner-import/publish",
            headers=HEADERS,
            data={"mapping_json": json.dumps({"run_date": "not-a-column"}), "defaults_json": "{}"},
            files={"file": ("partner.csv", b"Date,Batch\n2026-08-21,A-1\n", "text/csv")},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
    assert "no longer exists" in response.json()["detail"]
