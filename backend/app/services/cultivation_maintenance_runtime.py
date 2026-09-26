"""Trusted host bootstrap. Imports and absent host configuration start nothing."""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PureWindowsPath
import stat
import threading
import time

from sqlalchemy import select, text, exists, and_, or_, func, case, cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from modules.coman.models import Facility, Organization
from modules.operational_moats.models import ServiceAccount
from modules.cultivation.ingress_models import CultivationIngressGrant
from modules.cultivation.intelligence_models import TelemetryConnection
from modules.cultivation.local_maintenance import MaintenanceConfig, MaintenanceController, _host_path

_lock = threading.Lock()
_runtime = None
_MAX_CONFIG = 65536


@dataclass(frozen=True)
class HostMaintenanceConfig:
    maintenance: MaintenanceConfig
    dynamic_connections: bool = False


def _plain_path(value):
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError("invalid_host_config")
    path = Path(value)
    if (not path.is_absolute() or ".." in path.parts or value.startswith(("\\\\", "//"))
            or ":" in value[len(path.drive):] or "\x00" in value
            or PureWindowsPath(value).is_reserved()
            or any(p.endswith((" ", ".")) for p in path.parts)):
        raise ValueError("invalid_host_config")
    _host_path(path)
    return path


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid_host_config")
        result[key] = value
    return result


def load_host_config(config_path):
    """Read one <=64KiB local regular JSON file; errors never include input."""
    try:
        path = _plain_path(config_path)
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > _MAX_CONFIG:
            raise ValueError("invalid_host_config")
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)):
                raise ValueError("invalid_host_config")
            data = stream.read(_MAX_CONFIG + 1)
        _host_path(path)
        if len(data) > _MAX_CONFIG:
            raise ValueError("invalid_host_config")
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
        allowed = {"enabled", "organization_id", "facility_id", "database_path", "connection_ids",
                   "dynamic_connections", "archive_directory", "retention_days", "interval_seconds", "edge_options"}
        if type(obj) is not dict or obj.keys() - allowed or type(obj.get("enabled")) is not bool:
            raise ValueError("invalid_host_config")
        if not obj["enabled"]:
            if set(obj) != {"enabled"}:
                raise ValueError("invalid_host_config")
            return HostMaintenanceConfig(MaintenanceConfig())
        dynamic = obj.pop("dynamic_connections", False)
        if type(dynamic) is not bool:
            raise ValueError("invalid_host_config")
        ids = obj.pop("connection_ids", [])
        if type(ids) is not list or (dynamic and ids) or any(type(i) is not str for i in ids):
            raise ValueError("invalid_host_config")
        for key in ("organization_id", "facility_id", "database_path"):
            if type(obj.get(key)) is not str or not obj[key]:
                raise ValueError("invalid_host_config")
        database = _plain_path(obj["database_path"])
        if database.exists() and not database.is_file():
            raise ValueError("invalid_host_config")
        if obj.get("archive_directory") is not None:
            archive = _plain_path(obj["archive_directory"])
            if not archive.is_dir():
                raise ValueError("invalid_host_config")
        options = obj.pop("edge_options", {})
        if type(options) is not dict:
            raise ValueError("invalid_host_config")
        # Internal placeholder is never scheduled; discovery supplies real IDs before tick.
        config = MaintenanceConfig(**obj, connection_ids=tuple(ids) if not dynamic else ("host-discovery",),
                                   edge_options=tuple(sorted(options.items())))
        return HostMaintenanceConfig(config, dynamic)
    except Exception:
        raise ValueError("invalid_host_config") from None


def _discover(engine, config):
    """One bounded scoped SELECT; grants are EXISTS, never a per-connection query."""
    c, g, a = TelemetryConnection, CultivationIngressGrant, ServiceAccount
    if engine.dialect.name == "sqlite":
        safe_json = case((func.json_valid(a.scopes_json) == 1, a.scopes_json), else_="[]")
        values = func.json_each(safe_json).table_valued("value")
        permits = and_(func.json_type(safe_json) == "array",
                       exists(select(1).select_from(values).where(values.c.value == "cultivation:ingest")))
    elif engine.dialect.name == "postgresql":
        permits = cast(a.scopes_json, JSONB).contains(["cultivation:ingest"])
    else:
        raise ValueError("unsupported_database")
    grant = exists(select(1).select_from(g).join(a, a.id == g.service_account_id).where(
        g.organization_id == config.organization_id, g.facility_id == config.facility_id,
        g.connection_id == c.id, g.revoked_at.is_(None), g.expires_at > datetime.now(timezone.utc),
        a.organization_id == config.organization_id, a.facility_id == config.facility_id,
        a.active.is_(True), permits))
    query = select(c.id).join(Facility, and_(Facility.id == c.facility_id,
        Facility.organization_id == c.organization_id)).join(Organization, Organization.id == c.organization_id).where(
        c.organization_id == config.organization_id, c.facility_id == config.facility_id,
        c.status == "configured", c.revoked_at.is_(None), Facility.active.is_(True),
        Facility.cultivation_enabled.is_(True), Organization.active.is_(True),
        or_(c.mode == "file", and_(c.mode == "push", c.provider == "json", grant))).order_by(c.id).limit(101)
    with Session(engine) as session, session.begin():
        if engine.dialect.name == "postgresql":
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            session.execute(text("SET LOCAL lock_timeout = '3s'"))
        else:
            session.execute(text("PRAGMA busy_timeout=5000"))
        return tuple(session.scalars(query))


