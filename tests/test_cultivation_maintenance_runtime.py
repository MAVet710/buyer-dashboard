"""Host bootstrap acceptance using isolated SQLite; never load host configuration."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from tests.test_cultivation_intelligence_foundation import setup, configure, AT
from modules.coman.models import Facility
from modules.cultivation.edge_store import Scope
from modules.cultivation.ingress import IngressGrantService
from modules.cultivation.ingress_models import CultivationIngressGrant
from modules.cultivation.intelligence_models import TelemetryConnection
from modules.operational_moats.models import ServiceAccount
from backend.app.services import cultivation_maintenance_runtime as runtime


@pytest.fixture
def host(setup, tmp_path):
    engine, service = setup
    connection, device, payload = configure(service)
    obj = dict(enabled=True, organization_id='o1', facility_id='f1',
               database_path=str(service.edge().path), dynamic_connections=True)
    path = tmp_path/'host.json'
    path.write_text(json.dumps(obj), encoding='utf-8')
    return engine, service, connection, json.loads(payload['content'])[0], path, obj


def test_disabled_zero_io_thread(monkeypatch):
    monkeypatch.delenv('CULTIVATION_MAINTENANCE_CONFIG', raising=False)
    def forbidden(*args, **kwargs): raise AssertionError('IO or thread')
    monkeypatch.setattr(Path, 'lstat', forbidden)
    monkeypatch.setattr(threading, 'Thread', forbidden)
    assert runtime.start_host_maintenance(object()) is None


@pytest.mark.parametrize('change', [dict(secret='private'), dict(enabled=1), dict(dynamic_connections='yes'),
    dict(connection_ids=['x']), dict(database_path='relative.db'), dict(retention_days=True),
    dict(edge_options={'unknown':1}), dict(organization_id=''), dict(interval_seconds=1)])
def test_closed_config(host, change):
    *_, path, obj = host
    path.write_text(json.dumps({**obj, **change}), encoding='utf-8')
    with pytest.raises(ValueError, match='^invalid_host_config$'): runtime.load_host_config(str(path))


@pytest.mark.parametrize('data', ['{', '{"enabled":true,"enabled":false}', '[]', ' ' * 65537],
                         ids=['malformed', 'duplicate', 'array', 'oversized'])
def test_invalid_json(host, data):
    *_, path, obj = host
    path.write_text(data, encoding='utf-8')
    with pytest.raises(ValueError, match='^invalid_host_config$'): runtime.load_host_config(str(path))


@pytest.mark.parametrize('kind', ['relative', 'directory', 'reparse', 'symlink', 'hardlink', 'unc', 'ads'])
def test_unsafe_config_paths(host, monkeypatch, kind):
    *_, path, obj = host
    original = Path.lstat
    if kind in ('reparse', 'symlink', 'hardlink'):
        import stat
        def redirected(self):
            info = original(self)
            if self == path:
                return SimpleNamespace(st_mode=stat.S_IFLNK if kind == 'symlink' else info.st_mode,
                    st_file_attributes=0x400 if kind == 'reparse' else 0, st_nlink=2 if kind == 'hardlink' else 1)
            return info
        monkeypatch.setattr(Path, 'lstat', redirected)
    target = {'relative':'host.json', 'directory':str(path.parent), 'unc':r'\\server\host.json',
              'ads':str(path)+':stream'}.get(kind, str(path))
    with pytest.raises(ValueError, match='^invalid_host_config$'): runtime.load_host_config(target)


def test_discovery_one_select_and_capacity(host):
    engine, service, connection, raw, path, obj = host
    config = runtime.load_host_config(str(path))
    with Session(engine) as db, db.begin():
        db.add_all([TelemetryConnection(id=f'bounded-{i:03}', organization_id='o1', facility_id='f1',
                    provider='json', mode='file', label=f'fixture-{i}', status='configured', created_by='a') for i in range(100)])
    statements = []
    def record(conn, cursor, statement, *args): statements.append(statement)
    event.listen(engine, 'before_cursor_execute', record)
    try: ids = runtime._discover(engine, config.maintenance)
    finally: event.remove(engine, 'before_cursor_execute', record)
    assert len(ids) == 101
    assert len([q for q in statements if q.lstrip().upper().startswith('SELECT')]) == 1
    before = service.edge().path.read_bytes()
    controller = runtime.HostMaintenanceController(engine, config)
    result = controller.tick()
    assert result['error_code'] == 'connection_capacity' and result['excess'] == 1
    assert service.edge().path.read_bytes() == before


def test_actual_pending_resolution_rollup_new_ui_connection_retention_default(host, monkeypatch):
    engine, service, connection, raw, path, obj = host
    store = service.edge()
    sc = Scope('o1', 'f1', connection['id'])
    store.ingest(sc, [raw])
    config = runtime.load_host_config(str(path))
    assert config.maintenance.retention_days is None
    def forbidden(*args, **kwargs): raise AssertionError('retention disabled')
    monkeypatch.setattr(type(store), 'retention', forbidden)
    controller = runtime.HostMaintenanceController(engine, config)
    result = controller.tick()
    assert result['resolved'] == 1 and result['rebuilt'] >= 1
    with store._db() as db:
        assert db.execute('SELECT COUNT(*) FROM buckets WHERE dirty=0').fetchone()[0] >= 1
        assert db.execute('SELECT COUNT(*) FROM evidence WHERE raw IS NOT NULL').fetchone()[0] == 1
    new = service.create_connection(dict(provider='json', label='New UI push', mode='push'))
    assert new['id'] not in runtime._discover(engine, config.maintenance)
    IngressGrantService(engine, service.context).issue_grant(new['id'], dict(
        version=1, label='Fixture', expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
    assert controller.tick()['connections'] == 2
    assert new['id'] in controller.known_ids


@pytest.mark.parametrize('denial', ['revoked', 'paused', 'capability', 'foreign', 'grant', 'account', 'wildcard', 'malformed'])
def test_discovery_and_resolver_denials_preserve_pending(host, denial):
    engine, service, connection, raw, path, obj = host
    if denial in ('grant', 'account', 'wildcard', 'malformed'):
        connection = service.create_connection(dict(provider='json', label='Push', mode='push'))
        issued = IngressGrantService(engine, service.context).issue_grant(connection['id'], dict(
            version=1, label='Fixture', expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
    sc = Scope('o1', 'f1', connection['id'])
    service.edge().ingest(sc, [raw])
    with Session(engine) as db, db.begin():
        if denial == 'revoked': db.get(TelemetryConnection, connection['id']).revoked_at = AT
        if denial == 'paused': db.get(Facility, 'f1').active = False
        if denial == 'capability': db.get(Facility, 'f1').cultivation_enabled = False
        if denial == 'grant': db.get(CultivationIngressGrant, issued['grant']['id']).revoked_at = AT
        if denial == 'account': db.get(ServiceAccount, issued['grant']['service_account_id']).active = False
        if denial in ('wildcard', 'malformed'):
            db.get(ServiceAccount, issued['grant']['service_account_id']).scopes_json = '["*"]' if denial == 'wildcard' else '{'
    config = runtime.load_host_config(str(path))
    if denial == 'foreign': config = replace(config, maintenance=replace(config.maintenance, organization_id='o2', facility_id='f2'))
    controller = runtime.HostMaintenanceController(engine, config)
    controller.tick()
    assert connection['id'] not in controller.known_ids
    assert service.edge().evidence(sc)['items'][0]['state'] == 'pending'


def test_outage_preserves_known_scope_and_no_cached_resolution(host, monkeypatch):
    engine, service, connection, raw, path, obj = host
    controller = runtime.HostMaintenanceController(engine, runtime.load_host_config(str(path)))
    controller.tick()
    sc = Scope('o1', 'f1', connection['id'])
    service.edge().ingest(sc, [raw])
    def outage(*args): raise RuntimeError('private SQL path token')
    event.listen(engine, 'before_cursor_execute', outage)
    try:
        result = controller.tick()
        assert result['state'] == 'backoff' and result['connections'] == 1
        assert controller.known_ids == (connection['id'],)
        assert 'private' not in str(result)
        assert controller.tick() == result
        assert service.edge().evidence(sc)['items'][0]['state'] == 'pending'
    finally: event.remove(engine, 'before_cursor_execute', outage)
    controller._retry_at = 0
    assert controller.tick()['resolved'] == 1


def test_lifecycle_stop_timeout_no_duplicate_restart_env_and_safe_status(host, monkeypatch):
    engine, service, connection, raw, path, obj = host
    entered, release = threading.Event(), threading.Event()
    def blocked(self, stop):
        entered.set()
        release.wait(5)
    monkeypatch.setattr(runtime.HostMaintenanceController, 'run', blocked)
    monkeypatch.setenv('CULTIVATION_MAINTENANCE_CONFIG', str(path))
    handle = runtime.start_host_maintenance(engine)
    try:
        assert entered.wait(2)
        assert runtime.start_host_maintenance(engine, str(path)) is handle
        assert not runtime.stop_maintenance(0)
        assert runtime.start_host_maintenance(engine, str(path)) is handle
        with pytest.raises(ValueError, match='maintenance_already_running'):
            runtime.start_host_maintenance(object(), str(path))
        path.write_text(json.dumps({**obj, 'interval_seconds':60}), encoding='utf-8')
        with pytest.raises(ValueError, match='maintenance_already_running'):
            runtime.start_host_maintenance(engine, str(path))
        snapshot = runtime.maintenance_status()
        assert snapshot['state'] == 'stopping'
        assert set(snapshot) <= {'state', 'error_code', 'connections', 'excess'}
        release.set()
        assert runtime.stop_maintenance(2)
        second = runtime.start_host_maintenance(engine, str(path))
        assert second is not handle
    finally:
        release.set()
        assert runtime.stop_maintenance(5)


def test_static_and_disabled_file(host):
    *_, path, obj = host
    path.write_text('{"enabled":false}', encoding='utf-8')
    assert runtime.start_host_maintenance(object(), str(path)) is None
    obj.pop('dynamic_connections')
    obj['connection_ids'] = ['explicit']
    path.write_text(json.dumps(obj), encoding='utf-8')
    config = runtime.load_host_config(str(path))
    assert not config.dynamic_connections and config.maintenance.connection_ids == ('explicit',)


def test_current_resolver_rechecks_after_discovery(host, monkeypatch):
    engine, service, connection, raw, path, obj = host
    sc = Scope('o1', 'f1', connection['id'])
    service.edge().ingest(sc, [raw])
    discover = runtime._discover
    def revoke_after_discovery(engine, config):
        ids = discover(engine, config)
        with Session(engine) as db, db.begin():
            db.get(TelemetryConnection, connection['id']).revoked_at = AT
        return ids
    monkeypatch.setattr(runtime, '_discover', revoke_after_discovery)
    controller = runtime.HostMaintenanceController(engine, runtime.load_host_config(str(path)))
    assert controller.tick()['state'] == 'stopped'
    assert service.edge().evidence(sc)['items'][0]['state'] == 'pending'


def test_stop_before_discovery_no_io(host, monkeypatch):
    engine, service, connection, raw, path, obj = host
    controller = runtime.HostMaintenanceController(engine, runtime.load_host_config(str(path)))
    def forbidden(*args): raise AssertionError('discovery after stop')
    monkeypatch.setattr(runtime, '_discover', forbidden)
    stop = threading.Event()
    stop.set()
    assert controller.tick(stop)['state'] == 'stopped'


def test_supervisor_redacts_unexpected_exception(host, monkeypatch):
    engine, service, connection, raw, path, obj = host
    def fail(*args): raise RuntimeError('private exception')
    monkeypatch.setattr(runtime.HostMaintenanceController, 'run', fail)
    handle = runtime.start_host_maintenance(engine, str(path))
    handle.thread.join(2)
    assert handle.snapshot()['state'] == 'failed'
    assert 'private' not in str(handle.snapshot())
    assert runtime.stop_maintenance(2)
