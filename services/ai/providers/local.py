from __future__ import annotations

import json
import time
from typing import Any

import requests

from ..provider import ProviderProtocolError, ProviderTimeout, ProviderUnavailable
from ..schemas import AIRequest, AIResponse, ProviderHealth, ToolCall


class LocalOpenAIProvider:
    """OpenAI-compatible self-hosted provider for Ollama, vLLM, and similar servers."""

    name = "local"
    local = True
    max_health_timeout_seconds = 20.0

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        access_client_id: str = "",
        access_client_secret: str = "",
        timeout_seconds: float = 30.0,
        max_tokens: int = 1400,
        temperature: float = 0.2,
    ) -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.model = str(model or "").strip()
        self.api_key = str(api_key or "").strip()
        self.access_client_id = str(access_client_id or "").strip()
        self.access_client_secret = str(access_client_secret or "").strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_tokens = max(1, int(max_tokens))
        self.temperature = max(0.0, min(2.0, float(temperature)))

    def _endpoint(self, path: str) -> str:
        base = self.base_url
        if not base:
            return ""
        if base.endswith("/v1"):
            return f"{base}/{path.lstrip('/')}"
        return f"{base}/v1/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.access_client_id and self.access_client_secret:
            headers["CF-Access-Client-Id"] = self.access_client_id
            headers["CF-Access-Client-Secret"] = self.access_client_secret
        return headers

    def supports_tools(self) -> bool:
        return True

    def supports_structured_output(self) -> bool:
        return True

    @staticmethod
    def _model_aliases(value: str) -> set[str]:
        normalized = str(value or "").strip().casefold()
        if not normalized:
            return set()
        aliases = {normalized}
        if normalized.endswith(":latest"):
            aliases.add(normalized.removesuffix(":latest"))
        elif ":" not in normalized:
            aliases.add(f"{normalized}:latest")
        return aliases

    def _configured_model_is_listed(self, body: Any) -> tuple[bool, list[str]]:
        if not isinstance(body, dict):
            return True, []
        values = body.get("data")
        if not isinstance(values, list):
            return True, []
        available = [
            str(item.get("id") or "").strip()
            for item in values
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]
        if not available:
            # Some OpenAI-compatible gateways intentionally return an empty model
            # catalog. Reachability is still useful in that case, so generation is
            # allowed to make the final capability check.
            return True, []
        configured_aliases = self._model_aliases(self.model)
        listed_aliases: set[str] = set()
        for value in available:
            listed_aliases.update(self._model_aliases(value))
        return bool(configured_aliases & listed_aliases), available

    def health(self) -> ProviderHealth:
        if not self.base_url or not self.model:
            return ProviderHealth(self.name, False, False, self.model, True, True, True, "endpoint/model not configured")
        try:
            response = requests.get(
                self._endpoint("models"),
                headers=self._headers(),
                timeout=min(self.timeout_seconds, self.max_health_timeout_seconds),
            )
            if not response.ok:
                return ProviderHealth(self.name, True, False, self.model, True, True, True, f"HTTP {response.status_code}")
            try:
                model_available, available = self._configured_model_is_listed(response.json())
            except ValueError:
                model_available, available = True, []
            if not model_available:
                preview = ", ".join(available[:5])
                suffix = f"; available: {preview}" if preview else ""
                return ProviderHealth(
                    self.name,
                    True,
                    False,
                    self.model,
                    True,
                    True,
                    True,
                    f"configured model not found{suffix}",
                )
            return ProviderHealth(self.name, True, True, self.model, True, True, True, "ok")
        except requests.RequestException as exc:
            return ProviderHealth(self.name, True, False, self.model, True, True, True, exc.__class__.__name__)

    @staticmethod
    def _tool_calls(message: dict[str, Any]) -> list[ToolCall]:
        output: list[ToolCall] = []
        for item in message.get("tool_calls") or []:
            function = item.get("function") if isinstance(item, dict) else None
            if not isinstance(function, dict):
                continue
            raw = function.get("arguments") or "{}"
            try:
                arguments = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                arguments = {}
            output.append(ToolCall(str(item.get("id") or "tool"), str(function.get("name") or ""), arguments))
        return output

    @staticmethod
    def _http_error_detail(response: requests.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return ""
        if not isinstance(body, dict):
            return ""
        raw = body.get("error") or body.get("message") or ""
        if isinstance(raw, dict):
            raw = raw.get("message") or raw.get("type") or ""
        detail = " ".join(str(raw or "").split())
        return detail[:200]

    @staticmethod
    def _structured_response_format(schema: dict[str, Any]) -> dict[str, Any]:
        """Build the OpenAI-compatible JSON-schema request shape supported by Ollama."""
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "doobielogic_agent_response",
                "schema": schema,
                "strict": True,
            },
        }

    @staticmethod
    def _structured_system_prompt(system_prompt: str, schema: dict[str, Any]) -> str:
        """Reinforce the schema contract for local models without weakening validation."""
        compact_schema = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        return (
            f"{system_prompt}\n\n"
            "Return only valid JSON matching the supplied response schema. "
            "The top-level `answer` field is required and must contain the user-facing answer. "
            "Do not wrap the JSON in Markdown fences or add prose outside the JSON object. "
            f"Response schema: {compact_schema}"
        )

    def generate(self, request: AIRequest) -> AIResponse:
        if not self.base_url or not self.model:
            raise ProviderUnavailable("Local AI endpoint/model is not configured.")
        structured_request = bool(request.response_schema and not request.tools)
        system_prompt = (
            self._structured_system_prompt(request.system_prompt, request.response_schema)
            if structured_request and request.response_schema is not None
            else request.system_prompt
        )
        messages = [{"role": "system", "content": system_prompt}, *request.messages]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature if request.temperature is not None else self.temperature,
            "max_tokens": min(int(request.max_tokens or self.max_tokens), self.max_tokens),
        }
        if self.model.casefold().startswith("gpt-oss"):
            payload["reasoning_effort"] = "low"
        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = "auto"
        if structured_request and request.response_schema is not None:
            payload["response_format"] = self._structured_response_format(request.response_schema)
        started = time.perf_counter()
        try:
            response = requests.post(
                self._endpoint("chat/completions"),
                headers=self._headers(),
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise ProviderTimeout("Local AI request timed out.") from exc
        except requests.RequestException as exc:
            raise ProviderUnavailable(f"Local AI request failed: {exc.__class__.__name__}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            detail = self._http_error_detail(response)
            suffix = f": {detail}" if detail else "."
            raise ProviderUnavailable(f"Local AI returned HTTP {response.status_code}{suffix}")
        try:
            body = response.json()
            choice = (body.get("choices") or [])[0]
            message = choice.get("message") or {}
        except (ValueError, IndexError, TypeError) as exc:
            raise ProviderProtocolError("Local AI returned malformed JSON.") from exc
        text = str(message.get("content") or "").strip()
        usage = body.get("usage") or {}
        structured = None
        if request.response_schema and text:
            try:
                value = json.loads(text)
                structured = value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                structured = None
        return AIResponse(
            text=text,
            provider=self.name,
            model=self.model,
            local=True,
            latency_ms=latency_ms,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            tool_calls=self._tool_calls(message),
            structured=structured,
            finish_reason=str(choice.get("finish_reason") or ""),
        )
