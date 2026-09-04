from __future__ import annotations

from typing import Any

from modules.cultivation.batches import CultivationBatchService
from modules.regulatory.metrc_process_compliance import MetrcProcessComplianceService

from .metrc_cultivation_actions import MetrcCultivationActionError, MetrcCultivationActionService


class GovernedMetrcCultivationActionService(MetrcCultivationActionService):
    """Operator service with exact post-provider local reconciliation semantics."""

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
        if prepared.get("operation_type") != "plant_batch_vegetative":
            return super()._apply_local_verified_state(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                prepared=prepared,
                transaction_id=transaction_id,
                verification=verification,
                state=state,
                environment=environment,
                license_number=license_number,
            )

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

        destination_room_id = str(prepared.get("fingerprint_context", {}).get("destination_room_id") or "").strip()
        destination_room = self._room_by_id(organization_id, facility_id, destination_room_id)
        moved = CultivationBatchService(self.engine).transition_group(
            organization_id,
            facility_id,
            prepared["entity_id"],
            actor=actor,
            phase=None,
            room_code=destination_room.room_code,
            reason="Verified Metrc vegetative growth-phase/location change",
            notes=f"Traceability transaction {transaction_id}",
        )
        if str(moved.get("room_code") or "").strip() != destination_room.room_code:
            raise MetrcCultivationActionError("Local plant group did not reconcile to the verified Metrc destination room.")

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
            "room_code": destination_room.room_code,
            "plant_count": len(links),
            "plant_links": links,
        }
