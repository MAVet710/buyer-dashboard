"""Opt-in host maintenance of the canonical local evidence store.

No request context, machine token, central writes, or external transport.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import stat
import threading
import time

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from modules.coman.models import Facility, Organization
from modules.operational_moats.models import ServiceAccount
from .context_resolution import build_resolver
from .edge_store import EdgeStore, EdgeBackpressure, Scope
from .ingress_models import CultivationIngressGrant
from .intelligence_models import TelemetryConnection


class MaintenanceStopped(ValueError):
    pass


@dataclass(frozen=True)
class MaintenanceConfig:
    enabled: bool = False
    organization_id: str = ""
    facility_id: str = ""
    connection_ids: tuple[str, ...] = ()
    database_path: str = ""
    archive_directory: str | None = None
    retention_days: int | None = None
    interval_seconds: int = 30
    # Must match the canonical collector/receiver's explicit EdgeStore settings.
    edge_options: tuple[tuple[str, int], ...] = ()

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("explicit_enable_required")
        if not self.enabled:
            return
        if (type(self.connection_ids) is not tuple or not 1 <= len(self.connection_ids) <= 100
                or len(set(self.connection_ids)) != len(self.connection_ids)):
            raise ValueError("invalid_host_allowlist")
        for identity in self.connection_ids:
            if not self.organization_id or not self.facility_id or not identity:
                raise ValueError("host_binding_required")
            Scope(self.organization_id, self.facility_id, identity)
        for value in (self.database_path, self.archive_directory):
            if value is None:
                continue
            path = Path(value)
            if not path.is_absolute() or ".." in path.parts or str(path).startswith("\\\\"):
                raise ValueError("local_host_path_required")
        if type(self.interval_seconds) is not int or not 30 <= self.interval_seconds <= 3600:
            raise ValueError("invalid_interval")
        if self.retention_days is not None and (type(self.retention_days) is not int or not 1 <= self.retention_days <= 36500):
            raise ValueError("invalid_retention")
        allowed = {"max_scope_rows", "max_scope_bytes", "max_disk_bytes", "max_batch",
                   "max_query_rows", "max_gap_seconds", "bucket_seconds", "max_window_seconds",
                   "busy_timeout_ms", "max_rollup_rows", "max_rollup_streams"}
        if type(self.edge_options) is not tuple or any(type(pair) is not tuple or len(pair) != 2 for pair in self.edge_options):
            raise ValueError("immutable_edge_options_required")
        options = dict(self.edge_options)
        if len(options) != len(self.edge_options) or options.keys() - allowed:
            raise ValueError("invalid_edge_options")
        if any(type(v) is not int or v <= 0 for v in options.values()):
            raise ValueError("invalid_edge_options")
        if options.get("bucket_seconds", 3600) != 3600 or options.get("max_gap_seconds", 300) > 3600:
            raise ValueError("hourly_maintenance_required")
        if options.get("busy_timeout_ms", 5000) > 5000:
            raise ValueError("bounded_local_timeout_required")


def _host_path(path):
    """Host provisions directories and protects ACLs; reject redirected paths."""
    path = Path(path)
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            if part != path:
                raise MaintenanceStopped("host_path_unavailable") from None
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise MaintenanceStopped("host_path_unavailable")
        if part == path and stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise MaintenanceStopped("host_path_unavailable")


def _resolver(engine, config, scope):
    # Complete all central IO before opening SQLite. No cached authorization on outage.
    with Session(engine, expire_on_commit=False) as session, session.begin():
        if engine.dialect.name == "postgresql":
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            session.execute(text("SET LOCAL lock_timeout = '3s'"))
        elif engine.dialect.name == "sqlite":
            session.execute(text("PRAGMA busy_timeout=5000"))
            session.execute(text("BEGIN"))
        else:
            raise MaintenanceStopped("unsupported_database")
        facility = session.scalar(select(Facility).join(Organization, Organization.id == Facility.organization_id).where(
            Facility.id == scope.facility_id, Facility.organization_id == scope.organization_id,
            Organization.active.is_(True), Facility.active.is_(True), Facility.cultivation_enabled.is_(True)))
        connection = session.scalar(select(TelemetryConnection).where(
            TelemetryConnection.id == scope.connection_id, TelemetryConnection.organization_id == scope.organization_id,
            TelemetryConnection.facility_id == scope.facility_id,
            TelemetryConnection.status == "configured", TelemetryConnection.revoked_at.is_(None)))
        if facility is None or connection is None or connection.mode not in ("file", "push"):
            raise MaintenanceStopped("scope_stopped")
        if connection.mode == "push":
            if connection.provider != "json":
                raise MaintenanceStopped("scope_stopped")
            # Bounded grant/account set, never load token hashes or require a client token.
            accounts = session.scalars(select(ServiceAccount.scopes_json).join(
                CultivationIngressGrant, CultivationIngressGrant.service_account_id == ServiceAccount.id).where(
                CultivationIngressGrant.organization_id == scope.organization_id,
                CultivationIngressGrant.facility_id == scope.facility_id,
                CultivationIngressGrant.connection_id == scope.connection_id,
                CultivationIngressGrant.revoked_at.is_(None),
                CultivationIngressGrant.expires_at > datetime.now(timezone.utc),
                ServiceAccount.organization_id == scope.organization_id,
                ServiceAccount.facility_id == scope.facility_id, ServiceAccount.active.is_(True)).limit(201)).all()
            permitted = False
            for encoded in accounts[:200]:
                try:
                    scopes = json.loads(encoded)
                    permitted |= isinstance(scopes, list) and "cultivation:ingest" in scopes
                except (TypeError, ValueError):
                    pass
            if len(accounts) > 200 or not permitted:
                raise MaintenanceStopped("scope_stopped")
        return build_resolver(session, scope, max_gap_seconds=dict(config.edge_options).get("max_gap_seconds", 300))


class MaintenanceController:
    """One connection per tick, at most 100 retries and two one-hour rollups."""
    def __init__(self, engine, config):
        self.engine, self.config = engine, config
        self._next = 0
        self._lock = threading.Lock()
        self._failures = 0
        self._retry_at = 0.0
        self.status = {"state": "idle" if config.enabled else "disabled", "error_code": None}

    def _candidates(self, store, scope):
        # Two cursors per scope: dirty buckets and chronological evidence discovery.
        # Time-index seeks skip dense hours without reading raw rows or full-history GROUP BY.
        with store._db(write=True) as db:
            db.execute("CREATE TABLE IF NOT EXISTS local_cultivation_maintenance (scope TEXT PRIMARY KEY, discovery REAL, dirty REAL)")
            db.execute("CREATE INDEX IF NOT EXISTS local_cultivation_dirty ON buckets(scope,dirty,start)")
            db.execute("INSERT OR IGNORE INTO local_cultivation_maintenance(scope) VALUES(?)", (scope.key,))
            cursor = db.execute("SELECT discovery,dirty FROM local_cultivation_maintenance WHERE scope=?", (scope.key,)).fetchone()
            dirty = db.execute("SELECT start FROM buckets WHERE scope=? AND dirty=1 AND start>? ORDER BY start LIMIT 1",
                               (scope.key, cursor[1] if cursor[1] is not None else -1)).fetchone()
            if dirty is None:
                dirty = db.execute("SELECT start FROM buckets WHERE scope=? AND dirty=1 ORDER BY start LIMIT 1", (scope.key,)).fetchone()
            after = cursor[0] if cursor[0] is not None else 0
            row = db.execute("SELECT observed FROM evidence WHERE scope=? AND observed>=? ORDER BY observed LIMIT 1",
                             (scope.key, max(0, after-store.max_gap_seconds))).fetchone()
            if row is None:
                after = 0
                row = db.execute("SELECT observed FROM evidence WHERE scope=? AND observed>=0 ORDER BY observed LIMIT 1", (scope.key,)).fetchone()
            discovered = max(after, int(max(0, row[0]-store.max_gap_seconds)//3600)*3600) if row else None
            db.execute("UPDATE local_cultivation_maintenance SET discovery=?,dirty=? WHERE scope=?",
                       (discovered+3600 if discovered is not None else None, dirty[0] if dirty else None, scope.key))
            store._quota(db, scope.key)
        # Advance on an attempted bucket too: a quota-blocked old hour cannot starve others.
        return list(dict.fromkeys([value for value in (dirty[0] if dirty else None, discovered) if value is not None]))

    def tick(self, stop_event=None):
        if not self.config.enabled:
            return dict(self.status)
        if not self._lock.acquire(blocking=False):
            return {"state": "busy", "error_code": "iteration_busy"}
        try:
            if time.monotonic() < self._retry_at:
                return dict(self.status)
            if stop_event is not None and stop_event.is_set():
                return {"state": "stopped", "error_code": None}
            connection = self.config.connection_ids[self._next]
            self._next = (self._next+1) % len(self.config.connection_ids)
            scope = Scope(self.config.organization_id, self.config.facility_id, connection)
            facts = dict(state="running", error_code=None, attempted_at=datetime.now(timezone.utc).isoformat(),
                         examined=0, resolved=0, rebuilt=0, acknowledged=0, purged=0)
            try:
                resolver = _resolver(self.engine, self.config, scope)
                if stop_event is not None and stop_event.is_set():
                    facts["state"] = "stopped"
                    self.status = facts
                    return dict(facts)
                _host_path(self.config.database_path)
                for suffix in ("-wal", "-shm"):
                    _host_path(self.config.database_path + suffix)
                if self.config.archive_directory is not None:
                    _host_path(self.config.archive_directory)
                store = EdgeStore(self.config.database_path, **dict(self.config.edge_options))
                limit = min(100, store.max_batch, store.max_query_rows)
                retry = store.retry_pending(scope, resolver, limit=limit)
                facts.update(examined=retry["examined"], resolved=retry["resolved"])
                rollup_failed = False
                for start in self._candidates(store, scope):
                    if stop_event is not None and stop_event.is_set():
                        raise MaintenanceStopped("stop_requested")
                    try:
                        result = store.rollup(scope, datetime.fromtimestamp(start, timezone.utc),
                                              datetime.fromtimestamp(start+3600, timezone.utc))
                        rollup_failed |= bool(result["truncated"] or result["blocked"])
                        facts["rebuilt"] += result["rebuilt"]
                    except EdgeBackpressure:
                        rollup_failed = True
                if rollup_failed:
                    raise EdgeBackpressure("rollup_work_limit")
                if stop_event is not None and stop_event.is_set():
                    raise MaintenanceStopped("stop_requested")
                if self.config.archive_directory is not None:
                    archive = store.archive_aggregates(scope, self.config.archive_directory, limit=min(2, limit))
                    facts["acknowledged"] = archive["acknowledged"]
                    if archive["stale"]:
                        raise EdgeBackpressure("archive_stale")
                if self.config.retention_days is not None:
                    if stop_event is not None and stop_event.is_set():
                        raise MaintenanceStopped("stop_requested")
                    result = store.retention(scope, datetime.now(timezone.utc)-timedelta(days=self.config.retention_days), limit=limit)
                    facts["purged"] = result["purged"]
                facts.update(state="completed", completed_at=datetime.now(timezone.utc).isoformat())
                self._failures = 0
            except MaintenanceStopped:
                facts.update(state="stopped", error_code="maintenance_stopped")
            except EdgeBackpressure:
                facts.update(state="backoff", error_code="local_backpressure")
            except Exception:
                # Never echo SQL/connection strings, local paths, payloads, or exception text.
                facts.update(state="backoff", error_code="maintenance_unavailable")
            if facts["state"] != "completed":
                self._failures = min(4, self._failures+1)
                delay = min(300, self.config.interval_seconds * 2**(self._failures-1))
                self._retry_at = time.monotonic()+delay
                facts["retry_after_seconds"] = delay
            self.status = facts
            return dict(facts)
        finally:
            self._lock.release()

    def run(self, stop_event):
        while not stop_event.is_set():
            self.tick(stop_event)
            stop_event.wait(self.config.interval_seconds)
