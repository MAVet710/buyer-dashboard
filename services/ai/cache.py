from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from threading import RLock
from typing import Any


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class TenantCache:
    """Small process-local TTL cache. Tenant/source versions are mandatory key parts."""

    def __init__(self, *, max_entries: int = 512) -> None:
        self.max_entries = max(16, int(max_entries)); self._values: dict[str, CacheEntry] = {}; self._lock = RLock()

    @staticmethod
    def key(*, organization_id: str, facility_id: str, namespace: str, source_version: str, payload: Any) -> str:
        if not organization_id or not facility_id: raise ValueError("Tenant cache keys require organization and facility scope.")
        serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        return f"{organization_id}|{facility_id}|{namespace}|{source_version}|{digest}"

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            entry = self._values.get(key)
            if entry is None: return None
            if entry.expires_at <= now:
                self._values.pop(key, None); return None
            return entry.value

    def set(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        ttl = max(1, min(int(ttl_seconds), 86400))
        with self._lock:
            if len(self._values) >= self.max_entries:
                oldest = min(self._values, key=lambda item: self._values[item].expires_at); self._values.pop(oldest, None)
            self._values[key] = CacheEntry(value, time.time() + ttl)

    def clear_tenant(self, organization_id: str, facility_id: str) -> None:
        prefix = f"{organization_id}|{facility_id}|"
        with self._lock:
            for key in [key for key in self._values if key.startswith(prefix)]: self._values.pop(key, None)
