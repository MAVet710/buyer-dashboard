"""AI provider abstraction for buyer-dashboard.

Keeps provider-specific wiring out of business logic.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional


@dataclass
class AIResponse:
    text: str
    provider: str
    model: str


class AIProvider:
    provider_name: str = "unknown"

    def is_available(self) -> bool:
        raise NotImplementedError

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 600) -> AIResponse:
        raise NotImplementedError


class OpenAIProvider(AIProvider):
    provider_name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        from openai import OpenAI  # type: ignore

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def is_available(self) -> bool:
        return self._client is not None

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 600) -> AIResponse:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
        )
        text = (resp.choices[0].message.content or "").strip()
        return AIResponse(text=text, provider=self.provider_name, model=self._model)


class OllamaProvider(AIProvider):
    provider_name = "ollama"

    def __init__(self, model: str = "llama3.1") -> None:
        import requests

        self._requests = requests
        self._endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434/api/generate")
        self._model = model

    def is_available(self) -> bool:
        return bool(self._endpoint and self._model)

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 600) -> AIResponse:
        payload = {
            "model": self._model,
            "prompt": f"System:\n{system_prompt}\n\nUser:\n{user_prompt}",
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        r = self._requests.post(self._endpoint, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        text = str(data.get("response", "")).strip()
        return AIResponse(text=text, provider=self.provider_name, model=self._model)


def build_provider(preferred: Optional[str], openai_api_key: Optional[str]) -> Optional[AIProvider]:
    """Build the first available provider in preference order.

    Preferred values: "openai", "ollama", or None for auto.
    """
    candidates = [preferred] if preferred else ["openai", "ollama"]

    for candidate in candidates:
        try:
            if candidate == "openai" and openai_api_key:
                provider = OpenAIProvider(api_key=openai_api_key)
                if provider.is_available():
                    return provider
            if candidate == "ollama":
                provider = OllamaProvider(model=os.environ.get("OLLAMA_MODEL", "llama3.1"))
                if provider.is_available():
                    return provider
        except Exception:
            continue

    return None
