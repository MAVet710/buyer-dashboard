from __future__ import annotations

from datetime import date
from typing import Any

from modules.regulatory.metrc_process_compliance import MetrcProcessComplianceService

from .metrc_harvest_actions import MetrcHarvestActionError
from .metrc_harvest_execution import GovernedMetrcHarvestActionService


class MetrcHarvestOperatorService(GovernedMetrcHarvestActionService):
    """Final operator boundary for verified harvest writes and local reconciliation."""

    def _apply_single_local(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        transaction_id: str,
        prepared: dict[str, Any],
        all_waste_reported: bool,
    ) -> dict[str, Any]:
        if prepared.get("operation_type") != "harvest_waste":
            return super()._apply_single_local(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                transaction_id=transaction_id,
                prepared=prepared,
                all_waste_reported=all_waste_reported,
            )

        raw_date = prepared.get("provider_payload", {}).get("actual_date")
        if isinstance(raw_date, date):
            waste_date = raw_date
        else:
            try:
                waste_date = date.fromisoformat(str(raw_date or "").strip())
            except ValueError as exc:
                raise MetrcHarvestActionError(
                    "Verified Metrc waste is missing a valid local waste date; local reconciliation was stopped."
                ) from exc

        return MetrcProcessComplianceService(self.engine).record_waste(
            organization_id,
            facility_id,
            actor=actor,
            provider_confirmed=True,
            target_type="harvest",
            target_id=prepared["entity_id"],
            method=str(prepared["fingerprint_context"]["waste_method"]),
            material_mixed="",
            weight=float(prepared["provider_payload"]["waste_weight"]),
            unit="g",
            reason=str(prepared["fingerprint_context"]["waste_reason"]),
            waste_date=waste_date,
            location=str(prepared["fingerprint_context"]["waste_location"]),
            measurement_basis=str(prepared["fingerprint_context"]["measurement_basis"]),
            notes=f"Verified Metrc harvest waste transaction {transaction_id}",
        )

    def _composite_reconciliation(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        transaction,
        prepared: dict[str, Any],
        outcomes: list[dict[str, Any]],
        message: str,
        provider_reference: str,
    ) -> dict[str, Any]:
        if prepared.get("operation_type") == "harvest_start":
            return super()._composite_reconciliation(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                transaction=transaction,
                prepared=prepared,
                outcomes=outcomes,
                message=message,
                provider_reference=provider_reference,
            )

        self.traceability.record_reconciliation(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            actor=actor,
            local_state=prepared["fingerprint_context"],
            provider_state={"provider_reference": provider_reference, "outcomes": outcomes},
            mismatch_reason=message,
            evidence={
                "operation_type": prepared["operation_type"],
                "provider_atomic": True,
                "blind_retry_allowed": False,
                "outcomes": outcomes,
            },
            retry_eligible=False,
        )
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="reconciliation_required",
            actor=actor,
            reason=message,
            source="provider_worker",
            external_reference=provider_reference,
            error_code="unknown_provider_state",
            error_message=message,
        )
        return self._result(transaction, prepared, None, message)
