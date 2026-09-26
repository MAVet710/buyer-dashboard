"""Preview uses real scoped mappings, bounded SQL, and no local evidence writes."""
import json
from sqlalchemy import event
from modules.cultivation.gateway import TelemetryGatewayService
from tests.test_cultivation_intelligence_end_to_end import harness, historical_context


def preview(h, rows, metric='temperature', format='json'):
    content = json.dumps(rows) if format == 'json' else rows
    return TelemetryGatewayService(h.engine, h.state['context'], path='').preview(h.history.connection, {
        'format': format, 'content': content,
        'mappings': [{'source_channel': 'temp', 'source_metric': 'vendor_temp', 'unit': 'F', 'metric': metric}]})


def reading(h, **changes):
    return dict(event_id='e1', source_device_id='fixture', source_channel='temp',
                source_metric='vendor_temp', value='077.00', unit='F',
                observed_at=h.history.start.isoformat(), **changes)


def test_real_conversion_original_string_scoped_labels_and_no_edge(historical_context, monkeypatch):
    h = historical_context
    monkeypatch.setattr(TelemetryGatewayService, 'edge', lambda *_: (_ for _ in ()).throw(AssertionError('preview opened edge')))
    before = len(h.mutations)
    row = reading(h)
    content = ','.join(row) + '\n' + ','.join(row.values()) + '\n'
    result = preview(h, content, format='csv')
    sample, = result['sample_rows']
    assert sample['original_value'] == '077.00'
    assert (sample['normalized_value'], sample['normalized_unit']) == (25, 'C')
    assert (sample['room_id'], sample['room_name'], sample['cycle_id']) == (h.own.room, 'Flower A', h.history.cycle)
    assert sample['status'] == 'normalized_not_committed'
    assert result['samples_truncated'] is False
    assert len(h.mutations) == before
    assert result['digest'] == preview(h, content, format='csv')['digest']


def test_invalid_and_conflicting_samples_do_not_claim_normalized(historical_context):
    h = historical_context
    rows = []
    for changes in ({'quality': 'invalid'}, {'value': 'NaN'}, {'observed_at': 'no-time'},
                    {'observed_at': '2099-01-01T00:00:00Z'}, {'value': True},
                    {'source_device_id': 'dla_sensitive_credential'}, {'value': 'Bearer hidden'}):
        rows.append(dict(reading(h), **changes))
    result = preview(h, rows)
    assert all(row['status'] == 'invalid_measurement' and row['normalized_value'] is None for row in result['sample_rows'])
    assert 'dla_sensitive' not in json.dumps(result) and 'Bearer hidden' not in json.dumps(result)
    conflict = preview(h, [reading(h)], metric='relative_humidity')
    assert conflict['sample_rows'][0]['status'] == 'metric_conflict'
    assert conflict['sample_rows'][0]['normalized_value'] is None
    assert not conflict['can_commit']
    pending = preview(h, [dict(reading(h), source_device_id='unknown')])
    assert pending['sample_rows'][0]['status'] == 'pending_mapping'


def test_twenty_samples_fixed_queries_and_unknown_metadata_not_echoed(historical_context):
    h = historical_context
    statements = []
    def record(*args):
        if args[2].lstrip().upper().startswith('SELECT'):
            statements.append(args[2])
    event.listen(h.engine, 'before_cursor_execute', record)
    try:
        one = preview(h, [reading(h)])
        count = len(statements)
        statements.clear()
        many = preview(h, [dict(reading(h), private_metadata='secret', source_extra='do not echo') for _ in range(500)])
        assert len(statements) == count
    finally:
        event.remove(h.engine, 'before_cursor_execute', record)
    assert len(many['sample_rows']) == 20 and many['samples_truncated']
    assert 'private_metadata' not in json.dumps(many) and 'do not echo' not in json.dumps(many)
    assert one['context_fingerprint'] != many['context_fingerprint']
