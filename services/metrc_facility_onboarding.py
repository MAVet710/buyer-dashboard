from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import AuditEvent, Facility, Organization
from modules.integrations import IntegrationConfigurationService
from modules.integrations.models import IntegrationConfiguration
from modules.regulatory.models import RegulatoryFacilityMapping
from modules.regulatory.service import RegulatoryMappingService


class MetrcFacilityOnboardingError(ValueError):
    pass


def _source(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    nested = record.get("source")
    return dict(nested) if isinstance(nested, dict) else dict(record)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _license_number(record: Any) -> str:
    row = _source(record)
    for key in ("LicenseNumber", "licenseNumber", "Number", "number"):
        value = _text(row.get(key))
        if value:
            return value
    license_payload = row.get("License") or row.get("license")
    if isinstance(license_payload, dict):
        for key in ("Number", "number", "LicenseNumber", "licenseNumber"):
            value = _text(license_payload.get(key))
            if value:
                return value
    return ""


def _facility_name(record: Any) -> str:
    row = _source(record)
    for key in ("Name", "DisplayName", "Alias", "name", "displayName"):
        value = _text(row.get(key))
        if value:
            return value
    return _license_number(row)


def _provider_facility_id(record: Any) -> str:
    row = _source(record)
    for key in ("Id", "ID", "id", "FacilityId", "facilityId"):
        value = _text(row.get(key))
        if value:
            return value
    license_payload = row.get("License") or row.get("license")
    if isinstance(license_payload, dict):
        for key in ("Id", "ID", "id"):
            value = _text(license_payload.get(key))
            if value:
                return value
    return ""


def _license_type(record: Any) -> str:
    row = _source(record)
    candidates: list[Any] = [
        row.get("LicenseType"),
        row.get("licenseType"),
        row.get("FacilityType"),
        row.get("facilityType"),
    ]
    license_payload = row.get("License") or row.get("license")
    if isinstance(license_payload, dict):
        candidates.extend((license_payload.get("Type"), license_payload.get("LicenseType")))
    for candidate in candidates:
        if isinstance(candidate, dict):
            for key in ("Name", "name", "DisplayName", "displayName"):
                value = _text(candidate.get(key))
                if value:
                    return value
        else:
            value = _text(candidate)
            if value:
                return value
    return ""


def _normalize(value: Any) -> str:
    return "".join(character for character in _text(value).casefold() if character.isalnum())


def _facility_capabilities(license_type: str, facility_name: str) -> dict[str, bool]:
    """Infer UI workspaces conservatively from provider facility/license labels.

    These flags only shape DoobieLogic navigation. Metrc permissions remain the
    authority for provider operations, so an inferred workspace never bypasses
    provider permission checks.
    """

    text = f"{license_type} {facility_name}".casefold()
    cultivation = any(token in text for token in ("cultivat", "grow", "producer", "nursery"))
    production = any(token in text for token in ("manufact", "process", "product manufacturer", "mip"))
    retail = any(token in text for token in ("retail", "dispens", "store"))
    commercial = True
    if not any((cultivation, production, retail)):
        # Unknown license labels should not silently expose cultivation or
        # manufacturing surfaces. Commercial/receiving remains available while
        # the administrator reviews the imported facility type.
        cultivation = False
        production = False
        retail = False
    return {
        "retail_enabled": retail,
        "production_enabled": production,
        "cultivation_enabled": cultivation,
        "commercial_enabled": commercial,
    }


def _base_code(license_number: str, name: str) -> str:
    preferred = re.sub(r"[^A-Z0-9]+", "-", _text(license_number).upper()).strip("-")
    if preferred:
        return preferred[:64]
    fallback = re.sub(r"[^A-Z0-9]+", "-", _text(name).upper()).strip("-") or "METRC"
    return fallback[:64]


@dataclass(frozen=True)
class DiscoveredMetrcFacility:
    name: str
    license_number: str
    provider_facility_id: str
    license_type: str
    raw: dict[str, Any]

    @classmethod
    def from_record(cls, record: Any) -> "DiscoveredMetrcFacility":
        license_number = _license_number(record)
        if not license_number:
            raise MetrcFacilityOnboardingError("Metrc returned a facility without a license number.")
        return cls(
            name=_facility_name(record) or license_number,
            license_number=license_number,
            provider_facility_id=_provider_facility_id(record),
            license_type=_license_type(record),
            raw=_source(record),
        )

    def public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "license_number": self.license_number,
            "provider_facility_id": self.provider_facility_id,
            "license_type": self.license_type,
        }


