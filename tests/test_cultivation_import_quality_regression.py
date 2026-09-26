"""Real HTTP export quality and safe-error regressions from independent review."""
import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_cultivation_intelligence_end_to_end import (
    PREFIX, harness, historical_context, post, get,
)
from modules.cultivation.edge_store import Scope


def export_body(rows, format):
    if format == "json":
        content = json.dumps(rows)
    else:
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        content = stream.getvalue()
    return {"format": format, "content": content, "mappings": [
        {"source_channel": "temp", "source_metric": "vendor_temp", "metric": "temperature", "unit": "F"},
    ]}


@pytest.mark.parametrize("format", ["json", "csv"])
@pytest.mark.parametrize("quality", ["invalid", "suspect"])
def test_quality_is_preserved_and_breaks_coverage(historical_context, format, quality):
    h = historical_context
    x = h.history
    raw = dict(event_id="first", source_device_id="fixture", source_channel="temp",
               source_metric="vendor_temp", value=77, unit="F", quality="valid",
               observed_at=x.start.isoformat(), received_at=x.start.isoformat())
    bad = dict(raw, event_id="bad", quality=quality,
               observed_at=(x.start + timedelta(seconds=60)).isoformat())
    body = export_body([raw, bad], format)
    path = f"/connections/{x.connection}/imports"
    preview = post(h, path + "/preview", body)
    result = post(h, path, dict(body, digest=preview["digest"]))
    assert result["accepted"] == 1 and result["quarantined"] == 1
    assert result["queued_for_mapping"] == 0
    scope = Scope(h.own.org, h.own.facility, x.connection)
    evidence = h.edge.evidence(scope)["items"]
    quarantined = next(row for row in evidence if row["state"] == "quarantined")
    assert quarantined["raw"]["quality"] == quality
    assert quarantined["raw"]["received_at"] == x.start.isoformat()
    h.edge.rollup(scope, x.start, x.end)
    summary = h.edge.room_summary(h.own.org, h.own.facility, h.own.room, x.start, x.end)
    assert summary["streams"][0]["coverage_seconds"] == 60
    assert h.edge.diagnostics(scope)["last_valid_observed_at"].replace("Z", "+00:00") == x.start.isoformat()
    latest = get(h, f"/rooms/{h.own.room}")["edge_latest"]["readings"][0]
    assert latest["status"] == "invalid" and latest["value"] is None
    replay = post(h, path, dict(body, digest=preview["digest"]))
    assert replay["duplicates"] == 2 and replay["accepted"] == 0


@pytest.mark.parametrize("format,content", [("json", "{private-value-not-for-errors"),
                                           ("csv", "event_id,event_id\none,two")])
def test_malformed_exports_return_safe_422(harness, format, content):
    h = harness
    connection = post(h, "/connections", {"provider": "json", "label": "Malformed fixture"})
    path = f"/connections/{connection['id']}/imports/preview"
    response = h.client.post(PREFIX + path, json={"format": format, "content": content, "mappings": []})
    assert response.status_code == 422
    assert response.json() == {"detail": "Export could not be parsed. Check the format, columns and row limits."}
    assert content not in response.text
    scope = Scope(h.own.org, h.own.facility, connection["id"])
    assert h.edge.evidence(scope)["items"] == []


@pytest.mark.parametrize("format", ["json", "csv"])
def test_absent_optional_quality_defaults_without_losing_measurement(historical_context, format):
    h = historical_context
    raw = dict(event_id="no-quality", source_device_id="fixture", source_channel="temp",
               source_metric="vendor_temp", value=77, unit="F", observed_at=(datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat())
    body = export_body([raw], format)
    path = f"/connections/{h.history.connection}/imports"
    preview = post(h, path + "/preview", body)
    result = post(h, path, dict(body, digest=preview["digest"]))
    assert result["accepted"] == 1 and result["quarantined"] == 0
    latest = get(h, f"/rooms/{h.own.room}")["edge_latest"]["readings"][0]
    assert latest["value"] == 25 and latest["original_value"] in (77, "77")
