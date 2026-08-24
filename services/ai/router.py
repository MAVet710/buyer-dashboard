from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .provider import AIProvider, ProviderProtocolError, ProviderTimeout, ProviderUnavailable
from .schemas import AIRequest, AIResponse


@dataclass(frozen=True)
class RouteDecision:
    response: AIResponse
    fallback_used: bool
    fallback_reason: str
    attempts: tuple[str, ...]


class ProviderRouter:
    """Objective local-first provider routing with explicit failure reasons."""

    def __init__(self, providers: dict[str, AIProvider], *, order: list[str], allow_cloud_fallback: bool = True) -> None:
        self.providers = dict(providers)
        self.order = [name.strip().casefold() for name in order if name.strip()]
        self.allow_cloud_fallback = bool(allow_cloud_fallback)

    def health(self) -> dict[str, dict]:
        output: dict[str, dict] = {}
        for name in self.order:
            provider = self.providers.get(name)
            if provider is None:
                continue
            health = provider.health()
            output[name] = {
                "provider": health.provider,
                "configured": health.configured,
                "reachable": health.reachable,
                "model": health.model,
                "local": health.local,
                "supports_tools": health.supports_tools,
                "supports_structured_output": health.supports_structured_output,
                "detail": health.detail,
            }
        return output

    def generate(
        self,
        request: AIRequest,
        *,
        validate: Callable[[AIResponse], tuple[bool, str]] | None = None,
        require_tools: bool = False,
        require_structured: bool = False,
    ) -> RouteDecision:
        attempts: list[str] = []
        first_failure = ""
        for name in self.order:
            provider = self.providers.get(name)
            if provider is None:
                continue
            if not provider.local and not self.allow_cloud_fallback:
                continue
            health = provider.health()
            if not health.configured or not health.reachable:
                reason = f"{name}:unavailable"
                attempts.append(reason)
                first_failure = first_failure or reason
                continue
            # Tool calls are required only for the first reasoning pass. Runtime
            # can pre-execute bounded tools before escalating to a provider that
            # does not support native tool calls.
            if require_tools and not provider.supports_tools():
                reason = f"{name}:unsupported_tools"
                attempts.append(reason)
                first_failure = first_failure or reason
                continue
            if require_structured and not provider.supports_structured_output():
                reason = f"{name}:unsupported_structured_output"
                attempts.append(reason)
                first_failure = first_failure or reason
                continue
            try:
                response = provider.generate(request)
            except ProviderTimeout:
                reason = f"{name}:timeout"
                attempts.append(reason)
                first_failure = first_failure or reason
                continue
            except (ProviderUnavailable, ProviderProtocolError) as exc:
                reason = f"{name}:{exc.__class__.__name__}"
                attempts.append(reason)
                first_failure = first_failure or reason
                continue
            except Exception as exc:  # provider boundary must fail closed
                reason = f"{name}:{exc.__class__.__name__}"
                attempts.append(reason)
                first_failure = first_failure or reason
                continue
            if validate is not None:
                valid, reason = validate(response)
                if not valid:
                    failure = f"{name}:validation:{reason or 'failed'}"
                    attempts.append(failure)
                    first_failure = first_failure or failure
                    continue
            attempts.append(f"{name}:ok")
            return RouteDecision(
                response=response,
                fallback_used=len(attempts) > 1,
                fallback_reason=first_failure if len(attempts) > 1 else "",
                attempts=tuple(attempts),
            )
        raise ProviderUnavailable("No configured AI provider could satisfy this request. " + ", ".join(attempts))
