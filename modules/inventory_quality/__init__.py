"""Canonical lot QA / structured COA evidence shared across operations."""

from .coa import CoaDocumentService, MAX_COA_BYTES, parse_coa_pdf
from .models import CoaAnalyteResult, CoaDocument, LotQualityEvidence
from .service import LotQualityService
from .lineage_resolution import register_lineage_coa_resolution

register_lineage_coa_resolution()

__all__ = [
    "CoaAnalyteResult",
    "CoaDocument",
    "CoaDocumentService",
    "LotQualityEvidence",
    "LotQualityService",
    "MAX_COA_BYTES",
    "parse_coa_pdf",
]
