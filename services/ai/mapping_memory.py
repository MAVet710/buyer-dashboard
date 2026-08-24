from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import uuid
from typing import Iterable

from sqlalchemy import Engine, text


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().casefold()).strip()


def schema_fingerprint(columns: Iterable[str]) -> str:
    normalized = sorted(normalize_header(column) for column in columns if str(column).strip())
    return hashlib.sha256(json.dumps(normalized, separators=(",", ":")).encode()).hexdigest()


class MappingMemory:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def approved(self, *, organization_id: str, facility_id: str, dataset_type: str, source_vendor: str, columns: Iterable[str]) -> dict[str, str]:
        if not organization_id or not facility_id:
            raise ValueError("Mapping memory requires tenant scope.")
        fingerprint = schema_fingerprint(columns)
        rows: list[dict] = []
        try:
            with self.engine.begin() as connection:
                rows = [dict(row) for row in connection.execute(text("""
                    SELECT id, normalized_source_header, canonical_field FROM ai_mapping_memory
                    WHERE organization_id = :org AND (facility_id IS NULL OR facility_id = :facility)
                      AND dataset_type = :dataset AND source_vendor = :vendor
                      AND schema_fingerprint = :fingerprint AND human_approved
                """), {"org": organization_id, "facility": facility_id, "dataset": str(dataset_type)[:120], "vendor": normalize_header(source_vendor)[:160], "fingerprint": fingerprint}).mappings()]
                for row in rows:
                    connection.execute(text("UPDATE ai_mapping_memory SET usage_count = usage_count + 1, last_used_at = :now WHERE id = :id"), {"now": datetime.now(timezone.utc), "id": row["id"]})
        except Exception:
            return {}
        by_normalized = {normalize_header(column): str(column) for column in columns}
        output: dict[str, str] = {}
        for row in rows:
            source = by_normalized.get(str(row.get("normalized_source_header") or ""))
            if source:
                output[str(row.get("canonical_field") or "")] = source
        return {key: value for key, value in output.items() if key and value}

    def save(self, *, organization_id: str, facility_id: str | None, dataset_type: str, source_vendor: str, source_header: str, canonical_field: str, columns: Iterable[str], confidence: float, origin: str, human_approved: bool) -> None:
        if not organization_id:
            raise ValueError("Mapping memory requires organization scope.")
        normalized = normalize_header(source_header)
        fingerprint = schema_fingerprint(columns)
        now = datetime.now(timezone.utc)
        params = {"id": str(uuid.uuid4()), "org": organization_id, "facility": facility_id, "dataset": str(dataset_type)[:120], "vendor": normalize_header(source_vendor)[:160], "header": normalized[:255], "field": str(canonical_field)[:160], "confidence": max(0.0, min(float(confidence), 1.0)), "origin": str(origin)[:80], "approved": bool(human_approved), "fingerprint": fingerprint, "now": now}
        try:
            with self.engine.begin() as connection:
                existing = connection.execute(text("""SELECT id FROM ai_mapping_memory WHERE organization_id=:org AND COALESCE(facility_id,'')=COALESCE(:facility,'') AND dataset_type=:dataset AND source_vendor=:vendor AND normalized_source_header=:header AND schema_fingerprint=:fingerprint"""), params).scalar_one_or_none()
                if existing:
                    params["existing"] = existing
                    connection.execute(text("""UPDATE ai_mapping_memory SET canonical_field=:field, confidence=:confidence, origin=:origin, human_approved=:approved, last_used_at=:now WHERE id=:existing"""), params)
                else:
                    connection.execute(text("""INSERT INTO ai_mapping_memory (id, organization_id, facility_id, dataset_type, source_vendor, normalized_source_header, canonical_field, confidence, origin, last_used_at, usage_count, human_approved, schema_fingerprint) VALUES (:id,:org,:facility,:dataset,:vendor,:header,:field,:confidence,:origin,:now,0,:approved,:fingerprint)"""), params)
        except Exception:
            return
