"""Database configuration for the Co-Man workspace.

Co-Man data must never silently fall back to an ephemeral database in a hosted
deployment. Callers must provide COMAN_DATABASE_URL or DATABASE_URL. Tests and
local tools can pass an explicit SQLite URL.
"""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine


class ComanDatabaseConfigurationError(RuntimeError):
    """Raised when durable Co-Man persistence has not been configured."""


def resolve_database_url(explicit_url: str | None = None) -> str:
    database_url = str(
        explicit_url
        or os.environ.get("COMAN_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    if not database_url:
        # Root-level Streamlit secrets are the safest free-hosting option and
        # keep the Supabase password out of source control.
        try:
            import streamlit as st

            database_url = str(
                st.secrets.get("COMAN_DATABASE_URL")
                or st.secrets.get("DATABASE_URL")
                or ""
            ).strip()
        except Exception:
            database_url = ""
    if not database_url:
        raise ComanDatabaseConfigurationError(
            "Co-Man database is not configured. Set COMAN_DATABASE_URL."
        )
    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgres://") :]
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgresql://") :]
    return database_url


def _int_setting(name: str, default: int, *, minimum: int) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def create_coman_engine(database_url: str | None = None) -> Engine:
    resolved = resolve_database_url(database_url)
    options: dict = {"future": True, "pool_pre_ping": True}
    if resolved.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    else:
        # Supabase session-mode pooling has a finite server-side connection
        # budget. SQLAlchemy's QueuePool defaults (5 pooled + 10 overflow)
        # can consume that entire budget from a single Cloud Run process.
        # Keep the application pool deliberately small and bounded; callers
        # can tune it explicitly for larger database plans.
        options["pool_size"] = _int_setting("DATABASE_POOL_SIZE", 3, minimum=1)
        options["max_overflow"] = _int_setting("DATABASE_MAX_OVERFLOW", 0, minimum=0)
        options["pool_timeout"] = _int_setting("DATABASE_POOL_TIMEOUT", 30, minimum=1)
        options["pool_use_lifo"] = True
        options["pool_recycle"] = 300
        options["connect_args"] = {"connect_timeout": 5}
    return create_engine(resolved, **options)
