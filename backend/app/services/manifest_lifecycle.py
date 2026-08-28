from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import requests
from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.doobie_actions.models import ActionExecution, ActionProposal
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.metrc_client import resolve_metrc_base_url
from services.metrc_receiving import fetch_all_delivery_packages, fetch_all_transfer_deliveries
from services.metrc_wholesale import fetch_all_outgoing_transfer_templates, fetch_all_outgoing_transfers


class ManifestLifecycleError(ValueError):
    pass


def _json_dict(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in (result.get("rows") or []) if isinstance(row, dict)]


def _provider_id(row: dict[str, Any]) -> str:
    return _first(row, "Id", "id", "TransferId", "TemplateId")


def _package_label(row: dict[str, Any]) -> str:
    return _first(row, "PackageLabel", "Label", "label", "PackageTag", "Tag")


def _recipient_license(row: dict[str, Any]) -> str:
    return _first(
        row,
        "RecipientLicenseNumber",
        "RecipientFacilityLicenseNumber",
        "DestinationFacilityLicenseNumber",
        "DestinationLicenseNumber",
        "FacilityLicenseNumber",
    )


class ManifestLifecycleService:
    """Read back one employee-approved MA Metrc sandbox manifest workflow.

    The transfer-template POST is only considered verified after the exact
    template is visible through Metrc's outgoing-template GET resource. Final
    manifest availability is a separate state and requires an outgoing transfer
    whose delivery matches the approved recipient license and package labels.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.traceability = TraceabilityBackofficeRepository(engine)

    def inspect(
        self,
        *,
        organization_id: str,
        facility_id: str,
        proposal_id: str,
        actor: str,
        state: str,
        environment: str,
        license_number: str,
        user_api_key: str,
        integrator_api_key: str,
    ) -> dict[str, Any]:
        state = str(state or "").strip().upper()
        environment = str(environment or "").strip().casefold()
        if state != "MA" or environment != "sandbox":
            raise ManifestLifecycleError("Manifest lifecycle verification is currently enabled only for the Massachusetts Metrc sandbox.")

        proposal, transaction_id = self._proposal_and_transaction(
            organization_id=organization_id,
            facility_id=facility_id,
            proposal_id=proposal_id,
        )
        base = {
            "proposal_id": proposal.id,
            "proposal_status": proposal.status,
            "transaction_id": transaction_id,
            "jurisdiction_code": state,
            "environment": environment,
            "template_verified": False,
            "manifest_available": False,
            "manifest_download_available": False,
        }
        if not transaction_id:
            return base | {
                "state": proposal.status,
                "message": "Approve and submit this draft before checking Metrc lifecycle state.",
            }

        transaction = self.traceability.get_transaction(organization_id, facility_id, transaction_id)
        base |= {
            "traceability_status": transaction.status,
            "external_reference": transaction.external_reference,
        }
        if transaction.status in {"queued", "submitted"}:
            return base | {"state": transaction.status, "message": "The provider submission has not reached an accepted state yet."}
        if transaction.status in {"rejected", "reconciliation_required", "cancelled"}:
            return base | {
                "state": transaction.status,
                "message": transaction.error_message or "This manifest action requires reconciliation before verification can continue.",
            }
        if transaction.status not in {"accepted", "verified"}:
            return base | {"state": transaction.status, "message": "The manifest action is not ready for provider readback yet."}

        request_payload = _json_dict(transaction.request_payload_json)
        template = request_payload.get("template") if isinstance(request_payload.get("template"), dict) else {}
        template_name = str(template.get("Name") or "").strip()
        destinations = template.get("Destinations") if isinstance(template.get("Destinations"), list) else []
        first_destination = destinations[0] if destinations and isinstance(destinations[0], dict) else {}
        recipient_license = str(first_destination.get("RecipientLicenseNumber") or "").strip()
        expected_labels = {
            str(row.get("PackageLabel") or "").strip()
            for row in (first_destination.get("Packages") or [])
            if isinstance(row, dict) and str(row.get("PackageLabel") or "").strip()
        }
        if not template_name or not recipient_license or not expected_labels:
            raise ManifestLifecycleError("The durable manifest transaction is missing the approved template identity, recipient license, or package labels.")

        templates_result = fetch_all_outgoing_transfer_templates(
            state=state,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            license_number=license_number,
            environment=environment,
        )
        if not templates_result.get("ok"):
            return base | {
                "state": "readback_unavailable",
                "message": str(templates_result.get("message") or "Metrc outgoing transfer templates could not be loaded."),
            }

        provider_template = self._match_template(
            _rows(templates_result),
            external_reference=transaction.external_reference,
            template_name=template_name,
        )
        if provider_template is None:
            return base | {
                "state": "accepted",
                "message": "Metrc accepted the write, but the exact outgoing transfer template is not visible in readback yet.",
                "template_name": template_name,
            }

        provider_template_id = _provider_id(provider_template)
        if transaction.status == "accepted":
            transaction = self.traceability.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                new_status="verified",
                actor=actor,
                reason="Exact outgoing transfer template was found through Metrc readback after the authenticated write.",
                source="provider_readback",
                external_reference=provider_template_id or transaction.external_reference,
            )

        verified = base | {
            "state": "template_verified",
            "traceability_status": transaction.status,
            "external_reference": transaction.external_reference,
            "template_verified": True,
            "template_id": provider_template_id,
            "template_name": template_name,
            "recipient_license": recipient_license,
            "package_labels": sorted(expected_labels),
            "message": "The exact outgoing transfer template is visible in Metrc. Final manifest issuance remains a separate provider state.",
        }

        transfers_result = fetch_all_outgoing_transfers(
            state=state,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            license_number=license_number,
            environment=environment,
        )
        if not transfers_result.get("ok"):
            return verified | {
                "manifest_readback_error": str(transfers_result.get("message") or "Outgoing transfers could not be loaded."),
            }

        manifest = self._find_matching_manifest(
            transfers=_rows(transfers_result),
            state=state,
            environment=environment,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            recipient_license=recipient_license,
            expected_labels=expected_labels,
        )
        if manifest is None:
            return verified

        return verified | {
            "state": "manifest_available",
            "manifest_available": True,
            "manifest_download_available": True,
            "manifest_transfer_id": manifest["transfer_id"],
            "manifest_number": manifest["manifest_number"],
            "delivery_id": manifest["delivery_id"],
            "message": "The approved shipment now has matching outgoing-transfer evidence in Metrc and its manifest can be retrieved.",
        }

    def manifest_pdf(
        self,
        *,
        organization_id: str,
        facility_id: str,
        proposal_id: str,
        actor: str,
        state: str,
        environment: str,
        license_number: str,
        user_api_key: str,
        integrator_api_key: str,
        timeout_seconds: int = 20,
    ) -> tuple[bytes, str]:
        lifecycle = self.inspect(
            organization_id=organization_id,
            facility_id=facility_id,
            proposal_id=proposal_id,
            actor=actor,
            state=state,
            environment=environment,
            license_number=license_number,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
        )
        transfer_id = str(lifecycle.get("manifest_transfer_id") or "").strip()
        if not lifecycle.get("manifest_available") or not transfer_id:
            raise ManifestLifecycleError("The final Metrc manifest is not available for this approved shipment yet.")
        base_url, state_code = resolve_metrc_base_url(state)
        if not base_url or state_code != "MA" or str(environment).casefold() != "sandbox":
            raise ManifestLifecycleError("The manifest PDF request is not bound to the trusted Massachusetts sandbox.")
        url = f"{base_url.rstrip('/')}/transfers/v2/manifest/{quote(transfer_id, safe='')}/pdf"
        try:
            response = requests.get(
                url,
                auth=(integrator_api_key, user_api_key),
                headers={"Accept": "application/pdf"},
                timeout=timeout_seconds,
            )
        except requests.RequestException as exc:
            raise ManifestLifecycleError(f"Metrc manifest PDF request failed: {exc}") from exc
        if response.status_code == 404:
            raise ManifestLifecycleError("Metrc has not made the final manifest PDF available yet.")
        if response.status_code in {401, 403}:
            raise ManifestLifecycleError("Metrc rejected the saved API keys or manifest permissions.")
        if not response.ok:
            raise ManifestLifecycleError(f"Metrc manifest PDF request returned HTTP {response.status_code}.")
        content = bytes(response.content or b"")
        if not content or len(content) > 20 * 1024 * 1024:
            raise ManifestLifecycleError("Metrc returned an empty or unexpectedly large manifest PDF.")
        content_type = str(response.headers.get("Content-Type") or "application/pdf").split(";", 1)[0].strip()
        if content_type != "application/pdf" and not content.startswith(b"%PDF"):
            raise ManifestLifecycleError("Metrc did not return a PDF document for this manifest.")
        return content, str(lifecycle.get("manifest_number") or transfer_id)

    def _proposal_and_transaction(self, *, organization_id: str, facility_id: str, proposal_id: str) -> tuple[ActionProposal, str]:
        with self.sessions() as session:
            proposal = session.get(ActionProposal, proposal_id)
            if (
                proposal is None
                or proposal.organization_id != organization_id
                or proposal.facility_id != facility_id
                or proposal.action_type != "prepare_transfer_manifest"
            ):
                raise ManifestLifecycleError("Manifest draft was not found in the active facility.")
            execution = session.scalar(
                select(ActionExecution)
                .where(
                    ActionExecution.proposal_id == proposal.id,
                    ActionExecution.status == "succeeded",
                )
                .order_by(ActionExecution.attempt_number.desc())
                .limit(1)
            )
            if execution is None:
                return proposal, ""
            result = _json_dict(execution.result_json)
            return proposal, str(result.get("transaction_id") or "").strip()

    @staticmethod
    def _match_template(rows: list[dict[str, Any]], *, external_reference: str, template_name: str) -> dict[str, Any] | None:
        external_reference = str(external_reference or "").strip()
        if external_reference:
            for row in rows:
                if _provider_id(row) == external_reference:
                    return row
        for row in rows:
            if _first(row, "Name", "name") == template_name:
                return row
        return None

    @staticmethod
    def _find_matching_manifest(
        *,
        transfers: list[dict[str, Any]],
        state: str,
        environment: str,
        user_api_key: str,
        integrator_api_key: str,
        recipient_license: str,
        expected_labels: set[str],
    ) -> dict[str, str] | None:
        for transfer in transfers[:100]:
            transfer_id = _provider_id(transfer)
            if not transfer_id:
                continue
            deliveries_result = fetch_all_transfer_deliveries(
                state=state,
                user_api_key=user_api_key,
                integrator_api_key=integrator_api_key,
                transfer_id=transfer_id,
                environment=environment,
            )
            if not deliveries_result.get("ok"):
                continue
            transfer_recipient = _recipient_license(transfer)
            for delivery in _rows(deliveries_result):
                delivery_id = _provider_id(delivery)
                if not delivery_id:
                    continue
                provider_recipient = _recipient_license(delivery) or transfer_recipient
                if not provider_recipient or provider_recipient != recipient_license:
                    continue
                packages_result = fetch_all_delivery_packages(
                    state=state,
                    user_api_key=user_api_key,
                    integrator_api_key=integrator_api_key,
                    delivery_id=delivery_id,
                    environment=environment,
                )
                if not packages_result.get("ok"):
                    continue
                provider_labels = {_package_label(row) for row in _rows(packages_result) if _package_label(row)}
                if not expected_labels.issubset(provider_labels):
                    continue
                manifest_number = _first(
                    transfer,
                    "ManifestNumber",
                    "manifestNumber",
                    "Manifest",
                    "manifest",
                    "Name",
                    "name",
                ) or transfer_id
                return {
                    "transfer_id": transfer_id,
                    "delivery_id": delivery_id,
                    "manifest_number": manifest_number,
                }
        return None
