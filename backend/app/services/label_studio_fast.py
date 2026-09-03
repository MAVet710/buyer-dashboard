"""Latency-sensitive Label Studio reads.

The selector receives lightweight lot/package summaries. Full Product Master,
COA lineage, analyte results, QR, and barcode projection is built only for the
single lot the operator selects. This preserves Label Studio behavior while
avoiding per-lot COA and rendering work during initial page load.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import Facility, InventoryLot, InventoryTransaction, Product
from modules.inventory_quality.coa import CoaDocumentService
from modules.inventory_quality.models import LotQualityEvidence
from modules.product_master.models import ProductMasterProfile
from modules.product_master.packaging import ProductPackagingProfile

from .label_studio import LabelInventoryService, _raw_text
from .label_studio_integrity import normalize_testing_label_source


class FastLabelInventoryService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.coas = CoaDocumentService(engine)

    @staticmethod
    def _balance(organization_id: str, facility_id: str):
        return (
            select(
                InventoryTransaction.lot_id.label("lot_id"),
                func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0).label("balance"),
            )
            .where(
                InventoryTransaction.organization_id == organization_id,
                InventoryTransaction.facility_id == facility_id,
            )
            .group_by(InventoryTransaction.lot_id)
            .subquery()
        )

    def list_summaries(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        balance = self._balance(organization_id, facility_id)
        stmt = (
            select(InventoryLot, Product, func.coalesce(balance.c.balance, 0.0))
            .join(Product, Product.id == InventoryLot.product_id)
            .outerjoin(balance, balance.c.lot_id == InventoryLot.id)
            .where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
                Product.organization_id == organization_id,
                func.coalesce(balance.c.balance, 0.0) > 0,
            )
            .order_by(Product.name.asc(), InventoryLot.received_at.desc().nullslast(), InventoryLot.lot_code.asc())
        )
        with Session(self.engine) as session:
            rows = session.execute(stmt).all()
            return [
                {
                    "lot_id": lot.id,
                    "product_id": product.id,
                    "package_id": str(lot.compliance_package_id or "").strip(),
                    "lot_code": lot.lot_code,
                    "product_name": product.name,
                    "sku": product.sku,
                    "location": lot.location_code,
                    "status": lot.status,
                    "on_hand": float(on_hand or 0),
                    "inventory_unit": product.base_unit,
                }
                for lot, product, on_hand in rows
            ]

    def get_source(self, organization_id: str, facility_id: str, lot_id: str) -> dict[str, Any]:
        balance = self._balance(organization_id, facility_id)
        stmt = (
            select(
                InventoryLot,
                Product,
                Facility,
                ProductMasterProfile,
                ProductPackagingProfile,
                LotQualityEvidence,
                func.coalesce(balance.c.balance, 0.0),
            )
            .join(Product, Product.id == InventoryLot.product_id)
            .join(Facility, Facility.id == InventoryLot.facility_id)
            .outerjoin(
                ProductMasterProfile,
                (ProductMasterProfile.product_id == Product.id)
                & (ProductMasterProfile.organization_id == organization_id),
            )
            .outerjoin(
                ProductPackagingProfile,
                (ProductPackagingProfile.product_id == Product.id)
                & (ProductPackagingProfile.organization_id == organization_id),
            )
            .outerjoin(LotQualityEvidence, LotQualityEvidence.lot_id == InventoryLot.id)
            .outerjoin(balance, balance.c.lot_id == InventoryLot.id)
            .where(
                InventoryLot.id == lot_id,
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
                Product.organization_id == organization_id,
                Facility.organization_id == organization_id,
                func.coalesce(balance.c.balance, 0.0) > 0,
            )
        )
        with Session(self.engine) as session:
            row = session.execute(stmt).first()
            if row is None:
                raise ValueError("Inventory batch was not found in the active facility or has no on-hand balance.")
            lot = row[0]
            coa, results = self.coas.resolve_for_lot(session, lot)
            pending, pending_results = (None, []) if coa else LabelInventoryService._pending_coa(session, lot)
            source = LabelInventoryService._source(*row, coa, results, pending, pending_results)
            normalized = normalize_testing_label_source(source)
            normalized["raw_text"] = _raw_text(normalized["label"])
            return normalized
