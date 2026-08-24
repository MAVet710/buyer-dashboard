"""Provider-neutral DoobieLogic AI runtime.

The package owns agent routing, read-only tools, tenant-scoped datasets,
retrieval, telemetry, and evaluation independently of any model vendor.
"""

from .provider import AIProvider
from .runtime import AgentRuntime
from .schemas import AIRequest, AIResponse, AgentResult, ProviderHealth

__all__ = ["AIProvider", "AgentRuntime", "AIRequest", "AIResponse", "AgentResult", "ProviderHealth"]
