from __future__ import annotations

from dataclasses import dataclass
import json

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import AuditEvent, Facility
from modules.regulatory.models import RegulatoryFacilityMapping
from .models import AlphaOperatingMode


ALPHA_OPERATING_MODES = ("doobielogic_sandbox", "metrc_sandbox")


@dataclass(frozen=True)
class AlphaOperatingModeState:
    selected_mode: str
    effective_mode: str
    explicit: bool
    source: str
    metrc_sandbox_mapping_available: bool
    production_writes_enabled: bool = False

    @property
    def metrc_enabled(self) -> bool:
        return self.effective_mode == "metrc_sandbox"

    def public(self) -> dict:
        return {
            "selected_mode": self.selected_mode,
            "effective_mode": self.effective_mode,
            "explicit": self.explicit,
            "source": self.source,
            "metrc_sandbox_mapping_available": self.metrc_sandbox_mapping_available,
            "production_writes_enabled": False,
            "choices": [
                {
                    "id": "doobielogic_sandbox",
                    "label": "DoobieLogic Sandbox",
                    "description": "Use the self-contained alpha workflow. No Metrc credentials or provider writes are required.",
                },
                {
                    "id": "metrc_sandbox",
                    "label": "Metrc Sandbox",
                    "description": "Use the connected Massachusetts Metrc sandbox. Provider writes remain governed and sandbox-only.",
                },
            ],
            "message": (
                "DoobieLogic Sandbox is active. Saved Metrc credentials remain encrypted but provider dispatch is disabled."
                if self.effective_mode == "doobielogic_sandbox"
                else "Metrc Sandbox is active. Provider operations still require a trusted facility mapping and valid sandbox credentials."
            ),
        }


class AlphaOperatingModeService:
    """Resolve and persist the facility-wide alpha operating mode."""

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @staticmethod
    def _mapping(session: Session, organization_id: str, facility_id: str) -> RegulatoryFacilityMapping | None:
        return session.scalar(
            select(RegulatoryFacilityMapping)
            .where(
                RegulatoryFacilityMapping.organization_id == organization_id,
                RegulatoryFacilityMapping.facility_id == facility_id,
                RegulatoryFacilityMapping.provider == "metrc",
                RegulatoryFacilityMapping.environment == "sandbox",
                RegulatoryFacilityMapping.active.is_(True),
                RegulatoryFacilityMapping.verified_at.is_not(None),
            )
            .order_by(RegulatoryFacilityMapping.verified_at.desc())
            .limit(1)
        )

    @staticmethod
    def _facility(session: Session, organization_id: str, facility_id: str) -> Facility:
        facility = session.scalar(
            select(Facility).where(
                Facility.id == facility_id,
                Facility.organization_id == organization_id,
                Facility.active.is_(True),
            )
        )
        if facility is None:
            raise ValueError("The active DoobieLogic facility is unavailable.")
        return facility

    def current(self, organization_id: str, facility_id: str) -> AlphaOperatingModeState:
        with self.sessions() as session:
            self._facility(session, organization_id, facility_id)
            row = session.scalar(
                select(AlphaOperatingMode).where(
                    AlphaOperatingMode.organization_id == organization_id,
                    AlphaOperatingMode.facility_id == facility_id,
                )
            )
            mapping = self._mapping(session, organization_id, facility_id)
            if row is not None:
                return AlphaOperatingModeState(
                    selected_mode=row.mode,
                    effective_mode=row.mode,
                    explicit=True,
                    source="explicit",
                    metrc_sandbox_mapping_available=bool(mapping),
                )
            effective = "metrc_sandbox" if mapping else "doobielogic_sandbox"
            return AlphaOperatingModeState(
                selected_mode=effective,
                effective_mode=effective,
                explicit=False,
                source="existing_metrc_mapping" if mapping else "default_local_alpha",
                metrc_sandbox_mapping_available=bool(mapping),
            )

    def set_mode(
        self,
        organization_id: str,
        facility_id: str,
        *,
        mode: str,
        actor: str,
    ) -> AlphaOperatingModeState:
        normalized = str(mode or "").strip().casefold()
        if normalized not in ALPHA_OPERATING_MODES:
            raise ValueError("Alpha operating mode must be DoobieLogic Sandbox or Metrc Sandbox.")

        with self.sessions.begin() as session:
            self._facility(session, organization_id, facility_id)
            row = session.scalar(
                select(AlphaOperatingMode)
                .where(
                    AlphaOperatingMode.organization_id == organization_id,
                    AlphaOperatingMode.facility_id == facility_id,
                )
                .with_for_update()
            )
            before = row.mode if row is not None else "automatic"
            if row is None:
                row = AlphaOperatingMode(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    mode=normalized,
                    updated_by=actor,
                )
                session.add(row)
                session.flush()
            else:
                row.mode = normalized
                row.updated_by = actor
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="alpha_operating_mode",
                    entity_id=row.id,
                    action="operating_mode_changed",
                    actor=actor,
                    changes_json=json.dumps(
                        {
                            "before": before,
                            "after": normalized,
                            "production_writes_enabled": False,
                        },
                        sort_keys=True,
                    ),
                )
            )

        return self.current(organization_id, facility_id)