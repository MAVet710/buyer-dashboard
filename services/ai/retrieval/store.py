from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import uuid
from typing import Any

from sqlalchemy import Engine, text


_SOURCE_PRECEDENCE = {
    "regulation": 1.00,
    "regulatory_guidance": 0.92,
    "facility_sop": 0.90,
    "internal_policy": 0.86,
    "equipment_manual": 0.84,
    "manufacturer": 0.82,
    "metrc": 0.78,
    "dutchie": 0.74,
    "technical_reference": 0.68,
    "peer_reviewed": 0.70,
    "field_practice": 0.22,
}


@dataclass(frozen=True)
class KnowledgeScope:
    organization_id: str
    facility_id: str


class KnowledgeStore:
    """SQL knowledge store with tenant filtering applied before ranking."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _effective_timestamp(value: Any) -> float:
        text_value = str(value or "").strip()
        for fmt, width in (("%Y-%m-%d", 10), ("%Y-%m", 7), ("%Y", 4)):
            try:
                return datetime.strptime(text_value[:width], fmt).replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                continue
        return 0.0

    @classmethod
    def _precedence_score(cls, row: dict[str, Any]) -> float:
        source_type = str(row.get("source_type") or "").casefold().strip()
        source_rank = _SOURCE_PRECEDENCE.get(source_type, 0.50)
        effective = cls._effective_timestamp(row.get("effective_date"))
        if effective:
            year = datetime.fromtimestamp(effective, tz=timezone.utc).year
            freshness = max(0.0, min(1.0, (year - 2018) / 10.0))
        else:
            freshness = 0.35
        return round(0.82 * source_rank + 0.18 * freshness, 6)

    def add_document(self, *, scope: KnowledgeScope, title: str, source: str, source_type: str, authority_level: int, jurisdiction: str = "", effective_date: str = "", version: str = "", source_url: str = "", global_scope: bool = False, facility_scope: bool = True, document_hash: str = "") -> str:
        document_id = str(uuid.uuid4())
        organization_id = None if global_scope else scope.organization_id
        facility_id = None if global_scope or not facility_scope else scope.facility_id
        digest = document_hash or hashlib.sha256(f"{title}|{source}|{version}".encode()).hexdigest()
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO ai_knowledge_documents
                (id, organization_id, facility_id, title, source, source_type, authority_level, jurisdiction, effective_date, retrieved_or_uploaded_at, version, document_hash, source_url, active)
                VALUES (:id,:org,:facility,:title,:source,:source_type,:authority,:jurisdiction,:effective,:uploaded,:version,:hash,:url,:active)
            """), {"id": document_id, "org": organization_id, "facility": facility_id, "title": title[:500], "source": source[:500], "source_type": source_type[:120], "authority": max(1, min(int(authority_level), 99)), "jurisdiction": jurisdiction[:120], "effective": effective_date[:64], "uploaded": now, "version": version[:120], "hash": digest[:64], "url": source_url[:1000], "active": True})
        return document_id

    def add_chunk(self, *, document_id: str, scope: KnowledgeScope, content: str, chunk_number: int, page_or_section: str = "", authority_level: int = 99, embedding: list[float] | None = None, global_scope: bool = False, facility_scope: bool = True) -> str:
        chunk_id = str(uuid.uuid4())
        organization_id = None if global_scope else scope.organization_id
        facility_id = None if global_scope or not facility_scope else scope.facility_id
        with self.engine.begin() as connection:
            parent = connection.execute(text("""
                SELECT organization_id, facility_id, authority_level
                FROM ai_knowledge_documents
                WHERE id=:id AND active
            """), {"id": document_id}).mappings().first()
            if parent is None:
                raise ValueError("Knowledge parent document does not exist or is inactive.")
            if parent["organization_id"] != organization_id or parent["facility_id"] != facility_id:
                raise ValueError("Knowledge chunk scope must exactly match its parent document.")
            parent_authority = int(parent["authority_level"] or 99)
            if int(authority_level) != parent_authority:
                raise ValueError("Knowledge chunk authority must exactly match its parent document.")
            connection.execute(text("""
                INSERT INTO ai_knowledge_chunks
                (id, document_id, organization_id, facility_id, chunk_number, page_or_section, content, authority_level, embedding_json)
                VALUES (:id,:document,:org,:facility,:number,:page,:content,:authority,:embedding)
            """), {"id": chunk_id, "document": document_id, "org": organization_id, "facility": facility_id, "number": int(chunk_number), "page": page_or_section[:240], "content": str(content)[:20000], "authority": parent_authority, "embedding": json.dumps(embedding or [])})
        return chunk_id

    def find_document_by_hash(self, *, scope: KnowledgeScope, document_hash: str, facility_scope: bool = True) -> dict[str, Any] | None:
        if not scope.organization_id or not scope.facility_id or not document_hash:
            return None
        facility_sql = "facility_id = :facility" if facility_scope else "facility_id IS NULL"
        sql = text(f"""
            SELECT id, title, source_url, document_hash, version
            FROM ai_knowledge_documents
            WHERE active AND organization_id = :org AND {facility_sql} AND document_hash = :hash
            LIMIT 1
        """)
        params: dict[str, Any] = {"org": scope.organization_id, "hash": document_hash[:64]}
        if facility_scope:
            params["facility"] = scope.facility_id
        try:
            with self.engine.connect() as connection:
                row = connection.execute(sql, params).mappings().first()
            return dict(row) if row else None
        except Exception:
            return None

    def deactivate_superseded_source(self, *, scope: KnowledgeScope, source_url: str, keep_document_id: str, facility_scope: bool = True) -> int:
        if not scope.organization_id or not scope.facility_id or not source_url or not keep_document_id:
            return 0
        facility_sql = "facility_id = :facility" if facility_scope else "facility_id IS NULL"
        sql = text(f"""
            UPDATE ai_knowledge_documents
            SET active = :inactive
            WHERE active AND organization_id = :org AND {facility_sql}
              AND source_url = :url AND id <> :keep
        """)
        params: dict[str, Any] = {
            "inactive": False,
            "org": scope.organization_id,
            "url": source_url[:1000],
            "keep": keep_document_id,
        }
        if facility_scope:
            params["facility"] = scope.facility_id
        try:
            with self.engine.begin() as connection:
                result = connection.execute(sql, params)
                return int(result.rowcount or 0)
        except Exception:
            return 0

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0

    def list_documents(self, *, scope: KnowledgeScope, limit: int = 200) -> list[dict[str, Any]]:
        if not scope.organization_id or not scope.facility_id:
            return []
        sql = text("""
            SELECT id, organization_id, facility_id, title, source, source_type, authority_level,
                   jurisdiction, effective_date, retrieved_or_uploaded_at, version, document_hash,
                   source_url, active
            FROM ai_knowledge_documents
            WHERE active
              AND (organization_id IS NULL OR organization_id = :org)
              AND (facility_id IS NULL OR facility_id = :facility)
            ORDER BY authority_level ASC, retrieved_or_uploaded_at DESC, title ASC
            LIMIT :limit
        """)
        try:
            with self.engine.connect() as connection:
                rows = [dict(row._mapping) for row in connection.execute(sql, {
                    "org": scope.organization_id,
                    "facility": scope.facility_id,
                    "limit": max(1, min(int(limit), 500)),
                })]
        except Exception:
            return []
        for row in rows:
            row["scope"] = "global" if row.get("organization_id") is None else "organization" if row.get("facility_id") is None else "facility"
            row["precedence_score"] = self._precedence_score(row)
            row.pop("organization_id", None)
            row.pop("facility_id", None)
        return rows

    def search(self, *, scope: KnowledgeScope, query: str, query_embedding: list[float] | None = None, limit: int = 8, max_authority_level: int | None = None) -> list[dict[str, Any]]:
        if not scope.organization_id or not scope.facility_id:
            return []
        tokens = [token for token in re.findall(r"[a-z0-9]{3,}", str(query or "").casefold())[:8]]
        params: dict[str, Any] = {"org": scope.organization_id, "facility": scope.facility_id, "limit": 200}
        lexical_clauses = []
        for index, token in enumerate(tokens):
            key = f"q{index}"
            params[key] = f"%{token}%"
            lexical_clauses.append(f"LOWER(c.content) LIKE :{key}")
        lexical_sql = "(" + " OR ".join(lexical_clauses) + ")" if lexical_clauses else "1=0"
        authority_sql = ""
        if max_authority_level is not None:
            authority_sql = " AND c.authority_level <= :max_authority AND d.authority_level <= :max_authority"
            params["max_authority"] = int(max_authority_level)
        sql = text(f"""
            SELECT c.id, c.document_id, c.chunk_number, c.page_or_section, c.content, c.authority_level, c.embedding_json,
                   d.title, d.source, d.source_type, d.jurisdiction, d.effective_date, d.retrieved_or_uploaded_at, d.version, d.source_url
            FROM ai_knowledge_chunks c
            JOIN ai_knowledge_documents d ON d.id = c.document_id
            WHERE d.active
              AND (c.organization_id IS NULL OR c.organization_id = :org)
              AND (c.facility_id IS NULL OR c.facility_id = :facility)
              AND (d.organization_id IS NULL OR d.organization_id = :org)
              AND (d.facility_id IS NULL OR d.facility_id = :facility)
              AND (c.organization_id = d.organization_id OR (c.organization_id IS NULL AND d.organization_id IS NULL))
              AND (c.facility_id = d.facility_id OR (c.facility_id IS NULL AND d.facility_id IS NULL))
              AND c.authority_level = d.authority_level
              AND {lexical_sql}{authority_sql}
            ORDER BY c.authority_level ASC, c.chunk_number ASC
            LIMIT :limit
        """)
        try:
            with self.engine.connect() as connection:
                rows = [dict(row._mapping) for row in connection.execute(sql, params)]
        except Exception:
            return []
        query_tokens = set(tokens)
        for row in rows:
            text_tokens = set(re.findall(r"[a-z0-9]{3,}", str(row.get("content") or "").casefold()))
            lexical = len(query_tokens & text_tokens) / max(1, len(query_tokens))
            try:
                embedding = json.loads(row.get("embedding_json") or "[]")
            except (TypeError, ValueError, json.JSONDecodeError):
                embedding = []
            vector = self._cosine(query_embedding or [], [float(value) for value in embedding])
            authority = max(0.0, (7.0 - min(float(row.get("authority_level") or 99), 7.0)) / 7.0)
            precedence = self._precedence_score(row)
            row["precedence_score"] = precedence
            row["score"] = round(0.52 * lexical + 0.30 * max(0.0, vector) + 0.12 * authority + 0.06 * precedence, 6)
            row.pop("embedding_json", None)
        rows.sort(key=lambda row: (float(row.get("score") or 0), -int(row.get("authority_level") or 99), float(row.get("precedence_score") or 0)), reverse=True)
        return rows[: max(1, min(int(limit), 20))]

    def health(self, scope: KnowledgeScope) -> dict[str, Any]:
        if not scope.organization_id or not scope.facility_id:
            return {"ok": False, "document_count": 0, "error": "scope_required"}
        try:
            with self.engine.connect() as connection:
                count = int(connection.execute(text("""SELECT COUNT(*) FROM ai_knowledge_documents WHERE active AND (organization_id IS NULL OR organization_id = :org) AND (facility_id IS NULL OR facility_id = :facility)"""), {"org": scope.organization_id, "facility": scope.facility_id}).scalar() or 0)
            return {"ok": True, "document_count": count}
        except Exception as exc:
            return {"ok": False, "document_count": 0, "error": exc.__class__.__name__}
