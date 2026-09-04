from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import AuditEvent, InventoryLot, InventoryTransaction, Product, utc_now
from modules.inventory_availability.service import InventoryAvailabilityService
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from modules.traceability.object_links import TraceabilityObjectLinkRepository
from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_lifecycle import (
    LIFECYCLE_EVALUATION_ACTIONS,
    MetrcLifecycleEvaluationError,
    build_lifecycle_evaluation_payload,
    execute_lifecycle_evaluation_action,
)
from .metrc_package_readback import canonical_unit, package_snapshot, verify_package_state
from .metrc_package_reference import MetrcPackageReferenceError, fetch_package_adjustment_reasons


PROMOTED_PACKAGE_ACTIONS = frozenset({"package_adjust", "package_item", "package_finish", "package_unfinish"})


class MetrcPackageActionError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def package_confirmation_token(
    *,
    prepared: dict[str, Any],
    state: str,
    environment: str,
    license_number: str,
    confirmation_id: str,
) -> str:
    operation = str(prepared.get("operation_type") or "").strip().casefold()
    if operation not in PROMOTED_PACKAGE_ACTIONS:
        raise MetrcPackageActionError("This package action has not passed the current operator promotion gate.")
    document = {
        "confirmation_id": str(confirmation_id or "").strip(),
        "operation_type": operation,
        "state": str(state or "").strip().upper(),
        "environment": str(environment or "").strip().casefold(),
        "license_number": str(license_number or "").strip(),
        "entity_type": prepared.get("entity_type"),
        "entity_id": prepared.get("entity_id"),
        "provider_payload": prepared.get("provider_payload"),
        "fingerprint_context": prepared.get("fingerprint_context"),
    }
    if not document["confirmation_id"]:
        raise MetrcPackageActionError("A confirmation ID is required.")
    return sha256(_canonical(document).encode("utf-8")).hexdigest()


