"""Supplier-origin COA intake using the canonical inventory-quality pipeline."""

from __future__ import annotations

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from modules.inventory_quality.coa import CoaDocumentService
from modules.inventory_quality.models import CoaDocument
from modules.operational_moats.models import PartnerPortalAccess


CANONICAL_COA_PREFIX = "doobielogic-coa:"


def canonical_coa_reference(document_id: str) -> str:
    clean = str(document_id or "").strip()
    if not clean:
        raise ValueError("A canonical COA document ID is required.")
    return f"{CANONICAL_COA_PREFIX}{clean}"


class SupplierCoaService:
    """Adds supplier provenance without duplicating COA parsing or storage."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.documents = CoaDocumentService(engine)

    def ingest(
        self,
        *,
        access: PartnerPortalAccess,
        payload: bytes,
        filename: str,
        content_type: str,
    ) -> dict:
        document = self.documents.ingest_library(
            access.organization_id,
            access.facility_id,
            payload=payload,
            filename=filename,
            content_type=content_type,
            actor=f"supplier_portal:{access.id}",
        )
        document_id = str(document.get("id") or "").strip()
        if not document_id:
            raise RuntimeError("Canonical COA ingestion did not return a document ID.")
        with Session(self.engine) as session, session.begin():
            row = session.get(CoaDocument, document_id)
            if (
                row is None
                or row.organization_id != access.organization_id
                or row.facility_id != access.facility_id
            ):
                raise RuntimeError("Canonical COA ingestion escaped the supplier tenant/facility scope.")
            row.source = "supplier_portal"
            row.imported_by = f"supplier_portal:{access.id}"
        refreshed = self.documents.get_document(access.organization_id, access.facility_id, document_id)
        return {**refreshed, "coa_reference": canonical_coa_reference(document_id)}

    def validate_reference(self, organization_id: str, facility_id: str, reference: str) -> None:
        """Validate DoobieLogic references; external supplier links remain allowed."""

        clean = str(reference or "").strip()
        if not clean or not clean.casefold().startswith(CANONICAL_COA_PREFIX):
            return
        document_id = clean[len(CANONICAL_COA_PREFIX) :].strip()
        if not document_id:
            raise ValueError("The DoobieLogic COA reference is missing its document ID.")
        self.documents.get_document(organization_id, facility_id, document_id)
