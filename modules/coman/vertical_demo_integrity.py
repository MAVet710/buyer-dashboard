"""Post-seed integrity boundary for the canonical DEV vertical dataset.

The vertical generator intentionally exercises production services. This boundary
normalizes current-generation synthetic traceability identity into a realistic
Metrc-like shape and removes placeholder lab evidence that was never backed by an
external source certificate. It is restricted to dev-sandbox/SANDBOX and never
changes production, provider-issued, or retired historical identifiers.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent, Facility, InventoryLot, Organization
from modules.cultivation.models import CultivationPlant
from modules.demo_traceability import synthetic_metrc_tag
from modules.inventory_quality.models import LotQualityEvidence
from modules.coman.vertical_demo_ma_coas import DEV_MA_COA_EVIDENCE, DEV_MA_INHERITED_EVIDENCE
from services.sandbox_system_contract import is_dev_sandbox_scope

_ALLOWED_EXTERNAL_REFERENCE_EVIDENCE = {DEV_MA_COA_EVIDENCE, DEV_MA_INHERITED_EVIDENCE}


def _placeholder_lab_evidence(row: LotQualityEvidence) -> bool:
    source = str(row.evidence_source or "").strip().casefold()
    reference = str(row.coa_reference or "").strip().casefold()
    url = str(row.coa_url or "").strip().casefold()
    if row.coa_document_id or row.evidence_source in _ALLOWED_EXTERNAL_REFERENCE_EVIDENCE:
        return False
    return (
        "mock_finished" in source
        or "dev_vertical" in source
        or reference.startswith("dev-mock-")
        or reference.startswith("dev-coa-")
        or "example.invalid/dev-coa" in url
    )


def _clear_unsourced_lab_claim(row: LotQualityEvidence) -> None:
    row.lab_testing_state = ""
    row.coa_reference = ""
    row.coa_url = ""
    row.coa_document_id = None
    row.thca_percent = None
    row.tac_percent = None
    row.total_thc_percent = None
    row.total_cbd_percent = None
    row.total_cannabinoids_percent = None
    row.total_terpenes_percent = None
    row.evidence_source = "dev_sandbox:no_sourced_coa"
    row.inherited_from_lot_id = None
    row.verified_at = None


def enforce_vertical_demo_integrity(
    engine: Engine,
    organization_id: str,
    facility_id: str,
    *,
    generation: str,
    actor: str,
) -> dict[str, int]:
    """Normalize current DEV identifiers and strip unsupported demo COA claims."""
    normalized_generation = str(generation or "").strip().upper()
    with Session(engine) as session, session.begin():
        organization = session.get(Organization, organization_id)
        facility = session.get(Facility, facility_id)
        if organization is None or facility is None or not is_dev_sandbox_scope(organization, facility):
            raise RuntimeError("Vertical demo integrity enforcement is restricted to dev-sandbox/SANDBOX.")

        package_tags = 0
        for lot in session.scalars(
            select(InventoryLot).where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
                InventoryLot.status != "depleted",
            )
        ):
            current = str(lot.compliance_package_id or "").strip()
            current_upper = current.upper()
            if (
                not current
                or not current_upper.startswith(("DEV", "PKG-", "PACKAGE-"))
                or (normalized_generation and normalized_generation not in current_upper)
            ):
                continue
            replacement = synthetic_metrc_tag(f"package:{generation}:{lot.id}:{lot.lot_code}")
            if lot.barcode_value in {"", current}:
                lot.barcode_value = replacement
            lot.compliance_package_id = replacement
            package_tags += 1

        plant_tags = 0
        for plant in session.scalars(
            select(CultivationPlant).where(
                CultivationPlant.organization_id == organization_id,
                CultivationPlant.facility_id == facility_id,
                CultivationPlant.phase != "destroyed",
            )
        ):
            current = str(plant.plant_tag or "").strip()
            current_upper = current.upper()
            if (
                current_upper.startswith("DEV")
                and (not normalized_generation or normalized_generation in current_upper)
            ):
                plant.plant_tag = synthetic_metrc_tag(f"plant:{generation}:{plant.id}:{current}")
                plant_tags += 1
            mother = str(plant.mother_plant_tag or "").strip()
            if mother.upper().startswith("DEV"):
                plant.mother_plant_tag = synthetic_metrc_tag(f"mother:{generation}:{mother}")

        cleared_unsourced_coas = 0
        for evidence in session.scalars(
            select(LotQualityEvidence).where(
                LotQualityEvidence.organization_id == organization_id,
                LotQualityEvidence.facility_id == facility_id,
            )
        ):
            if _placeholder_lab_evidence(evidence):
                _clear_unsourced_lab_claim(evidence)
                cleared_unsourced_coas += 1

        session.add(
            AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="facility",
                entity_id=facility_id,
                action="dev_vertical_demo_integrity_enforced",
                actor=actor,
                changes_json=json.dumps(
                    {
                        "generation": generation,
                        "realistic_package_tags": package_tags,
                        "realistic_plant_tags": plant_tags,
                        "unsourced_lab_claims_cleared": cleared_unsourced_coas,
                        "external_provider_writes_enabled": False,
                    },
                    sort_keys=True,
                ),
            )
        )
        return {
            "realistic_package_tags": package_tags,
            "realistic_plant_tags": plant_tags,
            "unsourced_lab_claims_cleared": cleared_unsourced_coas,
        }


__all__ = ["enforce_vertical_demo_integrity"]