class MetrcPackageActionService:
    """Govern exact MA sandbox package writes around the append-only local ledger."""

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
            raise MetrcPackageActionError(
                "Promoted package writes are currently restricted to the verified Massachusetts Metrc sandbox."
            )
        if not license_value:
            raise MetrcPackageActionError("An exact Massachusetts sandbox facility license is required.")
        return state_code, env, license_value

    def _lot_state(self, organization_id: str, facility_id: str, lot_id: str) -> dict[str, Any]:
        with self.sessions() as session:
            lot = session.get(InventoryLot, lot_id)
            if not lot or lot.organization_id != organization_id or lot.facility_id != facility_id:
                raise MetrcPackageActionError("Inventory package was not found in the active facility.")
            product = session.get(Product, lot.product_id)
            if not product or product.organization_id != organization_id:
                raise MetrcPackageActionError("Inventory package has no valid Product Master identity.")
            balance = float(session.scalar(select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                InventoryTransaction.organization_id == organization_id,
                InventoryTransaction.facility_id == facility_id,
                InventoryTransaction.lot_id == lot.id,
            )) or 0.0)
            unit = session.scalar(select(InventoryTransaction.unit).where(InventoryTransaction.lot_id == lot.id).order_by(InventoryTransaction.occurred_at.desc()).limit(1)) or product.base_unit
            return {
                "lot_id": lot.id,
                "lot_code": lot.lot_code,
                "package_label": lot.compliance_package_id,
                "product_id": product.id,
                "product_name": product.name,
                "balance": balance,
                "unit": str(unit),
                "status": str(lot.status or ""),
            }

    def _verified_link(self, *, organization_id: str, facility_id: str, environment: str, entity_type: str, entity_id: str, resource: str, license_number: str):
        link = self.links.get_local(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            environment=environment,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        if not link or link.status != "verified" or link.provider_resource != resource or link.license_number != license_number:
            raise MetrcPackageActionError(f"This {entity_type.replace('_', ' ')} is not linked to an exact verified Metrc {resource.rstrip('s').title()} identity.")
        return link

    def _fresh_package(self, *, provider_id: str, state: str, environment: str, license_number: str, integrator_api_key: str, user_api_key: str) -> dict[str, Any]:
        readback = fetch_metrc_resource(
            state=state,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            resource="packages_by_id",
            environment=environment,
            license_number=license_number,
            path_parameters={"id": provider_id},
        )
        snapshot = package_snapshot(readback)
        if not snapshot.get("ok") or snapshot.get("provider_id") != str(provider_id).strip():
            raise MetrcPackageActionError(
                str((readback or {}).get("message") if isinstance(readback, dict) else "")
                or "Fresh exact Metrc package readback failed."
            )
        return {"readback": readback, "snapshot": snapshot}

    def _validated_current(self, *, organization_id: str, facility_id: str, lot_id: str, state: str, environment: str, license_number: str, integrator_api_key: str, user_api_key: str) -> dict[str, Any]:
        local = self._lot_state(organization_id, facility_id, lot_id)
        package_link = self._verified_link(
            organization_id=organization_id,
            facility_id=facility_id,
            environment=environment,
            entity_type="inventory_lot",
            entity_id=lot_id,
            resource="packages",
            license_number=license_number,
        )
        product_link = self._verified_link(
            organization_id=organization_id,
            facility_id=facility_id,
            environment=environment,
            entity_type="product",
            entity_id=local["product_id"],
            resource="items",
            license_number=license_number,
        )
        fresh = self._fresh_package(
            provider_id=package_link.provider_id,
            state=state,
            environment=environment,
            license_number=license_number,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        verification = verify_package_state(
            readback=fresh["readback"],
            provider_id=package_link.provider_id,
            expected_label=package_link.provider_label or local["package_label"],
            expected_item=product_link.provider_label,
            expected_quantity=local["balance"],
            expected_unit=local["unit"],
        )
        if not verification["matched"]:
            raise MetrcPackageActionError(
                "DoobieLogic and the linked Metrc Package no longer agree on identity, item, quantity, or unit. Reconcile the package before submitting another provider write."
            )
        return {
            "local": local,
            "package_link": package_link,
            "product_link": product_link,
            "readback": fresh["readback"],
            "snapshot": fresh["snapshot"],
        }

    def prepare(
        self,
        *,
        organization_id: str,
        facility_id: str,
        operation_type: str,
        lot_id: str,
        actual_date: str,
        quantity_delta: float = 0.0,
        adjustment_reason: str = "",
        reason_note: str = "",
        target_product_id: str = "",
        reason: str = "",
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        state_code, env, license_value = self._scope(state, environment, license_number)
        operation = str(operation_type or "").strip().casefold()
        if operation not in PROMOTED_PACKAGE_ACTIONS:
            raise MetrcPackageActionError("This package action has not passed the current operator promotion gate.")
        entity = str(lot_id or "").strip()
        action_date = str(actual_date or "").strip()
        if not entity or not action_date:
            raise MetrcPackageActionError("The exact local package and action date are required.")
        current = self._validated_current(
            organization_id=organization_id,
            facility_id=facility_id,
            lot_id=entity,
            state=state_code,
            environment=env,
            license_number=license_value,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        local = current["local"]
        package_link = current["package_link"]
        snapshot = current["snapshot"]
        payload: dict[str, Any]
        summary: dict[str, Any]
        target_product = None
        target_link = None
        expected = {
            "label": package_link.provider_label,
            "item": current["product_link"].provider_label,
            "quantity": local["balance"],
            "unit": snapshot.get("unit_of_measure") or local["unit"],
            "finished": snapshot.get("finished"),
        }

        if operation == "package_adjust":
            delta = float(quantity_delta or 0.0)
            if abs(delta) <= 1e-9:
                raise MetrcPackageActionError("Package adjustment must change the quantity.")
            final = float(local["balance"]) + delta
            if final < -1e-9:
                raise MetrcPackageActionError("Package adjustment cannot produce a negative final quantity.")
            availability = InventoryAvailabilityService(self.engine).facility_snapshot(organization_id, facility_id)
            reserved = max(0.0, float((availability.get("by_lot") or {}).get(entity, {}).get("reserved", 0.0) or 0.0))
            if final + 1e-9 < reserved:
                raise MetrcPackageActionError(f"Final package quantity cannot be below {reserved:g} committed or reserved locally.")
            try:
                references = fetch_package_adjustment_reasons(
                    state=state_code,
                    environment=env,
                    integrator_api_key=integrator_api_key,
                    user_api_key=user_api_key,
                )["items"]
            except MetrcPackageReferenceError as exc:
                raise MetrcPackageActionError(str(exc)) from exc
            selected_reason = str(adjustment_reason or "").strip()
            match = next((item for item in references if item.casefold() == selected_reason.casefold()), "")
            if not match:
                raise MetrcPackageActionError("Choose an exact current Metrc package adjustment reason.")
            payload = {
                "package_id": int(package_link.provider_id),
                "label": package_link.provider_label,
                "quantity": delta,
                "unit_of_measure": snapshot.get("unit_of_measure") or local["unit"],
                "adjustment_reason": match,
                "adjustment_date": action_date,
                "reason_note": str(reason_note or "").strip(),
            }
            expected["quantity"] = final
            summary = {
                "title": "Adjust package quantity",
                "package": package_link.provider_label,
                "current_quantity": local["balance"],
                "change": delta,
                "final_quantity": final,
                "unit": payload["unit_of_measure"],
                "adjustment_reason": match,
                "actual_date": action_date,
            }
        elif operation == "package_item":
            target_id = str(target_product_id or "").strip()
            if not target_id:
                raise MetrcPackageActionError("Choose the DoobieLogic Product this package should become.")
            with self.sessions() as session:
                target_product = session.get(Product, target_id)
                if not target_product or target_product.organization_id != organization_id or not target_product.active:
                    raise MetrcPackageActionError("Target Product was not found or is inactive.")
            if target_product.id == local["product_id"]:
                raise MetrcPackageActionError("The package already uses that Product identity.")
            target_link = self._verified_link(
                organization_id=organization_id,
                facility_id=facility_id,
                environment=env,
                entity_type="product",
                entity_id=target_product.id,
                resource="items",
                license_number=license_value,
            )
            payload = {"package_id": int(package_link.provider_id), "label": package_link.provider_label, "item": target_link.provider_label}
            expected["item"] = target_link.provider_label
            summary = {
                "title": "Change package item",
                "package": package_link.provider_label,
                "from_product": local["product_name"],
                "to_product": target_product.name,
                "metrc_item": target_link.provider_label,
            }
        elif operation == "package_finish":
            if snapshot.get("finished") is True:
                raise MetrcPackageActionError("Metrc already reports this package as finished.")
            if snapshot.get("finished") is None:
                raise MetrcPackageActionError("Fresh Metrc readback cannot prove the package is currently unfinished.")
            payload = {"package_id": int(package_link.provider_id), "label": package_link.provider_label, "actual_date": action_date}
            expected["finished"] = True
            summary = {"title": "Finish package", "package": package_link.provider_label, "quantity": local["balance"], "unit": local["unit"], "actual_date": action_date}
        else:
            if snapshot.get("finished") is not True:
                raise MetrcPackageActionError("Only a package freshly verified as finished can be reopened.")
            if local["status"].casefold() != "finished":
                raise MetrcPackageActionError("Local package is not in the governed finished state; reconcile before reopening it in Metrc.")
            with self.sessions() as session:
                prior = session.scalar(select(AuditEvent).where(
                    AuditEvent.organization_id == organization_id,
                    AuditEvent.facility_id == facility_id,
                    AuditEvent.entity_type == "inventory_lot",
                    AuditEvent.entity_id == entity,
                    AuditEvent.action == "metrc_package_finished",
                ).order_by(AuditEvent.created_at.desc()).limit(1))
            if prior is None:
                raise MetrcPackageActionError("No governed local finish evidence exists for this package, so its prior local status cannot be restored safely.")
            payload = {"package_id": int(package_link.provider_id), "label": package_link.provider_label}
            expected["finished"] = False
            summary = {"title": "Reopen package", "package": package_link.provider_label, "quantity": local["balance"], "unit": local["unit"]}

        body = build_lifecycle_evaluation_payload(operation, payload)
        return {
            "operation_type": operation,
            "evaluator_operation": operation,
            "entity_type": "inventory_lot",
            "entity_id": entity,
            "provider_payload": payload,
            "provider_request_body": body,
            "expected_provider_state": expected,
            "summary": summary,
            "fingerprint_context": {
                "local_balance": local["balance"],
                "local_unit": local["unit"],
                "local_product_id": local["product_id"],
                "local_status": local["status"],
                "package_link_id": package_link.id,
                "package_provider_id": package_link.provider_id,
                "package_last_modified": snapshot.get("last_modified"),
                "target_product_id": getattr(target_product, "id", "") if target_product is not None else "",
                "target_item_link_id": getattr(target_link, "id", "") if target_link is not None else "",
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
        lot_id: str,
        actual_date: str,
        confirmation_id: str,
        confirmation_token: str,
        quantity_delta: float = 0.0,
        adjustment_reason: str = "",
        reason_note: str = "",
        target_product_id: str = "",
        reason: str = "",
        state: str,
        environment: str,
        license_number: str,
        integrator_api_key: str,
        user_api_key: str,
    ) -> dict[str, Any]:
        prepared = self.prepare(
            organization_id=organization_id,
            facility_id=facility_id,
            operation_type=operation_type,
            lot_id=lot_id,
            actual_date=actual_date,
            quantity_delta=quantity_delta,
            adjustment_reason=adjustment_reason,
            reason_note=reason_note,
            target_product_id=target_product_id,
            reason=reason,
            state=state,
            environment=environment,
            license_number=license_number,
            integrator_api_key=integrator_api_key,
            user_api_key=user_api_key,
        )
        state_code, env, license_value = self._scope(state, environment, license_number)
        expected_token = package_confirmation_token(
            prepared=prepared,
            state=state_code,
            environment=env,
            license_number=license_value,
            confirmation_id=confirmation_id,
        )
        if str(confirmation_token or "").strip() != expected_token:
            raise MetrcPackageActionError("The package state changed after preview. Review the current package again before submitting to Metrc.")
        operation = prepared["operation_type"]
        spec = LIFECYCLE_EVALUATION_ACTIONS[operation]
        transaction = self.traceability.create_transaction(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            operation_type=operation,
            entity_type="inventory_lot",
            entity_id=lot_id,
            idempotency_key=f"metrc-package:{facility_id}:{confirmation_id}:{expected_token}",
            actor=actor,
            license_number=license_value,
            jurisdiction=state_code,
            environment=env,
            request_payload={
                "operator_payload": prepared["provider_payload"],
                "provider_request": {"method": spec.method, "path": spec.path, "query": {"licenseNumber": license_value}, "body": prepared["provider_request_body"]},
                "confirmation_id": confirmation_id,
                "local_state": prepared["fingerprint_context"],
            },
            reason=str(reason or prepared["summary"].get("title") or operation),
        )
        transaction, claimed = self.traceability.claim_transition_logged(
            organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id,
            expected_status="requested", new_status="validated", actor=actor,
            reason="Exact MA sandbox package identity, local/provider state, provider payload, and human confirmation fingerprint validated.", source="system",
        )
        if not claimed:
            return self._existing(transaction, prepared)
        transaction = self.traceability.transition_logged(
            organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id,
            new_status="queued", actor=actor, reason="Human-confirmed package action queued for immediate controlled execution.", source="system",
        )
        transaction = self.traceability.transition_logged(
            organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id,
            new_status="submitted", actor=actor, reason=f"Beginning authenticated {spec.method} /{spec.path} against the trusted Massachusetts sandbox mapping.", source="provider_worker",
        )
        try:
            evidence = execute_lifecycle_evaluation_action(
                operation_type=operation,
                payload=prepared["provider_payload"],
                license_number=license_value,
                integrator_api_key=integrator_api_key,
                user_api_key=user_api_key,
                state=state_code,
                environment=env,
            )
        except MetrcLifecycleEvaluationError as exc:
            return self._unknown(transaction, prepared, actor, organization_id, facility_id, str(exc))

        http_status = int(evidence.get("http_status") or 0)
        self.traceability.record_attempt(
            organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id,
            request_payload=evidence.get("request") if isinstance(evidence.get("request"), dict) else {"operation_type": operation},
            response_payload=evidence.get("response") if isinstance(evidence.get("response"), dict) else {"response": evidence.get("response")},
            http_status=http_status or None,
            error_code="" if http_status == 200 else "provider_rejected",
            error_message="" if http_status == 200 else str(evidence.get("message") or "Metrc rejected the package write."),
        )
        if http_status != 200:
            uncertain = http_status == 0 or http_status == 429 or http_status >= 500
            target = "reconciliation_required" if uncertain else "rejected"
            transaction = self.traceability.transition_logged(
                organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id,
                new_status=target, actor=actor, reason=str(evidence.get("message") or "Metrc did not accept the package write."), source="provider_worker",
                error_code="provider_outcome_unknown" if uncertain else "provider_rejected", error_message=str(evidence.get("message") or ""),
            )
            if uncertain:
                self.traceability.record_reconciliation(
                    organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id, actor=actor,
                    mismatch_reason=str(evidence.get("message") or "Provider outcome is unknown."),
                    evidence={"operation_type": operation, "stage": "provider_response", "provider_atomic": True, "blind_retry_allowed": False}, retry_eligible=False,
                )
            return self._result(transaction, prepared, str(evidence.get("message") or "Metrc rejected the package write."))

        provider_id = str(evidence.get("provider_id") or prepared["fingerprint_context"]["package_provider_id"])
        transaction = self.traceability.transition_logged(
            organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id,
            new_status="accepted", actor=actor,
            reason="Metrc returned HTTP 200. Fresh semantic package readback and the local commit are still required before verification.",
            source="provider_worker", external_reference=provider_id,
            response_payload=evidence.get("response") if isinstance(evidence.get("response"), dict) else {"response": evidence.get("response")},
        )
        expected = prepared["expected_provider_state"]
        verification = verify_package_state(
            readback=evidence.get("readback"),
            provider_id=provider_id,
            expected_label=expected.get("label") or "",
            expected_item=expected.get("item") or "",
            expected_quantity=expected.get("quantity"),
            expected_unit=expected.get("unit") or "",
            expected_finished=expected.get("finished"),
        )
        provider_verified = bool(evidence.get("passed")) and bool(verification.get("matched"))
        self.traceability.record_reconciliation(
            organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id, actor=actor,
            provider_state={"provider_id": provider_id, "http_status": http_status, "last_modified": str(evidence.get("last_modified") or "")},
            readback_result=evidence.get("readback") if isinstance(evidence.get("readback"), dict) else None,
            mismatch_reason="" if provider_verified else "Fresh Metrc package readback did not match the confirmed semantic post-state.",
            evidence={"operation_type": operation, "provider_verified": provider_verified, "semantic_verification": verification, "provider_atomic": True, "blind_retry_allowed": False},
            retry_eligible=False,
        )
        if not provider_verified:
            transaction = self.traceability.transition_logged(
                organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id,
                new_status="reconciliation_required", actor=actor,
                reason="Metrc accepted the write, but fresh readback did not verify the confirmed package state. Do not repeat the write blindly.",
                source="provider_readback", external_reference=provider_id, error_code="readback_not_verified",
                error_message="Fresh provider package state does not match the confirmed post-state.",
            )
            return self._result(transaction, prepared, "Metrc accepted the write, but semantic verification requires reconciliation.")
        try:
            local_result = self._apply_local(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                prepared=prepared,
                transaction_id=transaction.id,
            )
        except Exception as exc:
            transaction = self.traceability.transition_logged(
                organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id,
                new_status="reconciliation_required", actor=actor,
                reason="Metrc state was verified, but the corresponding local package commit failed. Provider write must not be repeated blindly.",
                source="local_commit", external_reference=provider_id, error_code="local_commit_failed", error_message=str(exc),
            )
            self.traceability.record_reconciliation(
                organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id, actor=actor,
                mismatch_reason=str(exc), evidence={"operation_type": operation, "provider_verified": True, "local_commit_failed": True, "provider_atomic": True, "blind_retry_allowed": False}, retry_eligible=False,
            )
            return self._result(transaction, prepared, "Metrc is verified, but DoobieLogic local state requires reconciliation.")
        transaction = self.traceability.transition_logged(
            organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id,
            new_status="verified", actor=actor,
            reason="Fresh Metrc readback verified the confirmed package state and the matching local commit completed.",
            source="provider_readback", external_reference=provider_id,
        )
        result = self._result(transaction, prepared, "Metrc and DoobieLogic package state are verified and synchronized.")
        result["local_result"] = local_result
        return result

    def _apply_local(self, *, organization_id: str, facility_id: str, actor: str, prepared: dict[str, Any], transaction_id: str) -> dict[str, Any]:
        operation = prepared["operation_type"]
        context = prepared["fingerprint_context"]
        with self.sessions.begin() as session:
            lot = session.scalar(select(InventoryLot).where(
                InventoryLot.id == prepared["entity_id"],
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
            ).with_for_update())
            if not lot:
                raise MetrcPackageActionError("Local inventory package disappeared after provider verification.")
            current_balance = float(session.scalar(select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                InventoryTransaction.organization_id == organization_id,
                InventoryTransaction.facility_id == facility_id,
                InventoryTransaction.lot_id == lot.id,
            )) or 0.0)
            if abs(current_balance - float(context["local_balance"])) > 1e-6 or lot.product_id != context["local_product_id"] or str(lot.status or "") != context["local_status"]:
                raise MetrcPackageActionError("Local package changed after provider confirmation and cannot be committed automatically.")
            changes: dict[str, Any] = {"traceability_transaction_id": transaction_id}
            if operation == "package_adjust":
                delta = float(prepared["provider_payload"]["quantity"])
                unit = str(context["local_unit"])
                session.add(InventoryTransaction(
                    organization_id=organization_id, facility_id=facility_id, lot_id=lot.id,
                    transaction_type="inventory_adjustment", quantity_delta=delta, unit=unit,
                    reason=str(prepared["provider_payload"]["adjustment_reason"]),
                    reference=str(prepared["provider_payload"].get("reason_note") or "")[:255], actor=actor,
                ))
                changes |= {"previous_quantity": current_balance, "delta": delta, "final_quantity": current_balance + delta, "unit": unit}
                action = "metrc_package_adjusted"
            elif operation == "package_item":
                target_product_id = str(context["target_product_id"])
                target = session.get(Product, target_product_id)
                if not target or target.organization_id != organization_id or not target.active:
                    raise MetrcPackageActionError("Target Product changed after provider verification.")
                old_product_id = lot.product_id
                lot.product_id = target.id
                changes |= {"previous_product_id": old_product_id, "product_id": target.id, "metrc_item": prepared["provider_payload"]["item"]}
                action = "metrc_package_item_changed"
            elif operation == "package_finish":
                old_status = str(lot.status or "")
                lot.status = "finished"
                changes |= {"previous_status": old_status, "status": "finished"}
                action = "metrc_package_finished"
            else:
                prior = session.scalar(select(AuditEvent).where(
                    AuditEvent.organization_id == organization_id,
                    AuditEvent.facility_id == facility_id,
                    AuditEvent.entity_type == "inventory_lot",
                    AuditEvent.entity_id == lot.id,
                    AuditEvent.action == "metrc_package_finished",
                ).order_by(AuditEvent.created_at.desc()).limit(1))
                if not prior:
                    raise MetrcPackageActionError("The prior governed package status could not be recovered.")
                try:
                    previous = json.loads(prior.changes_json or "{}")
                except (TypeError, ValueError) as exc:
                    raise MetrcPackageActionError("The prior governed package status evidence is unreadable.") from exc
                restore = str(previous.get("previous_status") or "").strip()
                if not restore or restore.casefold() == "finished":
                    raise MetrcPackageActionError("The prior local package status cannot be restored safely.")
                lot.status = restore
                changes |= {"previous_status": "finished", "status": restore, "source_finish_audit_id": prior.id}
                action = "metrc_package_reopened"
            session.add(AuditEvent(
                organization_id=organization_id, facility_id=facility_id, entity_type="inventory_lot", entity_id=lot.id,
                action=action, actor=actor, changes_json=json.dumps(changes, sort_keys=True),
            ))
            return {"lot_id": lot.id, "action": action, **changes}

    def _unknown(self, transaction, prepared, actor: str, organization_id: str, facility_id: str, message: str) -> dict[str, Any]:
        self.traceability.record_attempt(
            organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id,
            request_payload={"operation_type": prepared["operation_type"], "payload": prepared["provider_payload"]},
            error_code="provider_outcome_unknown", error_message=message,
        )
        transaction = self.traceability.transition_logged(
            organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id,
            new_status="reconciliation_required", actor=actor,
            reason="The Metrc package call did not produce evidence sufficient to classify the provider outcome. Blind retry is blocked.",
            source="provider_worker", error_code="provider_outcome_unknown", error_message=message,
        )
        self.traceability.record_reconciliation(
            organization_id=organization_id, facility_id=facility_id, transaction_id=transaction.id, actor=actor,
            mismatch_reason=message, evidence={"operation_type": prepared["operation_type"], "stage": "execution_exception", "provider_atomic": True, "blind_retry_allowed": False}, retry_eligible=False,
        )
        return self._result(transaction, prepared, message)

    @staticmethod
    def _existing(transaction, prepared: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": transaction.status == "verified", "verified": transaction.status == "verified", "status": transaction.status,
            "transaction_id": transaction.id, "external_reference": transaction.external_reference, "already_submitted": True,
            "summary": prepared["summary"],
            "message": "This exact confirmation already has a durable traceability transaction. Review its current status before any new action.",
        }

    @staticmethod
    def _result(transaction, prepared: dict[str, Any], message: str) -> dict[str, Any]:
        return {
            "ok": transaction.status == "verified", "verified": transaction.status == "verified", "status": transaction.status,
            "transaction_id": transaction.id, "external_reference": transaction.external_reference,
            "summary": prepared["summary"], "message": message,
        }
