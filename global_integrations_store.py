"""
Persistent global (admin-managed) integration storage.

This store is intentionally separate from per-user integration settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    from sqlalchemy import DateTime, MetaData, String, Table, Column, create_engine, select, insert, update
    from sqlalchemy import func as sa_func
    SQLALCHEMY_AVAILABLE = True
except Exception:
    SQLALCHEMY_AVAILABLE = False


GLOBAL_ROW_KEY = "global"


@dataclass
class GlobalIntegrationsRecord:
    record_key: str
    doobie_base_url: str
    doobie_api_key: str
    doobie_status: str
    doobie_last_validated: str | None
    metrc_api_key: str
    metrc_state: str
    metrc_license: str
    metrc_status: str
    metrc_last_validated: str | None
    updated_by: str
    updated_at: datetime | None
    created_at: datetime | None


class GlobalIntegrationsStore:
    """SQL-backed store with graceful degradation on DB failures."""

    def __init__(self) -> None:
        self._engine = None
        self._table = None
        if not SQLALCHEMY_AVAILABLE:
            return

        db_url = str(os.environ.get("GLOBAL_INTEGRATIONS_DATABASE_URL", "")).strip()
        db_path = str(os.environ.get("GLOBAL_INTEGRATIONS_DB_PATH", "")).strip()
        if not db_url:
            db_url = f"sqlite:///{db_path or 'global_integrations.db'}"

        try:
            self._engine = create_engine(db_url, future=True, pool_pre_ping=True)
            metadata = MetaData()
            self._table = Table(
                "global_integrations",
                metadata,
                Column("record_key", String(64), primary_key=True),
                Column("doobie_base_url", String(1024), nullable=False, server_default=""),
                Column("doobie_api_key", String(1024), nullable=False, server_default=""),
                Column("doobie_status", String(64), nullable=False, server_default="not_connected"),
                Column("doobie_last_validated", String(64), nullable=True),
                Column("metrc_api_key", String(1024), nullable=False, server_default=""),
                Column("metrc_state", String(128), nullable=False, server_default=""),
                Column("metrc_license", String(128), nullable=False, server_default=""),
                Column("metrc_status", String(64), nullable=False, server_default="not_connected"),
                Column("metrc_last_validated", String(64), nullable=True),
                Column("updated_by", String(255), nullable=False, server_default=""),
                Column("updated_at", DateTime(timezone=True), nullable=False, server_default=sa_func.now()),
                Column("created_at", DateTime(timezone=True), nullable=False, server_default=sa_func.now()),
            )
            metadata.create_all(self._engine)
        except Exception:
            self._engine = None
            self._table = None

    @property
    def available(self) -> bool:
        return self._engine is not None and self._table is not None

    def get_global(self) -> GlobalIntegrationsRecord | None:
        if not self.available:
            return None
        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    select(self._table).where(self._table.c.record_key == GLOBAL_ROW_KEY)
                ).mappings().first()
            if not row:
                return None
            return GlobalIntegrationsRecord(
                record_key=str(row.get("record_key") or GLOBAL_ROW_KEY),
                doobie_base_url=str(row.get("doobie_base_url") or ""),
                doobie_api_key=str(row.get("doobie_api_key") or ""),
                doobie_status=str(row.get("doobie_status") or "not_connected"),
                doobie_last_validated=row.get("doobie_last_validated"),
                metrc_api_key=str(row.get("metrc_api_key") or ""),
                metrc_state=str(row.get("metrc_state") or ""),
                metrc_license=str(row.get("metrc_license") or ""),
                metrc_status=str(row.get("metrc_status") or "not_connected"),
                metrc_last_validated=row.get("metrc_last_validated"),
                updated_by=str(row.get("updated_by") or ""),
                updated_at=row.get("updated_at"),
                created_at=row.get("created_at"),
            )
        except Exception:
            return None

    def save_global_integrations(self, values: dict[str, Any], updated_by: str) -> bool:
        if not self.available:
            return False
        allowed_keys = {
            "doobie_base_url",
            "doobie_api_key",
            "doobie_status",
            "doobie_last_validated",
            "metrc_api_key",
            "metrc_state",
            "metrc_license",
            "metrc_status",
            "metrc_last_validated",
        }
        update_values = {k: values.get(k) for k in allowed_keys if k in values}
        update_values["updated_by"] = str(updated_by or "").strip()
        update_values["updated_at"] = datetime.now(timezone.utc)

        try:
            with self._engine.begin() as conn:
                existing = conn.execute(
                    select(self._table.c.record_key).where(self._table.c.record_key == GLOBAL_ROW_KEY)
                ).first()
                if existing:
                    conn.execute(
                        update(self._table)
                        .where(self._table.c.record_key == GLOBAL_ROW_KEY)
                        .values(**update_values)
                    )
                else:
                    conn.execute(
                        insert(self._table).values(
                            record_key=GLOBAL_ROW_KEY,
                            **update_values,
                        )
                    )
            return True
        except Exception:
            return False
