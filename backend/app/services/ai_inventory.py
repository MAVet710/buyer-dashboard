"""Read-only AI projection of the exact inventory workspace service.

The observation lives for one registry/request, never in a global cache or a
second ledger. Missing evidence is not represented as zero stock. Quantities
retain their original units; sales velocity is deliberately not inferred here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

import pandas as pd
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import Facility, InventoryLot
from services.ai.datasets import DatasetAccessContext, DatasetRegistry, DatasetSpec

from ..auth import RequestContext
from .inventory import InventoryQueryService


MAX_AI_INVENTORY_LOTS = 10000
INVENTORY_COLUMNS = (
    "id", "package_id", "lot_code", "product_id", "sku", "product_name",
    "material_type", "location", "status", "source_name", "on_hand",
    "available", "reserved", "production_reserved", "wholesale_committed",
    "wholesale_reserved", "usable", "unit", "received_at", "expiration_at",
    "attention", "unit_cost", "retail_price", "age_days", "days_to_expiry",
)
EVIDENCE_COLUMNS = (
    "dataset", "state", "row_count", "source", "observed_at", "message",
    "provider_freshness", "quantity_policy",
)
SOURCE = "DoobieLogic inventory ledger and shared availability service"


def inventory_source_version(frame: pd.DataFrame | None, *, scope: tuple[str, str], state: str, observed_day: str) -> str:
    """Stable content version, not just row count or a per-request timestamp.

    Exact dates drive freshness; fractional age values vary every instant and
    are excluded. The UTC day still invalidates time-based aging answers daily.
    """
    payload = ""
    if frame is not None:
        columns = [name for name in INVENTORY_COLUMNS if name not in {"age_days", "days_to_expiry"} and name in frame]
        stable = frame.loc[:, columns]
        if "id" in stable:
            stable = stable.sort_values("id", kind="stable")
        payload = stable.to_json(orient="records", date_format="iso", date_unit="us", double_precision=15)
    header = json.dumps({"scope": scope, "state": state, "day": observed_day}, sort_keys=True)
    return hashlib.sha256((header + "\n" + payload).encode("utf-8")).hexdigest()


class InventoryEvidenceUnavailable(RuntimeError):
    """A safe error for a missing, invalid, or oversized inventory observation."""


class CurrentInventoryObservation:
    def __init__(self, context: RequestContext, engine: Engine):
        self.engine = engine
        self.scope = (context.organization_id, context.facility_id)
        self._attempted = False
        self._frame: pd.DataFrame | None = None
        self._evidence: dict = {}
        self._version = ""

    def _observe(self, access: DatasetAccessContext) -> None:
        # Check every access, including after caching: a registry cannot be
        # reused for a different tenant or facility by passing another context.
        if not all(self.scope) or (access.organization_id, access.facility_id) != self.scope:
            raise InventoryEvidenceUnavailable("Trusted inventory scope does not match this request.")
        if "retail" not in access.capabilities:
            raise InventoryEvidenceUnavailable("Retail inventory access is required.")
        if self._attempted:
            return
        self._attempted = True
        observed_at = datetime.now(timezone.utc)
        self._evidence = {
            "dataset": "inventory", "state": "unavailable", "row_count": None,
            "source": SOURCE, "observed_at": None,
            "message": "Current inventory could not be read. Do not interpret missing evidence as zero stock or substitute an uploaded snapshot.",
            "provider_freshness": "Not verified: a database observation is not a live Metrc sync check.",
            "quantity_policy": "Package-level quantities. Keep on_hand, available and reserved separate. Aggregate only within the same unit.",
        }
        try:
            organization_id, facility_id = self.scope
            with Session(self.engine) as session:
                allowed = session.scalar(select(Facility.id).where(
                    Facility.id == facility_id,
                    Facility.organization_id == organization_id,
                    Facility.retail_enabled.is_(True),
                ))
                if not allowed:
                    self._evidence["message"] = "The selected facility is unavailable or does not permit retail inventory. No stock conclusion can be drawn."
                    return
                # Refuse an oversized read rather than returning a partial
                # dataset that an agent could mistake for the facility total.
                count = session.scalar(select(func.count()).select_from(InventoryLot).where(
                    InventoryLot.organization_id == organization_id,
                    InventoryLot.facility_id == facility_id,
                )) or 0
            if count > MAX_AI_INVENTORY_LOTS:
                self._evidence.update(state="too_large", message="Inventory exceeds the bounded AI read limit. Use the Inventory workspace; no partial total is supplied.")
                return
            response = InventoryQueryService(self.engine).list_packages(
                organization_id, facility_id, operation="retail",
            )
            if len(response.items) > MAX_AI_INVENTORY_LOTS:
                self._evidence.update(state="too_large", message="Inventory changed beyond the bounded AI read limit. No partial total is supplied.")
                return
            rows = [{column: getattr(item, column) for column in INVENTORY_COLUMNS} for item in response.items]
            self._frame = pd.DataFrame(rows, columns=INVENTORY_COLUMNS)
            self._evidence.update(
                state="available" if rows else "empty",
                row_count=len(rows),
                observed_at=observed_at.isoformat(),
                message="Successfully read the current DoobieLogic retail inventory projection. Sales uploads are not required; this does not verify external-provider freshness.",
            )
        except Exception:
            # SQL/connection exceptions can contain DSNs and credentials. Only
            # the fixed safe availability message crosses the AI boundary.
            self._frame = None
        finally:
            self._version = inventory_source_version(
                self._frame, scope=self.scope, state=self._evidence["state"],
                observed_day=observed_at.date().isoformat(),
            )

    def inventory(self, access: DatasetAccessContext) -> pd.DataFrame:
        self._observe(access)
        if self._frame is None:
            raise InventoryEvidenceUnavailable(self._evidence["message"])
        result = self._frame.copy(deep=True)
        result.attrs["source_version"] = self._version
        return result

    def evidence(self, access: DatasetAccessContext) -> pd.DataFrame:
        self._observe(access)
        result = pd.DataFrame([dict(self._evidence)], columns=EVIDENCE_COLUMNS)
        result.attrs["source_version"] = self._version
        return result


def register_current_inventory(registry: DatasetRegistry, context: RequestContext, engine: Engine, agents: tuple[str, ...]) -> None:
    observation = CurrentInventoryObservation(context, engine)
    registry.register(DatasetSpec(
        key="inventory", domain="retail",
        description="Current authorized retail package inventory, identical to the Inventory workspace. Read inventory_evidence first; never substitute uploaded inventory or sum unlike units.",
        loader=observation.inventory, allowed_agents=agents,
        required_capabilities=("retail",), allowed_columns=INVENTORY_COLUMNS,
        freshness="Current local database observation; see inventory_evidence.observed_at. External sync freshness is not verified.", max_tool_rows=50,
    ))
    registry.register(DatasetSpec(
        key="inventory_evidence", domain="retail",
        description="Availability and source of current inventory. Distinguishes a successful empty read from unavailable evidence; row_count is unknown on failure.",
        loader=observation.evidence, allowed_agents=agents,
        required_capabilities=("retail",), allowed_columns=EVIDENCE_COLUMNS,
        freshness="Same request observation as inventory", max_tool_rows=5,
    ))
