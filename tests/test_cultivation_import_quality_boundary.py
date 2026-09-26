"""Independent regressions for supplied quality and safe export HTTP errors."""
import csv
from datetime import datetime, timedelta, timezone
import io
import json

import pytest
from tests.test_cultivation_intelligence_end_to_end import (
    PREFIX, harness, historical_context, get, post,
)
from modules.cultivation.edge_store import Scope


def export_body(h, format, quality='absent'):
    row = dict(event_id='quality-boundary', source_device_id='fixture',
               source_channel='temp', source_metric='vendor_temp', value=77,
               unit='F', observed_at=(datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat())
    if quality != 'absent':
        row['quality'] = quality
    content = json.dumps([row])
    if format == 'csv':
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
        content = stream.getvalue()
    return dict(format=format, content=content, mappings=[dict(
        source_channel='temp', source_metric='vendor_temp', metric='temperature', unit='F')])


@pytest.mark.parametrize('format', ['json', 'csv'])
@pytest.mark.parametrize('quality', ['invalid', 'suspect'])
def test_supplied_bad_quality_cannot_become_valid(historical_context, format, quality):
    h = historical_context
    body = export_body(h, format, quality)
    path = f'/connections/{h.history.connection}'
    preview = post(h, path + '/imports/preview', body)
    result = post(h, path + '/imports', dict(body, digest=preview['digest']))
    assert result['accepted'] == 0 and result['quarantined'] == 1
    scope = Scope(h.own.org, h.own.facility, h.history.connection)
    row = h.edge.evidence(scope)['items'][0]
    assert row['raw']['quality'] == quality and row['state'] == 'quarantined'
    assert h.edge.diagnostics(scope)['last_valid_observed_at'] is None
    room = get(h, f'/rooms/{h.own.room}')
    assert room['edge_latest']['readings'][0]['status'] == 'invalid'
    assert room['edge_latest']['readings'][0]['value'] is None


@pytest.mark.parametrize('format', ['json', 'csv'])
def test_absent_quality_keeps_documented_valid_default(historical_context, format):
    h = historical_context
    body = export_body(h, format)
    path = f'/connections/{h.history.connection}'
    preview = post(h, path + '/imports/preview', body)
    result = post(h, path + '/imports', dict(body, digest=preview['digest']))
    assert result['accepted'] == 1 and result['quarantined'] == 0
    room = get(h, f'/rooms/{h.own.room}')
    latest = room['edge_latest']['readings'][0]
    assert (latest['value'], latest['unit']) == (25, 'C')
    assert (latest['original_value'], latest['original_unit']) == ('77' if format == 'csv' else 77, 'F')
    assert latest['snapshot']['cycle_id'] == h.history.cycle


@pytest.mark.parametrize('suffix', ['/imports/preview', '/imports'])
@pytest.mark.parametrize('format,content', [
    ('json', '{broken export with private source text'),
    ('csv', 'event_id,event_id\na,b\n'),
])
def test_malformed_exports_return_safe_422(harness, suffix, format, content):
    h = harness
    connection = post(h, '/connections', {'provider': format, 'label': 'Malformed test'})
    body = dict(format=format, content=content, mappings=[])
    if suffix == '/imports':
        body['digest'] = '0' * 64
    response = h.client.post(PREFIX + f'/connections/{connection["id"]}' + suffix, json=body)
    assert response.status_code == 422
    assert response.json()['detail'] == 'Export could not be parsed. Check the format, columns and row limits.'
    assert 'private source text' not in response.text
