"""Provider-neutral DoobieLogic AI runtime.

The package owns agent routing, read-only tools, tenant-scoped datasets,
retrieval, learning, telemetry, and evaluation independently of any model vendor.
"""

from .learning import AgentLearningEngine
from .provider import AIProvider
from .runtime import AgentRuntime
from .schemas import AIRequest, AIResponse, AgentResult, ProviderHealth

__all__ = [
    "AIProvider",
    "AgentLearningEngine",
    "AgentRuntime",
    "AIRequest",
    "AIResponse",
    "AgentResult",
    "ProviderHealth",
]
