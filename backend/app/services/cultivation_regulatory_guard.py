from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.traceability.object_links import TraceabilityObjectLink


class CultivationRegulatoryGuard:
    """Fail closed when a verified state-system object would be changed locally only."""

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def verified_metrc_ids(
        self,
        *,
        organization_id: str,
        facility_id: str,
        entity_type: str,
        entity_ids: Iterable[str],
    ) -> set[str]:
        ids = {str(value or "").strip() for value in entity_ids if str(value or "").strip()}
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
                        TraceabilityObjectLink.status == "verified",
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
        tracked = self.verified_metrc_ids(
            organization_id=organization_id,
            facility_id=facility_id,
            entity_type=entity_type,
            entity_ids=entity_ids,
        )
        if tracked:
            noun = "object" if len(tracked) == 1 else "objects"
            raise ValueError(
                f"{len(tracked)} selected cultivation {noun} already has a verified Metrc identity. "
                f"{action_label} cannot be applied as a DoobieLogic-only change; use the controlled Metrc workflow so provider readback is verified before local state changes."
            )
