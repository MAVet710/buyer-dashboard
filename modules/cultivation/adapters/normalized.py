"""Explicit, bounded read-only JSON/CSV export adapter. No vendor detection."""
import csv
import io
import json

from .base import AdapterCapabilities, AdapterMalformedResponse


class NormalizedExportAdapter:
    provider = "normalized_export"
    capabilities = AdapterCapabilities(read_only=True)
    required = {"event_id", "source_device_id", "source_channel", "source_metric", "value", "unit", "observed_at"}
    optional = {"quality", "received_at"}

    def __init__(self, *, columns, metric_mappings, rows_key=None, max_bytes=2097152, max_rows=500):
        if not isinstance(columns, dict) or not self.required <= set(columns) or set(columns) - self.required - self.optional:
            raise AdapterMalformedResponse("explicit_columns_required")
        if any(not isinstance(v, str) or not v or len(v) > 100 for v in columns.values()) or len(set(columns.values())) != len(columns):
            raise AdapterMalformedResponse("invalid_columns")
        if rows_key is not None and (not isinstance(rows_key, str) or not rows_key or len(rows_key) > 100):
            raise AdapterMalformedResponse("invalid_rows_key")
        if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in (max_bytes, max_rows)):
            raise AdapterMalformedResponse("invalid_limit")
        if not isinstance(metric_mappings, list) or len(metric_mappings) > 500:
            raise AdapterMalformedResponse("invalid_metric_mappings")
        self._mapping = {}
        for mapping in metric_mappings:
            if not isinstance(mapping, dict) or set(mapping) != {"source_metric", "unit", "source_channel", "metric"}:
                raise AdapterMalformedResponse("explicit_metric_mapping_required")
            if any(not isinstance(v, str) or not v or len(v) > 160 or "://" in v for v in mapping.values()):
                raise AdapterMalformedResponse("invalid_metric_mapping")
            key = tuple(mapping[k] for k in ("source_metric", "unit", "source_channel"))
            if key in self._mapping:
                raise AdapterMalformedResponse("duplicate_metric_mapping")
            self._mapping[key] = mapping["metric"]
        self.columns = dict(columns)
        self.rows_key, self.max_bytes, self.max_rows = rows_key, max_bytes, max_rows

    def parse(self, content, *, format="json"):
        if isinstance(content, bytes):
            if len(content) > self.max_bytes:
                raise AdapterMalformedResponse("export_byte_limit")
            try:
                content = content.decode("utf-8-sig")
            except UnicodeError:
                raise AdapterMalformedResponse("invalid_export_encoding") from None
        if not isinstance(content, str) or len(content.encode("utf-8")) > self.max_bytes:
            raise AdapterMalformedResponse("export_byte_limit")
        try:
            if format == "json":
                payload = json.loads(content)
                rows = payload.get(self.rows_key) if self.rows_key is not None and isinstance(payload, dict) else payload if self.rows_key is None else None
                if not isinstance(rows, list):
                    raise AdapterMalformedResponse("explicit_rows_container_required")
            elif format == "csv":
                reader = csv.DictReader(io.StringIO(content))
                if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                    raise AdapterMalformedResponse("invalid_csv_columns")
                rows = []
                for row in reader:
                    rows.append(row)
                    if len(rows) > self.max_rows:
                        raise AdapterMalformedResponse("export_row_limit")
            else:
                raise AdapterMalformedResponse("unsupported_export_format")
        except (ValueError, csv.Error):
            raise AdapterMalformedResponse("invalid_export_syntax") from None
        if len(rows) > self.max_rows:
            raise AdapterMalformedResponse("export_row_limit")
        readings, hints = [], []
        for row in rows:
            source = row if isinstance(row, dict) else {}
            # Preserve explicitly supplied quality/receipt evidence; only absent
            # optional columns are omitted so defaults cannot upgrade bad samples.
            reading = {field: source.get(column) for field, column in self.columns.items()
                       if field in self.required or column in source}
            reading.setdefault("quality", "valid")
            key = tuple(reading.get(k) for k in ("source_metric", "unit", "source_channel"))
            metric = self._mapping.get(key) if all(isinstance(k, str) for k in key) else None
            readings.append(reading)
            hints.append({"metric": metric} if metric else None)
        return {"readings": readings, "mapping_hints": hints, "truncated": False, "read_only": True, "connected": False}

    def get_connection_health(self):
        return {"provider": self.provider, "mode": "local_export", "export_supported": True, "connected": False, "live_authorized": False, "read_only": True, "capabilities": self.capabilities.public()}
