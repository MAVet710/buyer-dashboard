"""Bounded local aggregate receiver. The directory is trusted host configuration."""
from contextlib import contextmanager
from dataclasses import asdict
import os
from pathlib import Path
import re
import stat
import uuid

try:
    from .edge_store import EdgeError, Scope, _hash, _json, _finite, _token, _SNAPSHOT_FIELDS
    from .metrics import METRIC_REGISTRY
except ImportError:
    from edge_store import EdgeError, Scope, _hash, _json, _finite, _token, _SNAPSHOT_FIELDS
    from metrics import METRIC_REGISTRY


def _validate(scope, item):
    if not isinstance(scope, Scope):
        raise EdgeError("scope_required")
    try:
        if set(item) != {"key", "revision", "payload"}:
            raise ValueError
        payload = item["payload"]
        match = re.fullmatch(r"([0-9]{20}):([0-9a-f]{64})", item["revision"])
        if not match or int(match[1]) < 1 or match[2] != _hash(payload):
            raise ValueError
        if set(payload) != {"start", "end", "calculation_version", "streams"}:
            raise ValueError
        start, end = _finite(payload["start"]), _finite(payload["end"])
        if not 0 <= start < end <= 4102444800 or end - start > 86400:
            raise ValueError
        if payload["calculation_version"] != 3 or item["key"] != _hash([scope.key, payload["start"]]):
            raise ValueError
        numeric = {"sample_count", "sample_sum", "integral", "coverage_seconds", "above_seconds",
                   "below_seconds", "in_target_seconds", "total", "active_seconds"}
        fields = numeric | {"stream", "snapshot", "metric", "unit", "kind", "sample_minimum",
                            "sample_maximum", "intervals", "attribution_intervals"}
        for sid, entry in payload["streams"].items():
            if set(entry) != fields:
                raise ValueError
            snapshot = entry["snapshot"]
            if set(snapshot) - (_SNAPSHOT_FIELDS - {"effective_from", "effective_to"}):
                raise ValueError
            if any(snapshot.get(k) != v for k, v in asdict(scope).items()):
                raise ValueError
            for field in ("room_id", "device_id", "sensor_id", "mapping_revision", "metric"):
                _token(snapshot.get(field))
            for field in ("zone_id", "cycle_id", "stage_id", "recipe_revision"):
                _token(snapshot.get(field), optional=True)
            for field in ("target_min", "target_max", "threshold_seconds"):
                if field in snapshot:
                    _finite(snapshot[field])
            if any(k in snapshot for k in ("target_min", "target_max")) and not snapshot.get("recipe_revision"):
                raise ValueError
            if "threshold_seconds" in snapshot and not 1 <= snapshot["threshold_seconds"] <= 2678400:
                raise ValueError
            if "target_min" in snapshot and "target_max" in snapshot and snapshot["target_min"] > snapshot["target_max"]:
                raise ValueError
            stream = entry["stream"]
            if not isinstance(stream, list) or len(stream) != 2:
                raise ValueError
            for token in stream:
                _token(token)
            if sid != _hash([_json(stream), snapshot]):
                raise ValueError
            definition = METRIC_REGISTRY[snapshot["metric"]]
            if (entry["metric"], entry["unit"], entry["kind"]) != (definition.key, definition.unit, definition.kind):
                raise ValueError
            for field in numeric | {"sample_minimum", "sample_maximum"}:
                if entry[field] is not None or field in numeric:
                    _finite(entry[field])
            if type(entry["sample_count"]) is not int or entry["sample_count"] < 0:
                raise ValueError
            for field in ("coverage_seconds", "above_seconds", "below_seconds", "in_target_seconds", "active_seconds"):
                if not 0 <= entry[field] <= end - start:
                    raise ValueError
            for field, width in (("intervals", 3), ("attribution_intervals", 2)):
                previous = start
                for interval in entry[field]:
                    if len(interval) != width or not previous <= _finite(interval[0]) < _finite(interval[1]) <= end:
                        raise ValueError
                    if width == 3 and interval[2] not in ("above", "below"):
                        raise ValueError
                    previous = interval[1]
        data = _json({"scope": asdict(scope), **item}).encode("utf-8")
        if len(data) > 8388608:
            raise ValueError
        return data
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise EdgeError("archive_invalid_aggregate") from None


def _check_path(path, *, directory=False):
    """Reject links/reparse points in every existing component, including root."""
    for component in reversed((path, *path.parents)):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise EdgeError("archive_unsafe_path")
        if component != path and not stat.S_ISDIR(info.st_mode):
            raise EdgeError("archive_unsafe_path")
    if directory and not stat.S_ISDIR(info.st_mode):
        raise EdgeError("archive_unsafe_path")
    if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
        raise EdgeError("archive_unsafe_path")


@contextmanager
def _receiver_lock(root):
    lock = root / ".receiver.lock"
    if os.path.lexists(lock):
        _check_path(lock)
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        _check_path(lock)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)  # OS releases locks on crash as well as normal completion.


def _sync_directory(path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _replace(source, destination):
    if os.name == "nt":
        import ctypes
        # WRITE_THROUGH persists the rename on Windows, where directory fsync
        # is not exposed by Python. Destination was checked under receiver lock.
        move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        move.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong)
        move.restype = ctypes.c_int
        if not move(str(source), str(destination), 0x1 | 0x8):
            raise OSError("archive_replace_failed")
    else:
        os.replace(source, destination)


def accept_aggregate(scope, archive_dir, item):
    """Validate and durably publish one immutable revision; never acknowledge it."""
    data = _validate(scope, item)
    temporary = None
    try:
        root = Path(archive_dir)
        if not root.is_absolute() or ".." in root.parts or str(root).startswith("\\\\"):
            raise EdgeError("archive_unsafe_path")
        _check_path(root, directory=True)  # Host must provision the root.
        with _receiver_lock(root):
            parent = root
            for name in (_hash(asdict(scope)), item["key"]):
                child = parent / name
                if not os.path.lexists(child):
                    child.mkdir(mode=0o700)
                    _sync_directory(parent)
                _check_path(child, directory=True)
                parent = child
            # One immutable slot per generation also rejects a second digest
            # claiming the same generation. The full revision is in the body.
            target = parent / (item["revision"].split(":")[0] + ".json")
            if os.path.lexists(target):
                _check_path(target)
                with target.open("r+b") as handle:
                    if handle.read(len(data) + 1) != data:
                        raise EdgeError("archive_artifact_conflict")
                    os.fsync(handle.fileno())
                _sync_directory(parent)
                return
            temporary = parent / (".pending-" + uuid.uuid4().hex)
            with temporary.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            _check_path(parent, directory=True)
            _replace(temporary, target)
            temporary = None
            _sync_directory(parent)
            _check_path(target)
            with target.open("r+b") as handle:
                if handle.read(len(data) + 1) != data:
                    raise EdgeError("archive_readback_failed")
                os.fsync(handle.fileno())
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, EdgeError):
            raise
        raise EdgeError("archive_storage_unavailable") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass
