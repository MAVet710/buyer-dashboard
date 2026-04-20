"""Doobie-only AI provider abstraction for buyer-dashboard.

Legacy provider names are retained only as inert compatibility values.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional

from services.doobie_client import DoobieClient


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


class DoobieProvider(AIProvider):
    provider_name = "doobielogic"

    def __init__(self) -> None:
        self._client = DoobieClient(
            base_url=os.environ.get("DOOBIE_BASE_URL") or os.environ.get("DOOBIELOGIC_URL", ""),
            api_key=os.environ.get("DOOBIE_API_KEY") or os.environ.get("DOOBIELOGIC_API_KEY", ""),
        )

    def is_available(self) -> bool:
        return self._client.enabled

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 600) -> AIResponse:
        result = self._client.copilot(
            question=str(user_prompt or "").strip(),
            data={"system_prompt": str(system_prompt or "").strip(), "max_tokens": int(max_tokens)},
            persona="main",
        )
        if str(result.get("mode", "")).lower() == "fallback":
            raise RuntimeError("Doobie AI is currently unavailable.")
        text = str(result.get("answer") or "").strip() or "Doobie AI is currently unavailable."
        return AIResponse(text=text, provider=self.provider_name, model="doobie-copilot")


def build_provider(preferred: Optional[str], openai_api_key: Optional[str]) -> Optional[AIProvider]:
    """Build the app AI provider.

    `preferred` and `openai_api_key` are accepted for backward compatibility only.
    """
    _ = preferred
    _ = openai_api_key
    provider = DoobieProvider()
    if provider.is_available():
        return provider
    return None
