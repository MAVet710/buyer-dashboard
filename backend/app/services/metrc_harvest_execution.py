from __future__ import annotations

from typing import Any

from modules.cultivation.post_harvest import PostHarvestService
from modules.cultivation.service import CultivationService
from modules.regulatory.metrc_guide_v11 import MetrcGuideV11Service
from modules.regulatory.metrc_process_compliance import MetrcProcessComplianceService
from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_lifecycle import (
    LIFECYCLE_EVALUATION_ACTIONS,
    MetrcLifecycleEvaluationError,
    execute_lifecycle_evaluation_action,
)

from .metrc_harvest_actions import (
    MetrcHarvestActionError,
    MetrcHarvestActionService,
    harvest_confirmation_token,
)
from .metrc_harvest_readback import verify_harvest_finished, verify_harvest_state, verify_harvest_waste, verify_plant_harvested


class GovernedMetrcHarvestActionService(MetrcHarvestActionService):
    """Execute promoted harvest actions with durable composite reconciliation."""

    def execute(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
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
        confirmation_id: str,
        confirmation_token: str,
    ) -> dict[str, Any]:
        state_code, env, license_value = self._scope_harvest(state, environment, license_number)
        prepared = self.prepare(
            organization_id=organization_id,
            facility_id=facility_id,
            operation_type=operation_type,
            harvest_id=harvest_id,
            actual_date=actual_date,
            plant_weights=plant_weights,
            drying_room_id=drying_room_id,
            waste_type=waste_type,
            waste_weight_g=waste_weight_g,
            waste_method=waste_method,
            waste_reason=waste_reason,
            waste_location=waste_location,
            measurement_basis=measurement_basis,
            all_waste_reported=all_waste_reported,
            reason=reason,
            state=state_code,
            environment=env,
            license_number=license_value,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        expected_token = harvest_confirmation_token(
            prepared=prepared,
            state=state_code,
            environment=env,
            license_number=license_value,
            confirmation_id=confirmation_id,
        )
        if str(confirmation_token or "").strip() != expected_token:
            raise MetrcHarvestActionError(
                "The harvest, weight, lineage, or Metrc state changed after preview. Review the action again before submitting it."
            )

        operation = prepared["operation_type"]
        evaluator_operation = prepared["evaluator_operation"]
        spec = LIFECYCLE_EVALUATION_ACTIONS[evaluator_operation]
        idempotency_key = f"metrc-harvest:{facility_id}:{confirmation_id}:{expected_token}"
        transaction = self.traceability.create_transaction(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            operation_type=operation,
            entity_type="cultivation_harvest",
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
                    "provider_atomic": operation != "harvest_start",
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
            reason="Exact MA sandbox license, regulatory identities, local harvest/weight state, provider readback, and confirmation fingerprint validated.",
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
            reason="Human-confirmed harvest action queued for immediate controlled execution.",
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

        if operation == "harvest_start":
            return self._execute_start(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                transaction=transaction,
                prepared=prepared,
                state=state_code,
                environment=env,
                license_number=license_value,
                integrator_api_key=integrator_api_key,
                user_api_key=user_api_key,
            )
        return self._execute_single(
            organization_id=organization_id,
            facility_id=facility_id,
            actor=actor,
            transaction=transaction,
            prepared=prepared,
            state=state_code,
            environment=env,
            license_number=license_value,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
            all_waste_reported=all_waste_reported,
        )

    def _execute_start(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        transaction,
        prepared: dict[str, Any],
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        outcomes: list[dict[str, Any]] = []
        harvest_provider_id = ""
        cumulative_weight = 0.0
        contexts = list(prepared["fingerprint_context"]["plant_provider_context"])
        payloads = list(prepared.get("provider_payloads") or [])
        if len(payloads) != len(contexts):
            return self._composite_reconciliation(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                transaction=transaction,
                prepared=prepared,
                outcomes=outcomes,
                message="Prepared harvest provider rows no longer match the reviewed local plant set.",
                provider_reference="",
            )

        for index, (payload, context) in enumerate(zip(payloads, contexts, strict=True), start=1):
            try:
                evidence = execute_lifecycle_evaluation_action(
                    operation_type="plant_harvest",
                    payload=payload,
                    license_number=license_number,
                    integrator_api_key=integrator_api_key,
                    user_api_key=user_api_key,
                    state=state,
                    environment=environment,
                )
            except MetrcLifecycleEvaluationError as exc:
                outcomes.append({"index": index, "plant": context.get("provider_label"), "status": "unknown", "message": str(exc)})
                self.traceability.record_attempt(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    transaction_id=transaction.id,
                    request_payload={"operation_type": "plant_harvest", "payload": payload, "sequence": index},
                    error_code="provider_outcome_unknown",
                    error_message=str(exc),
                )
                return self._composite_reconciliation(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    actor=actor,
                    transaction=transaction,
                    prepared=prepared,
                    outcomes=outcomes,
                    message="A per-plant harvest call has an unknown provider outcome. The composite harvest cannot be repeated blindly.",
                    provider_reference=harvest_provider_id,
                )

            http_status = int(evidence.get("http_status") or 0)
            provider_id = str(evidence.get("provider_id") or "").strip()
            self.traceability.record_attempt(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                request_payload={**(evidence.get("request") if isinstance(evidence.get("request"), dict) else {}), "sequence": index},
                response_payload=evidence.get("response") if isinstance(evidence.get("response"), dict) else {"response": evidence.get("response")},
                http_status=http_status or None,
                error_code="" if http_status == 200 else "provider_rejected",
                error_message="" if http_status == 200 else str(evidence.get("message") or "Metrc rejected this plant harvest row."),
            )
            if http_status != 200:
                definite_first_rejection = not outcomes and http_status not in {0, 429} and http_status < 500
                outcomes.append({"index": index, "plant": context.get("provider_label"), "status": "rejected", "http_status": http_status})
                if definite_first_rejection:
                    transaction = self.traceability.transition_logged(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        transaction_id=transaction.id,
                        new_status="rejected",
                        actor=actor,
                        reason=str(evidence.get("message") or "Metrc rejected the first plant harvest row before any provider success was observed."),
                        source="provider_worker",
                        error_code="provider_rejected",
                        error_message=str(evidence.get("message") or ""),
                    )
                    return self._result(transaction, prepared, evidence, str(evidence.get("message") or "Metrc rejected the harvest write."))
                return self._composite_reconciliation(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    actor=actor,
                    transaction=transaction,
                    prepared=prepared,
                    outcomes=outcomes,
                    message="The provider may now contain a partial harvest. Stop and reconcile before any additional write.",
                    provider_reference=harvest_provider_id or provider_id,
                )

            if not provider_id or not evidence.get("passed"):
                outcomes.append({"index": index, "plant": context.get("provider_label"), "status": "readback_unverified", "provider_id": provider_id})
                return self._composite_reconciliation(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    actor=actor,
                    transaction=transaction,
                    prepared=prepared,
                    outcomes=outcomes,
                    message="Metrc accepted a plant harvest row but exact harvest identity/readback was not verified.",
                    provider_reference=harvest_provider_id or provider_id,
                )
            if harvest_provider_id and provider_id != harvest_provider_id:
                outcomes.append({"index": index, "plant": context.get("provider_label"), "status": "harvest_identity_mismatch", "provider_id": provider_id})
                return self._composite_reconciliation(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    actor=actor,
                    transaction=transaction,
                    prepared=prepared,
                    outcomes=outcomes,
                    message="Metrc placed reviewed plants into different harvest provider IDs. Local harvest state remains uncommitted.",
                    provider_reference=harvest_provider_id,
                )
            harvest_provider_id = harvest_provider_id or provider_id
            cumulative_weight += float(payload["weight"])
            harvest_check = verify_harvest_state(
                readback=evidence.get("readback"),
                provider_id=harvest_provider_id,
                expected_name=str(payload["harvest_name"]),
                expected_location=str(payload["drying_location"]),
                expected_weight_g=cumulative_weight,
            )
            plant_read = fetch_metrc_resource(
                state=state,
                user_api_key=user_api_key,
                integrator_api_key=integrator_api_key,
                resource="plants_by_id",
                environment=environment,
                license_number=license_number,
                path_parameters={"id": str(context["provider_plant_id"])},
            )
            plant_check = verify_plant_harvested(
                readback=plant_read,
                plant_provider_id=str(context["provider_plant_id"]),
                harvest_provider_id=harvest_provider_id,
                harvest_name=str(payload["harvest_name"]),
            )
            matched = bool(harvest_check.get("matched")) and bool(plant_check.get("matched"))
            outcomes.append({
                "index": index,
                "plant": context.get("provider_label"),
                "status": "verified" if matched else "readback_mismatch",
                "provider_id": provider_id,
                "cumulative_weight_g": cumulative_weight,
                "harvest_verification": harvest_check,
                "plant_verification": plant_check,
            })
            if not matched:
                return self._composite_reconciliation(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    actor=actor,
                    transaction=transaction,
                    prepared=prepared,
                    outcomes=outcomes,
                    message="A plant harvest write was accepted, but fresh business-state readback did not prove the confirmed harvest assignment/weight/location.",
                    provider_reference=harvest_provider_id,
                )

        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="accepted",
            actor=actor,
            reason="Every reviewed per-plant harvest write returned HTTP 200 and operation-specific provider readback verified one shared harvest identity. Local reconciliation is still required.",
            source="provider_worker",
            external_reference=harvest_provider_id,
            response_payload={"plant_outcomes": outcomes},
        )
        try:
            local_result = self._apply_start_local(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                transaction_id=transaction.id,
                prepared=prepared,
                provider_harvest_id=harvest_provider_id,
                state=state,
                environment=environment,
                license_number=license_number,
            )
        except (ValueError, MetrcHarvestActionError) as exc:
            return self._local_failure(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                transaction=transaction,
                prepared=prepared,
                provider_reference=harvest_provider_id,
                verification={"plant_outcomes": outcomes},
                message=str(exc),
            )

        return self._complete_verified(
            organization_id=organization_id,
            facility_id=facility_id,
            actor=actor,
            transaction=transaction,
            prepared=prepared,
            provider_reference=harvest_provider_id,
            verification={"matched": True, "plant_outcomes": outcomes},
            local_result=local_result,
            message="Every plant, wet weight, drying location, shared Metrc harvest identity, and corresponding DoobieLogic state is verified and reconciled.",
        )

    def _execute_single(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        transaction,
        prepared: dict[str, Any],
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
        all_waste_reported: bool,
    ) -> dict[str, Any]:
        operation = prepared["operation_type"]
        try:
            evidence = execute_lifecycle_evaluation_action(
                operation_type=prepared["evaluator_operation"],
                payload=prepared["provider_payload"],
                license_number=license_number,
                integrator_api_key=integrator_api_key,
                user_api_key=user_api_key,
                state=state,
                environment=environment,
            )
        except MetrcLifecycleEvaluationError as exc:
            return self._composite_reconciliation(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                transaction=transaction,
                prepared=prepared,
                outcomes=[{"status": "unknown", "message": str(exc)}],
                message="The harvest provider call has an unknown outcome. Blind retry is blocked.",
                provider_reference=str(prepared["fingerprint_context"].get("provider_harvest_id") or ""),
            )
        http_status = int(evidence.get("http_status") or 0)
        self.traceability.record_attempt(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            request_payload=evidence.get("request") if isinstance(evidence.get("request"), dict) else {"operation_type": operation},
            response_payload=evidence.get("response") if isinstance(evidence.get("response"), dict) else {"response": evidence.get("response")},
            http_status=http_status or None,
            error_code="" if http_status == 200 else "provider_rejected",
            error_message="" if http_status == 200 else str(evidence.get("message") or "Metrc rejected the harvest write."),
        )
        provider_reference = str(prepared["fingerprint_context"].get("provider_harvest_id") or evidence.get("provider_id") or "").strip()
        if http_status != 200:
            uncertain = http_status in {0, 429} or http_status >= 500
            if uncertain:
                return self._composite_reconciliation(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    actor=actor,
                    transaction=transaction,
                    prepared=prepared,
                    outcomes=[{"status": "unknown_or_retryable_http", "http_status": http_status}],
                    message=str(evidence.get("message") or "Metrc provider outcome is uncertain."),
                    provider_reference=provider_reference,
                )
            transaction = self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                new_status="rejected",
                actor=actor,
                reason=str(evidence.get("message") or "Metrc rejected the harvest write."),
                source="provider_worker",
                error_code="provider_rejected",
                error_message=str(evidence.get("message") or ""),
            )
            return self._result(transaction, prepared, evidence, str(evidence.get("message") or "Metrc rejected the harvest write."))

        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="accepted",
            actor=actor,
            reason="Metrc returned HTTP 200. Operation-specific harvest readback is still required before local state changes.",
            source="provider_worker",
            external_reference=provider_reference,
            response_payload=evidence.get("response") if isinstance(evidence.get("response"), dict) else {"response": evidence.get("response")},
        )
        if operation == "harvest_waste":
            verification = verify_harvest_waste(
                readback=evidence.get("readback"),
                provider_id=provider_reference,
                baseline_waste_weight_g=float(prepared["fingerprint_context"]["baseline_waste_weight_g"]),
                submitted_waste_weight_g=float(prepared["provider_payload"]["waste_weight"]),
            )
        else:
            verification = verify_harvest_finished(
                readback=evidence.get("readback"),
                provider_id=provider_reference,
                expected_finished=operation == "harvest_finish",
            )
        verification["evaluator_passed"] = bool(evidence.get("passed"))
        verification["matched"] = bool(evidence.get("passed")) and bool(verification.get("matched"))
        if not verification.get("matched"):
            return self._provider_mismatch(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                transaction=transaction,
                prepared=prepared,
                provider_reference=provider_reference,
                verification=verification,
            )
        try:
            local_result = self._apply_single_local(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                transaction_id=transaction.id,
                prepared=prepared,
                all_waste_reported=all_waste_reported,
            )
        except (ValueError, MetrcHarvestActionError) as exc:
            return self._local_failure(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                transaction=transaction,
                prepared=prepared,
                provider_reference=provider_reference,
                verification=verification,
                message=str(exc),
            )
        return self._complete_verified(
            organization_id=organization_id,
            facility_id=facility_id,
            actor=actor,
            transaction=transaction,
            prepared=prepared,
            provider_reference=provider_reference,
            verification=verification,
            local_result=local_result,
            message="Metrc harvest state and DoobieLogic local state are verified and reconciled.",
        )

    def _apply_start_local(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        transaction_id: str,
        prepared: dict[str, Any],
        provider_harvest_id: str,
        state: str,
        environment: str,
        license_number: str,
    ) -> dict[str, Any]:
        contexts = list(prepared["fingerprint_context"]["plant_provider_context"])
        weights = [{"plant_id": str(row["local_plant_id"]), "wet_weight_g": float(row["wet_weight_g"])} for row in contexts]
        link = self.links.upsert_verified(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            jurisdiction=state,
            environment=environment,
            license_number=license_number,
            entity_type="cultivation_harvest",
            entity_id=prepared["entity_id"],
            provider_resource="harvests",
            provider_id=provider_harvest_id,
            provider_label=str(prepared["summary"]["harvest"]),
            source_transaction_id=transaction_id,
        )
        regulatory = MetrcProcessComplianceService(self.engine).record_harvest_wet_weights(
            organization_id,
            facility_id,
            prepared["entity_id"],
            plant_weights=weights,
            actor=actor,
            provider_confirmed=True,
        )
        harvest = CultivationService(self.engine).transition_harvest(
            organization_id,
            facility_id,
            prepared["entity_id"],
            status="drying",
            actor=actor,
            unit="g",
            notes=f"Verified Metrc harvest transaction {transaction_id}",
        )
        batches = PostHarvestService(self.engine).sync_open_harvests(organization_id, facility_id, actor=actor)
        post = next((row for row in batches if str(row.get("harvest_id") or "") == prepared["entity_id"]), None)
        if post is None:
            raise MetrcHarvestActionError("Post-Harvest work did not materialize from the verified local harvest.")
        post = PostHarvestService(self.engine).transition(
            organization_id,
            facility_id,
            str(post["id"]),
            stage="drying",
            location_code=str(prepared["fingerprint_context"]["drying_room_code"]),
            actor=actor,
            notes=f"Verified Metrc drying location via transaction {transaction_id}",
        )
        return {
            "harvest_id": prepared["entity_id"],
            "harvest_link": self.links.payload(link),
            "regulatory_wet_weights": regulatory,
            "local_harvest_status": harvest.get("status"),
            "post_harvest_batch_id": post.get("id"),
            "post_harvest_stage": post.get("stage"),
            "post_harvest_location": post.get("location_code"),
        }

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
        operation = prepared["operation_type"]
        if operation == "harvest_waste":
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
                waste_date=prepared["provider_payload"]["actual_date"],
                location=str(prepared["fingerprint_context"]["waste_location"]),
                measurement_basis=str(prepared["fingerprint_context"]["measurement_basis"]),
                notes=f"Verified Metrc harvest waste transaction {transaction_id}",
            )
        if operation == "harvest_finish":
            return MetrcGuideV11Service(self.engine).finish_harvest(
                organization_id,
                facility_id,
                prepared["entity_id"],
                actor=actor,
                provider_confirmed=True,
                all_waste_reported=bool(all_waste_reported),
            )
        return MetrcGuideV11Service(self.engine).unfinish_harvest(
            organization_id,
            facility_id,
            prepared["entity_id"],
            actor=actor,
            provider_confirmed=True,
            provider_reference=transaction_id,
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
        self.traceability.record_reconciliation(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            actor=actor,
            local_state=prepared["fingerprint_context"],
            provider_state={"provider_reference": provider_reference, "plant_outcomes": outcomes},
            mismatch_reason=message,
            evidence={"operation_type": prepared["operation_type"], "provider_atomic": False, "blind_retry_allowed": False, "outcomes": outcomes},
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
            error_code="partial_or_unknown_provider_state",
            error_message=message,
        )
        return self._result(transaction, prepared, None, message)

    def _provider_mismatch(self, *, organization_id: str, facility_id: str, actor: str, transaction, prepared: dict[str, Any], provider_reference: str, verification: dict[str, Any]):
        message = "Metrc accepted the harvest write, but fresh operation-specific readback did not verify the confirmed business state."
        self.traceability.record_reconciliation(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            actor=actor,
            local_state=prepared["fingerprint_context"],
            provider_state={"provider_reference": provider_reference},
            readback_result=verification,
            mismatch_reason=message,
            evidence={"operation_type": prepared["operation_type"], "provider_verification": verification, "blind_retry_allowed": False},
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
        return self._result(transaction, prepared, None, message)

    def _local_failure(self, *, organization_id: str, facility_id: str, actor: str, transaction, prepared: dict[str, Any], provider_reference: str, verification: dict[str, Any], message: str):
        detail = f"Metrc state is verified, but DoobieLogic local reconciliation failed: {message}"
        self.traceability.record_reconciliation(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            actor=actor,
            local_state=prepared["fingerprint_context"],
            provider_state={"provider_verified": True, "provider_reference": provider_reference},
            readback_result=verification,
            mismatch_reason=detail,
            evidence={"operation_type": prepared["operation_type"], "provider_verified": True, "local_apply_failed": True, "blind_retry_allowed": False},
            retry_eligible=False,
        )
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="reconciliation_required",
            actor=actor,
            reason="Provider state is verified but local harvest/post-harvest reconciliation requires review. Never repeat the provider write blindly.",
            source="system",
            external_reference=provider_reference,
            error_code="local_reconciliation_failed",
            error_message=detail,
        )
        return self._result(transaction, prepared, None, detail)

    def _complete_verified(self, *, organization_id: str, facility_id: str, actor: str, transaction, prepared: dict[str, Any], provider_reference: str, verification: dict[str, Any], local_result: dict[str, Any], message: str):
        self.traceability.record_reconciliation(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            actor=actor,
            local_state=local_result,
            provider_state={"provider_verified": True, "provider_reference": provider_reference},
            readback_result=verification,
            mismatch_reason="",
            evidence={"operation_type": prepared["operation_type"], "provider_verified": True, "local_reconciled": True, "blind_retry_allowed": False},
            retry_eligible=False,
        )
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="verified",
            actor=actor,
            reason="Fresh Metrc readback verified the exact harvest state and DoobieLogic reconciled the corresponding local harvest/post-harvest state.",
            source="provider_readback",
            external_reference=provider_reference,
        )
        return self._result(transaction, prepared, None, message, local_result)
