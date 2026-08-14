"""Framework-light adapters for replaying reviewed file sources."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Mapping


class UploadedFileLike(BytesIO):
    def __init__(self, payload: bytes, name: str):
        super().__init__(payload)
        self.name = str(name or "cached_upload")


def load_cached_upload(state: Mapping[str, Any], cache_key: str) -> UploadedFileLike | None:
    cached = state.get(cache_key)
    if not isinstance(cached, dict) or not cached.get("bytes"):
        return None
    return UploadedFileLike(bytes(cached["bytes"]), str(cached.get("name") or "cached_upload"))
