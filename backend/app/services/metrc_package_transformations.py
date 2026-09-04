from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import select

from modules.coman.models import AuditEvent, InventoryLot, Product
from modules.package_studio.models import PackageStudioRun
from modules.package_studio.service import PackageStudioPlan, PackageStudioService
from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_lifecycle import (
    LIFECYCLE_EVALUATION_ACTIONS,
    MetrcLifecycleEvaluationError,
    build_lifecycle_evaluation_payload,
    execute_lifecycle_evaluation_action,
)

from .metrc_package_actions import MetrcPackageActionError, MetrcPackageActionService
from .metrc_package_readback import canonical_unit, verify_package_state


class MetrcPackageTransformationError(MetrcPackageActionError):
    pass


_PROVIDER_UNITS = {
    "grams": "Grams",
    "kilograms": "Kilograms",
    "ounces": "Ounces",
    "pounds": "Pounds",
    "each": "Each",
    "milligrams": "Milligrams",
    "milliliters": "Milliliters",
    "liters": "Liters",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _provider_unit(value: str) -> str:
    canonical = canonical_unit(value)
    result = _PROVIDER_UNITS.get(canonical, "")
    if not result:
        raise MetrcPackageTransformationError(
            f"Unit {value!r} is not in the reviewed Metrc package unit mapping. Reconcile the Product unit before provider creation."
        )
    return result


def package_transformation_confirmation_token(
    *,
    prepared: dict[str, Any],
    state: str,
    environment: str,
    license_number: str,
    confirmation_id: str,
) -> str:
    confirmation = str(confirmation_id or "").strip()
    if not confirmation:
        raise MetrcPackageTransformationError("A confirmation ID is required.")
    document = {
        "confirmation_id": confirmation,
        "operation_type": "package_studio_transform",
        "state": str(state or "").strip().upper(),
        "environment": str(environment or "").strip().casefold(),
        "license_number": str(license_number or "").strip(),
        "entity_type": prepared.get("entity_type"),
        "entity_id": prepared.get("entity_id"),
        "actual_date": prepared.get("actual_date"),
        "provider_outputs": prepared.get("provider_outputs"),
        "fingerprint_context": prepared.get("fingerprint_context"),
    }
    return sha256(_canonical(document).encode("utf-8")).hexdigest()


class GovernedMetrcPackageTransformationService(MetrcPackageActionService):
    """Create Metrc child packages first, then atomically commit matching local lineage.

    The first promoted Package Studio slice deliberately supports one tracked source
    package. The current React Package Studio also operates on one source, so this
    avoids inventing per-output allocation across multiple provider ingredients.
    """

    def _available_package_tags(
        self,
        *,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> set[str]:
        labels: set[str] = set()
        for page_number in range(1, 21):
            result = fetch_metrc_resource(
                state=state,
                user_api_key=user_api_key,
                integrator_api_key=integrator_api_key,
                resource="package_tags_available",
                environment=environment,
                license_number=license_number,
                page_size=50,
                page_number=page_number,
            )
            if not isinstance(result, dict) or not result.get("ok"):
                raise MetrcPackageTransformationError(
                    str((result or {}).get("message") if isinstance(result, dict) else "")
                    or "Fresh Metrc available-package-tag lookup failed."
                )
            rows = [dict(row) for row in result.get("records") or [] if isinstance(row, dict)]
            for row in rows:
                source = row.get("source") if isinstance(row.get("source"), dict) else {}
                label = str(row.get("label") or row.get("name") or source.get("Label") or source.get("Tag") or "").strip()
                if label:
                    labels.add(label)
            if len(rows) < 50:
                break
        return labels

    def _verified_item_link(
        self,
        *,
        organization_id: str,
        facility_id: str,
        product_id: str,
        environment: str,
        license_number: str,
    ):
        link = self.links.get_local(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            environment=environment,
            entity_type="product",
            entity_id=product_id,
        )
        if not link or link.status != "verified" or link.provider_resource != "items" or link.license_number != license_number:
            raise MetrcPackageTransformationError(
                "Every output Product must be linked to an exact verified Metrc Item before a tracked Package Studio run can be submitted."
            )
        return link

    def prepare(
        self,
        *,
        organization_id: str,
        facility_id: str,
        plan: PackageStudioPlan,
        actual_date: str,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        state_code, env, license_value = self._scope(state, environment, license_number)
        action_date = str(actual_date or "").strip()
        if not action_date:
            raise MetrcPackageTransformationError("An actual date is required for Metrc package creation.")

        try:
            preview = PackageStudioService(self.engine).preview(plan)
        except ValueError as exc:
            raise MetrcPackageTransformationError(str(exc)) from exc
        if len(plan.inputs) != 1:
            raise MetrcPackageTransformationError(
                "The promoted Metrc Package Studio workflow currently requires exactly one tracked source package."
            )
        if abs(float(plan.loss_quantity or 0.0)) > 1e-9:
            raise MetrcPackageTransformationError(
                "Tracked Package Studio runs with recorded loss require a separate governed Metrc adjustment/waste reason. Set loss to zero here or record the loss through the governed provider adjustment workflow first."
            )

        source_input = plan.inputs[0]
        current = self._validated_current(
            organization_id=organization_id,
            facility_id=facility_id,
            lot_id=source_input.lot_id,
            state=state_code,
            environment=env,
            license_number=license_value,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        local = current["local"]
        source_link = current["package_link"]
        source_snapshot = current["snapshot"]
        if canonical_unit(source_input.unit) != canonical_unit(local["unit"]):
            raise MetrcPackageTransformationError("The Package Studio source unit no longer matches the verified local package unit.")
        source_quantity = float(source_input.quantity)
        if source_quantity <= 0 or source_quantity > float(local["balance"]) + 1e-9:
            raise MetrcPackageTransformationError("The requested source quantity is not available in the verified source package.")

        if preview.action_type == "sample_pull" and any(
            str(output.purpose or "").strip().casefold() == "lab_sample" for output in plan.outputs
        ):
            raise MetrcPackageTransformationError(
                "Lab-test samples use Metrc's dedicated testing-package workflow and are not promoted through generic package creation yet. Choose Trade sample/Retail sample or use the governed testing workflow when it is promoted."
            )

        available_tags = self._available_package_tags(
            state=state_code,
            environment=env,
            license_number=license_value,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        selected_tags: list[str] = []
        provider_outputs: list[dict[str, Any]] = []
        fingerprint_outputs: list[dict[str, Any]] = []
        source_provider_unit = str(source_snapshot.get("unit_of_measure") or local["unit"])

        with self.sessions() as session:
            source_lot = session.get(InventoryLot, source_input.lot_id)
            if not source_lot or source_lot.organization_id != organization_id or source_lot.facility_id != facility_id:
                raise MetrcPackageTransformationError("The tracked source package is unavailable in this facility.")
            output_products: list[Product] = []
            for output in plan.outputs:
                product = session.get(Product, output.product_id)
                if not product or product.organization_id != organization_id or not product.active:
                    raise MetrcPackageTransformationError("An output Product is unavailable or inactive.")
                duplicate = session.scalar(
                    select(InventoryLot.id).where(
                        InventoryLot.facility_id == facility_id,
                        InventoryLot.lot_code == str(output.lot_code or "").strip(),
                    )
                )
                if duplicate:
                    raise MetrcPackageTransformationError(
                        f"Output lot/package code {output.lot_code} already exists. Review the run before changing Metrc."
                    )
                output_products.append(product)
            if preview.action_type in {"breakdown", "sample_pull"} and any(
                product.id != source_lot.product_id for product in output_products
            ):
                raise MetrcPackageTransformationError(
                    "Breakdown and Sample Pull outputs must keep the source Product identity before Metrc creation."
                )

        for position, output in enumerate(plan.outputs, start=1):
            tag = str(output.compliance_package_id or "").strip()
            if not tag:
                raise MetrcPackageTransformationError(
                    f"Output {position} requires an exact available Metrc package tag before provider creation."
                )
            if tag in selected_tags:
                raise MetrcPackageTransformationError("Each output requires a different Metrc package tag.")
            if tag not in available_tags:
                raise MetrcPackageTransformationError(
                    f"Metrc package tag {tag} is not in the facility's fresh available-tag snapshot. Refresh tags before review."
                )
            selected_tags.append(tag)
            item_link = self._verified_item_link(
                organization_id=organization_id,
                facility_id=facility_id,
                product_id=output.product_id,
                environment=env,
                license_number=license_value,
            )
            purpose = str(output.purpose or "standard").strip().casefold()
            provider_payload = {
                "tag": tag,
                "item": item_link.provider_label,
                "quantity": float(output.inventory_quantity),
                "unit_of_measure": _provider_unit(output.inventory_unit),
                "actual_date": action_date,
                "ingredients": [
                    {
                        "package": source_link.provider_label,
                        "quantity": float(output.source_equivalent_quantity),
                        "unit_of_measure": source_provider_unit,
                    }
                ],
                "is_production_batch": preview.action_type in {"build_run", "multi_build", "rework"},
                "is_trade_sample": purpose == "trade_sample",
                "is_donation": False,
                "product_requires_remediation": False,
                "required_lab_test_batches": False,
                "use_same_item": output.product_id == local["product_id"],
            }
            provider_outputs.append(
                {
                    "position": position,
                    "lot_code": str(output.lot_code).strip(),
                    "product_id": output.product_id,
                    "item_link_id": item_link.id,
                    "item_provider_id": item_link.provider_id,
                    "item": item_link.provider_label,
                    "tag": tag,
                    "inventory_quantity": float(output.inventory_quantity),
                    "inventory_unit": str(output.inventory_unit),
                    "source_equivalent_quantity": float(output.source_equivalent_quantity),
                    "purpose": purpose,
                    "provider_payload": provider_payload,
                    "provider_request_body": build_lifecycle_evaluation_payload("package_create", provider_payload),
                }
            )
            fingerprint_outputs.append(
                {
                    "position": position,
                    "lot_code": str(output.lot_code).strip(),
                    "product_id": output.product_id,
                    "item_link_id": item_link.id,
                    "item_provider_id": item_link.provider_id,
                    "tag": tag,
                    "inventory_quantity": float(output.inventory_quantity),
                    "inventory_unit": str(output.inventory_unit),
                    "source_equivalent_quantity": float(output.source_equivalent_quantity),
                    "purpose": purpose,
                }
            )

        expected_source_quantity = float(local["balance"]) - source_quantity
        return {
            "operation_type": "package_studio_transform",
            "entity_type": "inventory_lot",
            "entity_id": source_input.lot_id,
            "actual_date": action_date,
            "summary": {
                "title": "Create tracked Package Studio outputs",
                "action": preview.action_type.replace("_", " ").title(),
                "source_package": source_link.provider_label,
                "source_quantity": source_quantity,
                "source_unit": local["unit"],
                "source_remaining": expected_source_quantity,
                "output_count": len(provider_outputs),
                "outputs": [
                    {
                        "lot_code": row["lot_code"],
                        "metrc_tag": row["tag"],
                        "metrc_item": row["item"],
                        "quantity": row["inventory_quantity"],
                        "unit": row["inventory_unit"],
                    }
                    for row in provider_outputs
                ],
            },
            "provider_outputs": provider_outputs,
            "expected_source_quantity": expected_source_quantity,
            "fingerprint_context": {
                "action_type": preview.action_type,
                "source_lot_id": source_input.lot_id,
                "source_local_balance": float(local["balance"]),
                "source_local_unit": local["unit"],
                "source_product_id": local["product_id"],
                "source_provider_id": source_link.provider_id,
                "source_provider_label": source_link.provider_label,
                "source_link_id": source_link.id,
                "source_last_modified": source_snapshot.get("last_modified"),
                "source_quantity": source_quantity,
                "outputs": fingerprint_outputs,
                "run_number": str(plan.run_number or "").strip(),
                "reason": str(plan.reason or "").strip(),
                "notes": str(plan.notes or "").strip(),
            },
        }

    def execute(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        plan: PackageStudioPlan,
        actual_date: str,
        confirmation_id: str,
        confirmation_token: str,
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        prepared = self.prepare(
            organization_id=organization_id,
            facility_id=facility_id,
            plan=plan,
            actual_date=actual_date,
            state=state,
            environment=environment,
            license_number=license_number,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        state_code, env, license_value = self._scope(state, environment, license_number)
        expected_token = package_transformation_confirmation_token(
            prepared=prepared,
            state=state_code,
            environment=env,
            license_number=license_value,
            confirmation_id=confirmation_id,
        )
        if str(confirmation_token or "").strip() != expected_token:
            raise MetrcPackageTransformationError(
                "Package Studio or Metrc state changed after preview. Review the tracked transformation again before submission."
            )

        transaction = self.traceability.create_transaction(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            operation_type="package_studio_transform",
            entity_type="inventory_lot",
            entity_id=prepared["entity_id"],
            idempotency_key=f"metrc-package-studio:{facility_id}:{confirmation_id}:{expected_token}",
            actor=actor,
            license_number=license_value,
            jurisdiction=state_code,
            environment=env,
            request_payload={
                "provider_operation": "package_create",
                "provider_requests": [row["provider_request_body"] for row in prepared["provider_outputs"]],
                "confirmation_id": confirmation_id,
                "local_state": prepared["fingerprint_context"],
            },
            local_state=prepared["fingerprint_context"],
            reason=str(plan.reason or "Tracked Package Studio transformation"),
        )
        transaction, claimed = self.traceability.claim_transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            expected_status="requested",
            new_status="validated",
            actor=actor,
            reason="Exact source Package, output Item links, fresh package tags, mass balance, and confirmation fingerprint validated.",
            source="system",
        )
        if not claimed:
            return self._existing_transform(transaction, prepared)
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="queued",
            actor=actor,
            reason="Human-confirmed tracked Package Studio transformation queued for controlled execution.",
            source="system",
        )
        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="submitted",
            actor=actor,
            reason="Beginning exact Metrc package creation for each confirmed Package Studio output.",
            source="provider_worker",
        )

        verified_outputs: list[dict[str, Any]] = []
        for row in prepared["provider_outputs"]:
            try:
                evidence = execute_lifecycle_evaluation_action(
                    operation_type="package_create",
                    payload=row["provider_payload"],
                    license_number=license_value,
                    integrator_api_key=integrator_api_key,
                    user_api_key=user_api_key,
                    state=state_code,
                    environment=env,
                )
            except MetrcLifecycleEvaluationError as exc:
                return self._reconcile_transform(
                    transaction=transaction,
                    prepared=prepared,
                    actor=actor,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    message=str(exc),
                    verified_outputs=verified_outputs,
                    stage=f"output_{row['position']}_exception",
                )

            http_status = int(evidence.get("http_status") or 0)
            self.traceability.record_attempt(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                request_payload=evidence.get("request") if isinstance(evidence.get("request"), dict) else {"operation_type": "package_create", "position": row["position"]},
                response_payload=evidence.get("response") if isinstance(evidence.get("response"), dict) else {"response": evidence.get("response")},
                http_status=http_status or None,
                error_code="" if http_status == 200 else "provider_rejected",
                error_message="" if http_status == 200 else str(evidence.get("message") or "Metrc rejected package creation."),
            )
            if http_status != 200:
                uncertain = http_status == 0 or http_status == 429 or http_status >= 500
                if not verified_outputs and not uncertain:
                    transaction = self.traceability.transition_logged(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        transaction_id=transaction.id,
                        new_status="rejected",
                        actor=actor,
                        reason=str(evidence.get("message") or "Metrc rejected the first package creation."),
                        source="provider_worker",
                        error_code="provider_rejected",
                        error_message=str(evidence.get("message") or ""),
                    )
                    return self._transform_result(transaction, prepared, str(evidence.get("message") or "Metrc rejected package creation."), verified_outputs)
                return self._reconcile_transform(
                    transaction=transaction,
                    prepared=prepared,
                    actor=actor,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    message=str(evidence.get("message") or "Metrc package creation did not complete safely."),
                    verified_outputs=verified_outputs,
                    stage=f"output_{row['position']}_provider_response",
                )

            provider_id = str(evidence.get("provider_id") or "").strip()
            verification = verify_package_state(
                readback=evidence.get("readback"),
                provider_id=provider_id,
                expected_label=row["tag"],
                expected_item=row["item"],
                expected_quantity=row["inventory_quantity"],
                expected_unit=row["inventory_unit"],
                expected_finished=False,
            )
            if not bool(evidence.get("passed")) or not provider_id or not verification.get("matched"):
                return self._reconcile_transform(
                    transaction=transaction,
                    prepared=prepared,
                    actor=actor,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    message="Metrc accepted a package creation, but fresh semantic readback did not verify the confirmed child package.",
                    verified_outputs=verified_outputs + [{"position": row["position"], "provider_id": provider_id, "tag": row["tag"], "semantic_verification": verification}],
                    stage=f"output_{row['position']}_readback",
                )
            verified_outputs.append(
                {
                    "position": row["position"],
                    "provider_id": provider_id,
                    "tag": row["tag"],
                    "item": row["item"],
                    "quantity": row["inventory_quantity"],
                    "unit": row["inventory_unit"],
                    "semantic_verification": verification,
                }
            )

        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="accepted",
            actor=actor,
            reason="Every child Package returned HTTP 200 and fresh exact child readback passed. Source depletion and local ledger commit still require verification.",
            source="provider_worker",
            external_reference=verified_outputs[0]["provider_id"] if verified_outputs else "",
            response_payload={"verified_outputs": [{key: row[key] for key in ("position", "provider_id", "tag")} for row in verified_outputs]},
        )

        source_fresh = self._fresh_package(
            provider_id=prepared["fingerprint_context"]["source_provider_id"],
            state=state_code,
            environment=env,
            license_number=license_value,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        source_verification = verify_package_state(
            readback=source_fresh["readback"],
            provider_id=prepared["fingerprint_context"]["source_provider_id"],
            expected_label=prepared["fingerprint_context"]["source_provider_label"],
            expected_quantity=prepared["expected_source_quantity"],
            expected_unit=prepared["fingerprint_context"]["source_local_unit"],
        )
        if not source_verification.get("matched"):
            return self._reconcile_transform(
                transaction=transaction,
                prepared=prepared,
                actor=actor,
                organization_id=organization_id,
                facility_id=facility_id,
                message="All child Packages were created, but fresh source Package readback did not verify the expected remaining quantity.",
                verified_outputs=verified_outputs,
                stage="source_readback",
                readback_result=source_fresh["readback"],
                extra_evidence={"source_semantic_verification": source_verification},
            )

        self.traceability.record_reconciliation(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            actor=actor,
            provider_state={
                "source_provider_id": prepared["fingerprint_context"]["source_provider_id"],
                "expected_source_quantity": prepared["expected_source_quantity"],
                "outputs": [{key: row[key] for key in ("position", "provider_id", "tag", "quantity", "unit")} for row in verified_outputs],
            },
            readback_result=source_fresh["readback"],
            mismatch_reason="",
            evidence={
                "provider_verified": True,
                "source_semantic_verification": source_verification,
                "output_semantic_verifications": [row["semantic_verification"] for row in verified_outputs],
                "provider_atomic": False,
                "blind_retry_allowed": False,
            },
            retry_eligible=False,
        )

        try:
            local_plan = replace(
                plan,
                outputs=tuple(
                    replace(output, compliance_package_id=verified_outputs[index]["tag"])
                    for index, output in enumerate(plan.outputs)
                ),
            )
            local_result = PackageStudioService(self.engine).commit(
                local_plan,
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
            )
            for index, lot_id in enumerate(local_result.output_lot_ids):
                provider = verified_outputs[index]
                self.links.upsert_verified(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    provider="metrc",
                    jurisdiction=state_code,
                    environment=env,
                    license_number=license_value,
                    entity_type="inventory_lot",
                    entity_id=lot_id,
                    provider_resource="packages",
                    provider_id=provider["provider_id"],
                    provider_label=provider["tag"],
                    source_transaction_id=transaction.id,
                )
            self.links.upsert_verified(
                organization_id=organization_id,
                facility_id=facility_id,
                provider="metrc",
                jurisdiction=state_code,
                environment=env,
                license_number=license_value,
                entity_type="inventory_lot",
                entity_id=prepared["entity_id"],
                provider_resource="packages",
                provider_id=prepared["fingerprint_context"]["source_provider_id"],
                provider_label=prepared["fingerprint_context"]["source_provider_label"],
                source_transaction_id=transaction.id,
            )
            with self.sessions.begin() as session:
                run = session.get(PackageStudioRun, local_result.run_id)
                if not run or run.organization_id != organization_id or run.facility_id != facility_id:
                    raise MetrcPackageTransformationError("Verified Package Studio run disappeared before sync evidence could be finalized.")
                run.external_sync_status = "synced"
                run.external_sync_reference = transaction.id
                session.add(
                    AuditEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        entity_type="package_studio_run",
                        entity_id=run.id,
                        action="metrc_verified",
                        actor=actor,
                        changes_json=json.dumps(
                            {
                                "traceability_transaction_id": transaction.id,
                                "external_sync_status": "synced",
                                "source_provider_id": prepared["fingerprint_context"]["source_provider_id"],
                                "output_provider_ids": [row["provider_id"] for row in verified_outputs],
                            },
                            sort_keys=True,
                        ),
                    )
                )
        except Exception as exc:
            return self._reconcile_transform(
                transaction=transaction,
                prepared=prepared,
                actor=actor,
                organization_id=organization_id,
                facility_id=facility_id,
                message=f"Metrc packages are verified, but the matching DoobieLogic Package Studio commit requires reconciliation: {exc}",
                verified_outputs=verified_outputs,
                stage="local_commit",
                extra_evidence={"provider_verified": True, "local_commit_failed": True},
            )

        transaction = self.traceability.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="verified",
            actor=actor,
            reason="Every Metrc child Package and the source depletion were freshly verified, then the matching local Package Studio lineage committed and exact object links were persisted.",
            source="provider_readback",
            external_reference=verified_outputs[0]["provider_id"] if verified_outputs else "",
        )
        result = self._transform_result(
            transaction,
            prepared,
            "Metrc and DoobieLogic Package Studio state are verified and synchronized.",
            verified_outputs,
        )
        result["local_result"] = {
            "run_id": local_result.run_id,
            "run_number": local_result.run_number,
            "output_lot_ids": list(local_result.output_lot_ids),
        }
        return result

    def _reconcile_transform(
        self,
        *,
        transaction,
        prepared: dict[str, Any],
        actor: str,
        organization_id: str,
        facility_id: str,
        message: str,
        verified_outputs: list[dict[str, Any]],
        stage: str,
        readback_result: dict[str, Any] | None = None,
        extra_evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.traceability.get_transaction(organization_id, facility_id, transaction.id)
        if current.status in {"submitted", "accepted"}:
            current = self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=current.id,
                new_status="reconciliation_required",
                actor=actor,
                reason=message,
                source="provider_readback" if "readback" in stage else "provider_worker",
                external_reference=verified_outputs[0].get("provider_id", "") if verified_outputs else "",
                error_code="partial_provider_state" if verified_outputs else "provider_outcome_unknown",
                error_message=message,
            )
        self.traceability.record_reconciliation(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=current.id,
            actor=actor,
            provider_state={"verified_outputs": verified_outputs},
            readback_result=readback_result,
            mismatch_reason=message,
            evidence={
                "operation_type": "package_studio_transform",
                "stage": stage,
                "verified_outputs": verified_outputs,
                "provider_atomic": False,
                "blind_retry_allowed": False,
                **dict(extra_evidence or {}),
            },
            retry_eligible=False,
        )
        return self._transform_result(current, prepared, message, verified_outputs)

    @staticmethod
    def _existing_transform(transaction, prepared: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": transaction.status == "verified",
            "verified": transaction.status == "verified",
            "status": transaction.status,
            "transaction_id": transaction.id,
            "external_reference": transaction.external_reference,
            "already_submitted": True,
            "summary": prepared["summary"],
            "verified_outputs": [],
            "message": "This exact Package Studio confirmation already has a durable traceability transaction. Review its status instead of submitting provider creation again.",
        }

    @staticmethod
    def _transform_result(transaction, prepared: dict[str, Any], message: str, verified_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "ok": transaction.status == "verified",
            "verified": transaction.status == "verified",
            "status": transaction.status,
            "transaction_id": transaction.id,
            "external_reference": transaction.external_reference,
            "summary": prepared["summary"],
            "verified_outputs": [
                {key: row.get(key) for key in ("position", "provider_id", "tag", "item", "quantity", "unit")}
                for row in verified_outputs
            ],
            "message": message,
        }
