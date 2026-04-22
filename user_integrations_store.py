"""
Persistent per-user integration storage.

This module intentionally does NOT replace authentication. It only stores
integration/settings payloads keyed by already-authenticated usernames.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    from sqlalchemy import Boolean, DateTime, MetaData, String, Table, Column, create_engine, select, insert, update
    from sqlalchemy import func as sa_func
    SQLALCHEMY_AVAILABLE = True
except Exception:
    SQLALCHEMY_AVAILABLE = False


def normalize_username(username: str | None) -> str:
    return str(username or "").strip().casefold()


@dataclass
class UserIntegrationRecord:
    username: str
    is_admin: bool
    doobie_base_url: str
    doobie_api_key: str
    doobie_status: str
    doobie_last_validated: str | None
    metrc_api_key: str
    metrc_state: str
    metrc_license: str
    created_at: datetime | None
    updated_at: datetime | None


class UserIntegrationsStore:
    """SQL-backed store with graceful degradation on DB failures."""

    def __init__(self) -> None:
        self._engine = None
        self._table = None
        if not SQLALCHEMY_AVAILABLE:
            return

        db_url = str(os.environ.get("USER_INTEGRATIONS_DATABASE_URL", "")).strip()
        db_path = str(os.environ.get("USER_INTEGRATIONS_DB_PATH", "")).strip()
        if not db_url:
            db_url = f"sqlite:///{db_path or 'user_integrations.db'}"
        try:
            self._engine = create_engine(db_url, future=True, pool_pre_ping=True)
            metadata = MetaData()
            self._table = Table(
                "user_integrations",
                metadata,
                Column("username", String(255), nullable=False),
                Column("normalized_username", String(255), primary_key=True),
                Column("is_admin", Boolean, nullable=False, server_default="0"),
                Column("doobie_base_url", String(1024), nullable=False, server_default=""),
                Column("doobie_api_key", String(1024), nullable=False, server_default=""),
                Column("doobie_status", String(64), nullable=False, server_default="not_connected"),
                Column("doobie_last_validated", String(64), nullable=True),
                Column("metrc_api_key", String(1024), nullable=False, server_default=""),
                Column("metrc_state", String(128), nullable=False, server_default=""),
                Column("metrc_license", String(128), nullable=False, server_default=""),
                Column("created_at", DateTime(timezone=True), nullable=False, server_default=sa_func.now()),
                Column("updated_at", DateTime(timezone=True), nullable=False, server_default=sa_func.now()),
            )
            metadata.create_all(self._engine)
        except Exception:
            self._engine = None
            self._table = None

    @property
    def available(self) -> bool:
        return self._engine is not None and self._table is not None

    def get_user(self, username: str) -> UserIntegrationRecord | None:
        if not self.available:
            return None
        norm = normalize_username(username)
        if not norm:
            return None
        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    select(self._table).where(self._table.c.normalized_username == norm)
                ).mappings().first()
            if not row:
                return None
            return UserIntegrationRecord(
                username=str(row.get("username") or ""),
                is_admin=bool(row.get("is_admin")),
                doobie_base_url=str(row.get("doobie_base_url") or ""),
                doobie_api_key=str(row.get("doobie_api_key") or ""),
                doobie_status=str(row.get("doobie_status") or "not_connected"),
                doobie_last_validated=row.get("doobie_last_validated"),
                metrc_api_key=str(row.get("metrc_api_key") or ""),
                metrc_state=str(row.get("metrc_state") or ""),
                metrc_license=str(row.get("metrc_license") or ""),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )
        except Exception:
            return None

    def ensure_user(self, username: str, is_admin: bool) -> UserIntegrationRecord | None:
        if not self.available:
            return None
        clean_username = str(username or "").strip()
        norm = normalize_username(clean_username)
        if not norm:
            return None
        payload: dict[str, Any] = {
            "username": clean_username,
            "normalized_username": norm,
            "is_admin": bool(is_admin),
            "updated_at": datetime.now(timezone.utc),
        }
        try:
            with self._engine.begin() as conn:
                existing = conn.execute(select(self._table.c.normalized_username).where(self._table.c.normalized_username == norm)).first()
                if existing:
                    conn.execute(
                        update(self._table)
                        .where(self._table.c.normalized_username == norm)
                        .values(
                            username=clean_username,
                            is_admin=bool(is_admin),
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
                else:
                    conn.execute(insert(self._table).values(**payload))
            return self.get_user(clean_username)
        except Exception:
            return None

    def save_user_integrations(self, username: str, values: dict[str, Any], is_admin: bool | None = None) -> bool:
        if not self.available:
            return False
        clean_username = str(username or "").strip()
        norm = normalize_username(clean_username)
        if not norm:
            return False

        allowed_keys = {
            "doobie_base_url",
            "doobie_api_key",
            "doobie_status",
            "doobie_last_validated",
            "metrc_api_key",
            "metrc_state",
            "metrc_license",
        }
        update_values = {k: values.get(k) for k in allowed_keys if k in values}
        update_values["username"] = clean_username
        update_values["normalized_username"] = norm
        update_values["updated_at"] = datetime.now(timezone.utc)
        if is_admin is not None:
            update_values["is_admin"] = bool(is_admin)

        try:
            with self._engine.begin() as conn:
                existing = conn.execute(select(self._table.c.normalized_username).where(self._table.c.normalized_username == norm)).first()
                if existing:
                    conn.execute(
                        update(self._table)
                        .where(self._table.c.normalized_username == norm)
                        .values(**update_values)
                    )
                else:
                    conn.execute(insert(self._table).values(**update_values))
            return True
        except Exception:
            return False
