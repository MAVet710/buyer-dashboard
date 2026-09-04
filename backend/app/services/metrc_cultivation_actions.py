from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.cultivation.batch_models import CultivationPlantGroup
from modules.cultivation.models import CultivationPlant, CultivationRoom
from modules.cultivation.batches import CultivationBatchService
from modules.cultivation.service import CultivationService
from modules.regulatory.metrc_process_compliance import MetrcProcessComplianceService
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from modules.traceability.object_links import TraceabilityObjectLinkRepository
from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_lifecycle import (
    LIFECYCLE_EVALUATION_ACTIONS,
    MetrcLifecycleEvaluationError,
    build_lifecycle_evaluation_payload,
    execute_lifecycle_evaluation_action,
)
from .metrc_cultivation_readback import (
    provider_ids_from_response,
    verify_plant_batch_creation,
    verify_plant_location,
    verify_vegetative_plants,
)


PROMOTED_CULTIVATION_ACTIONS = frozenset({"plant_batch_sync", "plant_batch_vegetative", "plant_move"})
_ACTION_TO_EVALUATOR = {
    "plant_batch_sync": "plant_batch_plantings",
    "plant_batch_vegetative": "plant_batch_growthphase",
    "plant_move": "plant_location",
}


class MetrcCultivationActionError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _source(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("source")
    return dict(value) if isinstance(value, dict) else {}


def _first(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source and source[key] is not None:
            value = source[key]
            if isinstance(value, dict):
                for nested in ("Name", "name", "Label", "label"):
                    if nested in value:
                        return value[nested]
            return value
    return None


def _as_int_provider_id(value: Any, label: str) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise MetrcCultivationActionError(f"{label} does not have a numeric Metrc provider ID.") from exc
    if number < 1:
        raise MetrcCultivationActionError(f"{label} does not have a valid Metrc provider ID.")
    return number


def cultivation_confirmation_token(
    *,
    prepared: dict[str, Any],
    state: str,
    environment: str,
    license_number: str,
    confirmation_id: str,
) -> str:
    operation = str(prepared.get("operation_type") or "").strip().casefold()
    if operation not in PROMOTED_CULTIVATION_ACTIONS:
        raise MetrcCultivationActionError("This cultivation action has not passed the current operator promotion gate.")
    evaluator_operation = _ACTION_TO_EVALUATOR[operation]
    spec = LIFECYCLE_EVALUATION_ACTIONS[evaluator_operation]
    document = {
        "confirmation_id": str(confirmation_id or "").strip(),
        "operation_type": operation,
        "evaluator_operation": evaluator_operation,
        "method": spec.method,
        "path": spec.path,
        "state": str(state or "").strip().upper(),
        "environment": str(environment or "").strip().casefold(),
        "license_number": str(license_number or "").strip(),
        "entity_type": prepared.get("entity_type"),
        "entity_id": prepared.get("entity_id"),
        "provider_payload": prepared.get("provider_payload"),
        "fingerprint_context": prepared.get("fingerprint_context"),
    }
    if not document["confirmation_id"]:
        raise MetrcCultivationActionError("A confirmation ID is required.")
    return sha256(_canonical(document).encode("utf-8")).hexdigest()


class MetrcCultivationActionService:
    """Controlled MA sandbox promotion for the first plant-batch/plant workflows."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.traceability = TraceabilityBackofficeRepository(engine)
        self.links = TraceabilityObjectLinkRepository(engine)

    @staticmethod
    def _scope(state: str, environment: str, license_number: str) -> tuple[str, str, str]:
        state_code = str(state or "").strip().upper()
        env = str(environment or "").strip().casefold()
        license_value = str(license_number or "").strip()
        if state_code != "MA" or env != "sandbox":
            raise MetrcCultivationActionError(
                "Promoted cultivation writes are currently restricted to the verified Massachusetts Metrc sandbox."
            )
        if not license_value:
            raise MetrcCultivationActionError("An exact Massachusetts sandbox facility license is required.")
        return state_code, env, license_value

    def _verified_link(
        self,
        *,
        organization_id: str,
        facility_id: str,
        environment: str,
        entity_type: str,
        entity_id: str,
        resource: str,
        license_number: str,
    ):
        link = self.links.get_local(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            environment=environment,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        if not link or link.status != "verified" or link.provider_resource != resource:
            raise MetrcCultivationActionError(
                f"{entity_type.replace('_', ' ').title()} is not linked to a freshly verified Metrc {resource} identity."
            )
        if str(link.license_number or "").strip() != license_number:
            raise MetrcCultivationActionError("Regulatory identity belongs to a different Metrc facility license.")
        return link

    def _room_by_id(self, organization_id: str, facility_id: str, room_id: str) -> CultivationRoom:
        with self.sessions() as session:
            room = session.get(CultivationRoom, room_id)
            if not room or room.organization_id != organization_id or room.facility_id != facility_id or not room.active:
                raise MetrcCultivationActionError("Active destination cultivation room was not found in this facility.")
            return room

    def _room_by_code(self, organization_id: str, facility_id: str, room_code: str) -> CultivationRoom | None:
        code = str(room_code or "").strip()
        if not code or code.casefold() == "unassigned":
            return None
        with self.sessions() as session:
            return session.scalar(
                select(CultivationRoom).where(
                    CultivationRoom.organization_id == organization_id,
                    CultivationRoom.facility_id == facility_id,
                    CultivationRoom.room_code == code,
                    CultivationRoom.active.is_(True),
                )
            )

    def _exact_read(
        self,
        *,
        resource: str,
        provider_id: str,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        result = fetch_metrc_resource(
            state=state,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            resource=resource,
            environment=environment,
            license_number=license_number,
            path_parameters={"id": provider_id},
        )
        records = [dict(row) for row in result.get("records") or [] if isinstance(row, dict)] if isinstance(result, dict) else []
        if not isinstance(result, dict) or not result.get("ok") or len(records) != 1:
            raise MetrcCultivationActionError(
                str((result or {}).get("message") if isinstance(result, dict) else "")
                or f"Fresh exact Metrc {resource} readback failed."
            )
        returned_id = str(records[0].get("provider_id") or _source(records[0]).get("Id") or "").strip()
        if returned_id != str(provider_id).strip():
            raise MetrcCultivationActionError("Fresh provider readback returned a different object identity.")
        return result

    def prepare(
        self,
        *,
        organization_id: str,
        facility_id: str,
        operation_type: str,
        entity_id: str,
        actual_date: str,
        destination_room_id: str = "",
        starting_tag: str = "",
        reason: str = "",
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        state_code, env, license_value = self._scope(state, environment, license_number)
        operation = str(operation_type or "").strip().casefold()
        if operation not in PROMOTED_CULTIVATION_ACTIONS:
            raise MetrcCultivationActionError("This cultivation action has not passed the current operator promotion gate.")
        entity = str(entity_id or "").strip()
        action_date = str(actual_date or "").strip()
        if not entity or not action_date:
            raise MetrcCultivationActionError("The exact cultivation object and action date are required.")

        common = {
            "organization_id": organization_id,
            "facility_id": facility_id,
            "state": state_code,
            "environment": env,
            "license_number": license_value,
            "integrator_api_key": integrator_api_key,
            "user_api_key": user_api_key,
        }
        if operation == "plant_batch_sync":
            return self._prepare_batch_sync(entity, action_date, reason, **common)
        if operation == "plant_batch_vegetative":
            return self._prepare_batch_vegetative(entity, action_date, destination_room_id, starting_tag, reason, **common)
        return self._prepare_plant_move(entity, action_date, destination_room_id, reason, **common)

    def _prepare_batch_sync(
        self,
        group_id: str,
        actual_date: str,
        reason: str,
        *,
        organization_id: str,
        facility_id: str,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        existing = self.links.get_local(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            environment=environment,
            entity_type="cultivation_group",
            entity_id=group_id,
        )
        if existing:
            raise MetrcCultivationActionError("This cultivation group already has a Metrc plant-batch identity; do not create it again.")
        group = CultivationBatchService(self.engine).group_detail(organization_id, facility_id, group_id)
        group_type = str(group.get("group_type") or "").strip().casefold()
        provider_type = {"clone_batch": "Clone", "seed_batch": "Seed"}.get(group_type)
        if provider_type is None:
            raise MetrcCultivationActionError(
                "Automatic Metrc batch creation is currently promoted only for clone and seed batches. Nursery groups remain local until their provider type is explicitly evaluated."
            )
        plants = [dict(row) for row in group.get("plants") or [] if isinstance(row, dict)]
        expected_phase = "clone" if group_type == "clone_batch" else "seedling"
        active = [row for row in plants if str(row.get("phase") or "").casefold() == expected_phase]
        if not plants or len(active) != len(plants):
            raise MetrcCultivationActionError("Initial Metrc plant-batch creation requires the full local group to still be in its original immature phase.")

        provider_location = ""
        room_link_id = ""
        room = self._room_by_code(organization_id, facility_id, str(group.get("room_code") or ""))
        if room is not None:
            room_link = self._verified_link(
                organization_id=organization_id,
                facility_id=facility_id,
                environment=environment,
                entity_type="cultivation_room",
                entity_id=room.id,
                resource="locations",
                license_number=license_number,
            )
            provider_location = str(room_link.provider_label or "").strip()
            room_link_id = room_link.id
            if not provider_location:
                raise MetrcCultivationActionError("Linked cultivation room is missing its verified Metrc location label.")

        payload: dict[str, Any] = {
            "name": str(group.get("group_code") or "").strip(),
            "type": provider_type,
            "count": len(plants),
            "strain": str(group.get("strain_name") or "").strip(),
            "actual_date": actual_date,
        }
        if provider_location:
            payload["location"] = provider_location
        body = build_lifecycle_evaluation_payload("plant_batch_plantings", payload)
        return {
            "operation_type": "plant_batch_sync",
            "evaluator_operation": "plant_batch_plantings",
            "entity_type": "cultivation_group",
            "entity_id": group_id,
            "provider_payload": payload,
            "provider_request_body": body,
            "summary": {
                "title": "Create Metrc plant batch",
                "group": payload["name"],
                "batch_type": provider_type,
                "count": len(plants),
                "strain": payload["strain"],
                "location": provider_location or "No Metrc location",
                "actual_date": actual_date,
            },
            "fingerprint_context": {
                "group_type": group_type,
                "plant_ids": sorted(str(row.get("id") or "") for row in plants),
                "plant_phases": sorted(str(row.get("phase") or "") for row in plants),
                "room_link_id": room_link_id,
                "reason": str(reason or "").strip(),
            },
        }

    def _prepare_batch_vegetative(
        self,
        group_id: str,
        actual_date: str,
        destination_room_id: str,
        starting_tag: str,
        reason: str,
        *,
        organization_id: str,
        facility_id: str,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        group_link = self._verified_link(
            organization_id=organization_id,
            facility_id=facility_id,
            environment=environment,
            entity_type="cultivation_group",
            entity_id=group_id,
            resource="plant_batches",
            license_number=license_number,
        )
        room = self._room_by_id(organization_id, facility_id, destination_room_id)
        room_link = self._verified_link(
            organization_id=organization_id,
            facility_id=facility_id,
            environment=environment,
            entity_type="cultivation_room",
            entity_id=room.id,
            resource="locations",
            license_number=license_number,
        )
        start = str(starting_tag or "").strip()
        if not start:
            raise MetrcCultivationActionError("Choose the exact first available Metrc plant tag before moving a batch to vegetative.")

        group = CultivationBatchService(self.engine).group_detail(organization_id, facility_id, group_id)
        plants = [dict(row) for row in group.get("plants") or [] if isinstance(row, dict)]
        immature = [row for row in plants if str(row.get("phase") or "").casefold() in {"clone", "seedling"}]
        if not immature or len(immature) != len(plants):
            raise MetrcCultivationActionError("Vegetative promotion requires every active group member to still be immature.")

        batch_read = self._exact_read(
            resource="plant_batches_by_id",
            provider_id=group_link.provider_id,
            state=state,
            environment=environment,
            license_number=license_number,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        batch_record = batch_read["records"][0]
        batch_source = _source(batch_record)
        batch_name = str(_first(batch_source, "Name", "PlantBatchName") or "").strip()
        provider_count = _first(batch_source, "UntrackedCount", "Count", "PlantCount")
        provider_strain = str(_first(batch_source, "StrainName", "Strain") or "").strip()
        if not batch_name or provider_count in (None, ""):
            raise MetrcCultivationActionError("Fresh Metrc plant-batch readback is missing the name/count required for safe vegetative conversion.")
        try:
            provider_count_number = int(float(provider_count))
        except (TypeError, ValueError) as exc:
            raise MetrcCultivationActionError("Fresh Metrc plant-batch count is not usable for safe vegetative conversion.") from exc
        if provider_count_number != len(immature):
            raise MetrcCultivationActionError(
                f"Metrc has {provider_count_number} untracked plant(s) in this batch but DoobieLogic has {len(immature)} immature member(s). Reconcile the batch before converting it."
            )
        local_strain = str(group.get("strain_name") or "").strip()
        if not provider_strain or provider_strain.casefold() != local_strain.casefold():
            raise MetrcCultivationActionError("Fresh Metrc plant-batch strain does not match the local cultivation group. Reconcile before converting it.")

        available = MetrcProcessComplianceService(self.engine).list_tags(
            organization_id,
            facility_id,
            environment=environment,
            tag_type="plant",
            status="available",
            limit=5000,
        )
        available_labels = {str(row.get("label") or "").strip() for row in available}
        if start not in available_labels:
            raise MetrcCultivationActionError("The selected starting plant tag is not in the freshly synced available-tag inventory for this sandbox facility.")
        if len(available_labels) < len(immature):
            raise MetrcCultivationActionError("Not enough freshly synced available Metrc plant tags exist for the full batch.")

        payload = {
            "name": batch_name,
            "count": len(immature),
            "starting_tag": start,
            "growth_phase": "Vegetative",
            "new_location": str(room_link.provider_label or "").strip(),
            "growth_date": actual_date,
        }
        if not payload["new_location"]:
            raise MetrcCultivationActionError("Destination room is missing its verified Metrc location label.")
        body = build_lifecycle_evaluation_payload("plant_batch_growthphase", payload)
        return {
            "operation_type": "plant_batch_vegetative",
            "evaluator_operation": "plant_batch_growthphase",
            "entity_type": "cultivation_group",
            "entity_id": group_id,
            "provider_payload": payload,
            "provider_request_body": body,
            "summary": {
                "title": "Move plant batch to vegetative",
                "group": batch_name,
                "count": len(immature),
                "starting_tag": start,
                "destination_room": room.display_name or room.room_code,
                "metrc_location": payload["new_location"],
                "growth_date": actual_date,
            },
            "fingerprint_context": {
                "group_link_id": group_link.id,
                "group_provider_id": group_link.provider_id,
                "room_link_id": room_link.id,
                "room_provider_id": room_link.provider_id,
                "destination_room_id": room.id,
                "destination_room_code": room.room_code,
                "plant_ids": sorted(str(row.get("id") or "") for row in immature),
                "provider_batch_last_modified": str(batch_record.get("last_modified") or ""),
                "reason": str(reason or "").strip(),
            },
        }

    def _prepare_plant_move(
        self,
        plant_id: str,
        actual_date: str,
        destination_room_id: str,
        reason: str,
        *,
        organization_id: str,
        facility_id: str,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        with self.sessions() as session:
            plant = session.get(CultivationPlant, plant_id)
            if not plant or plant.organization_id != organization_id or plant.facility_id != facility_id:
                raise MetrcCultivationActionError("Plant was not found in the active cultivation facility.")
            local = {
                "id": plant.id,
                "plant_tag": plant.plant_tag,
                "strain_name": plant.strain_name,
                "phase": plant.phase,
                "room_code": plant.room_code,
            }
        if local["phase"] not in {"vegetative", "flowering"}:
            raise MetrcCultivationActionError("Only individually tracked vegetative or flowering plants can use the promoted Metrc Move plant action.")
        plant_link = self._verified_link(
            organization_id=organization_id,
            facility_id=facility_id,
            environment=environment,
            entity_type="cultivation_plant",
            entity_id=plant_id,
            resource="plants",
            license_number=license_number,
        )
        room = self._room_by_id(organization_id, facility_id, destination_room_id)
        room_link = self._verified_link(
            organization_id=organization_id,
            facility_id=facility_id,
            environment=environment,
            entity_type="cultivation_room",
            entity_id=room.id,
            resource="locations",
            license_number=license_number,
        )
        plant_read = self._exact_read(
            resource="plants_by_id",
            provider_id=plant_link.provider_id,
            state=state,
            environment=environment,
            license_number=license_number,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        provider_record = plant_read["records"][0]
        provider_source = _source(provider_record)
        provider_label = str(provider_record.get("label") or _first(provider_source, "Label", "PlantLabel", "Tag") or "").strip()
        if not provider_label:
            raise MetrcCultivationActionError("Fresh Metrc plant readback is missing its regulatory plant tag.")
        if plant_link.provider_label and provider_label.casefold() != str(plant_link.provider_label).casefold():
            raise MetrcCultivationActionError("The stored plant identity label no longer matches fresh Metrc readback. Reconcile the plant before moving it.")
        current_provider_location = str(_first(provider_source, "LocationName", "Location") or "").strip()
        destination_provider_location = str(room_link.provider_label or "").strip()
        if not destination_provider_location:
            raise MetrcCultivationActionError("Destination room is missing its verified Metrc location label.")
        if current_provider_location and current_provider_location.casefold() == destination_provider_location.casefold():
            raise MetrcCultivationActionError("Metrc already shows this plant in the selected destination location.")

        payload = {
            "id": _as_int_provider_id(plant_link.provider_id, "Plant"),
            "label": provider_label,
            "location": destination_provider_location,
            "actual_date": actual_date,
        }
        body = build_lifecycle_evaluation_payload("plant_location", payload)
        return {
            "operation_type": "plant_move",
            "evaluator_operation": "plant_location",
            "entity_type": "cultivation_plant",
            "entity_id": plant_id,
            "provider_payload": payload,
            "provider_request_body": body,
            "summary": {
                "title": "Move plant",
                "plant": provider_label,
                "strain": local["strain_name"],
                "from_room": local["room_code"],
                "to_room": room.display_name or room.room_code,
                "metrc_location": destination_provider_location,
                "actual_date": actual_date,
            },
            "fingerprint_context": {
                "plant_link_id": plant_link.id,
                "provider_plant_id": plant_link.provider_id,
                "room_link_id": room_link.id,
                "provider_room_id": room_link.provider_id,
                "destination_room_id": room.id,
                "destination_room_code": room.room_code,
                "local_phase": local["phase"],
                "local_room_code": local["room_code"],
                "provider_current_location": current_provider_location,
                "provider_last_modified": str(provider_record.get("last_modified") or ""),
                "reason": str(reason or "").strip(),
            },
        }

    def execute(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        operation_type: str,
        entity_id: str,
        actual_date: str,
        destination_room_id: str = "",
        starting_tag: str = "",
        reason: str = "",
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
        confirmation_id: str,
        confirmation_token: str,
    ) -> dict[str, Any]:
        state_code, env, license_value = self._scope(state, environment, license_number)
        prepared = self.prepare(
            organization_id=organization_id,
            facility_id=facility_id,
            operation_type=operation_type,
            entity_id=entity_id,
            actual_date=actual_date,
            destination_room_id=destination_room_id,
            starting_tag=starting_tag,
            reason=reason,
            state=state_code,
            environment=env,
            license_number=license_value,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        expected_token = cultivation_confirmation_token(
            prepared=prepared,
            state=state_code,
            environment=env,
            license_number=license_value,
            confirmation_id=confirmation_id,
        )
        if str(confirmation_token or "").strip() != expected_token:
            raise MetrcCultivationActionError(
                "The cultivation or Metrc state changed after preview. Review the current action again before submitting it."
            )

        operation = prepared["operation_type"]
        evaluator_operation = prepared["evaluator_operation"]
        spec = LIFECYCLE_EVALUATION_ACTIONS[evaluator_operation]
        idempotency_key = f"metrc-cultivation:{facility_id}:{confirmation_id}:{expected_token}"
        transaction = self.traceability.create_transaction(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            operation_type=operation,
            entity_type=prepared["entity_type"],
            entity_id=prepared["entity_id"],
            idempotency_key=idempotency_key,
            actor=actor,
            license_number=license_value,
            jurisdiction=state_code,
            environment=env,
            request_payload={
                "provider_request": {
                    "method": spec.method,
                    "path": spec.path,
                    "query": {"licenseNumber": license_value},
                    "body": prepared["provider_request_body"],
                },
                "confirmation_id": confirmation_id,
                "summary": prepared["summary"],
            },
            local_state=prepared["fingerprint_context"],
            reason=str(reason or f"Authorized operator confirmed {prepared['summary']['title'].lower()}.").strip(),
        )
        transaction, claimed = self.traceability.claim_transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            expected_status="requested",
            new_status="validated",
            actor=actor,
            reason="Exact MA sandbox facility/license scope, durable regulatory identities, current local/provider state, and confirmation fingerprint validated.",
            source="system",
        )
        if not claimed:
            return self._existing(transaction, prepared)
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="queued",
            actor=actor,
            reason="Human-confirmed cultivation action queued for immediate controlled execution.",
            source="system",
        )
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="submitted",
            actor=actor,
            reason=f"Beginning authenticated {spec.method} /{spec.path} against the trusted Massachusetts sandbox mapping.",
            source="provider_worker",
        )

        try:
            evidence = execute_lifecycle_evaluation_action(
                operation_type=evaluator_operation,
                payload=prepared["provider_payload"],
                license_number=license_value,
                integrator_api_key=integrator_api_key,
                user_api_key=user_api_key,
                state=state_code,
                environment=env,
            )
        except MetrcLifecycleEvaluationError as exc:
            return self._unknown_provider_outcome(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                transaction=transaction,
                prepared=prepared,
                message=str(exc),
            )

        http_status = int(evidence.get("http_status") or 0)
        self.traceability.record_attempt(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            request_payload=evidence.get("request") if isinstance(evidence.get("request"), dict) else {"operation_type": evaluator_operation},
            response_payload=evidence.get("response") if isinstance(evidence.get("response"), dict) else {"response": evidence.get("response")},
            http_status=http_status or None,
            error_code="" if http_status == 200 else "provider_rejected",
            error_message="" if http_status == 200 else str(evidence.get("message") or "Metrc rejected the cultivation write."),
        )
        if http_status != 200:
            uncertain = http_status == 0 or http_status == 429 or http_status >= 500
            target = "reconciliation_required" if uncertain else "rejected"
            transaction = self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                new_status=target,
                actor=actor,
                reason=str(evidence.get("message") or "Metrc did not accept the cultivation write."),
                source="provider_worker",
                error_code="provider_outcome_unknown" if uncertain else "provider_rejected",
                error_message=str(evidence.get("message") or ""),
            )
            self.traceability.record_reconciliation(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                actor=actor,
                local_state=prepared["fingerprint_context"],
                provider_state={"http_status": http_status, "response": evidence.get("response")},
                readback_result=evidence.get("readback") if isinstance(evidence.get("readback"), dict) else None,
                mismatch_reason=str(evidence.get("message") or "Provider write was not accepted."),
                evidence={"operation_type": operation, "stage": evidence.get("stage"), "blind_retry_allowed": False},
                retry_eligible=False,
            )
            return self._result(transaction, prepared, evidence, str(evidence.get("message") or "Metrc rejected the change."))

        provider_reference = str(evidence.get("provider_id") or "").strip()
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="accepted",
            actor=actor,
            reason="Metrc returned HTTP 200. Operation-specific fresh readback and local reconciliation are still required before verification.",
            source="provider_worker",
            external_reference=provider_reference,
            response_payload=evidence.get("response") if isinstance(evidence.get("response"), dict) else {"response": evidence.get("response")},
        )

        verification = self._verify_provider_state(
            prepared=prepared,
            evidence=evidence,
            state=state_code,
            environment=env,
            license_number=license_value,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        if not verification.get("matched"):
            message = "Metrc accepted the write, but fresh operation-specific readback did not verify the confirmed cultivation state."
            self.traceability.record_reconciliation(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                actor=actor,
                local_state=prepared["fingerprint_context"],
                provider_state={"provider_id": provider_reference, "http_status": http_status},
                readback_result=verification,
                mismatch_reason=message,
                evidence={"operation_type": operation, "provider_verification": verification, "blind_retry_allowed": False},
                retry_eligible=False,
            )
            transaction = self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                new_status="reconciliation_required",
                actor=actor,
                reason=message,
                source="provider_readback",
                external_reference=provider_reference,
                error_code="readback_not_verified",
                error_message=message,
            )
            return self._result(transaction, prepared, evidence, message)

        try:
            local_result = self._apply_local_verified_state(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                prepared=prepared,
                transaction_id=transaction.id,
                verification=verification,
                state=state_code,
                environment=env,
                license_number=license_value,
            )
        except (ValueError, MetrcCultivationActionError) as exc:
            message = f"Metrc state is verified, but DoobieLogic could not complete the local reconciliation: {exc}"
            self.traceability.record_reconciliation(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                actor=actor,
                local_state=prepared["fingerprint_context"],
                provider_state={"provider_verified": True, "provider_reference": provider_reference},
                readback_result=verification,
                mismatch_reason=message,
                evidence={"operation_type": operation, "provider_verified": True, "local_apply_failed": True, "blind_retry_allowed": False},
                retry_eligible=False,
            )
            transaction = self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                new_status="reconciliation_required",
                actor=actor,
                reason="Provider mutation is verified but local state/link reconciliation requires review. Never repeat the provider write blindly.",
                source="system",
                external_reference=provider_reference,
                error_code="local_reconciliation_failed",
                error_message=message,
            )
            return self._result(transaction, prepared, evidence, message)

        self.traceability.record_reconciliation(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            actor=actor,
            local_state=local_result,
            provider_state={"provider_verified": True, "provider_reference": provider_reference},
            readback_result=verification,
            mismatch_reason="",
            evidence={"operation_type": operation, "provider_verified": True, "local_reconciled": True, "blind_retry_allowed": False},
            retry_eligible=False,
        )
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="verified",
            actor=actor,
            reason="Fresh Metrc readback verified the exact cultivation state and DoobieLogic reconciled the corresponding local identity/state successfully.",
            source="provider_readback",
            external_reference=provider_reference,
        )
        return self._result(transaction, prepared, evidence, "Metrc and DoobieLogic are verified and reconciled for this cultivation action.", local_result)

    def _verify_provider_state(
        self,
        *,
        prepared: dict[str, Any],
        evidence: dict[str, Any],
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        operation = prepared["operation_type"]
        if operation == "plant_batch_sync":
            semantic = verify_plant_batch_creation(
                provider_request_body=prepared["provider_request_body"],
                readback=evidence.get("readback"),
                provider_id=str(evidence.get("provider_id") or ""),
            )
            semantic["evaluator_passed"] = bool(evidence.get("passed"))
            semantic["matched"] = bool(evidence.get("passed")) and bool(semantic.get("matched"))
            return semantic
        if operation == "plant_move":
            semantic = verify_plant_location(
                provider_request_body=prepared["provider_request_body"],
                readback=evidence.get("readback"),
                provider_id=str(evidence.get("provider_id") or ""),
            )
            semantic["evaluator_passed"] = bool(evidence.get("passed"))
            semantic["matched"] = bool(evidence.get("passed")) and bool(semantic.get("matched"))
            return semantic

        provider_ids = provider_ids_from_response(evidence.get("response"))
        expected_count = int(prepared["provider_payload"]["count"])
        readbacks: list[dict[str, Any]] = []
        if len(provider_ids) == expected_count:
            for provider_id in provider_ids:
                readbacks.append(
                    fetch_metrc_resource(
                        state=state,
                        user_api_key=user_api_key,
                        integrator_api_key=integrator_api_key,
                        resource="plants_by_id",
                        environment=environment,
                        license_number=license_number,
                        path_parameters={"id": provider_id},
                    )
                )
        verification = verify_vegetative_plants(
            readbacks=readbacks,
            expected_count=expected_count,
            expected_location=str(prepared["provider_payload"]["new_location"]),
            expected_strain=str(prepared["summary"].get("strain") or "") or str(prepared.get("fingerprint_context", {}).get("strain") or ""),
        )
        if len(provider_ids) != expected_count:
            verification["differences"].append({
                "field": "Ids",
                "expected": expected_count,
                "actual": len(provider_ids),
                "reason": "mutation_response_id_count_mismatch",
            })
            verification["matched"] = False
        verification["provider_ids"] = provider_ids
        verification["evaluator_passed"] = bool(evidence.get("passed"))
        # The evaluator verifies the first returned plant; this stricter gate
        # verifies every returned plant and remains fail-closed if either layer fails.
        verification["matched"] = bool(evidence.get("passed")) and bool(verification.get("matched"))
        return verification

    def _apply_local_verified_state(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        prepared: dict[str, Any],
        transaction_id: str,
        verification: dict[str, Any],
        state: str,
        environment: str,
        license_number: str,
    ) -> dict[str, Any]:
        operation = prepared["operation_type"]
        if operation == "plant_batch_sync":
            record = verification.get("record") if isinstance(verification.get("record"), dict) else {}
            provider_id = str(record.get("provider_id") or _source(record).get("Id") or "").strip()
            provider_label = str(record.get("name") or _first(_source(record), "Name", "PlantBatchName") or prepared["summary"]["group"]).strip()
            link = self.links.upsert_verified(
                organization_id=organization_id,
                facility_id=facility_id,
                provider="metrc",
                jurisdiction=state,
                environment=environment,
                license_number=license_number,
                entity_type="cultivation_group",
                entity_id=prepared["entity_id"],
                provider_resource="plant_batches",
                provider_id=provider_id,
                provider_label=provider_label,
                source_transaction_id=transaction_id,
            )
            return {"group_id": prepared["entity_id"], "plant_batch_link": self.links.payload(link)}

        if operation == "plant_move":
            room_id = str(prepared["fingerprint_context"]["destination_room_id"])
            room = self._room_by_id(organization_id, facility_id, room_id)
            with self.sessions() as session:
                plant = session.get(CultivationPlant, prepared["entity_id"])
                if not plant or plant.organization_id != organization_id or plant.facility_id != facility_id:
                    raise MetrcCultivationActionError("Plant disappeared from the active facility before local reconciliation.")
                phase = plant.phase
            updated = CultivationService(self.engine).transition(
                organization_id,
                facility_id,
                prepared["entity_id"],
                phase=phase,
                room_code=room.room_code,
                actor=actor,
                reason=str(prepared["fingerprint_context"].get("reason") or "Verified Metrc plant move"),
                notes=f"Traceability transaction {transaction_id}",
            )
            plant_link = self.links.upsert_verified(
                organization_id=organization_id,
                facility_id=facility_id,
                provider="metrc",
                jurisdiction=state,
                environment=environment,
                license_number=license_number,
                entity_type="cultivation_plant",
                entity_id=prepared["entity_id"],
                provider_resource="plants",
                provider_id=str(prepared["fingerprint_context"]["provider_plant_id"]),
                provider_label=str(prepared["summary"]["plant"]),
                source_transaction_id=transaction_id,
            )
            return {
                "plant_id": updated.id,
                "room_code": updated.room_code,
                "phase": updated.phase,
                "plant_link": self.links.payload(plant_link),
            }

        provider_plants = [dict(row) for row in verification.get("plants") or [] if isinstance(row, dict)]
        labels = [str(row.get("label") or "").strip() for row in provider_plants]
        if len(labels) != len(set(label.casefold() for label in labels)) or any(not label for label in labels):
            raise MetrcCultivationActionError("Verified provider plants do not contain a complete unique tag set.")
        detail = MetrcProcessComplianceService(self.engine).assign_vegetative_tags(
            organization_id,
            facility_id,
            prepared["entity_id"],
            environment=environment,
            actor=actor,
            provider_confirmed=True,
            tag_labels=labels,
            provider_reference=transaction_id,
        )
        local_by_label = {
            str(row.get("metrc_plant_tag") or "").strip().casefold(): str(row.get("id") or "").strip()
            for row in detail.get("plants") or []
            if isinstance(row, dict) and row.get("metrc_plant_tag")
        }
        provider_by_label = {str(row["label"]).casefold(): row for row in provider_plants}
        if set(local_by_label) != set(provider_by_label):
            raise MetrcCultivationActionError("Local vegetative tag assignment does not exactly match the verified provider tag set.")
        links = []
        for normalized_label, local_plant_id in sorted(local_by_label.items()):
            provider = provider_by_label[normalized_label]
            link = self.links.upsert_verified(
                organization_id=organization_id,
                facility_id=facility_id,
                provider="metrc",
                jurisdiction=state,
                environment=environment,
                license_number=license_number,
                entity_type="cultivation_plant",
                entity_id=local_plant_id,
                provider_resource="plants",
                provider_id=str(provider["provider_id"]),
                provider_label=str(provider["label"]),
                source_transaction_id=transaction_id,
            )
            links.append(self.links.payload(link))
        return {
            "group_id": prepared["entity_id"],
            "phase": "vegetative",
            "room_code": prepared["fingerprint_context"]["destination_room_code"],
            "plant_count": len(links),
            "plant_links": links,
        }

    def _unknown_provider_outcome(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        transaction,
        prepared: dict[str, Any],
        message: str,
    ) -> dict[str, Any]:
        self.traceability.record_attempt(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            request_payload={"operation_type": prepared["evaluator_operation"], "payload": prepared["provider_payload"]},
            error_code="provider_outcome_unknown",
            error_message=message,
        )
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="reconciliation_required",
            actor=actor,
            reason="The controlled Metrc call did not produce evidence sufficient to classify the provider outcome. Blind retry is blocked.",
            source="provider_worker",
            error_code="provider_outcome_unknown",
            error_message=message,
        )
        self.traceability.record_reconciliation(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            actor=actor,
            local_state=prepared["fingerprint_context"],
            mismatch_reason=message,
            evidence={"operation_type": prepared["operation_type"], "stage": "execution_exception", "blind_retry_allowed": False},
            retry_eligible=False,
        )
        return self._result(transaction, prepared, None, message)

    @staticmethod
    def _existing(transaction, prepared: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": transaction.status == "verified",
            "verified": transaction.status == "verified",
            "status": transaction.status,
            "transaction_id": transaction.id,
            "external_reference": transaction.external_reference,
            "already_submitted": True,
            "summary": prepared["summary"],
            "message": (
                "This exact confirmation was already verified."
                if transaction.status == "verified"
                else "This exact confirmation already has a durable traceability transaction. Review its current status before any new action."
            ),
        }

    @staticmethod
    def _result(
        transaction,
        prepared: dict[str, Any],
        evidence: dict[str, Any] | None,
        message: str,
        local_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": transaction.status == "verified",
            "verified": transaction.status == "verified",
            "status": transaction.status,
            "transaction_id": transaction.id,
            "external_reference": transaction.external_reference,
            "summary": prepared["summary"],
            "http_status": int((evidence or {}).get("http_status") or 0),
            "stage": str((evidence or {}).get("stage") or ""),
            "local_result": local_result,
            "message": message,
        }
