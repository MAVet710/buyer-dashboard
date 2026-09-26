from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Protocol


class AdapterError(RuntimeError):
    code = "adapter_error"


class AdapterAuthenticationError(AdapterError):
    code = "authentication_failure"


class AdapterRateLimitError(AdapterError):
    code = "rate_limited"


class AdapterUnavailableError(AdapterError):
    code = "device_unavailable"


class AdapterMalformedResponse(AdapterError):
    code = "malformed_response"


@dataclass(frozen=True)
class AdapterCapabilities:
    history_supported: bool = False
    live_supported: bool = False
    device_discovery_supported: bool = False
    local_connection: bool = False
    cloud_connection: bool = False
    read_only: bool = True

    def public(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DiscoveredFacility:
    source_id: str
    name: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DiscoveredRoom:
    source_id: str
    name: str
    facility_source_id: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DiscoveredMetric:
    source_metric: str
    source_unit: str
    canonical_metric: str | None
    canonical_unit: str | None


@dataclass(frozen=True)
class DiscoveredDevice:
    source_device_id: str
    name: str
    model: str = ""
    serial_identifier: str = ""
    source_room_id: str = ""
    connection_type: str = ""
    metrics: tuple[DiscoveredMetric, ...] = ()
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterReading:
    event_id: str
    source_device_id: str
    source_channel: str
    source_metric: str
    value: float
    unit: str
    observed_at: datetime
    quality: str = "valid"
    raw_reference: str = ""


class CultivationAdapter(Protocol):
    provider: str
    capabilities: AdapterCapabilities

    def discover_facilities(self) -> list[DiscoveredFacility]: ...
    def discover_rooms(self) -> list[DiscoveredRoom]: ...
    def discover_devices(self) -> list[DiscoveredDevice]: ...
    def discover_metrics(self) -> list[DiscoveredMetric]: ...
    def get_current_readings(self) -> list[AdapterReading]: ...
    def get_history(self, start: datetime, end: datetime) -> list[AdapterReading]: ...
    def get_connection_health(self) -> dict: ...
