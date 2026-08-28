"""Fail-closed contracts for controlled Metrc mutations.

A documented endpoint is not enough to enable a write. Each contract records the
exact operation, endpoint, jurisdiction/environment scope, approval requirement,
and whether DoobieLogic has a verified deterministic payload implementation.
Operations without a verified payload contract remain visible to operators and
Doobie Agent as known capability gaps, but they cannot dispatch a network write.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .registry import DOCUMENTATION_VERIFIED_JURISDICTIONS, get_jurisdiction, require_capability


@dataclass(frozen=True)
class MetrcWriteContract:
    operation_type: str
    capability: str
    method: str
    path: str
    entity_type: str
    risk_level: str = "compliance"
    approval_required: bool = True
    dispatch_enabled: bool = False
    jurisdictions: frozenset[str] = frozenset()
    environments: frozenset[str] = frozenset({"sandbox", "production"})
    verification_resource: str = ""
    evidence_endpoint: str = ""
    note: str = ""

    def public(self, *, jurisdiction: str = "", environment: str = "") -> dict[str, object]:
        code = str(jurisdiction or "").strip().upper()
        env = str(environment or "").strip().casefold()
        in_scope = bool(
            (not code or code in self.jurisdictions)
            and (not env or env in self.environments)
        )
        return {
            "operation_type": self.operation_type,
            "capability": self.capability,
            "method": self.method,
            "path": self.path,
            "entity_type": self.entity_type,
            "risk_level": self.risk_level,
            "approval_required": self.approval_required,
            "dispatch_enabled": self.dispatch_enabled and in_scope,
            "payload_contract_verified": self.dispatch_enabled,
            "jurisdictions": sorted(self.jurisdictions),
            "environments": sorted(self.environments),
            "verification_resource": self.verification_resource,
            "evidence_endpoint": self.evidence_endpoint or f"{self.method} /{self.path.lstrip('/')}",
            "note": self.note,
        }


_VERIFIED_V2_PACKAGE_WRITES = frozenset(DOCUMENTATION_VERIFIED_JURISDICTIONS)

METRC_WRITE_CONTRACTS: dict[str, MetrcWriteContract] = {
    "package_adjust": MetrcWriteContract(
        operation_type="package_adjust",
        capability="package_adjustments",
        method="PUT",
        path="packages/v2/adjust",
        entity_type="package",
        dispatch_enabled=True,
        jurisdictions=_VERIFIED_V2_PACKAGE_WRITES,
        verification_resource="packages_active",
        evidence_endpoint="PUT /packages/v2/adjust",
        note="Deterministic quantity-delta payload is validated before dispatch; provider acceptance is followed by local reconciliation.",
    ),
    "package_finish": MetrcWriteContract(
        operation_type="package_finish",
        capability="package_finish_unfinish",
        method="PUT",
        path="packages/v2/finish",
        entity_type="package",
        dispatch_enabled=True,
        jurisdictions=_VERIFIED_V2_PACKAGE_WRITES,
        verification_resource="packages_active",
        evidence_endpoint="PUT /packages/v2/finish",
        note="Finish payload is deterministic and human approval is required for Doobie Agent proposals.",
    ),
    "transfer_template_create": MetrcWriteContract(
        operation_type="transfer_template_create",
        capability="transfer_templates",
        method="POST",
        path="transfers/v2/templates/outgoing",
        entity_type="sales_order",
        dispatch_enabled=True,
        jurisdictions=frozenset({"MA"}),
        environments=frozenset({"sandbox"}),
        verification_resource="transfer_templates_outgoing",
        evidence_endpoint="POST /transfers/v2/templates/outgoing",
        note="Outgoing transfer-template writes are currently enabled only for the Massachusetts Metrc sandbox; final manifest issuance is verified separately.",
    ),
    "inbound_transfer_accept": MetrcWriteContract(
        operation_type="inbound_transfer_accept",
        capability="transfers",
        method="",
        path="",
        entity_type="transfer",
        dispatch_enabled=False,
        jurisdictions=frozenset({"MA"}),
        environments=frozenset({"sandbox"}),
        note="No general v2 endpoint for accepting an existing incoming transfer is documented in the reviewed Massachusetts API index. DoobieLogic must not invent one; receiving remains provider-confirmed/readback-gated.",
    ),
    "processing_start": MetrcWriteContract(
        operation_type="processing_start",
        capability="processing_jobs",
        method="POST",
        path="processing/v2/start",
        entity_type="processing_job",
        dispatch_enabled=False,
        jurisdictions=frozenset({"MA"}),
        environments=frozenset({"sandbox"}),
        evidence_endpoint="POST /processing/v2/start",
        note="Endpoint is documented, but the exact request schema has not been promoted into the deterministic write adapter yet.",
    ),
    "processing_adjust": MetrcWriteContract(
        operation_type="processing_adjust",
        capability="processing_jobs",
        method="POST",
        path="processing/v2/adjust",
        entity_type="processing_job",
        dispatch_enabled=False,
        jurisdictions=frozenset({"MA"}),
        environments=frozenset({"sandbox"}),
        evidence_endpoint="POST /processing/v2/adjust",
        note="Endpoint is documented, but exact state payload semantics must be verified before execution is enabled.",
    ),
    "processing_finish": MetrcWriteContract(
        operation_type="processing_finish",
        capability="processing_jobs",
        method="PUT",
        path="processing/v2/finish",
        entity_type="processing_job",
        dispatch_enabled=False,
        jurisdictions=frozenset({"MA"}),
        environments=frozenset({"sandbox"}),
        evidence_endpoint="PUT /processing/v2/finish",
        note="Endpoint is documented, but exact state payload semantics must be verified before execution is enabled.",
    ),
    "plant_location_update": MetrcWriteContract(
        operation_type="plant_location_update",
        capability="plants",
        method="PUT",
        path="plants/v2/location",
        entity_type="plant",
        dispatch_enabled=False,
        jurisdictions=frozenset({"MA"}),
        environments=frozenset({"sandbox"}),
        evidence_endpoint="PUT /plants/v2/location",
        note="Cultivation endpoint is documented; deterministic payload contract remains locked pending exact schema verification.",
    ),
    "plant_growthphase_update": MetrcWriteContract(
        operation_type="plant_growthphase_update",
        capability="plants",
        method="PUT",
        path="plants/v2/growthphase",
        entity_type="plant",
        dispatch_enabled=False,
        jurisdictions=frozenset({"MA"}),
        environments=frozenset({"sandbox"}),
        evidence_endpoint="PUT /plants/v2/growthphase",
        note="Cultivation endpoint is documented; deterministic payload contract remains locked pending exact schema verification.",
    ),
    "plant_waste": MetrcWriteContract(
        operation_type="plant_waste",
        capability="plants",
        method="POST",
        path="plants/v2/waste",
        entity_type="plant",
        dispatch_enabled=False,
        jurisdictions=frozenset({"MA"}),
        environments=frozenset({"sandbox"}),
        evidence_endpoint="POST /plants/v2/waste",
        note="Plant waste is distinct from package waste; execution remains locked until the exact payload and reason/method contracts are verified.",
    ),
}


def get_metrc_write_contract(operation_type: str) -> MetrcWriteContract | None:
    return METRC_WRITE_CONTRACTS.get(str(operation_type or "").strip().casefold())


def list_metrc_write_contracts(*, jurisdiction: str = "", environment: str = "") -> tuple[MetrcWriteContract, ...]:
    code = str(jurisdiction or "").strip().upper()
    env = str(environment or "").strip().casefold()
    rows: Iterable[MetrcWriteContract] = METRC_WRITE_CONTRACTS.values()
    if code:
        rows = (row for row in rows if code in row.jurisdictions)
    if env:
        rows = (row for row in rows if env in row.environments)
    return tuple(rows)


def require_metrc_write_contract(*, operation_type: str, jurisdiction: str, environment: str) -> MetrcWriteContract:
    operation = str(operation_type or "").strip().casefold()
    code = str(jurisdiction or "").strip().upper()
    env = str(environment or "").strip().casefold()
    contract = get_metrc_write_contract(operation)
    if contract is None:
        raise ValueError(f"Metrc write operation '{operation}' has no reviewed DoobieLogic contract.")
    if get_jurisdiction(code) is None:
        raise ValueError("The Metrc write jurisdiction is not verified in the regulatory registry.")
    if code not in contract.jurisdictions or env not in contract.environments:
        raise ValueError(contract.note or f"{operation} is not enabled for {code or 'unknown jurisdiction'} {env or 'unknown environment'}.")
    require_capability(code, contract.capability, environment=env)
    if not contract.dispatch_enabled:
        raise ValueError(
            f"{operation} is documented for {code}, but automatic execution is locked until its deterministic payload contract is verified."
        )
    return contract
