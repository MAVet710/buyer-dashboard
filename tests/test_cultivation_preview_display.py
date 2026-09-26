"""Independent commercial-unit preview checks against the real scoped resolver."""
import json
import pytest
from sqlalchemy.orm import Session
from modules.cultivation.gateway import TelemetryGatewayService
from modules.cultivation.intelligence_models import CultivationSensor
from modules.cultivation.models import CultivationRoom
from tests.test_cultivation_intelligence_end_to_end import harness, historical_context


@pytest.mark.parametrize('metric,unit,value,expected,canonical', [
    ('relative_humidity', '%', '55', 55, '%'),
    ('substrate_ec', 'uS/cm', '1000', 1, 'mS/cm'),
    ('irrigation_volume', 'mL', '1000', 1, 'L'),
])
def test_source_units_and_human_room_names_remain_readable(historical_context, metric, unit, value, expected, canonical):
    h = historical_context
    with Session(h.engine) as session, session.begin():
        sensor = session.get(CultivationSensor, h.history.sensor)
        sensor.metric, sensor.source_unit, sensor.unit = metric, unit, canonical
        session.get(CultivationRoom, h.own.room).display_name = 'Flower Room 4'
    raw = {'event_id': 'unit-fixture', 'source_device_id': 'fixture', 'source_channel': 'temp',
           'source_metric': 'vendor_temp', 'value': value, 'unit': unit, 'observed_at': h.history.start.isoformat()}
    before = len(h.mutations)
    result = TelemetryGatewayService(h.engine, h.state['context'], path='').preview(h.history.connection, {
        'format': 'json', 'content': json.dumps([raw]),
        'mappings': [{'source_channel': 'temp', 'source_metric': 'vendor_temp', 'unit': unit, 'metric': metric}],
    })
    sample, = result['sample_rows']
    assert sample['room_name'] == 'Flower Room 4'
    assert sample['original_value'] == value and sample['original_unit'] == unit
    assert sample['normalized_value'] == expected and sample['normalized_unit'] == canonical
    assert sample['status'] == 'normalized_not_committed'
    assert len(h.mutations) == before
