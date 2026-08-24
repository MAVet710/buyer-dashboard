from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from sqlalchemy import Engine, text


class AITelemetry:
    """Non-sensitive AI observability. Prompts and raw datasets are never stored."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def record(self, *, request_id: str, organization_id: str, facility_id: str, agent: str, task_category: str, provider: str, model: str, local: bool, latency_ms: int, tool_call_count: int, retrieval_count: int, input_tokens: int, output_tokens: int, estimated_cost_usd: float, fallback_used: bool, fallback_reason: str, validation_result: str, success: bool) -> None:
        if not organization_id or not facility_id:
            return
        try:
            with self.engine.begin() as connection:
                connection.execute(text("""
                    INSERT INTO ai_telemetry
                    (id, timestamp, request_id, organization_id, facility_id, agent, task_category, provider, model, is_local, latency_ms, tool_call_count, retrieval_count, estimated_input_tokens, estimated_output_tokens, estimated_cloud_cost_usd, fallback_used, fallback_reason, validation_result, success)
                    VALUES (:id,:timestamp,:request_id,:org,:facility,:agent,:task,:provider,:model,:local,:latency,:tools,:retrieval,:input,:output,:cost,:fallback,:reason,:validation,:success)
                """), {
                    "id": str(uuid.uuid4()), "timestamp": datetime.now(timezone.utc), "request_id": str(request_id)[:64],
                    "org": organization_id, "facility": facility_id, "agent": str(agent)[:64], "task": str(task_category)[:120],
                    "provider": str(provider)[:64], "model": str(model)[:160], "local": bool(local),
                    "latency": max(0, int(latency_ms)), "tools": max(0, int(tool_call_count)), "retrieval": max(0, int(retrieval_count)),
                    "input": max(0, int(input_tokens)), "output": max(0, int(output_tokens)), "cost": max(0.0, float(estimated_cost_usd)),
                    "fallback": bool(fallback_used), "reason": str(fallback_reason)[:500], "validation": str(validation_result)[:120], "success": bool(success),
                })
        except Exception:
            return

    def summary(self, organization_id: str | None = None, facility_id: str | None = None, *, limit_days: int = 30) -> dict[str, Any]:
        since = datetime.now(timezone.utc).timestamp() - max(1, int(limit_days)) * 86400
        where = ["timestamp >= :since"]
        params: dict[str, Any] = {"since": datetime.fromtimestamp(since, tz=timezone.utc)}
        if organization_id:
            where.append("organization_id = :org")
            params["org"] = organization_id
        if facility_id:
            where.append("facility_id = :facility")
            params["facility"] = facility_id
        clause = " AND ".join(where)
        try:
            with self.engine.connect() as connection:
                totals = dict(connection.execute(text(f"""
                    SELECT COUNT(*) AS requests,
                           SUM(CASE WHEN is_local THEN 1 ELSE 0 END) AS local_requests,
                           SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END) AS fallback_requests,
                           SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) AS failures,
                           COALESCE(SUM(estimated_cloud_cost_usd),0) AS cloud_cost_usd,
                           COALESCE(AVG(latency_ms),0) AS avg_latency_ms,
                           COALESCE(SUM(tool_call_count),0) AS tool_calls
                    FROM ai_telemetry WHERE {clause}
                """), params).mappings().one())
                by_provider = [dict(row) for row in connection.execute(text(f"""
                    SELECT provider, model, COUNT(*) AS requests, COALESCE(SUM(estimated_cloud_cost_usd),0) AS cloud_cost_usd, COALESCE(AVG(latency_ms),0) AS avg_latency_ms
                    FROM ai_telemetry WHERE {clause} GROUP BY provider, model ORDER BY requests DESC
                """), params).mappings()]
                by_agent = [dict(row) for row in connection.execute(text(f"""
                    SELECT agent, COUNT(*) AS requests, COALESCE(SUM(estimated_cloud_cost_usd),0) AS cloud_cost_usd
                    FROM ai_telemetry WHERE {clause} GROUP BY agent ORDER BY requests DESC
                """), params).mappings()]
        except Exception as exc:
            return {"ok": False, "error": exc.__class__.__name__, "requests": 0}
        requests = int(totals.get("requests") or 0)
        totals["local_utilization_pct"] = round(int(totals.get("local_requests") or 0) / requests * 100, 2) if requests else 0.0
        totals["cloud_fallback_pct"] = round(int(totals.get("fallback_requests") or 0) / requests * 100, 2) if requests else 0.0
        return {"ok": True, **totals, "providers": by_provider, "agents": by_agent}
