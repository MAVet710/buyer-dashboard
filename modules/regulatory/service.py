from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import AuditEvent, Facility
from modules.integrations.models import IntegrationConfiguration
from .models import RegulatoryFacilityMapping
from .registry import get_jurisdiction


class RegulatoryMappingError(ValueError):
    pass


class RegulatoryMappingService:
    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def get(self, *, organization_id: str, facility_id: str, provider: str, license_number: str, environment: str) -> RegulatoryFacilityMapping | None:
        with self.sessions() as session:
            return session.scalar(select(RegulatoryFacilityMapping).where(
                RegulatoryFacilityMapping.organization_id == organization_id,
                RegulatoryFacilityMapping.facility_id == facility_id,
                RegulatoryFacilityMapping.provider == provider.casefold(),
                RegulatoryFacilityMapping.license_number == license_number.strip(),
                RegulatoryFacilityMapping.environment == environment.casefold(),
                RegulatoryFacilityMapping.active.is_(True),
            ))

    def list_for_facility(self, organization_id: str, facility_id: str) -> list[RegulatoryFacilityMapping]:
        with self.sessions() as session:
            return list(session.scalars(select(RegulatoryFacilityMapping).where(
                RegulatoryFacilityMapping.organization_id == organization_id,
                RegulatoryFacilityMapping.facility_id == facility_id,
            ).order_by(RegulatoryFacilityMapping.provider, RegulatoryFacilityMapping.license_number)))

    def verify(self, *, organization_id: str, facility_id: str, provider: str, jurisdiction_code: str,
               license_number: str, provider_facility_id: str, environment: str,
               integration_configuration_id: str | None, actor: str) -> RegulatoryFacilityMapping:
        provider = provider.strip().casefold()
        environment = environment.strip().casefold()
        license_number = license_number.strip()
        if provider not in {"metrc", "biotrack"}:
            raise RegulatoryMappingError("Unsupported regulatory provider.")
        if environment not in {"sandbox", "production"}:
            raise RegulatoryMappingError("Regulatory environment must be sandbox or production.")
        if not license_number:
            raise RegulatoryMappingError("A regulatory license number is required.")
        profile = get_jurisdiction(jurisdiction_code, provider=provider)
        if provider == "metrc" and profile is None:
            raise RegulatoryMappingError("The Metrc jurisdiction is not verified in the active registry.")
        normalized_jurisdiction = profile.code if profile else jurisdiction_code.strip().upper()
        if not normalized_jurisdiction:
            raise RegulatoryMappingError("A trusted jurisdiction is required.")

        with self.sessions.begin() as session:
            facility = session.get(Facility, facility_id)
            if facility is None or facility.organization_id != organization_id:
                raise RegulatoryMappingError("The facility does not belong to the active organization.")
            credential = None
            if integration_configuration_id:
                credential = session.get(IntegrationConfiguration, integration_configuration_id)
                if credential is None or credential.organization_id != organization_id or credential.facility_id != facility_id or credential.provider != provider:
                    raise RegulatoryMappingError("The credential does not match the active organization, facility, and provider.")
                try:
                    credential_configuration = json.loads(credential.configuration_json or "{}")
                except json.JSONDecodeError as exc:
                    raise RegulatoryMappingError("The credential configuration is unreadable.") from exc
                credential_license = str(credential_configuration.get("license_number") or "").strip()
                credential_environment = str(credential_configuration.get("environment") or "production").strip().casefold()
                credential_jurisdiction = str(
                    credential_configuration.get("state")
                    or credential_configuration.get("jurisdiction_code")
                    or ""
                ).strip().upper()
                if credential_license != license_number or credential_environment != environment or credential_jurisdiction != normalized_jurisdiction:
                    raise RegulatoryMappingError("The credential configuration does not match the requested license, jurisdiction, and environment.")
            row = session.scalar(select(RegulatoryFacilityMapping).where(
                RegulatoryFacilityMapping.organization_id == organization_id,
                RegulatoryFacilityMapping.facility_id == facility_id,
                RegulatoryFacilityMapping.provider == provider,
                RegulatoryFacilityMapping.license_number == license_number,
                RegulatoryFacilityMapping.environment == environment,
            ))
            if row is None:
                row = RegulatoryFacilityMapping(
                    organization_id=organization_id, facility_id=facility_id, provider=provider,
                    license_number=license_number, environment=environment,
                )
                session.add(row)
            row.jurisdiction_code = normalized_jurisdiction
            row.provider_facility_id = provider_facility_id.strip()
            row.integration_configuration_id = credential.id if credential else None
            row.active = True
            row.verified_at = datetime.now(timezone.utc)
            row.verified_by = actor
            session.flush()
            session.add(AuditEvent(
                organization_id=organization_id, facility_id=facility_id,
                entity_type="regulatory_facility_mapping", entity_id=row.id,
                action="mapping_verified", actor=actor,
                changes_json=json.dumps({
                    "provider": provider, "jurisdiction_code": normalized_jurisdiction,
                    "license_number": license_number, "environment": environment,
                    "credential_bound": bool(credential),
                }, sort_keys=True),
            ))
        return row

    @staticmethod
    def public(row: RegulatoryFacilityMapping) -> dict:
        return {
            "id": row.id, "provider": row.provider,
            "jurisdiction_code": row.jurisdiction_code,
            "license_number": row.license_number,
            "provider_facility_id": row.provider_facility_id,
            "environment": row.environment, "active": row.active,
            "credential_configured": bool(row.integration_configuration_id),
            "verified_at": row.verified_at, "verified_by": row.verified_by,
        }
