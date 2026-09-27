"""Local-only, scoped SQLite cultivation evidence and aggregate storage.

The backend supplies authorized scopes and immutable historical mappings. This
module has no transport or ORM dependency and may also be imported directly by
the offline CLI without importing the cultivation application's package init.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import uuid

try:
    from .metrics import METRIC_REGISTRY, normalize_metric_value
except ImportError:  # Standalone offline CLI, not the application package.
    from metrics import METRIC_REGISTRY, normalize_metric_value


class EdgeError(ValueError):
    """Fixed, safe error codes only."""


class EdgeBackpressure(EdgeError):
    pass


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _token(value, *, optional=False):
    if optional and value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[\w@ .:/%+Â°ÂµÂ²-]{1,160}", value) or "://" in value:
        raise EdgeError("invalid_identifier")
    if any(word in value.lower() for word in ("bearer ", "password", "secret", "api_key", "access_token")):
        raise EdgeError("unsafe_identifier")
    return value


def validate_source_identity(value):
    """Machine identifiers share durable-store safety, with a bounded wire alphabet."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:@-]{1,120}", value):
        raise EdgeError("invalid_identifier")
    return _token(value)


def _timestamp(value):
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError
        result = dt.timestamp()
        if not 0 <= result <= 4102444800:
            raise ValueError
        return result
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise EdgeError("invalid_timestamp") from None


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _finite(value):
    if isinstance(value, bool):
        raise EdgeError("invalid_number")
    try:
        result = float(value)
        if not math.isfinite(result) or abs(result) > 1e100:
            raise ValueError
        return result
    except (ValueError, TypeError, OverflowError):
        raise EdgeError("invalid_number") from None


@dataclass(frozen=True)
class Scope:
    organization_id: str
    facility_id: str
    connection_id: str

    def __post_init__(self):
        for value in asdict(self).values():
            _token(value)

    @property
    def key(self):
        return _json(asdict(self))


_READING_FIELDS = {"event_id", "source_device_id", "source_channel", "source_metric", "value", "unit", "observed_at", "received_at", "quality", "timestamp_basis"}
_SNAPSHOT_FIELDS = {"organization_id", "facility_id", "connection_id", "room_id", "device_id", "sensor_id", "mapping_revision", "metric", "effective_from", "effective_to", "zone_id", "cycle_id", "stage_id", "recipe_revision", "target_min", "target_max", "threshold_seconds"}


def _context(snapshot):
    # Absence and null optional values have identical semantics. Hold bounds
    # belong only to the immutable individual evidence, never the group.
    return {k: v for k, v in snapshot.items()
            if k not in ("effective_from", "effective_to") and v is not None}


def _merge_attribution(intervals, begin, end):
    if intervals and intervals[-1][1] == begin:
        intervals[-1][1] = end
    else:
        intervals.append([begin, end])


