"""Durable traceability transaction, execution, and reconciliation foundation."""

from .backoffice import TraceabilityBackofficeRepository
from .models import (
    TraceabilityStatusEvent,
    TraceabilityTransaction,
    TraceabilityTransactionAttempt,
)
from .processor import TraceabilityCredentials, process_queued, process_transaction
from .provider_contract import (
    ProviderExecutionResult,
    TraceabilityCapability,
    TraceabilityProviderAdapter,
    TraceabilityProviderRegistry,
    normalize_provider_result,
)
from .repository import TraceabilityRepository, VALID_TRANSITIONS

__all__ = [
    "ProviderExecutionResult",
    "TraceabilityBackofficeRepository",
    "TraceabilityCapability",
    "TraceabilityCredentials",
    "TraceabilityProviderAdapter",
    "TraceabilityProviderRegistry",
    "TraceabilityRepository",
    "TraceabilityStatusEvent",
    "TraceabilityTransaction",
    "TraceabilityTransactionAttempt",
    "VALID_TRANSITIONS",
    "normalize_provider_result",
    "process_queued",
    "process_transaction",
]
