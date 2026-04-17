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
