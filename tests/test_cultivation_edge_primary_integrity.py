"""Independent clock, default-alert and aggregate-summary regressions."""
from datetime import datetime, timedelta, timezone
import pytest
from modules.cultivation.edge_store import EdgeStore, Scope

SCOPE = Scope('primary-org', 'primary-facility', 'primary-connection')


def fixtures(tmp_path):
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    store = EdgeStore(tmp_path / 'edge.sqlite')
    snapshot = dict(organization_id=SCOPE.organization_id, facility_id=SCOPE.facility_id,
                    connection_id=SCOPE.connection_id, room_id='room', device_id='device',
                    sensor_id='sensor', mapping_revision='mapping', metric='temperature',
                    effective_from=start.isoformat(), effective_to=(start + timedelta(days=1)).isoformat(),
                    recipe_revision='approved-recipe', target_max=24)
    raw = dict(event_id='one', source_device_id='source-device', source_channel='air',
               source_metric='temperature', value=77, unit='F', observed_at=start.isoformat())
    return store, start, snapshot, raw


def test_future_observation_stays_quarantined_even_with_claimed_future_receipt(tmp_path):
    store, start, snapshot, raw = fixtures(tmp_path)
    future = datetime.now(timezone.utc) + timedelta(days=7)
    raw.update(observed_at=future.isoformat(), received_at=(future + timedelta(days=1)).isoformat())
    snapshot.update(effective_from=start.isoformat(), effective_to=(future + timedelta(days=2)).isoformat())
    result = store.ingest(SCOPE, [raw], [snapshot])
    assert result['accepted'] == 0 and result['quarantined'] == 1
    item = store.evidence(SCOPE)['items'][0]
    assert item['raw']['observed_at'] == raw['observed_at']
    assert item['reason'] == 'future_observation'
    assert store.diagnostics(SCOPE)['last_valid_observed_at'] is None


def test_absent_duration_does_not_create_threshold_alerts(tmp_path):
    store, start, snapshot, raw = fixtures(tmp_path)
    assert store.ingest(SCOPE, [raw], [snapshot])['accepted'] == 1
    store.rollup(SCOPE, start, start + timedelta(hours=1))
    summary = store.room_summary(SCOPE.organization_id, SCOPE.facility_id, 'room', start, start + timedelta(hours=1))
    stream = summary['streams'][0]
    assert stream['above_seconds'] == 300
    assert stream['outside_intervals'][0]['seconds'] == 300
    assert stream['alert_threshold_status'] == 'not_configured'
    assert stream['deviations'] == []


def test_sample_extrema_merge_across_buckets_without_implying_full_coverage(tmp_path):
    store, start, snapshot, raw = fixtures(tmp_path)
    second = dict(raw, event_id='two', value=68, observed_at=(start + timedelta(hours=1)).isoformat())
    store.ingest(SCOPE, [raw, second], [snapshot, snapshot])
    store.rollup(SCOPE, start, start + timedelta(hours=2))
    summary = store.room_summary(SCOPE.organization_id, SCOPE.facility_id, 'room', start, start + timedelta(hours=2))
    stream = summary['streams'][0]
    assert stream['sample_minimum'] == 20 and stream['sample_maximum'] == 25
    assert stream['sample_mean'] == pytest.approx(22.5)
    assert stream['sample_count'] == 2 and stream['status'] == 'PARTIAL'
    assert stream['coverage_seconds'] == 600 and stream['unknown_seconds'] == 6600
