"""Subsecond evidence keeps its identity without losing explicit Work eligibility."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from modules.cultivation.edge_work import EdgeWorkService
from tests.test_cultivation_edge_work import bridge, acquire, listing, create, counts
from tests.test_cultivation_intelligence_end_to_end import harness, historical_context


@pytest.mark.parametrize('times', [(20.991, 100.125, 300.124),
                                   (0.000001, 180.000003, 300.123456)])
def test_fractional_sensor_timestamps_produce_reviewable_work(bridge, times):
    h = bridge
    acquire(h, [('first', times[0], 77), ('second', times[1], 78.8), ('closed', times[2], 71.6)])
    before = counts(h)
    item, = listing(h)['items']
    expected = ((h.history.start + timedelta(seconds=times[2])) -
                (h.history.start + timedelta(seconds=times[0]))).total_seconds()
    assert item['duration_seconds'] == expected and expected >= item['threshold_seconds']
    assert counts(h) == before
    result = create(h, item['exception_id'])
    assert result.status_code == 200, result.text
    repeated = create(h, item['exception_id']).json()
    assert repeated['work_item_id'] == result.json()['work_item_id'] and repeated['existing']
    assert counts(h)[0] == before[0] + 1


@pytest.mark.parametrize('ending', [240.990999, 240.990998])
def test_subthreshold_time_is_not_rounded_into_a_qualifying_excursion(bridge, ending):
    h = bridge
    acquire(h, [('first', .991, 77), ('second', 100.125, 77), ('closed', ending, 71.6)])
    assert listing(h)['items'] == []
    assert counts(h)[0] == 0


@pytest.mark.parametrize('reported', [None, True, '600', float('nan'), float('inf'), 600.00001, 600.001])
def test_materially_mismatched_or_invalid_summary_duration_is_rejected(bridge, monkeypatch, reported):
    h = bridge
    acquire(h)
    service = EdgeWorkService(h.engine, h.state['context'], edge=h.edge)
    summary = service._summary(h.own.room, h.history.start, h.history.end)
    altered = deepcopy(summary)
    altered['streams'][0]['deviations'][0]['seconds'] = reported
    monkeypatch.setattr(EdgeWorkService, '_summary', lambda *args, **kwargs: altered)
    assert listing(h)['items'] == []
    assert counts(h)[0] == 0


def test_future_held_seconds_cannot_qualify_historical_work(bridge):
    h = bridge
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now.replace(minute=0, second=0)
    h.history.start, h.history.end = start, start + timedelta(hours=2)
    h.window = {'start': h.history.start.isoformat(), 'end': h.history.end.isoformat()}
    offset = (now - timedelta(seconds=1) - start).total_seconds()
    acquire(h, [('ongoing', offset, 77)])
    service = EdgeWorkService(h.engine, h.state['context'], edge=h.edge)
    summary = service._summary(h.own.room, h.history.start, h.history.end)
    deviation, = summary['streams'][0]['deviations']
    assert datetime.fromisoformat(deviation['end']) > datetime.now(timezone.utc)
    assert listing(h)['items'] == []
    assert counts(h)[0] == 0