class EdgeStore:
    def __init__(self, path, *, max_scope_rows=100000, max_scope_bytes=134217728,
                 max_disk_bytes=536870912, max_batch=500, max_query_rows=10000,
                 max_gap_seconds=300, bucket_seconds=3600,
                 max_window_seconds=2678400, busy_timeout_ms=5000,
                 max_rollup_rows=100000, max_rollup_streams=1000, read_only=False):
        for value in (max_scope_rows, max_scope_bytes, max_disk_bytes, max_batch,
                      max_query_rows, max_gap_seconds, bucket_seconds, max_window_seconds, busy_timeout_ms,
                      max_rollup_rows, max_rollup_streams):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise EdgeError("invalid_limit")
        if max_gap_seconds > 86400 or bucket_seconds > 86400 or max_window_seconds > 2678400:
            raise EdgeError("invalid_limit")
        if type(read_only) is not bool:
            raise EdgeError("invalid_read_mode")
        self.read_only = read_only
        self.path = Path(path)
        self.max_scope_rows, self.max_scope_bytes = max_scope_rows, max_scope_bytes
        self.max_disk_bytes, self.max_batch = max_disk_bytes, max_batch
        self.max_query_rows, self.max_gap_seconds = max_query_rows, max_gap_seconds
        self.bucket_seconds, self.max_window_seconds = bucket_seconds, max_window_seconds
        self.busy_timeout_ms = busy_timeout_ms
        self.max_rollup_rows, self.max_rollup_streams = max_rollup_rows, max_rollup_streams
        if self.read_only:
            # Query-time inspection must never initialize schema or invalidate
            # another tenant's legacy aggregates. Upgrades belong to host startup.
            with self._db() as db:
                config = _json({"schema": 1, "bucket_seconds": bucket_seconds, "max_gap_seconds": max_gap_seconds})
                row = db.execute("SELECT config FROM edge_config WHERE id=1").fetchone()
                if row is None or row[0] != config:
                    raise EdgeError("store_configuration_mismatch")
            return
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS edge_config (id INTEGER PRIMARY KEY CHECK(id=1), config TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS evidence (
                    scope TEXT NOT NULL, identity TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    raw TEXT, observed REAL, received REAL NOT NULL, stream TEXT NOT NULL,
                    snapshot TEXT, canonical TEXT, state TEXT NOT NULL, reason TEXT NOT NULL,
                    PRIMARY KEY(scope,identity,fingerprint));
                CREATE INDEX IF NOT EXISTS edge_time ON evidence(scope,observed);
                CREATE INDEX IF NOT EXISTS edge_state ON evidence(scope,state,identity);
                CREATE INDEX IF NOT EXISTS edge_latest_room ON evidence(
                    json_extract(scope,'$.organization_id'), json_extract(scope,'$.facility_id'),
                    json_extract(snapshot,'$.room_id'), COALESCE(observed,received) DESC,
                    identity DESC, fingerprint DESC);
                CREATE TABLE IF NOT EXISTS buckets (
                    scope TEXT NOT NULL, org TEXT NOT NULL, facility TEXT NOT NULL,
                    start REAL NOT NULL, key TEXT NOT NULL, revision TEXT NOT NULL,
                    payload TEXT NOT NULL, dirty INTEGER NOT NULL DEFAULT 0,
                    ack INTEGER NOT NULL DEFAULT 0, purged INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(scope,start), UNIQUE(scope,key));
                CREATE INDEX IF NOT EXISTS edge_rooms ON buckets(org,facility,start);
                CREATE INDEX IF NOT EXISTS edge_stream_time ON evidence(scope,stream,observed,identity,fingerprint);
                CREATE TABLE IF NOT EXISTS edge_transport (
                    scope TEXT PRIMARY KEY, last_committed_at TEXT, last_batch_id TEXT, last_grant_id TEXT,
                    accepted_total INTEGER NOT NULL, duplicate_total INTEGER NOT NULL,
                    pending_total INTEGER NOT NULL, quarantined_total INTEGER NOT NULL, conflict_total INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS edge_maintenance (
                    scope TEXT NOT NULL, task TEXT NOT NULL, identity TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    PRIMARY KEY(scope,task));
                CREATE TABLE IF NOT EXISTS edge_capacity_sample (
                    scope TEXT PRIMARY KEY, first_at REAL NOT NULL, last_at REAL NOT NULL,
                    first_rows INTEGER NOT NULL, first_bytes INTEGER NOT NULL,
                    last_rows INTEGER NOT NULL, last_bytes INTEGER NOT NULL);
            """)
            config = _json({"schema": 1, "bucket_seconds": bucket_seconds, "max_gap_seconds": max_gap_seconds})
            db.execute("INSERT OR IGNORE INTO edge_config VALUES(1,?)", (config,))
            if db.execute("SELECT config FROM edge_config WHERE id=1").fetchone()[0] != config:
                raise EdgeError("store_configuration_mismatch")
        # Old per-observation groups must not be published or acknowledged as
        # repaired evidence. Purged buckets remain blocked, never reconstructed
        # from incomplete history. Preserve their revision generation.
        with self._db(write=True) as db:
            self._initialize_usage(db)
            db.execute("UPDATE buckets SET dirty=1,ack=0 WHERE COALESCE(json_extract(payload,'$.calculation_version'),0)<3")

    @contextmanager
    def _db(self, write=False):
        db = None
        try:
            if self.read_only:
                if write:
                    raise EdgeError("read_only_store")
                db = sqlite3.connect(self.path.absolute().as_uri() + "?mode=ro", uri=True,
                                     timeout=self.busy_timeout_ms / 1000, isolation_level=None)
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA query_only=ON")
                db.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
                db.execute("BEGIN")
                yield db
                return
            db = sqlite3.connect(self.path, timeout=self.busy_timeout_ms / 1000, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
            if db.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() != "wal":
                raise EdgeBackpressure("wal_required")
            db.execute("PRAGMA synchronous=FULL")
            if db.execute("PRAGMA synchronous").fetchone()[0] != 2:
                raise EdgeBackpressure("full_durability_required")
            db.execute("PRAGMA secure_delete=ON")
            db.execute("PRAGMA wal_autocheckpoint=64")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            if write:
                db.commit()
        except (sqlite3.Error, OSError):
            if db is not None:
                db.rollback()
            raise EdgeBackpressure("local_storage_unavailable") from None
        except BaseException:
            if db is not None:
                db.rollback()
            raise
        finally:
            if db is not None:
                db.close()

    def _scope(self, scope):
        if not isinstance(scope, Scope):
            raise EdgeError("scope_required")
        return scope.key

    def _limit(self, limit):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.max_batch:
            raise EdgeError("invalid_limit")
        return limit

    def _recount_usage(self, db, scope):
        a = db.execute("SELECT COUNT(*), COALESCE(SUM(COALESCE(LENGTH(CAST(raw AS BLOB)),0)+1024+LENGTH(CAST(scope||identity||fingerprint||stream AS BLOB))+COALESCE(LENGTH(CAST(snapshot AS BLOB)),0)+COALESCE(LENGTH(CAST(canonical AS BLOB)),0)),0) FROM evidence WHERE scope=?", (scope,)).fetchone()
        b = db.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(CAST(payload||scope||org||facility||key||revision AS BLOB))+1024),0) FROM buckets WHERE scope=?", (scope,)).fetchone()
        return a[0] + b[0], a[1] + b[1]

    def _initialize_usage(self, db):
        # Schema marker, initial reconciliation and triggers commit atomically.
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='edge_usage'").fetchone():
            return
        db.execute("CREATE TABLE edge_usage(scope TEXT PRIMARY KEY, rows INTEGER NOT NULL, bytes INTEGER NOT NULL)")
        expressions = {
            "evidence": "COALESCE(LENGTH(CAST({p}raw AS BLOB)),0)+1024+LENGTH(CAST({p}scope||{p}identity||{p}fingerprint||{p}stream AS BLOB))+COALESCE(LENGTH(CAST({p}snapshot AS BLOB)),0)+COALESCE(LENGTH(CAST({p}canonical AS BLOB)),0)",
            "buckets": "LENGTH(CAST({p}payload||{p}scope||{p}org||{p}facility||{p}key||{p}revision AS BLOB))+1024",
        }
        for table, expression in expressions.items():
            db.execute(f"INSERT INTO edge_usage SELECT scope,COUNT(*),SUM({expression.format(p='')}) FROM {table} GROUP BY scope ON CONFLICT(scope) DO UPDATE SET rows=rows+excluded.rows,bytes=bytes+excluded.bytes")
            new, old = expression.format(p="NEW."), expression.format(p="OLD.")
            add = f"INSERT INTO edge_usage VALUES(NEW.scope,1,{new}) ON CONFLICT(scope) DO UPDATE SET rows=rows+1,bytes=bytes+excluded.bytes;"
            remove = f"UPDATE edge_usage SET rows=rows-1,bytes=bytes-({old}) WHERE scope=OLD.scope;"
            for operation, statements in (("INSERT", add), ("DELETE", remove), ("UPDATE", remove + add)):
                db.execute(f"CREATE TRIGGER edge_usage_{table}_{operation.lower()} AFTER {operation} ON {table} BEGIN {statements} END")

    def _usage(self, db, scope):
        row = db.execute("SELECT rows,bytes FROM edge_usage WHERE scope=?", (scope,)).fetchone()
        return tuple(row) if row else (0, 0)

    def _maintenance_page(self, db, scope, task, predicate, args, limit):
        cursor = db.execute("SELECT identity,fingerprint FROM edge_maintenance WHERE scope=? AND task=?", (scope, task)).fetchone()
        after = tuple(cursor) if cursor else ("", "")
        rows = db.execute(f"SELECT * FROM evidence WHERE scope=? AND {predicate} AND (identity,fingerprint)>(?,?) ORDER BY identity,fingerprint LIMIT ?", (scope, *args, *after, limit + 1)).fetchall()
        if not rows and cursor:
            rows = db.execute(f"SELECT * FROM evidence WHERE scope=? AND {predicate} ORDER BY identity,fingerprint LIMIT ?", (scope, *args, limit + 1)).fetchall()
        return rows

    def _advance_maintenance(self, db, scope, task, rows, limit):
        if rows:
            last = rows[min(len(rows), limit)-1]
            db.execute("INSERT INTO edge_maintenance VALUES(?,?,?,?) ON CONFLICT(scope,task) DO UPDATE SET identity=excluded.identity,fingerprint=excluded.fingerprint", (scope, task, last["identity"], last["fingerprint"]))

    def _quota(self, db, scope):
        rows, size = self._usage(db, scope)
        if rows > self.max_scope_rows or size > self.max_scope_bytes:
            raise EdgeBackpressure("scope_capacity_reached")
        physical = self._physical_size()
        pages = db.execute("PRAGMA page_count").fetchone()[0] * db.execute("PRAGMA page_size").fetchone()[0]
        # Reserve the whole transaction's possible WAL image before committing.
        if physical + pages > self.max_disk_bytes:
            raise EdgeBackpressure("disk_capacity_reached")

    def _physical_size(self):
        size = 0
        for path in (self.path, Path(str(self.path)+"-wal"), Path(str(self.path)+"-shm")):
            try:
                size += path.stat().st_size
            except FileNotFoundError:
                # A closing concurrent connection can remove WAL/SHM.
                if path == self.path:
                    raise
        return size

    def _raw(self, reading):
        if is_dataclass(reading):
            reading = asdict(reading)
        if not isinstance(reading, dict):
            raise EdgeError("reading_object_required")
        reason = "unsafe_metadata" if any(k not in _READING_FIELDS and v not in (None, "", {}) for k, v in reading.items()) else ""
        raw = {}
        for field in _READING_FIELDS:
            # Preserve old event fingerprints exactly when the optional basis
            # was not present; a new null field would turn retries into conflicts.
            if field == "timestamp_basis" and field not in reading:
                continue
            value = reading.get(field, "valid" if field == "quality" else None)
            if field == "received_at" and value is None:
                value = datetime.now(timezone.utc)
            if isinstance(value, datetime):
                value = value.isoformat()
            if field == "value":
                if isinstance(value, float) and not math.isfinite(value):
                    value = str(value)
                if not isinstance(value, (int, float, str, bool, type(None))) or (isinstance(value, str) and (len(value) > 80 or not re.fullmatch(r"[+\-\d.eE NaInfitynone]+", value))):
                    value, reason = "[rejected]", "unsafe_value"
            elif value is not None:
                try:
                    _token(value)
                except EdgeError:
                    value, reason = "[rejected]", "unsafe_field"
            if field == "timestamp_basis" and value not in {"provider_observation", "provider_normalized_sample", "provider_receipt", "receiver_time"}:
                value, reason = "[rejected]", "unsafe_timestamp_basis"
            raw[field] = value
        observed = None
        try:
            observed = _timestamp(raw["observed_at"])
            if observed > datetime.now(timezone.utc).timestamp():
                raise EdgeError("future_observation")
            _timestamp(raw["received_at"])
            _finite(raw["value"])
            for field in ("event_id", "source_device_id", "source_channel", "source_metric", "unit"):
                _token(raw[field])
            if raw["quality"] != "valid":
                reason = reason or "invalid_quality"
        except EdgeError as exc:
            reason = reason or str(exc)
        return raw, observed, reason

    def _resolve(self, scope, raw, observed, supplied):
        if supplied is None:
            return None, None, "unmapped"
        validated_snapshot = None
        try:
            if not isinstance(supplied, dict) or set(supplied) - _SNAPSHOT_FIELDS:
                raise EdgeError("invalid_mapping")
            snap = dict(supplied)
            for field, value in asdict(scope).items():
                if snap.get(field) != value:
                    raise EdgeError("mapping_scope_mismatch")
            for field in ("room_id", "device_id", "sensor_id", "mapping_revision", "metric"):
                _token(snap.get(field))
            for field in ("zone_id", "cycle_id", "stage_id", "recipe_revision"):
                if field in snap:
                    _token(snap[field], optional=True)
            start, end = _timestamp(snap.get("effective_from")), _timestamp(snap.get("effective_to"))
            if observed is None or not start <= observed < end:
                raise EdgeError("mapping_interval_mismatch")
            for field in ("target_min", "target_max", "threshold_seconds"):
                if snap.get(field) is not None:
                    snap[field] = _finite(snap[field])
                else:
                    snap.pop(field, None)
            if any(snap.get(k) is not None for k in ("target_min", "target_max")) and not snap.get("recipe_revision"):
                raise EdgeError("target_revision_required")
            if (snap.get("threshold_seconds") is not None and not 1 <= snap["threshold_seconds"] <= 2678400) or (snap.get("target_min") is not None and snap.get("target_max") is not None and snap["target_min"] > snap["target_max"]):
                raise EdgeError("invalid_target")
            snap["effective_from"], snap["effective_to"] = _iso(start), _iso(end)
            definition = METRIC_REGISTRY.get(snap["metric"])
            if definition is None:
                raise EdgeError("unknown_metric")
            validated_snapshot = snap
            value = _finite(raw["value"])
            if definition.kind == "state" and value not in (0, 1):
                raise EdgeError("invalid_state")
            metric, value, unit = normalize_metric_value(snap["metric"], value, raw["unit"])
            snap["effective_from"], snap["effective_to"] = _iso(start), _iso(end)
            return snap, {"metric": metric, "value": value, "unit": unit, "kind": definition.kind}, ""
        except (ValueError, TypeError, KeyError, OverflowError):
            return validated_snapshot, None, "invalid_mapping_or_measurement"

    def _dirty(self, db, scope, observed):
        if observed is not None:
            db.execute("UPDATE buckets SET dirty=1,ack=0 WHERE scope=? AND start < ? AND start+? > ?", (scope, observed + self.max_gap_seconds, self.bucket_seconds, observed - self.max_gap_seconds))

    def ingest(self, scope, readings, resolved=None, transport=None):
        sk = self._scope(scope)
        if transport is not None:
            if not isinstance(transport, dict) or set(transport) != {"batch_id", "grant_id"}:
                raise EdgeError("invalid_transport")
            transport = {key: _token(value) for key, value in transport.items()}
        if not isinstance(readings, (list, tuple)) or len(readings) > self.max_batch:
            raise EdgeBackpressure("batch_limit")
        if resolved is not None and (not isinstance(resolved, (list, tuple)) or len(resolved) != len(readings)):
            raise EdgeError("resolved_alignment_required")
        result = dict(accepted=0, duplicates=0, conflicts=0, quarantined=0, pending=0, items=[], committed=False)
        with self._db(write=True) as db:
            for index, reading in enumerate(readings):
                raw, observed, reason = self._raw(reading)
                parts = [raw[k] for k in ("source_device_id", "source_channel", "event_id")]
                identity = _hash([sk, *parts]) if all(p and p != "[rejected]" for p in parts) else uuid.uuid4().hex
                fingerprint = _hash({k: v for k, v in raw.items() if k != "received_at"})
                prior = db.execute("SELECT fingerprint,observed FROM evidence WHERE scope=? AND identity=? LIMIT ?", (sk, identity, self.max_batch + 1)).fetchall()
                if len(prior) > self.max_batch:
                    raise EdgeBackpressure("identity_dispute_limit")
                if any(row[0] == fingerprint for row in prior):
                    result["duplicates"] += 1
                    result["items"].append(dict(identity=identity, status="duplicate", reason=""))
                    continue
                snap, canonical, mapping_reason = self._resolve(scope, raw, observed, None if resolved is None else resolved[index])
                state = "quarantined" if reason else "pending" if mapping_reason == "unmapped" else "quarantined" if mapping_reason else "ready"
                reason = reason or mapping_reason
                if observed is not None and db.execute("SELECT 1 FROM buckets WHERE scope=? AND purged=1 AND start < ? AND start+? > ? LIMIT 1", (sk, observed + self.max_gap_seconds, self.bucket_seconds, observed - self.max_gap_seconds)).fetchone():
                    state, reason = "quarantined", "late_after_purge"
                if prior:
                    state, reason = "disputed", "identity_conflict"
                    for previous in prior:
                        self._dirty(db, sk, previous["observed"])
                    db.execute("UPDATE evidence SET state='disputed',reason='identity_conflict' WHERE scope=? AND identity=?", (sk, identity))
                    result["conflicts"] += 1
                else:
                    result[{"ready": "accepted", "pending": "pending", "quarantined": "quarantined"}[state]] += 1
                db.execute("INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?)", (sk, identity, fingerprint, _json(raw), observed, datetime.now(timezone.utc).timestamp(), _json(parts[:2]), _json(snap) if snap else None, _json(canonical) if canonical else None, state, reason))
                self._dirty(db, sk, observed)
                result["items"].append(dict(identity=identity, status=state, reason=reason))
            if transport is not None:
                db.execute("""INSERT INTO edge_transport VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(scope) DO UPDATE SET last_committed_at=excluded.last_committed_at,
                    last_batch_id=excluded.last_batch_id,last_grant_id=excluded.last_grant_id,
                    accepted_total=accepted_total+excluded.accepted_total,
                    duplicate_total=duplicate_total+excluded.duplicate_total,
                    pending_total=pending_total+excluded.pending_total,
                    quarantined_total=quarantined_total+excluded.quarantined_total,
                    conflict_total=conflict_total+excluded.conflict_total""",
                    (sk, datetime.now(timezone.utc).isoformat(), transport["batch_id"], transport["grant_id"],
                     result["accepted"], result["duplicates"], result["pending"], result["quarantined"], result["conflicts"]))
            if result["accepted"] + result["pending"] + result["quarantined"] + result["conflicts"]:
                count, size = self._usage(db, sk)
                at = datetime.now(timezone.utc).timestamp()
                db.execute("""INSERT INTO edge_capacity_sample VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(scope) DO UPDATE SET last_at=excluded.last_at,
                    last_rows=excluded.last_rows,last_bytes=excluded.last_bytes""",
                    (sk, at, at, count, size, count, size))
            self._quota(db, sk)
        result["committed"] = True
        return result

    def transport_status(self, scope):
        sk = self._scope(scope)
        fields = ("last_committed_at", "last_batch_id", "accepted_total", "duplicate_total", "pending_total", "quarantined_total", "conflict_total")
        with self._db() as db:
            row = db.execute("SELECT " + ",".join(fields) + " FROM edge_transport WHERE scope=?", (sk,)).fetchone()
        return dict(zip(fields, tuple(row) if row else (None, None, 0, 0, 0, 0, 0)))

    def retry_pending(self, scope, resolver, limit=100):
        sk, limit = self._scope(scope), self._limit(limit)
        result = dict(resolved=0, pending=0, examined=0, truncated=False)
        with self._db() as db:
            rows = self._maintenance_page(db, sk, "pending", "(state='pending' OR (state='quarantined' AND reason='invalid_mapping_or_measurement'))", (), limit)
        # Resolve outside SQLite transactions: a resolver may consult the
        # authorized control plane. Recheck evidence under the write lock.
        supplied_rows = [json.loads(row["snapshot"]) if row["snapshot"] else resolver(scope, json.loads(row["raw"])) for row in rows[:limit]]
        with self._db(write=True) as db:
            result["truncated"] = len(rows) > limit
            self._advance_maintenance(db, sk, "pending", rows, limit)
            for row, supplied in zip(rows[:limit], supplied_rows):
                current = db.execute("SELECT state,snapshot,reason FROM evidence WHERE scope=? AND identity=? AND fingerprint=?", (sk, row["identity"], row["fingerprint"])).fetchone()
                if current is None or tuple(current) != (row["state"], row["snapshot"], row["reason"]):
                    continue
                raw = json.loads(row["raw"])
                if db.execute("SELECT 1 FROM buckets WHERE scope=? AND purged=1 AND start<? AND start+?>? LIMIT 1", (sk, row["observed"] + self.max_gap_seconds, self.bucket_seconds, row["observed"] - self.max_gap_seconds)).fetchone():
                    result["examined"] += 1
                    result["pending"] += 1
                    continue
                snap, canonical, reason = self._resolve(scope, raw, row["observed"], supplied)
                result["examined"] += 1
                if reason:
                    result["pending"] += 1
                    continue
                db.execute("UPDATE evidence SET snapshot=?,canonical=?,state='ready',reason='' WHERE scope=? AND identity=? AND fingerprint=?", (_json(snap), _json(canonical), sk, row["identity"], row["fingerprint"]))
                self._dirty(db, sk, row["observed"])
                result["resolved"] += 1
            self._quota(db, sk)
        return result

    def evidence(self, scope, limit=100, after=""):
        sk, limit = self._scope(scope), self._limit(limit)
        with self._db() as db:
            rows = db.execute("SELECT * FROM evidence WHERE scope=? AND identity||':'||fingerprint>? ORDER BY identity,fingerprint LIMIT ?", (sk, after, limit + 1)).fetchall()
        items = []
        for row in rows[:limit]:
            items.append({"identity": row["identity"], "fingerprint": row["fingerprint"], "state": row["state"], "reason": row["reason"], "raw": json.loads(row["raw"]) if row["raw"] else None, "snapshot": json.loads(row["snapshot"]) if row["snapshot"] else None, "canonical": json.loads(row["canonical"]) if row["canonical"] else None})
        return {"items": items, "next": rows[limit-1]["identity"] + ":" + rows[limit-1]["fingerprint"] if len(rows) > limit else None, "truncated": len(rows) > limit}

    def diagnostics(self, scope):
        sk = self._scope(scope)
        with self._db() as db:
            counts = {row[0]: row[1] for row in db.execute("SELECT state,COUNT(*) FROM evidence WHERE scope=? GROUP BY state", (sk,))}
            times = db.execute("SELECT MAX(received), MAX(CASE WHEN state IN ('ready','archived') THEN observed END) FROM evidence WHERE scope=?", (sk,)).fetchone()
            rows, size = self._usage(db, sk)
            sample = db.execute("SELECT * FROM edge_capacity_sample WHERE scope=?", (sk,)).fetchone()
            pages = db.execute("PRAGMA page_count").fetchone()[0] * db.execute("PRAGMA page_size").fetchone()[0]
        physical = self._physical_size()
        ratios = {"rows": rows/self.max_scope_rows, "bytes": size/self.max_scope_bytes, "disk_reservation": (physical+pages)/self.max_disk_bytes}
        limiting = max(ratios, key=ratios.get)
        pressure = ratios[limiting]
        capacity = dict(state="full" if pressure >= 1 else "critical" if pressure >= .9 else "warning" if pressure >= .7 else "available",
            limiting_resource=limiting, physical_bytes=physical, disk_reservation_bytes=physical+pages,
            headroom_rows=max(0, self.max_scope_rows-rows), headroom_bytes=max(0, self.max_scope_bytes-size),
            disk_reservation_headroom_bytes=max(0, self.max_disk_bytes-physical-pages),
            projected_headroom_seconds=None, projection_status="unknown", replay_horizon="identity_evidence_retained_until_capacity",
            action="retain_source_backlog_and_review_capacity" if pressure >= .7 else "monitor")
        # A receipt-growth estimate, never a configured/assumed device cadence.
        # Do not extrapolate a short import burst, clock reversal, shrinking
        # storage, or a capture interval whose last receipt is stale.
        now = datetime.now(timezone.utc).timestamp()
        if sample and sample["last_at"]-sample["first_at"] >= 3600 and 0 <= now-sample["last_at"] <= 3600:
            elapsed = sample["last_at"]-sample["first_at"]
            row_growth, byte_growth = sample["last_rows"]-sample["first_rows"], sample["last_bytes"]-sample["first_bytes"]
            if row_growth >= 100 and byte_growth > 0:
                capacity.update(projected_headroom_seconds=min(capacity["headroom_rows"]*elapsed/row_growth, capacity["headroom_bytes"]*elapsed/byte_growth),
                    projection_status="observed_receipt_growth_scope_only", projection_interval_seconds=elapsed)
                if capacity["projected_headroom_seconds"] < 172800 and capacity["state"] == "available":
                    capacity.update(state="warning", action="retain_source_backlog_and_review_capacity")
        return dict(counts=counts, scope_rows=rows, scope_bytes=size, limits={"rows": self.max_scope_rows, "bytes": self.max_scope_bytes, "disk_bytes": self.max_disk_bytes}, capacity=capacity, raw_stays_local=True,
                    last_received_at=_iso(times[0]) if times[0] is not None else None,
                    last_valid_observed_at=_iso(times[1]) if times[1] is not None else None)

    def latest(self, org, facility, room, *, now=None, limit=200):
        """Bounded local current evidence; stream freshness is not room health."""
        for token in (org, facility, room):
            _token(token)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise EdgeError("invalid_limit")
        at = _timestamp(datetime.now(timezone.utc) if now is None else now)
        with self._db() as db:
            rows = db.execute("""SELECT * FROM evidence
                WHERE json_extract(scope,'$.organization_id')=?
                  AND json_extract(scope,'$.facility_id')=?
                  AND json_extract(snapshot,'$.room_id')=?
                ORDER BY COALESCE(observed,received) DESC,identity DESC,fingerprint DESC
                LIMIT ?""", (org, facility, room, self.max_query_rows + 1)).fetchall()
        readings, seen = [], set()
        truncated = len(rows) > self.max_query_rows
        for row in rows[:self.max_query_rows]:
            snap, scope = json.loads(row["snapshot"]), json.loads(row["scope"])
            if any(snap.get(k) != scope[k] for k in ("organization_id", "facility_id", "connection_id")):
                continue
            source_device, channel = json.loads(row["stream"])
            key = (scope["connection_id"], source_device, channel, snap["device_id"], snap["sensor_id"], snap["metric"])
            if key in seen:
                continue
            seen.add(key)
            if len(readings) >= limit:
                truncated = True
                break
            raw = json.loads(row["raw"]) if row["raw"] else None
            canonical = json.loads(row["canonical"]) if row["canonical"] else None
            observed = row["observed"]
            age = at - observed if observed is not None else None
            freshness = "unknown" if age is None or age < 0 else "stale" if age >= self.max_gap_seconds else "fresh"
            valid = row["state"] == "ready" and canonical is not None and raw is not None and age is not None and age >= 0
            active = _timestamp(snap["effective_from"]) <= at < _timestamp(snap["effective_to"])
            value = canonical["value"] if valid else None
            if row["state"] == "archived" or raw is None:
                status = "unavailable"
            elif row["state"] != "ready" or (age is not None and age < 0):
                status = "invalid"
            elif not valid or not active:
                status = "unavailable"
            elif freshness == "stale":
                status = "stale"
            elif snap.get("target_min") is None and snap.get("target_max") is None:
                status = "unconfigured"
            elif snap.get("target_min") is not None and value < snap["target_min"]:
                status = "below"
            elif snap.get("target_max") is not None and value > snap["target_max"]:
                status = "above"
            else:
                status = "in_target"
            readings.append(dict(connection_id=scope["connection_id"], source_device_id=source_device,
                source_channel=channel, device_id=snap["device_id"], sensor_id=snap["sensor_id"],
                metric=snap["metric"], value=value if active else None,
                unit=canonical["unit"] if canonical else None,
                original_value=raw["value"] if raw else None, original_unit=raw["unit"] if raw else None,
                timestamp_basis=raw.get("timestamp_basis") if raw else None,
                observed_at=_iso(observed) if observed is not None else None, received_at=_iso(row["received"]),
                data_age_seconds=age, latency_seconds=row["received"]-observed if observed is not None else None,
                quality=raw["quality"] if raw else None, state=row["state"], reason=row["reason"],
                freshness=freshness, status=status,
                snapshot={k: v for k, v in snap.items() if k in _SNAPSHOT_FIELDS}))
        return dict(as_of=_iso(at), readings=readings, truncated=truncated, status="UNKNOWN")

    def _window(self, start, end):
        start, end = _timestamp(start), _timestamp(end)
        if not start < end or end - start > self.max_window_seconds or start % self.bucket_seconds or end % self.bucket_seconds:
            raise EdgeError("bounded_aligned_window_required")
        return start, end

    def _calculate(self, rows, start, end):
        streams, output = {}, {}
        for row in rows:
            streams.setdefault(row["stream"], []).append(row)
        for stream, samples in streams.items():
            samples.sort(key=lambda r: (r["observed"], r["identity"]))
            for i, row in enumerate(samples):
                if row["state"] != "ready" or not row["snapshot"]:
                    continue
                snap, canon = json.loads(row["snapshot"]), json.loads(row["canonical"])
                if row["observed"] >= end:
                    continue  # Lookahead clips earlier evidence, not this bucket's samples.
                context = _context(snap)
                sid = _hash([stream, context])
                result = output.setdefault(sid, {"stream": json.loads(stream), "snapshot": context, "metric": canon["metric"], "unit": canon["unit"], "kind": canon["kind"], "sample_count": 0, "sample_minimum": None, "sample_maximum": None, "sample_sum": 0.0, "integral": 0.0, "coverage_seconds": 0.0, "above_seconds": 0.0, "below_seconds": 0.0, "in_target_seconds": 0.0, "total": 0.0, "active_seconds": 0.0, "intervals": [], "attribution_intervals": []})
                value, at = canon["value"], row["observed"]
                if start <= at < end:
                    result["sample_count"] += 1
                    result["sample_sum"] += value
                    result["sample_minimum"] = value if result["sample_minimum"] is None else min(result["sample_minimum"], value)
                    result["sample_maximum"] = value if result["sample_maximum"] is None else max(result["sample_maximum"], value)
                    if canon["kind"] in ("event", "volume", "duration"):
                        result["total"] += value
                if canon["kind"] not in ("continuous", "state", "rate"):
                    continue
                # Simultaneous contradictory/independent events on one channel are
                # ambiguous: no hold interval is assigned to any tied timestamp.
                if (i and samples[i-1]["observed"] == at) or (i+1 < len(samples) and samples[i+1]["observed"] == at):
                    continue
                stop = min(end, at + self.max_gap_seconds, _timestamp(snap["effective_to"]), samples[i+1]["observed"] if i+1 < len(samples) else end)
                if i+1 < len(samples) and samples[i+1]["state"] == "ready" and samples[i+1]["snapshot"]:
                    following = json.loads(samples[i+1]["snapshot"])
                    if _context(following) != context:
                        stop = min(stop, max(at, _timestamp(following["effective_from"])))
                begin = max(start, at, _timestamp(snap["effective_from"]))
                seconds = max(0, stop - begin)
                if not seconds:
                    continue
                result["coverage_seconds"] += seconds
                _merge_attribution(result["attribution_intervals"], begin, stop)
                result["integral"] += value * seconds
                result["active_seconds"] += seconds if canon["kind"] == "state" and value == 1 else 0
                band = "unknown"
                if snap.get("target_min") is not None and value < snap["target_min"]:
                    band = "below"
                elif snap.get("target_max") is not None and value > snap["target_max"]:
                    band = "above"
                elif snap.get("target_min") is not None or snap.get("target_max") is not None:
                    band = "in_target"
                if band != "unknown":
                    result[band + "_seconds"] += seconds
                if band in ("above", "below"):
                    intervals = result["intervals"]
                    if intervals and intervals[-1][1] == begin and intervals[-1][2] == band:
                        intervals[-1][1] = stop
                    else:
                        intervals.append([begin, stop, band])
        return {"start": start, "end": end, "calculation_version": 3, "streams": output}

    def rollup(self, scope, start, end):
        sk = self._scope(scope)
        start, end = self._window(start, end)
        result = dict(rebuilt=0, unchanged=0, blocked=0, truncated=False)
        if (end-start) / self.bucket_seconds > self.max_batch:
            return dict(result, truncated=True)
        with self._db(write=True) as db:
            # Preflight a bounded indexed window before publishing any bucket.
            # SQL reads at most work-budget+1 keys; Python holds only counts.
            streams = db.execute("""SELECT stream,COUNT(*) AS n FROM
                (SELECT stream FROM evidence WHERE scope=? AND observed>=? AND observed<? LIMIT ?)
                GROUP BY stream LIMIT ?""", (sk, start-self.max_gap_seconds, end+self.max_gap_seconds,
                self.max_rollup_rows+1, min(self.max_rollup_streams, self.max_query_rows)+1)).fetchall()
            if (len(streams) > min(self.max_rollup_streams, self.max_query_rows)
                    or sum(r["n"] for r in streams) > self.max_rollup_rows
                    or any(r["n"] > self.max_query_rows for r in streams)):
                return dict(result, truncated=True)
            for bucket in range(int(start), int(end), self.bucket_seconds):
                old = db.execute("SELECT * FROM buckets WHERE scope=? AND start=?", (sk, bucket)).fetchone()
                if old and not old["dirty"]:
                    result["unchanged"] += 1
                    continue
                if old and old["purged"]:
                    result["blocked"] += 1
                    continue
                payload = {"start": bucket, "end": bucket+self.bucket_seconds, "calculation_version": 3, "streams": {}}
                payload_size = 0
                for stream in streams:
                    rows = db.execute("SELECT * FROM evidence WHERE scope=? AND stream=? AND observed>=? AND observed<? ORDER BY observed,identity,fingerprint LIMIT ?",
                        (sk, stream["stream"], bucket-self.max_gap_seconds, bucket+self.bucket_seconds+self.max_gap_seconds, self.max_query_rows+1)).fetchall()
                    calculated = self._calculate(rows, bucket, bucket+self.bucket_seconds)
                    payload_size += len(_json(calculated).encode())
                    if payload_size > 8388608 or len(payload["streams"])+len(calculated["streams"]) > self.max_query_rows:
                        raise EdgeBackpressure("aggregate_byte_or_stream_limit")
                    payload["streams"].update(calculated["streams"])
                digest = _hash(payload)
                previous_digest = old["revision"].split(":")[-1] if old else None
                generation = int(old["revision"].split(":")[0]) if old and ":" in old["revision"] else 0
                revision = old["revision"] if old and previous_digest == digest else f"{generation+1:020d}:{digest}"
                key = _hash([sk, bucket])
                if len(_json(payload).encode()) > 8388608:
                    raise EdgeBackpressure("aggregate_byte_limit")
                db.execute("INSERT INTO buckets(scope,org,facility,start,key,revision,payload) VALUES(?,?,?,?,?,?,?) ON CONFLICT(scope,start) DO UPDATE SET revision=excluded.revision,payload=excluded.payload,dirty=0,ack=CASE WHEN buckets.revision=excluded.revision THEN buckets.ack ELSE 0 END", (sk, scope.organization_id, scope.facility_id, bucket, key, revision, _json(payload)))
                result["rebuilt"] += 1
            self._quota(db, sk)
        return result

    def pending_aggregates(self, scope, limit=100):
        sk, limit = self._scope(scope), self._limit(limit)
        with self._db() as db:
            sizes = db.execute("SELECT LENGTH(CAST(payload AS BLOB)) FROM buckets WHERE scope=? AND dirty=0 AND ack=0 ORDER BY start LIMIT ?", (sk, limit + 1)).fetchall()
            count, size = 0, 0
            for candidate in sizes[:limit]:
                if size + candidate[0] > 8388608:
                    break
                count += 1
                size += candidate[0]
            rows = db.execute("SELECT key,revision,payload FROM buckets WHERE scope=? AND dirty=0 AND ack=0 ORDER BY start LIMIT ?", (sk, count)).fetchall()
        return {"items": [{"key": r["key"], "revision": r["revision"], "payload": json.loads(r["payload"])} for r in rows], "truncated": len(sizes) > count}

    def ack_aggregate(self, scope, key, revision):
        sk = self._scope(scope)
        if not isinstance(key, str) or not isinstance(revision, str):
            raise EdgeError("opaque_ack_required")
        with self._db(write=True) as db:
            return bool(db.execute("UPDATE buckets SET ack=1 WHERE scope=? AND key=? AND revision=? AND dirty=0", (sk, key, revision)).rowcount)

    def archive_aggregates(self, scope, archive_dir, limit=100):
        """Durably accept bounded aggregates at a host-configured local path."""
        try:
            from .aggregate_archive import accept_aggregate
        except ImportError:
            from aggregate_archive import accept_aggregate
        page = self.pending_aggregates(scope, limit)
        result = dict(archived=0, acknowledged=0, stale=0, truncated=page["truncated"])
        for item in page["items"]:
            accept_aggregate(scope, archive_dir, item)
            result["archived"] += 1
            if self.ack_aggregate(scope, item["key"], item["revision"]):
                result["acknowledged"] += 1
            else:
                result["stale"] += 1
        return result

    def room_summary(self, org, facility, room, start, end, cycle_id=None, targets=None):
        for token in (org, facility, room):
            _token(token)
        if targets is not None:
            raise EdgeError("historical_snapshot_targets_required")
        start, end = self._window(start, end)
        with self._db() as db:
            sizes = db.execute("SELECT LENGTH(CAST(payload AS BLOB)) FROM buckets WHERE org=? AND facility=? AND start>=? AND start<? LIMIT ?", (org, facility, start, end, self.max_query_rows + 1)).fetchall()
            if len(sizes) > self.max_query_rows or sum(r[0] for r in sizes) > 8388608:
                return dict(status="UNKNOWN", streams=[], truncated=True, start=_iso(start), end=_iso(end))
            rows = db.execute("SELECT scope,payload,dirty FROM buckets WHERE org=? AND facility=? AND start>=? AND start<? ORDER BY start LIMIT ?", (org, facility, start, end, self.max_query_rows + 1)).fetchall()
        if len(rows) > self.max_query_rows:
            return dict(status="UNKNOWN", streams=[], truncated=True, start=_iso(start), end=_iso(end))
        groups = {}
        for row in rows:
            if row["dirty"]:
                continue
            payload = json.loads(row["payload"])
            for sid, entry in payload["streams"].items():
                snap = entry["snapshot"]
                if snap["room_id"] != room or (cycle_id is not None and snap.get("cycle_id") != cycle_id):
                    continue
                key = _hash([row["scope"], sid])
                if key not in groups:
                    if len(groups) >= self.max_query_rows:
                        return dict(status="UNKNOWN", streams=[], truncated=True, start=_iso(start), end=_iso(end))
                    groups[key] = dict(entry, intervals=[], attribution_intervals=[], **{"sample_count": 0, "sample_minimum": None, "sample_maximum": None, "sample_sum": 0.0, "integral": 0.0, "coverage_seconds": 0.0, "above_seconds": 0.0, "below_seconds": 0.0, "in_target_seconds": 0.0, "total": 0.0, "active_seconds": 0.0})
                dest = groups[key]
                if entry.get("sample_minimum") is not None:
                    dest["sample_minimum"] = entry["sample_minimum"] if dest["sample_minimum"] is None else min(dest["sample_minimum"], entry["sample_minimum"])
                if entry.get("sample_maximum") is not None:
                    dest["sample_maximum"] = entry["sample_maximum"] if dest["sample_maximum"] is None else max(dest["sample_maximum"], entry["sample_maximum"])
                for field in ("sample_count", "sample_sum", "integral", "coverage_seconds", "above_seconds", "below_seconds", "in_target_seconds", "total", "active_seconds"):
                    dest[field] += entry[field]
                for interval in entry["intervals"]:
                    if dest["intervals"] and dest["intervals"][-1][1] == interval[0] and dest["intervals"][-1][2] == interval[2]:
                        dest["intervals"][-1][1] = interval[1]
                    else:
                        dest["intervals"].append(interval[:])
                for begin, finish in entry["attribution_intervals"]:
                    _merge_attribution(dest["attribution_intervals"], begin, finish)
        for entry in groups.values():
            coverage, count, kind = entry["coverage_seconds"], entry["sample_count"], entry["kind"]
            entry["unknown_seconds"] = max(0, end - start - coverage)
            entry["sample_mean"] = entry["sample_sum"] / count if count and kind in ("continuous", "rate") else None
            entry["time_weighted_mean"] = entry["integral"] / coverage if coverage and kind in ("continuous", "rate") else None
            entry["status"] = "UNKNOWN" if not coverage else "PARTIAL" if entry["unknown_seconds"] else "COMPLETE"
            entry["total"] = entry["total"] if kind in ("event", "duration", "volume") else None
            entry["total_kind"] = {"event": "event_total", "volume": "volume_total", "duration": "duration_total"}.get(kind)
            threshold = entry["snapshot"].get("threshold_seconds")
            configured = (isinstance(threshold, (int, float)) and not isinstance(threshold, bool)
                          and math.isfinite(threshold) and threshold > 0)
            entry["alert_threshold_status"] = "configured" if configured else "not_configured"
            entry["threshold_semantics"] = "continuous_same_direction"
            entry["outside_intervals"] = [{"start": _iso(a), "end": _iso(b), "direction": band, "seconds": b-a} for a, b, band in entry.pop("intervals")]
            entry["deviations"] = [item for item in entry["outside_intervals"] if configured and item["seconds"] >= threshold]
            if entry["metric"] == "ppfd":
                daily_window = int(start // 86400) == int((end-1) // 86400)
                entry["measured_light_integral_mol_m2"] = entry["integral"] / 1000000
                entry["measured_dli_contribution"] = entry["integral"] / 1000000 if daily_window else None
                entry["dli_partial"] = coverage < 86400 or end-start != 86400
                entry["dli_status"] = "PARTIAL" if daily_window and entry["dli_partial"] else "COMPLETE" if daily_window else "NOT_DAILY_WINDOW"
            del entry["sample_sum"]
            del entry["integral"]
        status = "UNKNOWN" if not groups or all(v["status"] == "UNKNOWN" for v in groups.values()) else "COMPLETE" if all(v["status"] == "COMPLETE" for v in groups.values()) else "PARTIAL"
        return dict(status=status, streams=list(groups.values()), truncated=False, start=_iso(start), end=_iso(end))

    def retention(self, scope, before, limit=100):
        sk, limit = self._scope(scope), self._limit(limit)
        cutoff = _timestamp(before)
        result = dict(purged=0, protected=0, truncated=False)
        with self._db(write=True) as db:
            rows = self._maintenance_page(db, sk, "retention", "raw IS NOT NULL AND received<?", (cutoff,), limit)
            result["truncated"] = len(rows) > limit
            self._advance_maintenance(db, sk, "retention", rows, limit)
            for row in rows[:limit]:
                at = row["observed"]
                if row["state"] != "ready" or at is None or at >= cutoff:
                    result["protected"] += 1
                    continue
                first = int(at // self.bucket_seconds) * self.bucket_seconds
                last = int((at + self.max_gap_seconds) // self.bucket_seconds) * self.bucket_seconds
                buckets = db.execute("SELECT * FROM buckets WHERE scope=? AND start>=? AND start<=? ORDER BY start", (sk, first, last)).fetchall()
                needed = (last-first) // self.bucket_seconds + 1
                if len(buckets) != needed or any(b["dirty"] or not b["ack"] for b in buckets):
                    result["protected"] += 1
                    continue
                unresolved = db.execute("SELECT 1 FROM evidence WHERE scope=? AND state NOT IN ('ready','archived') AND (observed IS NULL OR (observed>=? AND observed<?)) LIMIT 1", (sk, first-self.max_gap_seconds, last+self.bucket_seconds)).fetchone()
                if unresolved:
                    result["protected"] += 1
                    continue
                db.execute("UPDATE evidence SET raw=NULL,canonical=NULL,state='archived' WHERE scope=? AND identity=? AND fingerprint=?", (sk, row["identity"], row["fingerprint"]))
                db.execute("UPDATE buckets SET purged=1 WHERE scope=? AND start>=? AND start<=?", (sk, first, last))
                result["purged"] += 1
        return result
