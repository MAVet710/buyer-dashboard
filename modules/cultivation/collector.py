"""Host-configured finalized exports only; no network, ORM or equipment control.

Producers must fsync/close a temporary file then atomically rename to *.ready.*.
The host owns the directory and must not permit untrusted directory mutations.
Original files are never changed. The same EdgeStore holds all raw evidence.
"""
from contextlib import contextmanager
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import random
import stat
import threading

try:
    from .edge_store import EdgeError, EdgeBackpressure, _token
    from .adapters.base import AdapterError
except ImportError:
    from edge_store import EdgeError, EdgeBackpressure, _token
    from adapters.base import AdapterError


def _plain_path(path):
    if ".." in Path(path).parts or str(path).startswith("\\\\"):
        raise EdgeError("collector_unsafe_path")
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise EdgeError("collector_link_rejected")
    return path


@contextmanager
def _open_file(path, *, create=False):
    """Windows denies concurrent writers/deletion and opens reparse points themselves."""
    path = Path(os.path.abspath(path))
    _plain_path(path.parent)
    if path.exists() or path.is_symlink():
        _plain_path(path)
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        import msvcrt
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        handle = kernel.CreateFileW(str(path), 0xC0000000 if create else 0x80000000,
                                    1 if not create else 3, None, 4 if create else 3, 0x00200000, None)
        if handle == wintypes.HANDLE(-1).value:
            raise OSError("collector_open_unavailable")
        try:
            name = ctypes.create_unicode_buffer(32768)
            length = kernel.GetFinalPathNameByHandleW(handle, name, len(name), 0)
            if not length or length >= len(name) or os.path.normcase(name.value.removeprefix("\\\\?\\")) != os.path.normcase(str(path)):
                raise EdgeError("collector_path_changed")
            fd = msvcrt.open_osfhandle(handle, (os.O_RDWR if create else os.O_RDONLY) | os.O_BINARY)
            handle = None
        finally:
            if handle is not None:
                kernel.CloseHandle(handle)
    else:
        fd = os.open(path, (os.O_RDWR | os.O_CREAT if create else os.O_RDONLY) | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "r+b" if create else "rb") as file:
        info = os.fstat(file.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
            raise EdgeError("collector_regular_file_required")
        _plain_path(path)
        yield file


class FileCollector:
    def __init__(self, store, scope, directory, adapter, *, format="json", max_scan=100,
                 max_files=10, max_source_files=10000, poll_seconds=2, backoff_cap=60):
        if format not in ("json", "csv"):
            raise EdgeError("collector_format_required")
        for value in (max_scan, max_files, max_source_files):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise EdgeError("invalid_limit")
        if not 0 < poll_seconds <= backoff_cap <= 300:
            raise EdgeError("invalid_limit")
        if not Path(directory).is_absolute():
            raise EdgeError("collector_absolute_directory_required")
        self.directory = _plain_path(directory)
        if not self.directory.is_dir():
            raise EdgeError("collector_directory_required")
        _plain_path(store.path)
        if store.path.stat().st_nlink != 1:
            raise EdgeError("collector_store_hardlink_rejected")
        self.store, self.scope, self.adapter, self.format = store, scope, adapter, format
        # Held-source decisions depend on the approved parsing contract. A fixed
        # contract must be able to retry an unchanged held file, without replaying
        # already committed sources or changing the collector's exclusive lock.
        contract = dict(format=format, columns=adapter.columns, rows_key=adapter.rows_key,
                        mappings=sorted((list(key), value) for key, value in adapter._mapping.items()),
                        max_bytes=adapter.max_bytes, max_rows=adapter.max_rows,
                        max_batch=store.max_batch)
        self.contract_fingerprint = hashlib.sha256(json.dumps(contract, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        self.max_scan, self.max_files, self.max_source_files = max_scan, max_files, max_source_files
        self.poll_seconds, self.backoff_cap = poll_seconds, backoff_cap
        directory_key = os.path.normcase(str(self.directory.resolve()))
        store_key = os.path.normcase(str(store.path.resolve()))
        self.owner = hashlib.sha256((directory_key+"\0"+scope.key).encode()).hexdigest()
        self.lock_path = store.path.parent / (".collector-" + hashlib.sha256((store_key+self.owner).encode()).hexdigest() + ".lock")
        self._scan = None
        self._locked = False
        with store._db(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS edge_collector_files(
                owner TEXT NOT NULL, file_key TEXT NOT NULL, signature TEXT NOT NULL,
                state TEXT NOT NULL, reason TEXT NOT NULL, PRIMARY KEY(owner,file_key))""")

    @contextmanager
    def exclusive(self):
        with _open_file(self.lock_path, create=True) as lock:
            if os.name == "nt":
                import msvcrt
                lock.seek(0)
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    raise EdgeBackpressure("collector_already_running") from None
            else:
                import fcntl
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise EdgeBackpressure("collector_already_running") from None
            self._locked = True
            try:
                yield self
            finally:
                self._locked = False
                if self._scan is not None:
                    self._scan.close()
                    self._scan = None
                if os.name == "nt":
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

    def _record(self, key, signature, state, reason):
        with self.store._db(write=True) as db:
            count = db.execute("SELECT COUNT(*) FROM edge_collector_files WHERE owner=?", (self.owner,)).fetchone()[0]
            known = db.execute("SELECT 1 FROM edge_collector_files WHERE owner=? AND file_key=?", (self.owner, key)).fetchone()
            if not known and count >= self.max_source_files:
                raise EdgeBackpressure("collector_manifest_capacity")
            db.execute("INSERT INTO edge_collector_files VALUES(?,?,?,?,?) ON CONFLICT(owner,file_key) DO UPDATE SET signature=excluded.signature,state=excluded.state,reason=excluded.reason", (self.owner, key, signature, state, reason))
            self.store._quota(db, self.scope.key)

    def _parse(self, content):
        # Adapter's permissive preview must not silently discard metadata here.
        if self.format == "json":
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise EdgeError("collector_duplicate_field")
                    result[key] = value
                return result
            payload = json.loads(content.decode("utf-8-sig"), object_pairs_hook=unique)
            if self.adapter.rows_key is not None:
                if not isinstance(payload, dict) or set(payload) != {self.adapter.rows_key}:
                    raise EdgeError("collector_metadata_rejected")
                payload = payload[self.adapter.rows_key]
            if not isinstance(payload, list) or any(not isinstance(r, dict) or set(r)-set(self.adapter.columns.values()) for r in payload):
                raise EdgeError("collector_metadata_rejected")
        else:
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
            if not reader.fieldnames or set(reader.fieldnames)-set(self.adapter.columns.values()):
                raise EdgeError("collector_metadata_rejected")
            if any(None in r for r in reader):
                raise EdgeError("collector_metadata_rejected")
        parsed = self.adapter.parse(content, format=self.format)
        readings = parsed["readings"]
        if not readings or len(readings) > self.store.max_batch:
            raise EdgeError("collector_batch_limit")
        for reading, hint in zip(readings, parsed["mapping_hints"]):
            for field in ("event_id", "source_device_id", "source_channel"):
                _token(reading.get(field))
            if hint is None:
                raise EdgeError("collector_metric_contract_required")
        return readings

    def collect_once(self, stop=None):
        if not self._locked:
            raise EdgeError("collector_lock_required")
        _plain_path(self.directory)
        result = dict(scanned=0, committed_files=0, held_files=0, skipped=0, transient_errors=0, scan_complete=False, last_error=None)
        if self._scan is None:
            self._scan = os.scandir(self.directory)
        for _ in range(self.max_scan):
            if stop is not None and stop.is_set():
                break
            if result["committed_files"]+result["held_files"]+result["transient_errors"] >= self.max_files:
                break
            entry = next(self._scan, None)
            if entry is None:
                self._scan.close()
                self._scan = None
                result["scan_complete"] = True
                break
            result["scanned"] += 1
            if not entry.name.endswith(".ready." + self.format):
                continue
            key = hashlib.sha256(entry.name.encode()).hexdigest()
            signature = "unsafe"
            try:
                # Windows DirEntry's cached stat has zero inode/device values;
                # obtain the actual no-follow identity before opening the file.
                info = os.stat(entry.path, follow_symlinks=False)
                signature = ":".join(str(v) for v in (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns))
                with self.store._db() as db:
                    previous = db.execute("SELECT signature,state FROM edge_collector_files WHERE owner=? AND file_key=?", (self.owner, key)).fetchone()
                    count = db.execute("SELECT COUNT(*) FROM edge_collector_files WHERE owner=?", (self.owner,)).fetchone()[0]
                if previous and previous[0] == (signature if previous[1] == "committed" else signature + ":" + self.contract_fingerprint):
                    result["skipped"] += 1
                    continue
                if not previous and count >= self.max_source_files:
                    raise EdgeBackpressure("collector_manifest_capacity")
                if info.st_size > self.adapter.max_bytes:
                    raise EdgeError("collector_file_byte_limit")
                with _open_file(entry.path) as handle:
                    before = os.fstat(handle.fileno())
                    if (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns) != (info.st_ino, info.st_dev, info.st_size, info.st_mtime_ns):
                        raise OSError("collector_source_changed")
                    content = handle.read(self.adapter.max_bytes+1)
                    after = os.fstat(handle.fileno())
                    if len(content) != before.st_size or (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (before.st_size, before.st_mtime_ns, before.st_ctime_ns):
                        raise OSError("collector_source_changed")
                    readings = self._parse(content)
                    accepted = self.store.ingest(self.scope, readings)
                    if not accepted["committed"]:
                        raise EdgeBackpressure("collector_commit_required")
                    # Separate commit is deliberate: crash/lost ack replays stable
                    # observations, never advances the cursor before raw commit.
                    self._record(key, signature, "committed", "")
                result["committed_files"] += 1
            except (EdgeBackpressure, OSError) as exc:
                result["transient_errors"] += 1
                allowed = {"collector_manifest_capacity", "scope_capacity_reached", "disk_capacity_reached", "local_storage_unavailable", "collector_commit_required"}
                result["last_error"] = str(exc) if isinstance(exc, EdgeBackpressure) and str(exc) in allowed else "local_source_or_storage_unavailable"
            except (EdgeError, AdapterError, ValueError, TypeError, RecursionError, csv.Error):
                self._record(key, signature + ":" + self.contract_fingerprint, "held", "invalid_finalized_export")
                result["held_files"] += 1
                result["last_error"] = "invalid_finalized_export"
        return result

    def run(self, *, once=False, max_iterations=None, stop=None, report=None):
        if max_iterations is not None and (isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations <= 0):
            raise EdgeError("invalid_limit")
        stop = stop or threading.Event()
        failures, iteration, result = 0, 0, {}
        with self.exclusive():
            while not stop.is_set() and (max_iterations is None or iteration < max_iterations):
                try:
                    result = self.collect_once(stop)
                except (OSError, EdgeBackpressure):
                    result = {"transient_errors": 1, "error": "local_collection_unavailable"}
                iteration += 1
                if result["transient_errors"]:
                    failures = min(failures+1, 20)
                elif result.get("committed_files") or result.get("held_files"):
                    failures = 0
                if report:
                    report(result)
                if once or (max_iterations is not None and iteration >= max_iterations):
                    break
                delay = min(self.backoff_cap, self.poll_seconds*2**failures)
                stop.wait(random.uniform(delay/2, delay) if failures else self.poll_seconds)
        return result
