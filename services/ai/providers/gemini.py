from __future__ import annotations

import json
import time

from ..provider import ProviderProtocolError, ProviderUnavailable
from ..schemas import AIRequest, AIResponse, ProviderHealth

try:
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover - optional dependency at import time
    genai = None
    types = None


class GeminiProvider:
    name = "gemini"
    local = False

    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip()

    def supports_tools(self) -> bool:
        # AgentRuntime pre-executes deterministic read-only tools for fallback
        # providers, keeping Gemini SDK objects out of the runtime contract.
        return False

    def supports_structured_output(self) -> bool:
        return True

    def health(self) -> ProviderHealth:
        configured = bool(self.api_key and self.model and genai is not None and types is not None)
        return ProviderHealth(self.name, configured, configured, self.model, False, False, True, "configured" if configured else "not configured")

    def generate(self, request: AIRequest) -> AIResponse:
        if not self.health().configured:
            raise ProviderUnavailable("Gemini is not configured.")
        transcript = "\n\n".join(f"{item.get('role', 'user')}: {item.get('content', '')}" for item in request.messages)
        prompt = f"{request.system_prompt}\n\n{transcript}".strip()
        config_kwargs = {
            "temperature": request.temperature,
            "max_output_tokens": request.max_tokens,
        }
        if request.response_schema:
            config_kwargs["response_mime_type"] = "application/json"
        started = time.perf_counter()
        try:
            response = genai.Client(api_key=self.api_key).models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except Exception as exc:
            raise ProviderUnavailable(f"Gemini request failed: {exc.__class__.__name__}") from exc
        text = str(getattr(response, "text", "") or "").strip()
        structured = None
        if request.response_schema and text:
            try:
                parsed = json.loads(text)
                structured = parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                structured = None
        if not text:
            raise ProviderProtocolError("Gemini returned an empty response.")
        usage = getattr(response, "usage_metadata", None)
        return AIResponse(
            text=text,
            provider=self.name,
            model=self.model,
            local=False,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
            output_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
            structured=structured,
        )
