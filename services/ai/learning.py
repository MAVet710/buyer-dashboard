from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any
import uuid

import pandas as pd
from sqlalchemy import Engine, text

from .datasets import LoadedDataset
from .sanitization import is_business_column, is_sensitive_name, norm, sanitize_text


_IDENTIFIER_TOKENS = {
    "id", "uuid", "sku", "upc", "tag", "package_id", "lot_id", "batch_id", "manifest_id",
    "license", "license_number", "reference", "source_url", "file", "filename",
}
_GROUP_SKIP = _IDENTIFIER_TOKENS | {"notes", "description", "reason", "status", "date", "time"}
_TARGET_HINTS = (
    "yield", "recovery", "margin", "revenue", "cost", "cogs", "fill_rate", "attainment",
    "variance", "days_of_supply", "velocity", "throughput", "downtime", "cycle_time",
    "turnaround", "scrap", "loss", "balance", "quantity", "units", "quality",
)


def _safe_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _safe_label(value: Any) -> str:
    return sanitize_text(value, max_chars=120).strip()


class AgentLearningEngine:
    """Controlled facility learning shared by every DoobieLogic agent.

    The engine stores aggregate associations, provider-quality summaries, and
    explicitly learning-approved corrections. It never stores raw operational
    rows, never changes model weights, and never promotes learned patterns into
    regulatory/SOP authority.
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _learning_key(*parts: str) -> str:
        raw = "|".join(norm(part) for part in parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]

    @staticmethod
    def _numeric_candidates(frame: pd.DataFrame) -> dict[str, pd.Series]:
        output: dict[str, pd.Series] = {}
        for raw in list(frame.columns)[:80]:
            name = str(raw)
            normalized = norm(name)
            if is_sensitive_name(name) or not is_business_column(name):
                continue
            if normalized in _IDENTIFIER_TOKENS or normalized.endswith("_id"):
                continue
            values = pd.to_numeric(frame[raw], errors="coerce")
            if int(values.notna().sum()) < 8 or int(values.nunique(dropna=True)) < 3:
                continue
            output[name] = values.astype(float)
            if len(output) >= 14:
                break
        return output

    @staticmethod
    def _categorical_candidates(frame: pd.DataFrame) -> list[str]:
        output: list[str] = []
        for raw in list(frame.columns)[:80]:
            name = str(raw)
            normalized = norm(name)
            if is_sensitive_name(name) or not is_business_column(name):
                continue
            if normalized in _GROUP_SKIP or normalized.endswith("_id"):
                continue
            values = frame[raw].dropna().astype(str).str.strip()
            unique = int(values[values.ne("")].nunique())
            if 2 <= unique <= 12:
                output.append(name)
            if len(output) >= 8:
                break
        return output

    def _correlation_patterns(self, dataset: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
        numeric = self._numeric_candidates(frame)
        names = list(numeric)
        patterns: list[dict[str, Any]] = []
        for i, left in enumerate(names):
            for right in names[i + 1 :]:
                pair = pd.DataFrame({"left": numeric[left], "right": numeric[right]}).dropna()
                sample = len(pair)
                if sample < 8:
                    continue
                correlation = _safe_number(pair["left"].corr(pair["right"]))
                if correlation is None or abs(correlation) < 0.55:
                    continue
                confidence = min(0.95, abs(correlation) * min(1.0, sample / 30.0))
                direction = "move together" if correlation > 0 else "move in opposite directions"
                patterns.append({
                    "learning_key": self._learning_key("correlation", dataset, left, right),
                    "learning_type": "numeric_association",
                    "source_kind": "historical_data",
                    "summary": f"In {dataset}, {left} and {right} {direction} in the available history (r={correlation:.2f}, n={sample}). This is an association, not proof of causation.",
                    "evidence": {"dataset": dataset, "left_metric": left, "right_metric": right, "correlation": round(correlation, 4)},
                    "sample_size": sample,
                    "confidence": round(confidence, 4),
                })
        patterns.sort(key=lambda row: (row["confidence"], row["sample_size"]), reverse=True)
        return patterns[:6]

    def _group_patterns(self, dataset: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
        numeric = self._numeric_candidates(frame)
        targets = [name for name in numeric if any(hint in norm(name) for hint in _TARGET_HINTS)][:5]
        categories = self._categorical_candidates(frame)
        patterns: list[dict[str, Any]] = []
        for category in categories:
            labels = frame[category].fillna("").astype(str).str.strip()
            for target in targets:
                working = pd.DataFrame({"group": labels, "metric": numeric[target]}).dropna()
                working = working.loc[working["group"].ne("")]
                if len(working) < 10:
                    continue
                grouped = working.groupby("group")["metric"].agg(["mean", "count"])
                grouped = grouped.loc[grouped["count"] >= 3]
                if len(grouped) < 2:
                    continue
                high = grouped.sort_values("mean", ascending=False).iloc[0]
                low = grouped.sort_values("mean", ascending=True).iloc[0]
                high_name = _safe_label(grouped["mean"].idxmax())
                low_name = _safe_label(grouped["mean"].idxmin())
                high_value = _safe_number(high["mean"])
                low_value = _safe_number(low["mean"])
                if not high_name or not low_name or high_value is None or low_value is None:
                    continue
                spread = abs(high_value - low_value)
                scale = max(abs(high_value), abs(low_value), 1.0)
                relative = spread / scale
                sample = int(high["count"] + low["count"])
                if relative < 0.10:
                    continue
                confidence = min(0.90, 0.35 + relative * 0.35 + min(sample, 40) / 200.0)
                patterns.append({
                    "learning_key": self._learning_key("group", dataset, category, target, high_name, low_name),
                    "learning_type": "group_outcome_association",
                    "source_kind": "historical_data",
                    "summary": f"In {dataset}, {target} differs across {category}: {high_name} averages {high_value:.2f} versus {low_name} at {low_value:.2f} across the compared groups (n={sample}). Treat this as a historical association and validate confounders before acting.",
                    "evidence": {"dataset": dataset, "group_field": category, "target_metric": target, "higher_group": high_name, "lower_group": low_name, "higher_mean": round(high_value, 4), "lower_mean": round(low_value, 4)},
                    "sample_size": sample,
                    "confidence": round(confidence, 4),
                })
        patterns.sort(key=lambda row: (row["confidence"], row["sample_size"]), reverse=True)
        return patterns[:6]

    def derive_patterns(self, datasets: dict[str, LoadedDataset]) -> list[dict[str, Any]]:
        patterns: list[dict[str, Any]] = []
        for dataset, loaded in sorted(datasets.items()):
            frame = loaded.frame
            if frame is None or len(frame) < 8:
                continue
            bounded = frame.tail(500).copy()
            patterns.extend(self._correlation_patterns(dataset, bounded))
            patterns.extend(self._group_patterns(dataset, bounded))
        patterns.sort(key=lambda row: (row["confidence"], row["sample_size"]), reverse=True)
        return patterns[:16]

    def _telemetry_patterns(self, *, organization_id: str, facility_id: str, agent: str) -> list[dict[str, Any]]:
        try:
            with self.engine.connect() as connection:
                rows = [dict(row) for row in connection.execute(text("""
                    SELECT provider, model, is_local, latency_ms, fallback_used, success
                    FROM ai_telemetry
                    WHERE organization_id=:org AND facility_id=:facility AND agent=:agent
                    ORDER BY timestamp DESC LIMIT 500
                """), {"org": organization_id, "facility": facility_id, "agent": agent[:64]}).mappings()]
        except Exception:
            return []
        sample = len(rows)
        if sample < 5:
            return []
        successes = sum(1 for row in rows if bool(row.get("success")))
        fallbacks = sum(1 for row in rows if bool(row.get("fallback_used")))
        local = sum(1 for row in rows if bool(row.get("is_local")))
        latencies = [int(row.get("latency_ms") or 0) for row in rows if int(row.get("latency_ms") or 0) >= 0]
        avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
        success_pct = round(successes / sample * 100.0, 1)
        fallback_pct = round(fallbacks / sample * 100.0, 1)
        local_pct = round(local / sample * 100.0, 1)
        confidence = min(0.95, 0.45 + min(sample, 100) / 200.0)
        return [{
            "learning_key": self._learning_key("telemetry", agent, "runtime_quality"),
            "learning_type": "runtime_quality_pattern",
            "source_kind": "telemetry",
            "summary": f"For {agent}, the latest {sample} AI requests were {success_pct:.1f}% successful, {local_pct:.1f}% local, with {fallback_pct:.1f}% fallback and {avg_latency:.0f} ms average recorded latency. Use this for routing/quality monitoring, not business conclusions.",
            "evidence": {"requests": sample, "success_pct": success_pct, "local_pct": local_pct, "fallback_pct": fallback_pct, "avg_latency_ms": avg_latency},
            "sample_size": sample,
            "confidence": round(confidence, 4),
        }]

    def _upsert(self, *, organization_id: str, facility_id: str, agent: str, pattern: dict[str, Any], now: datetime) -> None:
        params = {
            "org": organization_id,
            "facility": facility_id,
            "agent": agent[:64],
            "key": str(pattern["learning_key"])[:255],
        }
        with self.engine.begin() as connection:
            existing = connection.execute(text("""
                SELECT id, first_observed_at FROM ai_agent_learnings
                WHERE organization_id=:org AND facility_id=:facility AND agent=:agent AND learning_key=:key
                LIMIT 1
            """), params).mappings().first()
            payload = {
                **params,
                "type": str(pattern.get("learning_type") or "pattern")[:80],
                "source": str(pattern.get("source_kind") or "historical_data")[:80],
                "summary": sanitize_text(pattern.get("summary"), max_chars=4000),
                "evidence": json.dumps(pattern.get("evidence") or {}, default=str)[:12000],
                "sample": max(0, int(pattern.get("sample_size") or 0)),
                "confidence": max(0.0, min(1.0, float(pattern.get("confidence") or 0.0))),
                "now": now,
                "active": True,
            }
            if existing:
                connection.execute(text("""
                    UPDATE ai_agent_learnings
                    SET learning_type=:type, source_kind=:source, summary=:summary, evidence_json=:evidence,
                        sample_size=:sample, confidence=:confidence, last_observed_at=:now, active=:active
                    WHERE id=:id
                """), {**payload, "id": existing["id"]})
            else:
                connection.execute(text("""
                    INSERT INTO ai_agent_learnings
                    (id,organization_id,facility_id,agent,learning_key,learning_type,source_kind,summary,evidence_json,sample_size,confidence,first_observed_at,last_observed_at,active)
                    VALUES (:id,:org,:facility,:agent,:key,:type,:source,:summary,:evidence,:sample,:confidence,:now,:now,:active)
                """), {**payload, "id": str(uuid.uuid4())})

    def _replace_source(self, *, organization_id: str, facility_id: str, agent: str, source_kind: str, patterns: list[dict[str, Any]], now: datetime) -> int:
        with self.engine.begin() as connection:
            connection.execute(text("""
                UPDATE ai_agent_learnings SET active=:inactive
                WHERE organization_id=:org AND facility_id=:facility AND agent=:agent AND source_kind=:source
            """), {"inactive": False, "org": organization_id, "facility": facility_id, "agent": agent[:64], "source": source_kind[:80]})
        for pattern in patterns:
            self._upsert(organization_id=organization_id, facility_id=facility_id, agent=agent, pattern=pattern, now=now)
        return len(patterns)

    def refresh(self, *, organization_id: str, facility_id: str, agent: str, datasets: dict[str, LoadedDataset]) -> int:
        if not organization_id or not facility_id or not agent:
            return 0
        historical = self.derive_patterns(datasets)
        telemetry = self._telemetry_patterns(organization_id=organization_id, facility_id=facility_id, agent=agent)
        now = datetime.now(timezone.utc)
        try:
            total = self._replace_source(organization_id=organization_id, facility_id=facility_id, agent=agent, source_kind="historical_data", patterns=historical, now=now)
            total += self._replace_source(organization_id=organization_id, facility_id=facility_id, agent=agent, source_kind="telemetry", patterns=telemetry, now=now)
            return total
        except Exception:
            return 0

    def _approved_corrections(self, *, organization_id: str, facility_id: str, agent: str, limit: int = 3) -> list[dict[str, Any]]:
        try:
            with self.engine.connect() as connection:
                rows = [dict(row) for row in connection.execute(text("""
                    SELECT normalized_task_type, sanitized_prompt, corrected_answer, user_rating, evaluation_score, created_at
                    FROM ai_agent_feedback
                    WHERE organization_id=:org AND facility_id=:facility AND agent=:agent
                      AND learning_approved AND corrected_answer <> ''
                    ORDER BY created_at DESC LIMIT :limit
                """), {"org": organization_id, "facility": facility_id, "agent": agent[:64], "limit": max(1, min(limit, 5))}).mappings()]
        except Exception:
            return []
        output = []
        for row in rows:
            output.append({
                "task_type": str(row.get("normalized_task_type") or "")[:120],
                "prompt": sanitize_text(row.get("sanitized_prompt"), max_chars=600),
                "approved_correction": sanitize_text(row.get("corrected_answer"), max_chars=900),
                "rating": row.get("user_rating"),
                "evaluation_score": row.get("evaluation_score"),
            })
        return output

    def context(self, *, organization_id: str, facility_id: str, agent: str, compliance_agent: bool = False, limit: int = 10) -> dict[str, Any]:
        if not organization_id or not facility_id or not agent:
            return {"patterns": [], "approved_corrections": [], "rules": []}
        try:
            with self.engine.connect() as connection:
                rows = [dict(row) for row in connection.execute(text("""
                    SELECT learning_type, source_kind, summary, sample_size, confidence, last_observed_at
                    FROM ai_agent_learnings
                    WHERE organization_id=:org AND facility_id=:facility AND agent=:agent AND active
                    ORDER BY confidence DESC, sample_size DESC, last_observed_at DESC
                    LIMIT :limit
                """), {"org": organization_id, "facility": facility_id, "agent": agent[:64], "limit": max(1, min(limit, 20))}).mappings()]
        except Exception:
            rows = []
        patterns = [{
            "type": row.get("learning_type"),
            "source": row.get("source_kind"),
            "summary": row.get("summary"),
            "sample_size": int(row.get("sample_size") or 0),
            "confidence": round(float(row.get("confidence") or 0.0), 3),
            "last_observed_at": str(row.get("last_observed_at") or ""),
        } for row in rows]
        corrections = [] if compliance_agent else self._approved_corrections(
            organization_id=organization_id, facility_id=facility_id, agent=agent
        )
        return {
            "patterns": patterns,
            "approved_corrections": corrections,
            "rules": [
                "Learned patterns are advisory historical associations, not causal proof.",
                "Deterministic calculations and current authorized data override learned summaries.",
                "Regulations, legal conclusions, SOP requirements, and machine setpoints can never be learned from feedback or correlations.",
                "Facility-learning approval never implies consent for model training or tuning.",
            ],
        }

    def health(self, *, organization_id: str, facility_id: str) -> dict[str, Any]:
        try:
            with self.engine.connect() as connection:
                count = int(connection.execute(text("""
                    SELECT COUNT(*) FROM ai_agent_learnings
                    WHERE organization_id=:org AND facility_id=:facility AND active
                """), {"org": organization_id, "facility": facility_id}).scalar() or 0)
                agents = int(connection.execute(text("""
                    SELECT COUNT(DISTINCT agent) FROM ai_agent_learnings
                    WHERE organization_id=:org AND facility_id=:facility AND active
                """), {"org": organization_id, "facility": facility_id}).scalar() or 0)
            return {"ok": True, "active_learnings": count, "agents_with_learnings": agents}
        except Exception as exc:
            return {"ok": False, "active_learnings": 0, "agents_with_learnings": 0, "error": exc.__class__.__name__}
