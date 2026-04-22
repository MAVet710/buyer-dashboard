from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


FALLBACK_RESPONSE: dict[str, Any] = {
    "answer": "Doobie is currently unavailable.",
    "explanation": "",
    "recommendations": [],
    "confidence": "low",
    "sources": [],
    "mode": "fallback",
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
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _fallback(self, reason: str | None = None, status_code: int | None = None) -> dict[str, Any]:
        response = dict(FALLBACK_RESPONSE)
        if reason:
            response["error"] = reason
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
        out["mode"] = str(out.get("mode") or "live")
        return out

    def call_endpoint(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return self._fallback("disabled")

        path = endpoint if str(endpoint).startswith("/") else f"/{endpoint}"
        try:
            resp = requests.post(
                f"{self.base_url}{path}",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
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

    def buyer_brief(self, data: dict[str, Any], state: str | None = None) -> dict[str, Any]:
        return self.call_endpoint(
            "/api/v1/support/buyer-brief",
            {"state": state, "data": data},
        )

    def inventory_check(self, data: dict[str, Any], state: str | None = None) -> dict[str, Any]:
        return self.call_endpoint(
            "/api/v1/support/inventory-check",
            {"state": state, "data": data},
        )

    def extraction_brief(self, data: dict[str, Any], state: str | None = None) -> dict[str, Any]:
        return self.call_endpoint(
            "/api/v1/support/extraction-brief",
            {"state": state, "data": data},
        )

    def ops_brief(self, data: dict[str, Any], state: str | None = None) -> dict[str, Any]:
        return self.call_endpoint(
            "/api/v1/support/ops-brief",
            {"state": state, "data": data},
        )

    def copilot(self, question: str, data: dict[str, Any], persona: str | None = None) -> dict[str, Any]:
        return self.call_endpoint(
            "/api/v1/support/copilot",
            {"question": question, "persona": persona, "data": data},
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
