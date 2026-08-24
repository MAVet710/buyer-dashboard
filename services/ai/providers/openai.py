from __future__ import annotations

from ..schemas import AIRequest, AIResponse, ProviderHealth
from .local import LocalOpenAIProvider


class OpenAIProvider(LocalOpenAIProvider):
    name = "openai"
    local = False

    def __init__(self, *, api_key: str, model: str, base_url: str = "https://api.openai.com", timeout_seconds: float = 30.0) -> None:
        super().__init__(base_url=base_url, model=model, api_key=api_key, timeout_seconds=timeout_seconds)

    def health(self) -> ProviderHealth:
        if not self.api_key or not self.model:
            return ProviderHealth(self.name, False, False, self.model, False, True, True, "API key/model not configured")
        health = super().health()
        return ProviderHealth(self.name, health.configured, health.reachable, self.model, False, True, True, health.detail)

    def generate(self, request: AIRequest) -> AIResponse:
        response = super().generate(request)
        response.provider = self.name
        response.local = False
        # Pricing changes independently of application code. Cost is populated by
        # telemetry only when configured rates are supplied by deployment settings.
        return response
