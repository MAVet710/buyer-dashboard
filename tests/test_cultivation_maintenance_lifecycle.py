"""App lifecycle starts no unconfigured worker and always joins enabled maintenance."""
import asyncio
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('enabled', [False, True])
def test_application_lifespan_starts_and_stops_explicit_maintenance(monkeypatch, enabled):
    from backend.app import main
    from backend.app.security import runtime as security
    from backend.app.services import cultivation_maintenance_runtime as maintenance
    events = []
    engine = object()
    monkeypatch.setenv('SANDBOX_STARTUP_SEED_ENABLED', 'false')
    monkeypatch.setattr(main, 'get_engine', lambda: engine)
    class Monitor:
        def __init__(self, *args): pass
        def start(self): events.append('security-start')
        async def stop(self): events.append('security-stop')
    monkeypatch.setattr(security, 'SecurityMonitor', Monitor)
    def start(actual):
        assert actual is engine
        events.append('maintenance-config')
        return object() if enabled else None
    monkeypatch.setattr(maintenance, 'start_host_maintenance', start)
    monkeypatch.setattr(maintenance, 'stop_maintenance', lambda: events.append('maintenance-stop') or True)
    async def exercise():
        async with main.lifespan(SimpleNamespace(state=SimpleNamespace())):
            events.append('application-ready')
    asyncio.run(exercise())
    assert events == ['security-start', 'maintenance-config', 'application-ready'] + (
        ['maintenance-stop'] if enabled else []) + ['security-stop']


def test_failed_host_configuration_does_not_leave_security_monitor_running(monkeypatch):
    from backend.app import main
    from backend.app.security import runtime as security
    from backend.app.services import cultivation_maintenance_runtime as maintenance
    events = []
    monkeypatch.setenv('SANDBOX_STARTUP_SEED_ENABLED', 'false')
    monkeypatch.setattr(main, 'get_engine', object)
    class Monitor:
        def __init__(self, *args): pass
        def start(self): events.append('start')
        async def stop(self): events.append('stop')
    monkeypatch.setattr(security, 'SecurityMonitor', Monitor)
    def fail(engine): raise ValueError('invalid_host_config')
    monkeypatch.setattr(maintenance, 'start_host_maintenance', fail)
    async def exercise():
        async with main.lifespan(SimpleNamespace(state=SimpleNamespace())):
            pytest.fail('Must not serve with invalid requested maintenance configuration')
    with pytest.raises(ValueError, match='invalid_host_config'):
        asyncio.run(exercise())
    assert events == ['start', 'stop']
