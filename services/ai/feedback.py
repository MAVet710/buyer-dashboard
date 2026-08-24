from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid
from typing import Any

from sqlalchemy import Engine, text

from .sanitization import sanitize_mapping, sanitize_text


class AgentFeedbackStore:
    """Tenant-bound feedback foundation. Nothing is training-approved by default."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def save(self, *, organization_id: str, facility_id: str, agent: str, task_type: str, sanitized_prompt: str, tool_names: list[str], sanitized_tool_outcomes: dict[str, Any], answer: str, rating: int | None, corrected_answer: str, provider: str, model: str, evaluation_score: float | None = None) -> str:
        if not organization_id or not facility_id:
            raise ValueError("Feedback requires tenant scope.")
        row_id = str(uuid.uuid4())
        prompt = sanitize_text(sanitized_prompt, max_chars=8000)
        response = sanitize_text(answer, max_chars=16000)
        correction = sanitize_text(corrected_answer, max_chars=16000)
        safe_outcomes = sanitize_mapping(sanitized_tool_outcomes)
        with self.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO ai_agent_feedback
                (id, organization_id, facility_id, created_at, agent, normalized_task_type, sanitized_prompt, tool_names_json, sanitized_tool_outcomes_json, answer, user_rating, corrected_answer, provider, model, evaluation_score, training_approved)
                VALUES (:id,:org,:facility,:created,:agent,:task,:prompt,:tools,:outcomes,:answer,:rating,:correction,:provider,:model,:score,:training_approved)
            """), {"id": row_id, "org": organization_id, "facility": facility_id, "created": datetime.now(timezone.utc), "agent": str(agent)[:64], "task": str(task_type)[:120], "prompt": prompt, "tools": json.dumps([str(value)[:120] for value in tool_names[:50]]), "outcomes": json.dumps(safe_outcomes, default=str), "answer": response, "rating": rating, "correction": correction, "provider": str(provider)[:64], "model": str(model)[:160], "score": evaluation_score, "training_approved": False})
        return row_id

    def export_approved(self) -> list[dict[str, Any]]:
        """Explicit-policy export: only rows independently marked training-approved."""
        with self.engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(text("""
                SELECT agent, normalized_task_type, sanitized_prompt, tool_names_json, sanitized_tool_outcomes_json, answer, corrected_answer
                FROM ai_agent_feedback WHERE training_approved ORDER BY created_at
            """)).mappings()]
        output = []
        for row in rows:
            output.append({
                "agent": row["agent"], "task_type": row["normalized_task_type"], "prompt": row["sanitized_prompt"],
                "tools": json.loads(row["tool_names_json"] or "[]"), "tool_outcomes": json.loads(row["sanitized_tool_outcomes_json"] or "{}"),
                "answer": row["corrected_answer"] or row["answer"],
            })
        return output
