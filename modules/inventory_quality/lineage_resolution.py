"""Lineage-aware COA resolution for split/repackaged cannabis packages.

The current METRC package tag identifies the physical package in front of the
operator. A COA identifies the material that was actually tested. Package Studio
may create a new child package/tag without changing the tested material, so
Label Studio must be able to resolve the ancestor COA through durable QA lineage
without rewriting the COA to pretend the child package was lab-tested directly.

DEV Sandbox also carries explicit real Massachusetts COA reference fixtures for
hands-on testing. Those documents are usable as read-only tested-material
evidence only inside the exact DEV tenant/facility and never become the current
regulatory package identity.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.coman.models import Facility, Organization

from .coa import CoaDocumentService
from .models import CoaAnalyteResult, CoaDocument, LotQualityEvidence
from .service import LotQualityService


_ALLOWED_VERIFICATION = {"matched", "tag_extracted", "operator_confirmed"}
_DEV_EXTERNAL_EVIDENCE = {
    "coa:dev_ma_external_reference",
    "inherited:dev_ma_external_reference",
}
_ORIGINAL_RESOLVE_FOR_LOT = CoaDocumentService.resolve_for_lot
_REGISTERED = False


def _results(session: Session, document_id: str) -> list[CoaAnalyteResult]:
    return list(
        session.scalars(
            select(CoaAnalyteResult)
            .where(CoaAnalyteResult.coa_document_id == document_id)
            .order_by(CoaAnalyteResult.sort_order, CoaAnalyteResult.name)
        )
    )


def _dev_external_reference_allowed(
    session: Session,
    lot,
    evidence: LotQualityEvidence,
    document: CoaDocument,
) -> bool:
    """Permit real MA reference COAs only in the exact isolated DEV sandbox.

    This is deliberately narrower than the normal verification-state allowlist.
    It never changes a lot's compliance package/tag and never makes an external
    source tag eligible for provider writes; it only makes explicitly attached
    DEV reference evidence readable by QA/Label Studio projections.
    """

    if document.verification_state != "external_reference":
        return False
    if evidence.evidence_source not in _DEV_EXTERNAL_EVIDENCE:
        return False
    if not str(document.metrc_source_id or "").strip():
        return False

    organization = session.get(Organization, lot.organization_id)
    facility = session.get(Facility, lot.facility_id)
    return bool(
        organization is not None
        and organization.slug == "dev-sandbox"
        and facility is not None
        and facility.organization_id == lot.organization_id
        and facility.code == "SANDBOX"
    )


def _lineage_document(session: Session, lot) -> CoaDocument | None:
    """Find usable COA evidence explicitly carried through the lot's QA lineage."""

    seen: set[str] = set()
    current_lot_id = str(lot.id)
    for _ in range(32):
        if not current_lot_id or current_lot_id in seen:
            return None
        seen.add(current_lot_id)
        evidence = session.get(LotQualityEvidence, current_lot_id)
        if evidence is None:
            return None
        if evidence.organization_id != lot.organization_id or evidence.facility_id != lot.facility_id:
            return None
        if (
            evidence.coa_document_id
            and LotQualityService.is_passed(evidence.lab_testing_state, evidence.coa_reference)
        ):
            document = session.get(CoaDocument, evidence.coa_document_id)
            if (
                document is not None
                and document.organization_id == lot.organization_id
                and document.facility_id == lot.facility_id
                and document.status == "parsed"
                and (
                    document.verification_state in _ALLOWED_VERIFICATION
                    or _dev_external_reference_allowed(session, lot, evidence, document)
                )
            ):
                return document
        current_lot_id = str(evidence.inherited_from_lot_id or "")
    return None


def _resolve_for_lot_with_lineage(
    self: CoaDocumentService,
    session: Session,
    lot,
) -> tuple[CoaDocument | None, list[CoaAnalyteResult]]:
    # Direct current-package match remains highest priority.
    document, results = _ORIGINAL_RESOLVE_FOR_LOT(self, session, lot)
    if document is not None:
        return document, results

    # A split/repackaged child can legitimately retain the parent's tested COA.
    # Exact DEV external references are also readable here, but only through the
    # explicit tenant/facility/evidence guard above.
    document = _lineage_document(session, lot)
    if document is None:
        return None, []
    return document, _results(session, document.id)


def register_lineage_coa_resolution() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    CoaDocumentService.resolve_for_lot = _resolve_for_lot_with_lineage
    _REGISTERED = True


register_lineage_coa_resolution()
