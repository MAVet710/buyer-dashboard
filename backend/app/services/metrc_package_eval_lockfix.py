"""Runtime lock adapter for the scoped MA Metrc package evaluation.

Render's zero-cost API deliberately uses a one-connection SQLAlchemy pool. The
original transaction advisory lock kept that sole connection checked out while
the runner opened tenant-scoped audit/config sessions, causing a fail-safe pool
timeout before any provider mutation. This wrapper keeps concurrency protection
inside the single API process without consuming a database connection.

The live evaluation remains protected by its explicit run-id approval, exact
organization/facility/source bindings, durable started/result audit markers,
and no-retry behavior after uncertain provider outcomes.
"""
from __future__ import annotations

from contextlib import contextmanager
import threading

from sqlalchemy import Engine

from . import metrc_package_eval_resume as _runner

_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.Lock] = {}


@contextmanager
def _process_facility_lock(engine: Engine, organization_id: str, facility_id: str):
    if engine.dialect.name != "postgresql":
        raise _runner.MetrcPackageResumeError(
            "Live execution requires the configured PostgreSQL database."
        )
    token = f"{organization_id}:{facility_id}:{_runner.EVALUATION_BASE_RUN}"
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(token, threading.Lock())
    if not lock.acquire(blocking=False):
        raise _runner.MetrcPackageResumeError(
            "Another package evaluation owns the facility execution lock."
        )
    try:
        yield
    finally:
        lock.release()


def run_package_tasks_25_26(engine: Engine, settings, run_id: str):
    # The Render API is configured with WEB_CONCURRENCY=1. The durable audit
    # markers in the underlying runner still provide restart/idempotency guards;
    # this process lock only replaces the connection-consuming advisory lock.
    original = _runner._facility_lock
    _runner._facility_lock = _process_facility_lock
    try:
        return _runner.run_package_tasks_25_26(engine, settings, run_id)
    finally:
        _runner._facility_lock = original
