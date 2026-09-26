import csv
import io
import json
import os
from pathlib import Path
import socket
import sys

import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["COMAN_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AI_ALLOW_CLOUD_FALLBACK"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules" / "cultivation"))
from adapters.base import AdapterMalformedResponse, AdapterUnavailableError
from adapters.growlink import GrowlinkAdapter
from adapters.normalized import NormalizedExportAdapter
from edge_store import EdgeStore, Scope


def config():
    return {"columns": {k: k for k in NormalizedExportAdapter.required}, "metric_mappings": [{"source_metric": "Air", "unit": "F", "source_channel": "1", "metric": "temperature"}]}


def row():
    return dict(event_id="event", source_device_id="device", source_channel="1", source_metric="Air", value=77, unit="F", observed_at="2026-09-26T00:00:00Z")


def test_explicit_json_csv_mapping_and_missing_rows():
    adapter = NormalizedExportAdapter(**config())
    results = adapter.parse(json.dumps([row(), dict(row(), source_metric="unknown"), {}]))
    assert len(results["readings"]) == 3
    assert results["mapping_hints"] == [{"metric": "temperature"}, None, None]
    assert results["readings"][0]["value"] == 77
    assert results["readings"][0]["unit"] == "F"
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(row()))
    writer.writeheader()
    writer.writerow(row())
    assert adapter.parse(stream.getvalue(), format="csv")["mapping_hints"][0]["metric"] == "temperature"
    with pytest.raises(AdapterMalformedResponse):
        adapter.parse(json.dumps({"data": [row()]}))


def test_bounds_and_no_raw_metadata_leakage():
    adapter = NormalizedExportAdapter(**config(), max_rows=1)
    with pytest.raises(AdapterMalformedResponse):
        adapter.parse(json.dumps([row(), row()]))
    with pytest.raises(AdapterMalformedResponse):
        NormalizedExportAdapter(**config(), max_bytes=1).parse("[]")
    result = adapter.parse(json.dumps([dict(row(), Authorization="SECRET", raw_body={"url": "https://a/?secret=x"})]))
    assert "SECRET" not in json.dumps(result) and "https://" not in json.dumps(result)
    with pytest.raises(AdapterMalformedResponse):
        NormalizedExportAdapter(columns={}, metric_mappings=[])


def test_growlink_fail_closed_no_network_or_control(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("network called"))
    for unsafe in ({"base_url": "https://127.0.0.1"}, {"auth_header": "Authorization"}, {"redirect": "https://host"}):
        with pytest.raises(AdapterUnavailableError) as exc:
            GrowlinkAdapter(configuration=unsafe)
        assert "https://" not in str(exc.value)
    with pytest.raises(AdapterUnavailableError):
        GrowlinkAdapter(secret="private")
    adapter = GrowlinkAdapter(configuration=config(), fixture=json.dumps([row()]))
    assert adapter.validate_fixture()["mapping_hints"][0]["metric"] == "temperature"
    health = adapter.get_connection_health()
    assert health["fixture_validated"] and not health["connected"] and not health["live_authorized"]
    assert not health["capabilities"]["live_supported"] and not health["capabilities"]["history_supported"]
    for name in ("get_current_readings", "discover_facilities", "discover_rooms", "discover_devices", "discover_metrics"):
        with pytest.raises(AdapterUnavailableError):
            getattr(adapter, name)()
    with pytest.raises(AdapterUnavailableError):
        adapter.get_history(None, None)
    assert not hasattr(adapter, "control") and not hasattr(adapter, "_get_json")


@pytest.mark.parametrize("format", ["json", "csv"])
def test_export_to_local_normalization_preserves_source_evidence(tmp_path, format):
    adapter = NormalizedExportAdapter(**config())
    if format == "json":
        content = json.dumps([row()])
    else:
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(row()))
        writer.writeheader()
        writer.writerow(row())
        content = stream.getvalue()
    parsed = adapter.parse(content, format=format)
    scope = Scope("org", "facility", "connection")
    # This test snapshot stands in for deterministic backend relationship checks.
    snapshot = dict(organization_id="org", facility_id="facility", connection_id="connection", room_id="room", device_id="device-db", sensor_id="sensor-db", mapping_revision="1", metric=parsed["mapping_hints"][0]["metric"], effective_from="2026-09-26T00:00:00Z", effective_to="2026-09-27T00:00:00Z")
    store = EdgeStore(tmp_path / "edge.db")
    assert store.ingest(scope, parsed["readings"], [snapshot])["accepted"] == 1
    evidence = store.evidence(scope)["items"][0]
    assert evidence["raw"]["value"] == (77 if format == "json" else "77")
    assert evidence["raw"]["unit"] == "F" and evidence["raw"]["source_metric"] == "Air"
    assert evidence["canonical"]["value"] == 25 and evidence["canonical"]["unit"] == "C"
