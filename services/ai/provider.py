from __future__ import annotations

from typing import Protocol, runtime_checkable

from .schemas import AIRequest, AIResponse, ProviderHealth


@runtime_checkable
class AIProvider(Protocol):
    """Stable model-provider contract. Provider SDK types must not cross it."""

    name: str
    model: str
    local: bool

    def health(self) -> ProviderHealth: ...

    def generate(self, request: AIRequest) -> AIResponse: ...

    def supports_tools(self) -> bool: ...

    def supports_structured_output(self) -> bool: ...


class ProviderUnavailable(RuntimeError):
    pass


class ProviderTimeout(RuntimeError):
    pass


class ProviderProtocolError(RuntimeError):
    pass
