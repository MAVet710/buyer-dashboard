"""Growlink exports only. No reviewed live vendor contract is available."""
from .base import AdapterCapabilities, AdapterUnavailableError
from .normalized import NormalizedExportAdapter


class GrowlinkAdapter:
    provider = "growlink"
    capabilities = AdapterCapabilities(read_only=True)

    def __init__(self, *, configuration=None, secret="", fixture=None):
        config = dict(configuration or {})
        if secret or set(config) - {"columns", "metric_mappings", "format", "rows_key"}:
            raise AdapterUnavailableError("growlink_live_contract_unavailable")
        self._fixture = fixture
        self._format = config.get("format", "json")
        self._adapter = None
        if fixture is not None:
            self._adapter = NormalizedExportAdapter(columns=config.get("columns", {}), metric_mappings=config.get("metric_mappings", []), rows_key=config.get("rows_key"))
        self._validated = False

    @property
    def fixture_mode(self):
        return self._fixture is not None

    def validate_fixture(self):
        if self._adapter is None:
            raise AdapterUnavailableError("growlink_live_contract_unavailable")
        result = self._adapter.parse(self._fixture, format=self._format)
        self._validated = True
        return result

    def get_current_readings(self):
        raise AdapterUnavailableError("growlink_live_contract_unavailable")

    def get_history(self, start, end):
        raise AdapterUnavailableError("growlink_live_contract_unavailable")

    def discover_facilities(self):
        raise AdapterUnavailableError("growlink_discovery_unimplemented")

    def discover_rooms(self):
        raise AdapterUnavailableError("growlink_discovery_unimplemented")

    def discover_devices(self):
        raise AdapterUnavailableError("growlink_discovery_unimplemented")

    def discover_metrics(self):
        raise AdapterUnavailableError("growlink_discovery_unimplemented")

    def get_connection_health(self):
        return {"provider": self.provider, "mode": "fixture" if self.fixture_mode else "disabled", "export_supported": True, "connected": False, "live_authorized": False, "fixture_validated": self._validated, "read_only": True, "capabilities": self.capabilities.public()}
