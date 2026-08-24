from __future__ import annotations

import time

from services.doobie_client import DoobieClient

from ..provider import ProviderUnavailable
from ..schemas import AIRequest, AIResponse, ProviderHealth


class DoobieProvider:
    name = "doobie"
    local = False

    def __init__(self, *, base_url: str, api_key: str, model: str = "doobie-cloud", timeout_seconds: int = 20) -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "doobie-cloud")
        self.client = DoobieClient(self.base_url, self.api_key, timeout_seconds=timeout_seconds)

    def supports_tools(self) -> bool:
        return False

    def supports_structured_output(self) -> bool:
        return False

    def health(self) -> ProviderHealth:
        configured = bool(self.base_url and self.api_key)
        if not configured:
            return ProviderHealth(self.name, False, False, self.model, False, False, False, "not configured")
        result = self.client.health()
        return ProviderHealth(self.name, True, bool(result.get("ok")), self.model, False, False, False, str(result.get("error") or "ok"))

    def generate(self, request: AIRequest) -> AIResponse:
        if not self.base_url or not self.api_key:
            raise ProviderUnavailable("Doobie cloud is not configured.")
        started = time.perf_counter()
        question = next((item.get("content", "") for item in reversed(request.messages) if item.get("role") == "user"), "")
        context = request.metadata.get("sanitized_context") if isinstance(request.metadata.get("sanitized_context"), dict) else {}
        result = self.client.copilot(
            question=f"{request.system_prompt}\n\nUser request: {question}",
            data=context,
            persona=str(request.metadata.get("agent_key") or "ops"),
            state=str(request.metadata.get("state") or "MA"),
            department=str(request.metadata.get("agent_key") or "ops"),
            history=request.messages[:-1],
        )
        error = str(result.get("error") or "")
        answer = str(result.get("answer") or "").strip()
        if error in {"missing_service_key", "service_key_rejected", "disabled", "timeout", "request_error", "http_error"} or not answer:
            raise ProviderUnavailable(f"Doobie cloud failed: {error or 'empty_response'}")
        return AIResponse(
            text=answer,
            provider=self.name,
            model=self.model,
            local=False,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
