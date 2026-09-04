from __future__ import annotations

from typing import Any


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

    Import the client lazily so importing this policy can never create a circular
    dependency through regulatory/integration/traceability module initialization.
    Runtime composition calls this only after the API router graph is initialized.
    """
    from services import metrc_client

    metrc_client._bounded_retry_after = bounded_retry_after
