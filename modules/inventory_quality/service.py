"""Shared QA/COA evidence service with a legacy inventory-note compatibility mirror."""

from __future__ import annotations

import json
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryLot, utc_now

from .models import LotQualityEvidence


PASSED_STATES = {"passed", "pass", "released", "testpassed"}


def _normalized_state(value: Any) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _legacy_metadata(lot: InventoryLot) -> dict[str, Any]:
    raw = str(lot.notes or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"legacy_note": raw}
    return parsed if isinstance(parsed, dict) else {"legacy_note": raw}


class LotQualityService:
    """Own current lot QA evidence while preserving compatibility with older readers."""

    @staticmethod
    def read(session: Session, lot_id: str) -> LotQualityEvidence | None:
        evidence = session.get(LotQualityEvidence, lot_id)
        if evidence is not None:
            return evidence
        lot = session.get(InventoryLot, lot_id)
        if lot is None:
            return None
        meta = _legacy_metadata(lot)
        state = str(meta.get("lab_testing_state") or "").strip()
        reference = str(meta.get("coa_reference") or "").strip()
        if not state and not reference:
            return None
        evidence = LotQualityEvidence(
            lot_id=lot.id,
            organization_id=lot.organization_id,
            facility_id=lot.facility_id,
            lab_testing_state=state,
            coa_reference=reference,
            coa_url=str(meta.get("coa_url") or meta.get("certificate_url") or meta.get("lab_report_url") or "").strip(),
            thca_percent=LotQualityService._float(meta.get("thca_percent")),
            tac_percent=LotQualityService._float(meta.get("tac_percent")),
            total_terpenes_percent=LotQualityService._float(meta.get("total_terpenes_percent")),
            evidence_source="legacy_inventory_metadata",
            actor="legacy-import",
            verified_at=utc_now() if LotQualityService.is_passed(state, reference) else None,
        )
        session.add(evidence)
        return evidence

    @staticmethod
    def set_evidence(
        session: Session,
        *,
        lot_id: str,
        lab_testing_state: str,
        coa_reference: str = "",
        coa_url: str = "",
        thca_percent: float | None = None,
        tac_percent: float | None = None,
        total_terpenes_percent: float | None = None,
        evidence_source: str = "manual",
        inherited_from_lot_id: str | None = None,
        actor: str = "system",
    ) -> LotQualityEvidence:
        lot = session.get(InventoryLot, lot_id)
        if lot is None:
            raise ValueError("Inventory lot was not found for QA evidence.")
        evidence = session.get(LotQualityEvidence, lot.id)
        if evidence is None:
            evidence = LotQualityEvidence(
                lot_id=lot.id,
                organization_id=lot.organization_id,
                facility_id=lot.facility_id,
            )
            session.add(evidence)
        evidence.lab_testing_state = str(lab_testing_state or "").strip()
        evidence.coa_reference = str(coa_reference or "").strip()
        evidence.coa_url = str(coa_url or "").strip()
        evidence.thca_percent = LotQualityService._validated_percent(thca_percent)
        evidence.tac_percent = LotQualityService._validated_percent(tac_percent)
        evidence.total_terpenes_percent = LotQualityService._validated_percent(total_terpenes_percent)
        evidence.evidence_source = str(evidence_source or "manual").strip() or "manual"
        evidence.inherited_from_lot_id = inherited_from_lot_id
        evidence.actor = str(actor or "system").strip() or "system"
        evidence.verified_at = utc_now() if LotQualityService.is_passed(evidence.lab_testing_state, evidence.coa_reference) else None
        LotQualityService._mirror_to_inventory_notes(lot, evidence)
        return evidence

    @staticmethod
    def inherit(
        session: Session,
        *,
        source_lot_ids: Iterable[str],
        child_lot_id: str,
        transformation_type: str,
        actor: str,
    ) -> LotQualityEvidence | None:
        action = str(transformation_type or "").strip().casefold()
        if action == "rework":
            return LotQualityService.set_evidence(
                session,
                lot_id=child_lot_id,
                lab_testing_state="pending",
                evidence_source="rework_requires_review",
                actor=actor,
            )
        sources: list[LotQualityEvidence] = []
        for lot_id in dict.fromkeys(str(item) for item in source_lot_ids if item):
            evidence = LotQualityService.read(session, lot_id)
            if evidence is None or not LotQualityService.is_passed(evidence.lab_testing_state, evidence.coa_reference):
                return None
            sources.append(evidence)
        if not sources:
            return None
        references = sorted({row.coa_reference.strip() for row in sources if row.coa_reference.strip()})
        if len(references) != len({row.coa_reference.strip() for row in sources}):
            references = sorted(set(references))
        single_source = sources[0] if len(sources) == 1 else None
        return LotQualityService.set_evidence(
            session,
            lot_id=child_lot_id,
            lab_testing_state="Passed",
            coa_reference="; ".join(references),
            coa_url=single_source.coa_url if single_source else "",
            thca_percent=single_source.thca_percent if single_source else LotQualityService._common(sources, "thca_percent"),
            tac_percent=single_source.tac_percent if single_source else LotQualityService._common(sources, "tac_percent"),
            total_terpenes_percent=single_source.total_terpenes_percent if single_source else LotQualityService._common(sources, "total_terpenes_percent"),
            evidence_source=f"inherited:{action or 'transformation'}",
            inherited_from_lot_id=single_source.lot_id if single_source else None,
            actor=actor,
        )

    @staticmethod
    def is_passed(state: str, reference: str) -> bool:
        return bool(str(reference or "").strip()) and _normalized_state(state) in PASSED_STATES

    @staticmethod
    def _mirror_to_inventory_notes(lot: InventoryLot, evidence: LotQualityEvidence) -> None:
        meta = _legacy_metadata(lot)
        meta.update(
            {
                "lab_testing_state": evidence.lab_testing_state,
                "coa_reference": evidence.coa_reference,
                "coa_url": evidence.coa_url,
                "thca_percent": evidence.thca_percent,
                "tac_percent": evidence.tac_percent,
                "total_terpenes_percent": evidence.total_terpenes_percent,
                "quality_evidence_source": evidence.evidence_source,
            }
        )
        lot.notes = json.dumps(meta, sort_keys=True)

    @staticmethod
    def _common(rows: list[LotQualityEvidence], field: str) -> float | None:
        values = {getattr(row, field) for row in rows}
        return next(iter(values)) if len(values) == 1 else None

    @staticmethod
    def _validated_percent(value: float | None) -> float | None:
        if value is None:
            return None
        number = float(value)
        if number < 0 or number > 100:
            raise ValueError("Lab percentages must be between 0 and 100.")
        return round(number, 4)

    @staticmethod
    def _float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return LotQualityService._validated_percent(float(str(value).replace("%", "")))
        except (TypeError, ValueError):
            return None