class HostMaintenanceController:
    """Discovery schedules existing maintenance, preserving its fresh admission checks."""
    def __init__(self, engine, config):
        self.engine, self.config = engine, config
        self.worker = MaintenanceController(engine, config.maintenance)
        self.known_ids = ()
        self.status = {"state": "idle", "error_code": None, "connections": 0, "excess": 0}
        self._retry_at = 0.0
        self._failures = 0
        self._lock = threading.Lock()

    def tick(self, stop_event=None):
        if not self._lock.acquire(blocking=False):
            return {"state": "busy", "error_code": "iteration_busy"}
        try:
            if stop_event is not None and stop_event.is_set():
                self.status = {**self.status, "state": "stopped"}
                return dict(self.status)
            if time.monotonic() < max(self._retry_at, self.worker._retry_at):
                return dict(self.status)
            try:
                ids = _discover(self.engine, self.config.maintenance)
                if len(ids) > 100:
                    self.status = {"state": "backoff", "error_code": "connection_capacity", "connections": len(self.known_ids), "excess": 1}
                    self._retry_at = time.monotonic() + 300
                    return dict(self.status)
                self.known_ids = ids
                self._failures = 0
                if not ids:
                    self.status = {"state": "idle", "error_code": None, "connections": 0, "excess": 0}
                    return dict(self.status)
                self.worker.config = replace(self.config.maintenance, connection_ids=ids)
                self.worker._next %= len(ids)
                self.status = {**self.worker.tick(stop_event), "connections": len(ids), "excess": 0}
            except Exception:
                self._failures = min(5, self._failures + 1)
                delay = min(300, self.config.maintenance.interval_seconds * 2 ** (self._failures - 1))
                self._retry_at = time.monotonic() + delay
                self.status = {"state": "backoff", "error_code": "maintenance_unavailable",
                               "connections": len(self.known_ids), "excess": 0, "retry_after_seconds": delay}
            return dict(self.status)
        finally:
            self._lock.release()

    def run(self, stop_event):
        while not stop_event.is_set():
            self.tick(stop_event)
            stop_event.wait(self.config.maintenance.interval_seconds)


class MaintenanceRuntime:
    def __init__(self, engine, config):
        self.engine, self.config = engine, config
        self.controller = (HostMaintenanceController(engine, config) if isinstance(config, HostMaintenanceConfig)
                           and config.dynamic_connections else MaintenanceController(
                               engine, config.maintenance if isinstance(config, HostMaintenanceConfig) else config))
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="cultivation-local-maintenance", daemon=True)
        self._failed = False

    def _run(self):
        try:
            self.controller.run(self.stop_event)
        except Exception:
            self._failed = True  # Never expose exception details through thread excepthook.

    def snapshot(self):
        result = {key: value for key, value in dict(self.controller.status).items()
                  if key in {"state", "error_code", "examined", "resolved", "rebuilt", "acknowledged",
                             "purged", "connections", "excess", "retry_after_seconds"}}
        if self._failed:
            result.update(state="failed", error_code="maintenance_unavailable")
        elif self.stop_event.is_set():
            result["state"] = "stopping" if self.thread.is_alive() else "stopped"
        return result

    def stop(self, timeout=5):
        """False means still stopping: the singleton stays reserved until exit."""
        if type(timeout) not in (int, float) or not 0 <= timeout <= 5:
            raise ValueError("invalid_stop_timeout")
        self.stop_event.set()
        self.thread.join(timeout)
        return not self.thread.is_alive()


def start_maintenance(engine, config=MaintenanceConfig()):
    """Compatibility API for trusted Python callers; engine must have bounded IO."""
    global _runtime
    settings = config.maintenance if isinstance(config, HostMaintenanceConfig) else config
    if not settings.enabled:
        return None
    with _lock:
        if _runtime is not None and _runtime.thread.is_alive():
            if _runtime.engine is not engine or _runtime.config != config:
                raise ValueError("maintenance_already_running")
            return _runtime
        _runtime = MaintenanceRuntime(engine, config)
        _runtime.thread.start()
        return _runtime


def start_host_maintenance(engine, config_path=None):
    """Launcher/lifespan only. No path and no host env setting means zero IO/thread."""
    path = config_path if config_path is not None else os.environ.get("CULTIVATION_MAINTENANCE_CONFIG")
    if path is None or path == "":
        return None
    return start_maintenance(engine, load_host_config(path))


def maintenance_status():
    with _lock:
        return {"state": "disabled", "error_code": None} if _runtime is None else _runtime.snapshot()


def stop_maintenance(timeout=5):
    with _lock:
        return _runtime is None or _runtime.stop(timeout)