class MetrcFacilityOnboardingService:
    """Mirror regulator-owned Metrc facilities into a DoobieLogic organization.

    The provider facility/license is authoritative. DoobieLogic creates a local
    operational mirror only when no plausible existing facility exists. Exact
    license or existing regulatory mappings are safe automatic matches; name-only
    matches require one administrator confirmation to avoid duplicates.
    """

    def __init__(self, engine: Engine, encryption_key: str):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.configurations = IntegrationConfigurationService(engine, encryption_key)
        self.mappings = RegulatoryMappingService(engine)

    def discover(
        self,
        *,
        organization_id: str,
        actor: str,
        state: str,
        environment: str,
        records: Iterable[dict[str, Any]],
        source_user_credential: IntegrationConfiguration,
        source_vendor_credential: IntegrationConfiguration | None = None,
        auto_create: bool = True,
    ) -> dict[str, Any]:
        state = _text(state).upper()
        environment = _text(environment).casefold()
        if environment not in {"sandbox", "production"}:
            raise MetrcFacilityOnboardingError("Metrc environment must be sandbox or production.")
        facilities = [DiscoveredMetrcFacility.from_record(record) for record in records]
        if not facilities:
            return {"facilities": [], "auto_created": 0, "auto_linked": 0, "needs_confirmation": 0}

        with self.sessions() as session:
            organization = session.get(Organization, organization_id)
            if not organization or not organization.active:
                raise MetrcFacilityOnboardingError("The active DoobieLogic organization is unavailable.")
            local_facilities = list(session.scalars(
                select(Facility).where(Facility.organization_id == organization_id, Facility.active.is_(True))
            ))
            existing_mappings = list(session.scalars(
                select(RegulatoryFacilityMapping).where(
                    RegulatoryFacilityMapping.organization_id == organization_id,
                    RegulatoryFacilityMapping.provider == "metrc",
                    RegulatoryFacilityMapping.environment == environment,
                    RegulatoryFacilityMapping.active.is_(True),
                )
            ))

        results: list[dict[str, Any]] = []
        for discovered in facilities:
            mapping = next(
                (row for row in existing_mappings if _normalize(row.license_number) == _normalize(discovered.license_number)),
                None,
            )
            if mapping is not None:
                target = next((row for row in local_facilities if row.id == mapping.facility_id), None)
                if target is not None:
                    self._ensure_credentials_and_mapping(
                        organization_id=organization_id,
                        target_facility=target,
                        discovered=discovered,
                        state=state,
                        environment=environment,
                        actor=actor,
                        source_user_credential=source_user_credential,
                        source_vendor_credential=source_vendor_credential,
                    )
                    results.append(self._result(discovered, target, "linked", "existing_regulatory_mapping", False))
                    continue

            exact_license = [row for row in local_facilities if _normalize(row.license_number) == _normalize(discovered.license_number) and _normalize(row.license_number)]
            if len(exact_license) == 1:
                target = exact_license[0]
                self._ensure_credentials_and_mapping(
                    organization_id=organization_id,
                    target_facility=target,
                    discovered=discovered,
                    state=state,
                    environment=environment,
                    actor=actor,
                    source_user_credential=source_user_credential,
                    source_vendor_credential=source_vendor_credential,
                )
                results.append(self._result(discovered, target, "linked", "exact_license", False))
                continue

            exact_name = [row for row in local_facilities if _normalize(row.name) == _normalize(discovered.name) and _normalize(row.name)]
            if exact_name:
                results.append({
                    **discovered.public(),
                    "status": "needs_confirmation",
                    "match_reason": "exact_name",
                    "suggested_matches": [self._local(row) for row in exact_name],
                    "message": "A DoobieLogic facility with the same name already exists. Confirm the match once or create a separate mirror.",
                })
                continue

            if not auto_create:
                results.append({
                    **discovered.public(),
                    "status": "ready_to_create",
                    "match_reason": "none",
                    "suggested_matches": [],
                })
                continue

            target = self._create_facility(
                organization_id=organization_id,
                discovered=discovered,
                actor=actor,
            )
            local_facilities.append(target)
            self._ensure_credentials_and_mapping(
                organization_id=organization_id,
                target_facility=target,
                discovered=discovered,
                state=state,
                environment=environment,
                actor=actor,
                source_user_credential=source_user_credential,
                source_vendor_credential=source_vendor_credential,
            )
            results.append(self._result(discovered, target, "created", "no_existing_match", True))

        return {
            "facilities": results,
            "auto_created": sum(1 for row in results if row.get("status") == "created"),
            "auto_linked": sum(1 for row in results if row.get("status") == "linked"),
            "needs_confirmation": sum(1 for row in results if row.get("status") == "needs_confirmation"),
        }

    def confirm(
        self,
        *,
        organization_id: str,
        actor: str,
        state: str,
        environment: str,
        record: dict[str, Any],
        source_user_credential: IntegrationConfiguration,
        source_vendor_credential: IntegrationConfiguration | None,
        target_facility_id: str = "",
        create_new: bool = False,
    ) -> dict[str, Any]:
        discovered = DiscoveredMetrcFacility.from_record(record)
        with self.sessions() as session:
            if target_facility_id:
                target = session.get(Facility, target_facility_id)
                if target is None or target.organization_id != organization_id or not target.active:
                    raise MetrcFacilityOnboardingError("The selected DoobieLogic facility is unavailable.")
            elif create_new:
                target = None
            else:
                raise MetrcFacilityOnboardingError("Choose an existing facility or explicitly create a new DoobieLogic mirror.")

        if target is None:
            target = self._create_facility(organization_id=organization_id, discovered=discovered, actor=actor)
            status = "created"
            reason = "administrator_create_new"
        else:
            status = "linked"
            reason = "administrator_confirmed"

        self._ensure_credentials_and_mapping(
            organization_id=organization_id,
            target_facility=target,
            discovered=discovered,
            state=_text(state).upper(),
            environment=_text(environment).casefold(),
            actor=actor,
            source_user_credential=source_user_credential,
            source_vendor_credential=source_vendor_credential,
        )
        return self._result(discovered, target, status, reason, status == "created")

    def _create_facility(self, *, organization_id: str, discovered: DiscoveredMetrcFacility, actor: str) -> Facility:
        capabilities = _facility_capabilities(discovered.license_type, discovered.name)
        with self.sessions.begin() as session:
            code = self._unique_code(session, organization_id, _base_code(discovered.license_number, discovered.name))
            row = Facility(
                organization_id=organization_id,
                name=discovered.name,
                code=code,
                timezone_name="America/New_York",
                license_number=discovered.license_number,
                license_type=discovered.license_type,
                active=True,
                **capabilities,
            )
            session.add(row)
            session.flush()
            session.add(AuditEvent(
                organization_id=organization_id,
                facility_id=row.id,
                entity_type="facility",
                entity_id=row.id,
                action="created_from_metrc_discovery",
                actor=actor,
                changes_json=json.dumps({
                    "provider": "metrc",
                    "provider_facility_id": discovered.provider_facility_id,
                    "license_number": discovered.license_number,
                    "name": discovered.name,
                    "license_type": discovered.license_type,
                }, sort_keys=True),
            ))
        return row

    def _ensure_credentials_and_mapping(
        self,
        *,
        organization_id: str,
        target_facility: Facility,
        discovered: DiscoveredMetrcFacility,
        state: str,
        environment: str,
        actor: str,
        source_user_credential: IntegrationConfiguration,
        source_vendor_credential: IntegrationConfiguration | None,
    ) -> None:
        user_secret = self.configurations.secret(source_user_credential)
        if not user_secret:
            raise MetrcFacilityOnboardingError("The Metrc user API key is not available for facility discovery.")
        target_credential = self.configurations.save(
            scope_type="user",
            scope_key=f"{actor}|{target_facility.id}",
            provider="metrc",
            organization_id=organization_id,
            facility_id=target_facility.id,
            configuration={
                "state": state,
                "license_number": discovered.license_number,
                "environment": environment,
            },
            secret=user_secret,
            actor=actor,
        )
        # A Metrc user key can legitimately span several facilities. We keep the
        # encrypted facility copy today because the operational resolver is
        # facility-isolated; the operator never has to re-enter it.
        if environment == "sandbox" and source_vendor_credential is not None:
            vendor_secret = self.configurations.secret(source_vendor_credential)
            vendor_config = self.configurations.public(source_vendor_credential).get("configuration") or {}
            vendor_config = dict(vendor_config) if isinstance(vendor_config, dict) else {}
            vendor_config.update({
                "state": state,
                "license_number": discovered.license_number,
                "environment": "sandbox",
            })
            self.configurations.save(
                scope_type="facility",
                scope_key=f"{organization_id}:{target_facility.id}:sandbox",
                provider="metrc_sandbox",
                organization_id=organization_id,
                facility_id=target_facility.id,
                configuration=vendor_config,
                secret=vendor_secret,
                actor=actor,
            )

        mapping = self.mappings.verify(
            organization_id=organization_id,
            facility_id=target_facility.id,
            provider="metrc",
            jurisdiction_code=state,
            license_number=discovered.license_number,
            provider_facility_id=discovered.provider_facility_id,
            environment=environment,
            integration_configuration_id=target_credential.id,
            actor=actor,
        )
        with self.sessions.begin() as session:
            local = session.get(Facility, target_facility.id)
            if local is not None:
                local.license_number = discovered.license_number
                if discovered.license_type:
                    local.license_type = discovered.license_type
            session.add(AuditEvent(
                organization_id=organization_id,
                facility_id=target_facility.id,
                entity_type="regulatory_facility_mapping",
                entity_id=mapping.id,
                action="metrc_facility_discovered_and_bound",
                actor=actor,
                changes_json=json.dumps({
                    "provider": "metrc",
                    "jurisdiction_code": state,
                    "license_number": discovered.license_number,
                    "provider_facility_id": discovered.provider_facility_id,
                    "environment": environment,
                    "credential_copied_automatically": True,
                }, sort_keys=True),
            ))

    @staticmethod
    def _unique_code(session: Session, organization_id: str, base: str) -> str:
        candidate = base[:64] or "METRC"
        index = 2
        while session.scalar(select(Facility.id).where(Facility.organization_id == organization_id, Facility.code == candidate)):
            suffix = f"-{index}"
            candidate = f"{base[:64-len(suffix)]}{suffix}"
            index += 1
        return candidate

    @staticmethod
    def _local(row: Facility) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "code": row.code,
            "license_number": row.license_number,
            "license_type": row.license_type,
        }

    @classmethod
    def _result(
        cls,
        discovered: DiscoveredMetrcFacility,
        target: Facility,
        status: str,
        reason: str,
        created: bool,
    ) -> dict[str, Any]:
        return {
            **discovered.public(),
            "status": status,
            "match_reason": reason,
            "created": created,
            "doobielogic_facility": cls._local(target),
            "mapping_permanent": True,
            "next": "bootstrap_metrc_resources",
        }
