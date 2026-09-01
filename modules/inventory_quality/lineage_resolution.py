"""Lineage-aware COA resolution for split/repackaged cannabis packages.

The current METRC package tag identifies the physical package in front of the
operator. A COA identifies the material that was actually tested. Package Studio
may create a new child package/tag without changing the tested material, so
Label Studio must be able to resolve the ancestor COA through durable QA lineage
without rewriting the COA to pretend the child package was lab-tested directly.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .coa import CoaDocumentService
from .models import CoaAnalyteResult, CoaDocument, LotQualityEvidence
from .service import LotQualityService


_ALLOWED_VERIFICATION = {"matched", "tag_extracted", "operator_confirmed"}
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


def _lineage_document(session: Session, lot) -> CoaDocument | None:
    """Find the verified COA explicitly carried through the lot's QA lineage."""

    seen: set[str] = set()
    current_lot_id = str(lot.id)
    for _ in range(32):
        if not current_lot_id or current_lot_id in seen:
            return None
        seen.add(current_lot_id)
        evidence = session.get(LotQualityEvidence, current_lot_id)
        if evidence is None:
            return None
        if (
            evidence.coa_document_id
            and LotQualityService.is_passed(evidence.lab_testing_state, evidence.coa_reference)
        ):
            document = session.get(CoaDocument, evidence.coa_document_id)
            if (
                document is not None
                and document.organization_id == lot.organization_id
                and document.status == "parsed"
                and document.verification_state in _ALLOWED_VERIFICATION
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
