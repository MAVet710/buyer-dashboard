from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.cultivation.models import CultivationHarvestPlant, CultivationPlant
from modules.operational_moats.models import CultivationHarvest
from modules.regulatory.metrc_guide_v11 import MetrcGuideV11Service
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
from .metrc_cultivation_actions import MetrcCultivationActionError, MetrcCultivationActionService
from .metrc_harvest_readback import (
    harvest_waste_weight,
    verify_harvest_finished,
    verify_harvest_state,
    verify_harvest_waste,
    verify_plant_harvested,
)


PROMOTED_HARVEST_ACTIONS = frozenset({"harvest_start", "harvest_waste", "harvest_finish", "harvest_unfinish"})
_SINGLE_EVALUATORS = {
    "harvest_waste": "harvest_waste",
    "harvest_finish": "harvest_finish",
    "harvest_unfinish": "harvest_unfinish",
}


class MetrcHarvestActionError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _source(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("source")
    return dict(value) if isinstance(value, dict) else {}


def _first(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key not in source or source[key] is None:
            continue
        value = source[key]
        if isinstance(value, dict):
            for nested in ("Name", "name", "Label", "label", "Id", "id"):
                if nested in value and value[nested] is not None:
                    return value[nested]
        return value
    return None


def harvest_confirmation_token(
    *,
    prepared: dict[str, Any],
    state: str,
    environment: str,
    license_number: str,
    confirmation_id: str,
) -> str:
    operation = str(prepared.get("operation_type") or "").strip().casefold()
    if operation not in PROMOTED_HARVEST_ACTIONS:
        raise MetrcHarvestActionError("This harvest action has not passed the current operator promotion gate.")
    document = {
        "confirmation_id": str(confirmation_id or "").strip(),
        "operation_type": operation,
        "state": str(state or "").strip().upper(),
        "environment": str(environment or "").strip().casefold(),
        "license_number": str(license_number or "").strip(),
        "entity_type": prepared.get("entity_type"),
        "entity_id": prepared.get("entity_id"),
        "provider_payload": prepared.get("provider_payload"),
        "provider_payloads": prepared.get("provider_payloads"),
        "fingerprint_context": prepared.get("fingerprint_context"),
    }
    if not document["confirmation_id"]:
        raise MetrcHarvestActionError("A confirmation ID is required.")
    return sha256(_canonical(document).encode("utf-8")).hexdigest()


class MetrcHarvestActionService(MetrcCultivationActionService):
    """Controlled MA sandbox harvest/post-harvest provider checkpoint service."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.traceability = TraceabilityBackofficeRepository(engine)
        self.links = TraceabilityObjectLinkRepository(engine)

    def _scope_harvest(self, state: str, environment: str, license_number: str) -> tuple[str, str, str]:
        try:
            return self._scope(state, environment, license_number)
        except MetrcCultivationActionError as exc:
            raise MetrcHarvestActionError(str(exc)) from exc

    def _verified_harvest_link(
        self,
        *,
        organization_id: str,
        facility_id: str,
        environment: str,
        license_number: str,
        harvest_id: str,
    ):
        try:
            return self._verified_link(
                organization_id=organization_id,
                facility_id=facility_id,
                environment=environment,
                entity_type="cultivation_harvest",
                entity_id=harvest_id,
                resource="harvests",
                license_number=license_number,
            )
        except MetrcCultivationActionError as exc:
            raise MetrcHarvestActionError(str(exc)) from exc

    def _harvest(self, organization_id: str, facility_id: str, harvest_id: str) -> CultivationHarvest:
        with self.sessions() as session:
            harvest = session.get(CultivationHarvest, harvest_id)
            if not harvest or harvest.organization_id != organization_id or harvest.facility_id != facility_id:
                raise MetrcHarvestActionError("Harvest was not found in the active cultivation facility.")
            return harvest

    def _harvest_read(
        self,
        *,
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
            resource="harvests_by_id",
            environment=environment,
            license_number=license_number,
            path_parameters={"id": provider_id},
        )
        records = [dict(row) for row in result.get("records") or [] if isinstance(row, dict)] if isinstance(result, dict) else []
        if not isinstance(result, dict) or not result.get("ok") or len(records) != 1:
            raise MetrcHarvestActionError(str((result or {}).get("message") if isinstance(result, dict) else "") or "Fresh exact Metrc harvest readback failed.")
        returned_id = str(records[0].get("provider_id") or _source(records[0]).get("Id") or "").strip()
        if returned_id != str(provider_id).strip():
            raise MetrcHarvestActionError("Fresh harvest readback returned a different provider identity.")
        return result

    def prepare(
        self,
        *,
        organization_id: str,
        facility_id: str,
        operation_type: str,
        harvest_id: str,
        actual_date: str,
        plant_weights: list[dict[str, Any]] | None = None,
        drying_room_id: str = "",
        waste_type: str = "",
        waste_weight_g: float = 0.0,
        waste_method: str = "",
        waste_reason: str = "",
        waste_location: str = "",
        measurement_basis: str = "",
        all_waste_reported: bool = False,
        reason: str = "",
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        state_code, env, license_value = self._scope_harvest(state, environment, license_number)
        operation = str(operation_type or "").strip().casefold()
        if operation not in PROMOTED_HARVEST_ACTIONS:
            raise MetrcHarvestActionError("This harvest action has not passed the current operator promotion gate.")
        entity = str(harvest_id or "").strip()
        action_date = str(actual_date or "").strip()
        if not entity or not action_date:
            raise MetrcHarvestActionError("The exact local harvest and action date are required.")
        common = {
            "organization_id": organization_id,
            "facility_id": facility_id,
            "state": state_code,
            "environment": env,
            "license_number": license_value,
            "integrator_api_key": integrator_api_key,
            "user_api_key": user_api_key,
        }
        if operation == "harvest_start":
            return self._prepare_start(entity, action_date, plant_weights or [], drying_room_id, reason, **common)
        if operation == "harvest_waste":
            return self._prepare_waste(
                entity,
                action_date,
                waste_type,
                waste_weight_g,
                waste_method,
                waste_reason,
                waste_location,
                measurement_basis,
                reason,
                **common,
            )
        if operation == "harvest_finish":
            return self._prepare_finish(entity, action_date, all_waste_reported, reason, expected_current_finished=False, **common)
        return self._prepare_finish(entity, action_date, all_waste_reported, reason, expected_current_finished=True, **common)

    def _prepare_start(
        self,
        harvest_id: str,
        actual_date: str,
        plant_weights: list[dict[str, Any]],
        drying_room_id: str,
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
        harvest = self._harvest(organization_id, facility_id, harvest_id)
        if harvest.status != "planned":
            raise MetrcHarvestActionError("Only a planned local harvest can use Start harvest in Metrc.")
        existing = self.links.get_local(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            environment=environment,
            entity_type="cultivation_harvest",
            entity_id=harvest_id,
        )
        if existing:
            raise MetrcHarvestActionError("This local harvest already has a Metrc harvest identity; do not start it again.")

        supplied: dict[str, float] = {}
        for row in plant_weights:
            plant_id = str(row.get("plant_id") or "").strip()
            if not plant_id or plant_id in supplied:
                raise MetrcHarvestActionError("Provide each harvest plant exactly once with its wet weight.")
            try:
                weight = float(row.get("wet_weight_g"))
            except (TypeError, ValueError) as exc:
                raise MetrcHarvestActionError("Every plant wet weight must be numeric grams.") from exc
            if weight < 0:
                raise MetrcHarvestActionError("Plant wet weights cannot be negative.")
            supplied[plant_id] = weight

        with self.sessions() as session:
            links = list(session.scalars(select(CultivationHarvestPlant).where(CultivationHarvestPlant.harvest_id == harvest_id)))
            expected_ids = {row.plant_id for row in links}
            plants = list(session.scalars(select(CultivationPlant).where(CultivationPlant.id.in_(expected_ids or {"__none__"}))))
        if not expected_ids or set(supplied) != expected_ids:
            raise MetrcHarvestActionError("Wet-weight review must contain exactly every plant assigned to this local harvest.")
        if len(plants) != len(expected_ids) or any(row.organization_id != organization_id or row.facility_id != facility_id for row in plants):
            raise MetrcHarvestActionError("One or more harvest plants no longer belongs to the active facility.")
        if any(row.phase != "flowering" for row in plants):
            raise MetrcHarvestActionError("Every plant must still be flowering immediately before the regulated harvest write.")

        try:
            room = self._room_by_id(organization_id, facility_id, drying_room_id)
            room_link = self._verified_link(
                organization_id=organization_id,
                facility_id=facility_id,
                environment=environment,
                entity_type="cultivation_room",
                entity_id=room.id,
                resource="locations",
                license_number=license_number,
            )
        except MetrcCultivationActionError as exc:
            raise MetrcHarvestActionError(str(exc)) from exc
        drying_location = str(room_link.provider_label or "").strip()
        if not drying_location:
            raise MetrcHarvestActionError("The drying room is missing its verified Metrc Location label.")

        payloads: list[dict[str, Any]] = []
        provider_context: list[dict[str, Any]] = []
        for plant in sorted(plants, key=lambda row: row.plant_tag.casefold()):
            try:
                link = self._verified_link(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    environment=environment,
                    entity_type="cultivation_plant",
                    entity_id=plant.id,
                    resource="plants",
                    license_number=license_number,
                )
                fresh = self._exact_read(
                    resource="plants_by_id",
                    provider_id=link.provider_id,
                    state=state,
                    environment=environment,
                    license_number=license_number,
                    integrator_api_key=integrator_api_key,
                    user_api_key=user_api_key,
                )
            except MetrcCultivationActionError as exc:
                raise MetrcHarvestActionError(str(exc)) from exc
            record = fresh["records"][0]
            source = _source(record)
            provider_label = str(record.get("label") or _first(source, "Label", "PlantLabel", "Tag") or "").strip()
            phase = str(_first(source, "GrowthPhase", "GrowthPhaseName", "Phase") or "").strip()
            if not provider_label or (link.provider_label and provider_label.casefold() != str(link.provider_label).casefold()):
                raise MetrcHarvestActionError("A harvest plant's stored Metrc tag no longer matches fresh provider readback.")
            if not phase or phase.casefold() != "flowering":
                raise MetrcHarvestActionError(f"Metrc plant {provider_label or link.provider_id} is not freshly verified as Flowering.")
            payload = {
                "plant": provider_label,
                "weight": supplied[plant.id],
                "unit_of_weight": "Grams",
                "drying_location": drying_location,
                "harvest_name": harvest.harvest_code,
                "actual_date": actual_date,
            }
            payloads.append(payload)
            provider_context.append({
                "local_plant_id": plant.id,
                "provider_plant_id": link.provider_id,
                "provider_label": provider_label,
                "provider_last_modified": str(record.get("last_modified") or ""),
                "wet_weight_g": supplied[plant.id],
            })

        bodies = [build_lifecycle_evaluation_payload("plant_harvest", payload)[0] for payload in payloads]
        return {
            "operation_type": "harvest_start",
            "evaluator_operation": "plant_harvest",
            "entity_type": "cultivation_harvest",
            "entity_id": harvest_id,
            "provider_payloads": payloads,
            "provider_request_body": bodies,
            "summary": {
                "title": "Start harvest in Metrc",
                "harvest": harvest.harvest_code,
                "plant_count": len(payloads),
                "wet_weight_g": round(sum(supplied.values()), 4),
                "drying_room": room.display_name or room.room_code,
                "metrc_location": drying_location,
                "actual_date": actual_date,
                "provider_atomic": False,
            },
            "fingerprint_context": {
                "local_status": harvest.status,
                "plant_provider_context": provider_context,
                "drying_room_id": room.id,
                "drying_room_code": room.room_code,
                "drying_room_link_id": room_link.id,
                "reason": str(reason or "").strip(),
            },
        }

    def _prepare_waste(
        self,
        harvest_id: str,
        actual_date: str,
        waste_type: str,
        waste_weight_g: float,
        waste_method: str,
        waste_reason: str,
        waste_location: str,
        measurement_basis: str,
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
        harvest = self._harvest(organization_id, facility_id, harvest_id)
        if harvest.status not in {"active", "drying"}:
            raise MetrcHarvestActionError("Only an active/drying harvest can record regulated harvest waste.")
        link = self._verified_harvest_link(
            organization_id=organization_id,
            facility_id=facility_id,
            environment=environment,
            license_number=license_number,
            harvest_id=harvest_id,
        )
        try:
            weight = float(waste_weight_g)
        except (TypeError, ValueError) as exc:
            raise MetrcHarvestActionError("Waste weight must be numeric grams.") from exc
        if weight <= 0:
            raise MetrcHarvestActionError("Regulated harvest waste requires a positive waste weight.")
        waste_kind = str(waste_type or "").strip()
        method = str(waste_method or "").strip()
        local_reason = str(waste_reason or reason or "").strip()
        location = str(waste_location or "").strip()
        if not all((waste_kind, method, local_reason, location)):
            raise MetrcHarvestActionError("Waste type, disposal method, reason, and physical location are required.")
        basis = str(measurement_basis or "").strip().casefold()
        if basis not in {"wet", "dry"}:
            raise MetrcHarvestActionError("Choose whether this waste is measured against the wet or dry harvest basis.")

        fresh = self._harvest_read(
            provider_id=link.provider_id,
            state=state,
            environment=environment,
            license_number=license_number,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        source = _source(fresh["records"][0])
        baseline = harvest_waste_weight(source)
        if baseline is None:
            raise MetrcHarvestActionError("Fresh Metrc harvest readback does not expose a waste total, so this waste delta cannot be verified safely.")
        payload = {
            "id": int(link.provider_id),
            "waste_type": waste_kind,
            "unit_of_weight": "Grams",
            "waste_weight": weight,
            "actual_date": actual_date,
        }
        return {
            "operation_type": "harvest_waste",
            "evaluator_operation": "harvest_waste",
            "entity_type": "cultivation_harvest",
            "entity_id": harvest_id,
            "provider_payload": payload,
            "provider_request_body": build_lifecycle_evaluation_payload("harvest_waste", payload),
            "summary": {
                "title": "Record harvest waste",
                "harvest": harvest.harvest_code,
                "waste_type": waste_kind,
                "waste_weight_g": weight,
                "measurement_basis": basis,
                "actual_date": actual_date,
            },
            "fingerprint_context": {
                "harvest_link_id": link.id,
                "provider_harvest_id": link.provider_id,
                "baseline_waste_weight_g": baseline,
                "waste_method": method,
                "waste_reason": local_reason,
                "waste_location": location,
                "measurement_basis": basis,
                "provider_last_modified": str(fresh["records"][0].get("last_modified") or ""),
                "local_status": harvest.status,
                "reason": str(reason or "").strip(),
            },
        }

    def _prepare_finish(
        self,
        harvest_id: str,
        actual_date: str,
        all_waste_reported: bool,
        reason: str,
        *,
        expected_current_finished: bool,
        organization_id: str,
        facility_id: str,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        operation = "harvest_unfinish" if expected_current_finished else "harvest_finish"
        harvest = self._harvest(organization_id, facility_id, harvest_id)
        expected_local_status = "completed" if expected_current_finished else {"active", "drying"}
        if isinstance(expected_local_status, set):
            if harvest.status not in expected_local_status:
                raise MetrcHarvestActionError("Only an active/drying local harvest can be finished.")
        elif harvest.status != expected_local_status:
            raise MetrcHarvestActionError("Only a completed local harvest can be unfinished.")
        if operation == "harvest_finish":
            if not all_waste_reported:
                raise MetrcHarvestActionError("Confirm all actual harvest waste is already reported before finishing.")
            preview = MetrcGuideV11Service(self.engine).harvest_closeout_preview(organization_id, facility_id, harvest_id)
            if not preview.get("can_finish"):
                raise MetrcHarvestActionError("Harvest closeout is not balanced yet. Create/allocate at least one output and reconcile waste/loss before finishing.")
        else:
            preview = {"can_finish": False}

        link = self._verified_harvest_link(
            organization_id=organization_id,
            facility_id=facility_id,
            environment=environment,
            license_number=license_number,
            harvest_id=harvest_id,
        )
        fresh = self._harvest_read(
            provider_id=link.provider_id,
            state=state,
            environment=environment,
            license_number=license_number,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        current = verify_harvest_finished(readback=fresh, provider_id=link.provider_id, expected_finished=expected_current_finished)
        if not current.get("matched"):
            desired = "finished" if expected_current_finished else "open"
            raise MetrcHarvestActionError(f"Fresh Metrc readback does not prove this harvest is currently {desired}; reconcile before changing its finish state.")
        payload: dict[str, Any] = {"id": int(link.provider_id)}
        if operation == "harvest_finish":
            payload["actual_date"] = actual_date
        return {
            "operation_type": operation,
            "evaluator_operation": operation,
            "entity_type": "cultivation_harvest",
            "entity_id": harvest_id,
            "provider_payload": payload,
            "provider_request_body": build_lifecycle_evaluation_payload(operation, payload),
            "summary": {
                "title": "Reopen harvest" if operation == "harvest_unfinish" else "Finish harvest",
                "harvest": harvest.harvest_code,
                "current_status": harvest.status,
                "actual_date": actual_date if operation == "harvest_finish" else "—",
                "all_waste_reported": bool(all_waste_reported) if operation == "harvest_finish" else None,
            },
            "fingerprint_context": {
                "harvest_link_id": link.id,
                "provider_harvest_id": link.provider_id,
                "provider_last_modified": str(fresh["records"][0].get("last_modified") or ""),
                "local_status": harvest.status,
                "closeout": preview,
                "reason": str(reason or "").strip(),
            },
        }
