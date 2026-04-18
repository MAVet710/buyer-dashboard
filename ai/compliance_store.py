"""SQLite-backed structured compliance source storage."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from pathlib import Path
from typing import Iterable


@dataclass
class ComplianceRecord:
    state: str
    scope: str
    topic: str
    answer: str
    source_citation: str
    source_url: str
    last_updated_date: str
    review_status: str


class SQLiteComplianceStore:
    def __init__(self, db_path: str = "./data/compliance/compliance.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS compliance_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state TEXT NOT NULL,
                scope TEXT NOT NULL,
                topic TEXT NOT NULL,
                answer TEXT NOT NULL,
                source_citation TEXT NOT NULL,
                source_url TEXT NOT NULL,
                last_updated_date TEXT NOT NULL,
                review_status TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def upsert_many(self, records: Iterable[ComplianceRecord]) -> int:
        payload = [
            (
                r.state,
                r.scope,
                r.topic,
                r.answer,
                r.source_citation,
                r.source_url,
                r.last_updated_date,
                r.review_status,
            )
            for r in records
        ]
        if not payload:
            return 0

        self._conn.executemany(
            """
            INSERT INTO compliance_sources (
                state, scope, topic, answer, source_citation, source_url, last_updated_date, review_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
        self._conn.commit()
        return len(payload)

    def search(self, state: str, scope: str, topic: str, limit: int = 5) -> list[ComplianceRecord]:
        topic_like = f"%{topic.strip().lower()}%"
        rows = self._conn.execute(
            """
            SELECT state, scope, topic, answer, source_citation, source_url, last_updated_date, review_status
            FROM compliance_sources
            WHERE lower(state) = lower(?)
              AND (lower(scope) = lower(?) OR lower(scope) = 'both')
              AND lower(topic) LIKE ?
            ORDER BY last_updated_date DESC
            LIMIT ?
            """,
            (state.strip(), scope.strip(), topic_like, limit),
        ).fetchall()

        return [ComplianceRecord(**dict(row)) for row in rows]

    def close(self) -> None:
        self._conn.close()
