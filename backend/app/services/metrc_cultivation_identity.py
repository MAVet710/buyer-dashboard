from __future__ import annotations

from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from modules.cultivation.models import CultivationRoom
from modules.traceability.object_links import TraceabilityObjectLinkRepository
from services.metrc_client import fetch_metrc_resource


class MetrcCultivationIdentityError(ValueError):
    pass


def _source(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("source")
    return dict(value) if isinstance(value, dict) else {}


def _provider_id(record: dict[str, Any]) -> str:
    source = _source(record)
    return str(record.get("provider_id") or source.get("Id") or source.get("id") or "").strip()


def _provider_name(record: dict[str, Any]) -> str:
    source = _source(record)
    return str(record.get("name") or source.get("Name") or source.get("LocationName") or "").strip()


class MetrcCultivationIdentityService:
    """Establish exact local↔Metrc identities using fresh provider readback.

    No provider mutation occurs here. A link can only be marked verified after the
    selected provider ID is read back under the current trusted facility license
    and environment. Names are stored as labels for operators, never used as the
    identity key.
    """

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.links = TraceabilityObjectLinkRepository(engine)

    @staticmethod
    def _scope(state: str, environment: str, license_number: str) -> tuple[str, str, str]:
        state_code = str(state or "").strip().upper()
        env = str(environment or "").strip().casefold()
        license_value = str(license_number or "").strip()
        if state_code != "MA" or env != "sandbox":
            raise MetrcCultivationIdentityError(
                "Cultivation identity promotion is currently restricted to the verified Massachusetts Metrc sandbox."
            )
        if not license_value:
            raise MetrcCultivationIdentityError("An exact Massachusetts sandbox facility license is required.")
        return state_code, env, license_value

    def link_room(
        self,
        *,
        organization_id: str,
        facility_id: str,
        room_id: str,
        provider_location_id: str,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        state_code, env, license_value = self._scope(state, environment, license_number)
        provider_id = str(provider_location_id or "").strip()
        if not provider_id:
            raise MetrcCultivationIdentityError("Choose an exact Metrc location to link to this cultivation room.")

        with self.sessions() as session:
            room = session.get(CultivationRoom, room_id)
            if not room or room.organization_id != organization_id or room.facility_id != facility_id:
                raise MetrcCultivationIdentityError("Cultivation room was not found in the active facility.")
            local_room = {
                "id": room.id,
                "room_code": room.room_code,
                "display_name": room.display_name,
                "active": bool(room.active),
            }
        if not local_room["active"]:
            raise MetrcCultivationIdentityError("Inactive cultivation rooms cannot be newly linked to Metrc.")

        readback = fetch_metrc_resource(
            state=state_code,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            resource="locations_by_id",
            environment=env,
            license_number=license_value,
            path_parameters={"id": provider_id},
        )
        records = [dict(row) for row in readback.get("records") or [] if isinstance(row, dict)] if isinstance(readback, dict) else []
        if not isinstance(readback, dict) or not readback.get("ok") or len(records) != 1:
            raise MetrcCultivationIdentityError(
                str((readback or {}).get("message") if isinstance(readback, dict) else "")
                or "Fresh exact Metrc location readback failed; the room was not linked."
            )
        record = records[0]
        if _provider_id(record) != provider_id:
            raise MetrcCultivationIdentityError("Metrc returned a different location identity than the one selected.")
        source = _source(record)
        if source.get("IsArchived") is True or source.get("IsActive") is False:
            raise MetrcCultivationIdentityError("The selected Metrc location is inactive and cannot back an active cultivation room.")
        provider_name = _provider_name(record)
        if not provider_name:
            raise MetrcCultivationIdentityError("The selected Metrc location did not return a stable operator label.")

        link = self.links.upsert_verified(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            jurisdiction=state_code,
            environment=env,
            license_number=license_value,
            entity_type="cultivation_room",
            entity_id=room_id,
            provider_resource="locations",
            provider_id=provider_id,
            provider_label=provider_name,
        )
        return {
            "room": local_room,
            "link": self.links.payload(link),
            "readback": {
                "provider_id": provider_id,
                "name": provider_name,
                "last_modified": str(record.get("last_modified") or ""),
            },
            "message": "Cultivation room is linked to the exact freshly verified Metrc location identity.",
        }

    def list_links(
        self,
        *,
        organization_id: str,
        facility_id: str,
        environment: str,
    ) -> dict[str, list[dict[str, Any]]]:
        rows = self.links.list_facility(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            environment=str(environment or "").strip().casefold(),
            limit=5000,
        )
        result: dict[str, list[dict[str, Any]]] = {
            "rooms": [],
            "plant_batches": [],
            "plants": [],
            "harvests": [],
            "packages": [],
        }
        mapping = {
            "cultivation_room": "rooms",
            "cultivation_group": "plant_batches",
            "cultivation_plant": "plants",
            "cultivation_harvest": "harvests",
            "inventory_lot": "packages",
        }
        for row in rows:
            bucket = mapping.get(row.entity_type)
            if bucket:
                result[bucket].append(self.links.payload(row))
        return result
