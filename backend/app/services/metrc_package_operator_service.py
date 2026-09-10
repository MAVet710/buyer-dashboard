from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select

from modules.coman.models import AuditEvent, InventoryLot, InventoryTransaction
from services.metrc_evaluation_lifecycle import build_lifecycle_evaluation_payload

from .metrc_package_actions import MetrcPackageActionError, MetrcPackageActionService


class GovernedMetrcPackageActionService(MetrcPackageActionService):
    """Operator boundary for package writes whose current provider state is provable."""

    def prepare(self, **kwargs: Any) -> dict[str, Any]:
        operation = str(kwargs.get("operation_type") or "").strip().casefold()
        try:
            prepared = self._prepare_unfinish(**kwargs) if operation == "package_unfinish" else super().prepare(**kwargs)
        except MetrcPackageActionError:
            raise
        except (TypeError, ValueError) as exc:
            raise MetrcPackageActionError(
                "The linked Metrc package identity or reviewed package values are not valid for the promoted write contract."
            ) from exc

        operation = str(prepared.get("operation_type") or "").strip().casefold()
        if operation in {"package_adjust", "package_item"}:
            finished = (prepared.get("expected_provider_state") or {}).get("finished")
            if finished is True:
                raise MetrcPackageActionError(
                    "This Metrc package is finished. Reopen it through the governed package workflow before changing quantity or item."
                )
            if finished is not False:
                raise MetrcPackageActionError(
                    "Fresh Metrc readback cannot prove this package is unfinished, so quantity/item mutation remains blocked."
                )
        return prepared

    def _prepare_unfinish(self, **kwargs: Any) -> dict[str, Any]:
        organization_id = str(kwargs.get("organization_id") or "").strip()
        facility_id = str(kwargs.get("facility_id") or "").strip()
        entity = str(kwargs.get("lot_id") or "").strip()
        action_date = str(kwargs.get("actual_date") or "").strip()
        state_code, env, license_value = self._scope(
            str(kwargs.get("state") or ""),
            str(kwargs.get("environment") or ""),
            str(kwargs.get("license_number") or ""),
        )
        if not entity or not action_date:
            raise MetrcPackageActionError("The exact local package and action date are required.")

        current = self._validated_current(
            organization_id=organization_id,
            facility_id=facility_id,
            lot_id=entity,
            state=state_code,
            environment=env,
            license_number=license_value,
            integrator_api_key=str(kwargs.get("integrator_api_key") or ""),
            user_api_key=str(kwargs.get("user_api_key") or ""),
        )
        local = current["local"]
        package_link = current["package_link"]
        snapshot = current["snapshot"]
        if snapshot.get("finished") is not True:
            raise MetrcPackageActionError("Only a package freshly verified as finished can be reopened.")
        if local["status"].casefold() != "finished":
            raise MetrcPackageActionError(
                "Local package is not in the governed finished state; reconcile before reopening it in Metrc."
            )
        with self.sessions() as session:
            prior = session.scalar(
                select(AuditEvent)
                .where(
                    AuditEvent.organization_id == organization_id,
                    AuditEvent.facility_id == facility_id,
                    AuditEvent.entity_type == "inventory_lot",
                    AuditEvent.entity_id == entity,
                    AuditEvent.action == "metrc_package_finished",
                )
                .order_by(AuditEvent.occurred_at.desc())
                .limit(1)
            )
        if prior is None:
            raise MetrcPackageActionError(
                "No governed local finish evidence exists for this package, so its prior local status cannot be restored safely."
            )

        payload = {"package_id": int(package_link.provider_id), "label": package_link.provider_label}
        expected = {
            "label": package_link.provider_label,
            "item": current["product_link"].provider_label,
            "quantity": local["balance"],
            "unit": snapshot.get("unit_of_measure") or local["unit"],
            "finished": False,
        }
        body = build_lifecycle_evaluation_payload("package_unfinish", payload)
        return {
            "operation_type": "package_unfinish",
            "evaluator_operation": "package_unfinish",
            "entity_type": "inventory_lot",
            "entity_id": entity,
            "provider_payload": payload,
            "provider_request_body": body,
            "expected_provider_state": expected,
            "summary": {
                "title": "Reopen package",
                "package": package_link.provider_label,
                "quantity": local["balance"],
                "unit": local["unit"],
            },
            "fingerprint_context": {
                "local_balance": local["balance"],
                "local_unit": local["unit"],
                "local_product_id": local["product_id"],
                "local_status": local["status"],
                "package_link_id": package_link.id,
                "package_provider_id": package_link.provider_id,
                "package_last_modified": snapshot.get("last_modified"),
                "target_product_id": "",
                "target_item_link_id": "",
                "reason": str(kwargs.get("reason") or "").strip(),
            },
        }

    def _apply_local(
        self,
        *,
        organization_id: str,
        facility_id: str,
        actor: str,
        prepared: dict[str, Any],
        transaction_id: str,
    ) -> dict[str, Any]:
        if str(prepared.get("operation_type") or "").strip().casefold() != "package_unfinish":
            return super()._apply_local(
                organization_id=organization_id,
                facility_id=facility_id,
                actor=actor,
                prepared=prepared,
                transaction_id=transaction_id,
            )

        context = prepared["fingerprint_context"]
        with self.sessions.begin() as session:
            lot = session.scalar(
                select(InventoryLot)
                .where(
                    InventoryLot.id == prepared["entity_id"],
                    InventoryLot.organization_id == organization_id,
                    InventoryLot.facility_id == facility_id,
                )
                .with_for_update()
            )
            if not lot:
                raise MetrcPackageActionError("Local inventory package disappeared after provider verification.")
            current_balance = float(
                session.scalar(
                    select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                        InventoryTransaction.organization_id == organization_id,
                        InventoryTransaction.facility_id == facility_id,
                        InventoryTransaction.lot_id == lot.id,
                    )
                )
                or 0.0
            )
            if (
                abs(current_balance - float(context["local_balance"])) > 1e-6
                or lot.product_id != context["local_product_id"]
                or str(lot.status or "") != context["local_status"]
            ):
                raise MetrcPackageActionError(
                    "Local package changed after provider confirmation and cannot be committed automatically."
                )

            prior = session.scalar(
                select(AuditEvent)
                .where(
                    AuditEvent.organization_id == organization_id,
                    AuditEvent.facility_id == facility_id,
                    AuditEvent.entity_type == "inventory_lot",
                    AuditEvent.entity_id == lot.id,
                    AuditEvent.action == "metrc_package_finished",
                )
                .order_by(AuditEvent.occurred_at.desc())
                .limit(1)
            )
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
            changes = {
                "traceability_transaction_id": transaction_id,
                "previous_status": "finished",
                "status": restore,
                "source_finish_audit_id": prior.id,
            }
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="inventory_lot",
                    entity_id=lot.id,
                    action="metrc_package_reopened",
                    actor=actor,
                    changes_json=json.dumps(changes, sort_keys=True),
                )
            )
            return {"lot_id": lot.id, "action": "metrc_package_reopened", **changes}
