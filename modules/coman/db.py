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


def create_coman_engine(database_url: str | None = None) -> Engine:
    resolved = resolve_database_url(database_url)
    options: dict = {"future": True, "pool_pre_ping": True}
    if resolved.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    else:
        options["pool_recycle"] = 300
    return create_engine(resolved, **options)
