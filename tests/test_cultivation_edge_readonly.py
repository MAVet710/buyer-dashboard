"""Authenticated deviation inspection cannot migrate or alter local evidence."""
import json
import sqlite3

import pytest

from modules.cultivation.edge_store import EdgeStore, EdgeError, Scope
from tests.test_cultivation_edge_work import bridge, acquire, listing, counts
from tests.test_cultivation_intelligence_end_to_end import harness, historical_context


def test_actual_get_never_invalidates_another_tenant_or_initializes(bridge, monkeypatch):
    h = bridge
    acquire(h)
    foreign = Scope(h.other.org, h.other.facility, 'foreign-connection')
    with h.edge._db(write=True) as db:
        row = dict(db.execute('SELECT * FROM buckets WHERE scope=?', (h.scope.key,)).fetchone())
        payload = json.loads(row['payload'])
        payload['calculation_version'] = 2
        row.update(scope=foreign.key, org=h.other.org, facility=h.other.facility,
                   dirty=0, ack=1, payload=json.dumps(payload))
        db.execute('INSERT INTO buckets (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))
    original = sqlite3.connect
    statements = []
    def tracked(*args, **kwargs):
        conn = original(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn
    before = counts(h)
    monkeypatch.setattr(sqlite3, 'connect', tracked)
    result = listing(h)
    assert result['can_create_work'] is True and result['items']
    writes = [sql for sql in statements if sql.lstrip().upper().startswith(
        ('CREATE ', 'INSERT ', 'UPDATE ', 'DELETE ', 'ALTER ', 'BEGIN IMMEDIATE', 'PRAGMA JOURNAL_MODE='))]
    assert writes == []
    assert counts(h) == before
    with original(h.edge.path) as db:
        assert db.execute('SELECT dirty,ack FROM buckets WHERE scope=?', (foreign.key,)).fetchone() == (0, 1)


def test_missing_store_is_unavailable_without_file_creation(bridge, monkeypatch, tmp_path):
    path = tmp_path / 'missing-edge.sqlite3'
    monkeypatch.setenv('CULTIVATION_EDGE_PATH', str(path))
    response = bridge.api.get(bridge.path, params=bridge.window)
    assert response.status_code == 503
    assert not path.exists()


def test_readonly_store_refuses_a_mutating_operation(bridge):
    store = EdgeStore(bridge.edge.path, read_only=True)
    with pytest.raises(EdgeError, match='read_only_store'):
        with store._db(write=True):
            pytest.fail('Write context must not be entered')
