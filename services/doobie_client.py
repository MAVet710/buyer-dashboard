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
    "routed_mode": "fallback",
    "routed_by": "",
    "ai": {},
    "needs_clarification": False,
    "missing_context": [],
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
    "laboratory",
    "quality",
    "security",
    "finance",
    "sales",
    "distribution",
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
        # Development deployments may intentionally run without service auth.
        # Production will still reject unauthenticated calls with a clear 401.
        return bool(self.base_url)

    @property
    def authenticated(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers.update(
                {
                    "x-api-key": self.api_key,
                    "Authorization": f"Bearer {self.api_key}",
                }
            )
        return headers

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
        out["missing_context"] = out["missing_context"] if isinstance(out.get("missing_context"), list) else []
        out["ai"] = out["ai"] if isinstance(out.get("ai"), dict) else {}
        out["mode"] = str(out.get("mode") or "live")
        out["routed_mode"] = str(out.get("routed_mode") or out["mode"])
        out["routed_by"] = str(out.get("routed_by") or "")
        out["needs_clarification"] = bool(out.get("needs_clarification"))
        return out

    def _get_json(self, endpoint: str, *, protected: bool = True) -> dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "error": "disabled", "status_code": None, "data": {}}
        path = endpoint if str(endpoint).startswith("/") else f"/{endpoint}"
        try:
            resp = requests.get(
                f"{self.base_url}{path}",
                headers=self._headers() if protected else {"Accept": "application/json"},
                timeout=self.timeout_seconds,
            )
            if resp.status_code in {401, 403}:
                return {
                    "ok": False,
                    "error": "service_key_rejected" if self.api_key else "missing_service_key",
                    "status_code": int(resp.status_code),
                    "data": {},
                }
            if resp.status_code >= 400:
                return {
                    "ok": False,
                    "error": "http_error",
                    "status_code": int(resp.status_code),
                    "data": {},
                }
            payload = resp.json()
            if not isinstance(payload, dict):
                return {"ok": False, "error": "invalid_response", "status_code": int(resp.status_code), "data": {}}
            return {"ok": True, "error": "", "status_code": int(resp.status_code), "data": payload}
        except requests.Timeout:
            return {"ok": False, "error": "timeout", "status_code": None, "data": {}}
        except requests.RequestException:
            return {"ok": False, "error": "request_error", "status_code": None, "data": {}}
        except (ValueError, TypeError):
            return {"ok": False, "error": "invalid_json", "status_code": None, "data": {}}

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
                reason = "service_key_rejected" if self.api_key else "missing_service_key"
                return self._fallback(reason, status_code=resp.status_code)
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
        # Extraction is intentionally local/data-first. The remote rules endpoint
        # produced generic curriculum text and could recommend measurements that
        # were not present in the current run data.
        from services.extraction_brief import generate_extraction_brief

        return generate_extraction_brief(data, state=state, question=question)

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
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        requested_mode = str(persona or "auto").strip().lower()
        mode = MODE_ALIASES.get(requested_mode, requested_mode)
        if mode not in VALID_MODES | {"auto"}:
            mode = "auto"
        clean_history = [
            {
                "role": str(item.get("role") or "user"),
                "content": str(item.get("content") or "").strip(),
            }
            for item in (history or [])[-20:]
            if isinstance(item, dict) and str(item.get("content") or "").strip()
        ]
        return self.call_endpoint(
            "/api/v1/support/copilot",
            {
                "question": question,
                "mode": mode,
                "persona": mode,
                "state": state,
                "department": department,
                "data": data,
                "history": clean_history,
            },
        )

    def health(self) -> dict[str, Any]:
        """Return the public Doobie API build and provider diagnostics."""

        return self._get_json("/health", protected=False)

    def auth_check(self) -> dict[str, Any]:
        return self._get_json("/api/v1/auth/check")

    def knowledge_modules(self) -> dict[str, Any]:
        return self._get_json("/api/v1/knowledge/modules")

    def professional_domains(self) -> dict[str, Any]:
        return self._get_json("/api/v1/knowledge/professional-domains")

    def compliance_jurisdictions(self) -> dict[str, Any]:
        return self._get_json("/api/v1/compliance/jurisdictions")

    def capability_snapshot(self) -> dict[str, Any]:
        """Discover the updated Doobie API without exposing credentials."""

        health = self.health()
        auth = self.auth_check()
        modules = self.knowledge_modules() if auth.get("ok") else {"ok": False, "data": {}}
        domains = self.professional_domains() if auth.get("ok") else {"ok": False, "data": {}}
        jurisdictions = (
            self.compliance_jurisdictions() if auth.get("ok") else {"ok": False, "data": {}}
        )
        health_data = health.get("data") if isinstance(health.get("data"), dict) else {}
        module_data = modules.get("data") if isinstance(modules.get("data"), dict) else {}
        domain_data = domains.get("data") if isinstance(domains.get("data"), dict) else {}
        jurisdiction_data = (
            jurisdictions.get("data") if isinstance(jurisdictions.get("data"), dict) else {}
        )
        return {
            "ok": bool(health.get("ok") and auth.get("ok")),
            "health": health_data,
            "authenticated": bool(auth.get("ok")),
            "api_version": str((auth.get("data") or {}).get("api_version") or ""),
            "modules": sorted((module_data.get("modules") or {}).keys()),
            "professional_domains": sorted((domain_data.get("domains") or {}).keys()),
            "jurisdiction_count": int(jurisdiction_data.get("count") or 0),
            "ai_provider": str(health_data.get("ai_provider") or ""),
            "ai_model": str(health_data.get("ai_model") or ""),
            "ai_enabled": str(health_data.get("ai_enabled") or "").lower() == "true",
            "conversation_ready": str(health_data.get("conversation_ready") or "").lower() == "true",
            "app_version": str(health_data.get("app_version") or ""),
            "git_commit": str(health_data.get("git_commit_short") or ""),
            "error": str(auth.get("error") or health.get("error") or ""),
        }

    def buyer_intelligence(
        self, question: str, inventory: dict[str, Any], state: str | None = None
    ) -> dict[str, Any]:
        return self.call_endpoint(
            "/buyer/intelligence",
            {"question": str(question or "").strip(), "state": state, "inventory": inventory},
        )

    def extraction_intelligence(
        self, question: str, run_data: dict[str, Any], state: str | None = None
    ) -> dict[str, Any]:
        return self.call_endpoint(
            "/extraction/intelligence",
            {"question": str(question or "").strip(), "state": state, "run_data": run_data},
        )

    def learning_feedback(
        self,
        *,
        mode: str,
        question: str,
        outcome: str,
        state: str | None = None,
        recommendation: str | None = None,
    ) -> dict[str, Any]:
        return self.call_endpoint(
            "/learning/feedback",
            {
                "mode": str(mode or "copilot"),
                "question": str(question or ""),
                "state": state,
                "outcome": str(outcome or ""),
                "recommendation": recommendation,
            },
        )

    def learning_summary(self) -> dict[str, Any]:
        return self._get_json("/learning/summary")

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
