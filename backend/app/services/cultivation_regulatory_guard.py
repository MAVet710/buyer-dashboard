from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.traceability.models import TraceabilityTransaction
from modules.traceability.object_links import TraceabilityObjectLink


UNRESOLVED_METRC_STATUSES = {
    "requested",
    "validated",
    "queued",
    "submitted",
    "accepted",
    "reconciliation_required",
}


class CultivationRegulatoryGuard:
    """Fail closed when a state-system object cannot safely change locally only."""

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @staticmethod
    def _ids(entity_ids: Iterable[str]) -> set[str]:
        return {str(value or "").strip() for value in entity_ids if str(value or "").strip()}

    def verified_metrc_ids(
        self,
        *,
        organization_id: str,
        facility_id: str,
        entity_type: str,
        entity_ids: Iterable[str],
    ) -> set[str]:
        ids = self._ids(entity_ids)
        if not ids:
            return set()
        with self.sessions() as session:
            return set(
                session.scalars(
                    select(TraceabilityObjectLink.entity_id).where(
                        TraceabilityObjectLink.organization_id == organization_id,
                        TraceabilityObjectLink.facility_id == facility_id,
                        TraceabilityObjectLink.provider == "metrc",
                        TraceabilityObjectLink.entity_type == str(entity_type or "").strip().casefold(),
                        TraceabilityObjectLink.entity_id.in_(ids),
                        TraceabilityObjectLink.status.in_({"verified", "reconciliation_required", "stale"}),
                    )
                )
            )

    def unresolved_metrc_ids(
        self,
        *,
        organization_id: str,
        facility_id: str,
        entity_type: str,
        entity_ids: Iterable[str],
    ) -> set[str]:
        ids = self._ids(entity_ids)
        if not ids:
            return set()
        with self.sessions() as session:
            return set(
                session.scalars(
                    select(TraceabilityTransaction.entity_id).where(
                        TraceabilityTransaction.organization_id == organization_id,
                        TraceabilityTransaction.facility_id == facility_id,
                        TraceabilityTransaction.provider == "metrc",
                        TraceabilityTransaction.entity_type == str(entity_type or "").strip().casefold(),
                        TraceabilityTransaction.entity_id.in_(ids),
                        TraceabilityTransaction.status.in_(UNRESOLVED_METRC_STATUSES),
                    )
                )
            )

    def require_local_only_allowed(
        self,
        *,
        organization_id: str,
        facility_id: str,
        entity_type: str,
        entity_ids: Iterable[str],
        action_label: str,
    ) -> None:
        ids = self._ids(entity_ids)
        tracked = self.verified_metrc_ids(
            organization_id=organization_id,
            facility_id=facility_id,
            entity_type=entity_type,
            entity_ids=ids,
        )
        unresolved = self.unresolved_metrc_ids(
            organization_id=organization_id,
            facility_id=facility_id,
            entity_type=entity_type,
            entity_ids=ids,
        )
        blocked = tracked | unresolved
        if blocked:
            noun = "object" if len(blocked) == 1 else "objects"
            if unresolved:
                reason = "has an in-flight or reconciliation-required Metrc transaction"
            else:
                reason = "already has a state-system identity that is verified or requires reconciliation"
            raise ValueError(
                f"{len(blocked)} selected cultivation {noun} {reason}. "
                f"{action_label} cannot be applied as a DoobieLogic-only change; use or reconcile the controlled Metrc workflow before changing local state."
            )
