from __future__ import annotations

from typing import Any

from services import metrc_client


MAX_RETRY_AFTER_SECONDS = 30.0


def bounded_retry_after(value: Any) -> float | None:
    """Respect provider Retry-After while preventing unbounded request sleeps."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(seconds, MAX_RETRY_AFTER_SECONDS))


def install_metrc_rate_limit_policy() -> None:
    """Compose the bounded provider policy into the shared Metrc transport.

    The transport intentionally keeps its retry parser module-local. Installing
    this once during API composition means discovery, full hydration, incremental
    sync and explicit live verification all use the same provider-pressure rule
    without duplicating HTTP clients or credential handling.
    """
    metrc_client._bounded_retry_after = bounded_retry_after
