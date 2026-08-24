from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import pandas as pd

from .sanitization import sanitize_frame


@dataclass(frozen=True)
class DatasetAccessContext:
    organization_id: str
    facility_id: str
    user_id: str
    role: str
    capabilities: frozenset[str]
    operation_type: str = "retail"
    engine: Any = None


DatasetLoader = Callable[[DatasetAccessContext], pd.DataFrame]


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    domain: str
    description: str
    loader: DatasetLoader
    allowed_agents: tuple[str, ...]
    scopes: tuple[str, ...] = ("organization", "facility")
    allowed_roles: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    allowed_columns: tuple[str, ...] = ()
    sensitive_columns: tuple[str, ...] = ()
    allow_business_columns: bool = False
    freshness: str = "live repository"
    max_tool_rows: int = 50


@dataclass
class LoadedDataset:
    spec: DatasetSpec
    frame: pd.DataFrame
    freshness: str


class DatasetRegistry:
    """Tenant-safe registry. Models never supply organization/facility arguments."""

    def __init__(self) -> None:
        self._specs: dict[str, DatasetSpec] = {}

    def register(self, spec: DatasetSpec) -> None:
        key = str(spec.key).strip().casefold()
        if not key:
            raise ValueError("Dataset key is required.")
        if key in self._specs:
            raise ValueError(f"Dataset '{key}' is already registered.")
        if "organization" not in spec.scopes:
            raise ValueError(f"Dataset '{key}' must be organization scoped.")
        if not spec.allowed_columns and not spec.allow_business_columns:
            raise ValueError(f"Dataset '{key}' requires an explicit field allowlist or bounded business-column policy.")
        self._specs[key] = spec

    def specs_for_agent(self, agent_key: str, context: DatasetAccessContext) -> list[DatasetSpec]:
        if not context.organization_id or not context.facility_id:
            raise ValueError("Trusted organization and facility scope are required for AI datasets.")
        agent = str(agent_key or "").casefold()
        role = str(context.role or "").casefold()
        output: list[DatasetSpec] = []
        for spec in self._specs.values():
            if agent not in spec.allowed_agents:
                continue
            if spec.allowed_roles and role not in {value.casefold() for value in spec.allowed_roles}:
                continue
            if spec.required_capabilities and not set(spec.required_capabilities) & set(context.capabilities):
                continue
            output.append(spec)
        return output

    def load_for_agent(self, agent_key: str, context: DatasetAccessContext) -> dict[str, LoadedDataset]:
        output: dict[str, LoadedDataset] = {}
        for spec in self.specs_for_agent(agent_key, context):
            try:
                raw = spec.loader(context)
            except Exception:
                continue
            if raw is None:
                continue
            if not isinstance(raw, pd.DataFrame):
                raw = pd.DataFrame(raw)
            safe = sanitize_frame(
                raw,
                explicit_columns=spec.allowed_columns,
                allow_business_columns=spec.allow_business_columns,
                sensitive_columns=spec.sensitive_columns,
            )
            if safe.empty and len(raw) > 0 and len(safe.columns) == 0:
                continue
            output[spec.key] = LoadedDataset(spec, safe, spec.freshness)
        return output

    def describe(self, agent_key: str, context: DatasetAccessContext) -> list[dict[str, Any]]:
        return [
            {
                "key": spec.key,
                "domain": spec.domain,
                "description": spec.description,
                "scopes": list(spec.scopes),
                "freshness": spec.freshness,
                "max_tool_rows": spec.max_tool_rows,
            }
            for spec in self.specs_for_agent(agent_key, context)
        ]

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))


def objects_frame(rows: Iterable[Any]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            records.append(dict(row))
            continue
        table = getattr(row, "__table__", None)
        if table is not None:
            records.append({column.name: getattr(row, column.name, None) for column in table.columns})
            continue
        payload = getattr(row, "__dict__", None)
        if isinstance(payload, dict):
            records.append({key: value for key, value in payload.items() if not key.startswith("_")})
    return pd.DataFrame(records)
