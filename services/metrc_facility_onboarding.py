from __future__ import annotations

from difflib import SequenceMatcher
import json
import re
from dataclasses import dataclass
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


def _normalize(value: Any) -> str:
    return "".join(character for character in _text(value).casefold() if character.isalnum())


def _name_words(value: Any) -> set[str]:
    stop = {"facility", "marijuana", "cannabis", "license", "licensed", "the", "inc", "llc", "corp", "corporation"}
    return {
        word
        for word in re.findall(r"[a-z0-9]+", _text(value).casefold())
        if len(word) > 2 and word not in stop
    }


def _name_score(left: str, right: str) -> float:
    a = _normalize(left)
    b = _normalize(right)
    if not a or not b:
        return 0.0
    sequence = SequenceMatcher(None, a, b).ratio()
    left_words = _name_words(left)
    right_words = _name_words(right)
    overlap = len(left_words & right_words) / max(1, len(left_words | right_words))
    return max(sequence, overlap)


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
    candidates: list[Any] = [row.get("LicenseType"), row.get("licenseType"), row.get("FacilityType"), row.get("facilityType")]
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


def _facility_capabilities(license_type: str, facility_name: str) -> dict[str, bool]:
    text = f"{license_type} {facility_name}".casefold()
    cultivation = any(token in text for token in ("cultivat", "grow", "producer", "nursery"))
    production = any(token in text for token in ("manufact", "process", "product manufacturer", "mip"))
    retail = any(token in text for token in ("retail", "dispens", "store"))
    # Navigation hints never grant Metrc permission; provider permissions remain authoritative.
    return {
        "retail_enabled": retail,
        "production_enabled": production,
        "cultivation_enabled": cultivation,
        "commercial_enabled": True,
    }


