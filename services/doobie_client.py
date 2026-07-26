from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


FALLBACK_RESPONSE: dict[str, Any] = {
    "answer": "Doobie server is unavailable.",
    "explanation": "",
    "recommendations": [],
    "confidence": "low",
    "sources": [],
    "mode": "fallback",
    "risk_flags": [],
    "inefficiencies": [],
}

MODE_ALIASES = {
    "buyer_assistant": "buyer",
    "support": "copilot",
    "main": "copilot",
    "operations": "ops",
}
VALID_MODES = {
    "buyer",
    "inventory",
    "extraction",
    "ops",
    "copilot",
    "compliance",
    "executive",
    "retail_ops",
    "cultivation",
    "kitchen",
    "packaging",
}


@dataclass
class DoobieClient:
    base_url: str
    api_key: str
    timeout_seconds: int = 4

    def __post_init__(self) -> None:
        self.base_url = (self.base_url or "").strip().rstrip("/")
        self.api_key = (self.api_key or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _fallback(self, reason: str | None = None, status_code: int | None = None) -> dict[str, Any]:
        response = dict(FALLBACK_RESPONSE)
        if reason:
            response["error"] = reason
            if reason == "missing_service_key":
                response["answer"] = "Doobie service key is missing. Admin must configure Integrations."
            elif reason == "invalid_license":
                response["answer"] = "Doobie license key is invalid or expired."
            elif reason == "service_key_rejected":
                response["answer"] = "Doobie service is reachable, but AI endpoint rejected the service key."
            elif reason == "plan_blocked":
                response["answer"] = "Doobie is connected, but this user’s plan does not include AI support."
        if status_code is not None:
            response["status_code"] = int(status_code)
        return response

    def _standardize_response(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return self._fallback("invalid_response")
        out = dict(FALLBACK_RESPONSE)
        out.update({k: v for k, v in payload.items() if v is not None})
        out["recommendations"] = out["recommendations"] if isinstance(out.get("recommendations"), list) else []
        out["sources"] = out["sources"] if isinstance(out.get("sources"), list) else []
        out["risk_flags"] = out["risk_flags"] if isinstance(out.get("risk_flags"), list) else []
        out["inefficiencies"] = out["inefficiencies"] if isinstance(out.get("inefficiencies"), list) else []
        out["mode"] = str(out.get("mode") or "live")
        return out

    @staticmethod
    def _brief_payload(
        data: dict[str, Any],
        *,
        state: str | None,
        question: str | None,
        default_question: str,
    ) -> dict[str, Any]:
        context = dict(data or {})
        embedded_question = context.pop("question", None) or context.pop("prompt", None)
        final_question = str(question or embedded_question or default_question).strip()
        return {"question": final_question, "state": state, "data": context}

    def call_endpoint(self, endpoint: str, payload: dict[str, Any], license_context: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled:
            return self._fallback("disabled")

        path = endpoint if str(endpoint).startswith("/") else f"/{endpoint}"
        try:
            body = dict(payload)
            if license_context:
                body.update({k: v for k, v in license_context.items() if v not in (None, "")})
            resp = requests.post(
                f"{self.base_url}{path}",
                json=body,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            if resp.status_code in {401, 403}:
                return self._fallback("service_key_rejected", status_code=resp.status_code)
            if resp.status_code >= 400:
                return self._fallback("http_error", status_code=resp.status_code)
            return self._standardize_response(resp.json())
        except requests.Timeout:
            return self._fallback("timeout")
        except requests.RequestException:
            return self._fallback("request_error")
        except ValueError:
            return self._fallback("invalid_json")
        except Exception:
            return self._fallback("unexpected_error")

    def buyer_brief(
        self,
        data: dict[str, Any],
        state: str | None = None,
        question: str | None = None,
    ) -> dict[str, Any]:
        return self.call_endpoint(
            "/api/v1/support/buyer_brief",
            self._brief_payload(
                data,
                state=state,
                question=question,
                default_question="What should the buyer prioritize from this dataset?",
            ),
        )

    def inventory_check(
        self,
        data: dict[str, Any],
        state: str | None = None,
        question: str | None = None,
    ) -> dict[str, Any]:
        return self.call_endpoint(
            "/api/v1/support/inventory_check",
            self._brief_payload(
                data,
                state=state,
                question=question,
                default_question="Which inventory risks need immediate attention?",
            ),
        )

    def extraction_brief(
        self,
        data: dict[str, Any],
        state: str | None = None,
        question: str | None = None,
    ) -> dict[str, Any]:
        return self.call_endpoint(
            "/api/v1/support/extraction_brief",
            self._brief_payload(
                data,
                state=state,
                question=question,
                default_question="Which extraction risks and process opportunities matter most?",
            ),
        )

    def ops_brief(
        self,
        data: dict[str, Any],
        state: str | None = None,
        question: str | None = None,
        department: str | None = None,
    ) -> dict[str, Any]:
        payload = self._brief_payload(
            data,
            state=state,
            question=question,
            default_question="Which operational bottlenecks should we address first?",
        )
        if department:
            payload["department"] = department
        return self.call_endpoint(
            "/api/v1/support/ops_brief",
            payload,
        )

    def copilot(
        self,
        question: str,
        data: dict[str, Any],
        persona: str | None = None,
        state: str | None = None,
        department: str | None = None,
    ) -> dict[str, Any]:
        requested_mode = str(persona or "copilot").strip().lower()
        mode = MODE_ALIASES.get(requested_mode, requested_mode)
        if mode not in VALID_MODES:
            mode = "copilot"
        return self.call_endpoint(
            "/api/v1/support/copilot",
            {
                "question": question,
                "mode": mode,
                "persona": mode,
                "state": state,
                "department": department,
                "data": data,
            },
        )

    def support_copilot_health_check(self) -> dict[str, Any]:
        """Run a dedicated readiness check against the support copilot endpoint."""
        if not self.enabled:
            return {
                "ok": False,
                "status": "not_connected",
                "message": "Doobie base URL or API key is missing.",
                "error_code": "missing_config",
            }

        payload = {
            "question": "Respond with: AI health check OK.",
            "persona": "ops",
            "data": {},
        }

        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/support/copilot",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
        except requests.Timeout:
            return {
                "ok": False,
                "status": "failed",
                "message": "Support endpoint timed out.",
                "error_code": "timeout",
            }
        except requests.RequestException:
            return {
                "ok": False,
                "status": "failed",
                "message": "Support endpoint request failed.",
                "error_code": "request_error",
            }

        if resp.status_code == 404:
            return {
                "ok": False,
                "status": "failed",
                "message": "Support endpoint not found.",
                "error_code": "endpoint_missing",
                "http_status": 404,
            }
        if resp.status_code in {401, 403}:
            return {
                "ok": False,
                "status": "failed",
                "message": "Unauthorized for support endpoint.",
                "error_code": "unauthorized",
                "http_status": int(resp.status_code),
            }
        if resp.status_code >= 400:
            return {
                "ok": False,
                "status": "failed",
                "message": f"Support endpoint returned HTTP {resp.status_code}.",
                "error_code": "http_error",
                "http_status": int(resp.status_code),
            }

        try:
            payload_json = resp.json()
        except ValueError:
            return {
                "ok": False,
                "status": "failed",
                "message": "Support endpoint returned invalid JSON.",
                "error_code": "invalid_json",
                "http_status": int(resp.status_code),
            }

        if not isinstance(payload_json, dict):
            return {
                "ok": False,
                "status": "failed",
                "message": "Support endpoint returned an invalid response format.",
                "error_code": "invalid_response",
                "http_status": int(resp.status_code),
            }

        mode = str(payload_json.get("mode") or "").strip().lower()
        answer = str(payload_json.get("answer") or "").strip()
        if mode == "fallback":
            return {
                "ok": False,
                "status": "failed",
                "message": "Support endpoint returned fallback mode.",
                "error_code": "fallback_response_detected",
                "http_status": int(resp.status_code),
            }
        if not answer:
            return {
                "ok": False,
                "status": "failed",
                "message": "Support endpoint returned an empty answer.",
                "error_code": "invalid_response",
                "http_status": int(resp.status_code),
            }

        expected_text = "ai health check ok"
        return {
            "ok": True,
            "status": "ready",
            "message": "Support endpoint is ready.",
            "http_status": int(resp.status_code),
            "health_phrase_present": expected_text in answer.lower(),
            "answer_preview": answer[:160],
        }