def _base_code(license_number: str, name: str) -> str:
    preferred = re.sub(r"[^A-Z0-9]+", "-", _text(license_number).upper()).strip("-")
    fallback = re.sub(r"[^A-Z0-9]+", "-", _text(name).upper()).strip("-")
    return (preferred or fallback or "METRC")[:64]


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
    """Treat Metrc facilities as regulator-owned and mirror them into DoobieLogic."""

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
        discovered_rows = [DiscoveredMetrcFacility.from_record(record) for record in records]
        with self.sessions() as session:
            organization = session.get(Organization, organization_id)
            if not organization or not organization.active:
                raise MetrcFacilityOnboardingError("The active DoobieLogic organization is unavailable.")
            local_facilities = list(session.scalars(select(Facility).where(
                Facility.organization_id == organization_id,
                Facility.active.is_(True),
            )))
            existing_mappings = list(session.scalars(select(RegulatoryFacilityMapping).where(
                RegulatoryFacilityMapping.organization_id == organization_id,
                RegulatoryFacilityMapping.provider == "metrc",
                RegulatoryFacilityMapping.environment == environment,
                RegulatoryFacilityMapping.active.is_(True),
            )))

        mapped_local_ids = {row.facility_id for row in existing_mappings}
        results: list[dict[str, Any]] = []
        for discovered in discovered_rows:
            mapping = next((row for row in existing_mappings if _normalize(row.license_number) == _normalize(discovered.license_number)), None)
            if mapping is not None:
                target = next((row for row in local_facilities if row.id == mapping.facility_id), None)
                if target is not None:
                    self._bind(
                        organization_id=organization_id,
                        target=target,
                        discovered=discovered,
                        state=state,
                        environment=environment,
                        actor=actor,
                        source_user_credential=source_user_credential,
                        source_vendor_credential=source_vendor_credential,
                    )
                    results.append(self._result(discovered, target, "linked", "existing_regulatory_mapping"))
                    continue

            exact_license = [
                row for row in local_facilities
                if _normalize(row.license_number)
                and _normalize(row.license_number) == _normalize(discovered.license_number)
            ]
            if len(exact_license) == 1:
                target = exact_license[0]
                self._bind(
                    organization_id=organization_id,
                    target=target,
                    discovered=discovered,
                    state=state,
                    environment=environment,
                    actor=actor,
                    source_user_credential=source_user_credential,
                    source_vendor_credential=source_vendor_credential,
                )
                results.append(self._result(discovered, target, "linked", "exact_license"))
                continue

            # Existing DoobieLogic facilities with no regulatory identity deserve
            # one explicit match decision instead of an automatic duplicate.
            unmapped = [
                row for row in local_facilities
                if row.id not in mapped_local_ids and not _normalize(row.license_number)
            ]
            exact_name = [row for row in unmapped if _normalize(row.name) == _normalize(discovered.name)]
            fuzzy_name = [row for row in unmapped if _name_score(row.name, discovered.name) >= 0.72]
            suggested = exact_name or fuzzy_name
            match_reason = "exact_name" if exact_name else "similar_name" if fuzzy_name else ""
            if not suggested and len(unmapped) == 1 and len(discovered_rows) == 1:
                suggested = unmapped
                match_reason = "single_unmapped_facility"
            if suggested:
                unique = {row.id: row for row in suggested}
                results.append({
                    **discovered.public(),
                    "status": "needs_confirmation",
                    "match_reason": match_reason,
                    "suggested_matches": [self._local(row) for row in unique.values()],
                    "mapping_permanent": False,
                    "message": "We found a possible existing DoobieLogic facility. Confirm the match once or create a separate mirror.",
                })
                continue

            if not auto_create:
                results.append({**discovered.public(), "status": "ready_to_create", "suggested_matches": []})
                continue

            target = self._create_facility(organization_id=organization_id, discovered=discovered, actor=actor)
            local_facilities.append(target)
            mapped_local_ids.add(target.id)
            self._bind(
                organization_id=organization_id,
                target=target,
                discovered=discovered,
                state=state,
                environment=environment,
                actor=actor,
                source_user_credential=source_user_credential,
                source_vendor_credential=source_vendor_credential,
            )
            results.append(self._result(discovered, target, "created", "no_existing_match"))

        return {
            "facilities": results,
            "auto_created": sum(1 for row in results if row.get("status") == "created"),
            "auto_linked": sum(1 for row in results if row.get("status") == "linked"),
            "needs_confirmation": sum(1 for row in results if row.get("status") == "needs_confirmation"),
            "bootstrap_resources": [
                "locations", "sublocations", "location_types", "strains", "items", "item_categories",
                "item_brands", "units_of_measure", "package_tags", "plant_tags", "packages", "plant_batches",
                "plants", "harvests", "facility_permissions",
            ],
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
        target: Facility | None = None
        if target_facility_id:
            with self.sessions() as session:
                target = session.get(Facility, target_facility_id)
                if target is None or target.organization_id != organization_id or not target.active:
                    raise MetrcFacilityOnboardingError("The selected DoobieLogic facility is unavailable.")
        elif not create_new:
            raise MetrcFacilityOnboardingError("Choose an existing facility or explicitly create a new DoobieLogic mirror.")

        if target is None:
            target = self._create_facility(organization_id=organization_id, discovered=discovered, actor=actor)
            status, reason = "created", "administrator_create_new"
        else:
            status, reason = "linked", "administrator_confirmed"
        self._bind(
            organization_id=organization_id,
            target=target,
            discovered=discovered,
            state=_text(state).upper(),
            environment=_text(environment).casefold(),
            actor=actor,
            source_user_credential=source_user_credential,
            source_vendor_credential=source_vendor_credential,
        )
        return self._result(discovered, target, status, reason)

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

    def _bind(
        self,
        *,
        organization_id: str,
        target: Facility,
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
            scope_key=f"{actor}|{target.id}",
            provider="metrc",
            organization_id=organization_id,
            facility_id=target.id,
            configuration={"state": state, "license_number": discovered.license_number, "environment": environment},
            secret=user_secret,
            actor=actor,
        )
        if environment == "sandbox" and source_vendor_credential is not None:
            vendor_secret = self.configurations.secret(source_vendor_credential)
            vendor_public = self.configurations.public(source_vendor_credential)
            vendor_config = dict(vendor_public.get("configuration") or {})
            vendor_config.update({"state": state, "license_number": discovered.license_number, "environment": "sandbox"})
            self.configurations.save(
                scope_type="facility",
                scope_key=f"{organization_id}:{target.id}:sandbox",
                provider="metrc_sandbox",
                organization_id=organization_id,
                facility_id=target.id,
                configuration=vendor_config,
                secret=vendor_secret,
                actor=actor,
            )
        mapping = self.mappings.verify(
            organization_id=organization_id,
            facility_id=target.id,
            provider="metrc",
            jurisdiction_code=state,
            license_number=discovered.license_number,
            provider_facility_id=discovered.provider_facility_id,
            environment=environment,
            integration_configuration_id=target_credential.id,
            actor=actor,
        )
        with self.sessions.begin() as session:
            local = session.get(Facility, target.id)
            if local is not None:
                local.license_number = discovered.license_number
                if discovered.license_type:
                    local.license_type = discovered.license_type
            session.add(AuditEvent(
                organization_id=organization_id,
                facility_id=target.id,
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
    def _result(cls, discovered: DiscoveredMetrcFacility, target: Facility, status: str, reason: str) -> dict[str, Any]:
        return {
            **discovered.public(),
            "status": status,
            "match_reason": reason,
            "doobielogic_facility": cls._local(target),
            "mapping_permanent": True,
            "next": "bootstrap_metrc_resources",
        }
