"""Deterministic competitor-data migration and reconciliation service.

The switch center never fuzzy-auto-commits. Exact identifiers/names may auto-match;
anything weaker is surfaced for human review before durable writes occur.
"""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

import pandas as pd
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import (
    AuditEvent,
    Facility,
    InventoryLot,
    InventoryTransaction,
    Product,
    TradePartner,
    utc_now,
)
from modules.product_master.models import ProductAlias, ProductExternalMapping, ProductMasterProfile, ProductValueEvent
from modules.product_master.repository import normalize_alias
from modules.product_master.resolver import search_product_master

from .models import MigrationBatch, MigrationRecord, MigrationSalesHistory


SOURCE_SYSTEMS = {"dutchie", "distru", "metrc", "spreadsheet", "other"}
ENTITY_TYPES = {"product", "vendor", "inventory", "sales"}


def _clean(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _norm_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean(value).casefold()).strip()


def _float(value: Any) -> float:
    try:
        if value is None or _clean(value) == "":
            return 0.0
        return float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _date(value: Any) -> date | None:
    if value is None or _clean(value) == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        parsed = pd.to_datetime(value, errors="coerce")
        return None if pd.isna(parsed) else parsed.date()
    except Exception:
        return None


def detect_source_system(columns: Iterable[Any]) -> str:
    """Infer likely export source from headers only."""
    keys = {_norm_key(column) for column in columns}
    joined = " | ".join(sorted(keys))
    scores = {
        "metrc": sum(token in joined for token in ("package tag", "item name", "unit of measure", "license number", "metrc")),
        "dutchie": sum(token in joined for token in ("master category", "inventory available", "dutchie", "product type", "vendor name")),
        "distru": sum(token in joined for token in ("distru", "inventory item", "batch id", "sales order", "warehouse")),
    }
    winner = max(scores, key=scores.get)
    return winner if scores[winner] >= 2 else "spreadsheet"


ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("product name", "item name", "item", "product", "name", "inventory item", "description"),
    "sku": ("sku", "product sku", "item sku", "external sku"),
    "upc": ("upc", "barcode", "gtin"),
    "external_id": ("id", "product id", "item id", "external id", "dutchie id", "distru id", "metrc item id"),
    "brand": ("brand", "brand name"),
    "category": ("category", "master category", "product category"),
    "subcategory": ("subcategory", "sub category"),
    "strain": ("strain", "strain name"),
    "manufacturer": ("manufacturer", "producer", "vendor"),
    "format": ("format", "product type", "type"),
    "unit": ("unit", "unit of measure", "uom", "base unit"),
    "unit_cost": ("unit cost", "cost", "wholesale cost", "average cost", "avg cost"),
    "retail_price": ("retail price", "price", "unit price", "msrp"),
    "vendor_name": ("vendor name", "vendor", "supplier", "supplier name"),
    "license": ("license", "license number", "registration"),
    "contact_name": ("contact", "contact name"),
    "contact_email": ("email", "contact email"),
    "contact_phone": ("phone", "contact phone"),
    "package_id": ("package tag", "package id", "metrc package", "package", "tag"),
    "lot_code": ("lot", "lot code", "batch", "batch id", "batch number"),
    "quantity": ("quantity", "qty", "on hand", "available", "inventory available"),
    "location": ("location", "room", "warehouse", "storage location"),
    "sale_date": ("sale date", "date", "transaction date", "order date"),
    "units": ("units sold", "quantity sold", "qty sold", "units", "quantity"),
    "revenue": ("revenue", "net sales", "gross sales", "sales", "total sales"),
    "sale_id": ("sale id", "transaction id", "order id", "receipt id", "external id"),
}


def _lookup(row: Mapping[str, Any], field: str) -> Any:
    normalized = {_norm_key(key): value for key, value in row.items()}
    for alias in ALIASES.get(field, ()):
        if _norm_key(alias) in normalized:
            return normalized[_norm_key(alias)]
    return ""


def normalize_import_row(row: Mapping[str, Any], entity_type: str) -> dict[str, Any]:
    entity = _clean(entity_type).casefold()
    if entity not in ENTITY_TYPES:
        raise ValueError("Unsupported migration entity type.")
    if entity == "product":
        return {
            "name": _clean(_lookup(row, "name")),
            "sku": _clean(_lookup(row, "sku")),
            "upc": _clean(_lookup(row, "upc")),
            "external_id": _clean(_lookup(row, "external_id")),
            "brand": _clean(_lookup(row, "brand")),
            "category": _clean(_lookup(row, "category")),
            "subcategory": _clean(_lookup(row, "subcategory")),
            "strain": _clean(_lookup(row, "strain")),
            "manufacturer": _clean(_lookup(row, "manufacturer")),
            "product_format": _clean(_lookup(row, "format")),
            "unit": _clean(_lookup(row, "unit")) or "unit",
            "unit_cost": max(0.0, _float(_lookup(row, "unit_cost"))),
            "retail_price": max(0.0, _float(_lookup(row, "retail_price"))),
        }
    if entity == "vendor":
        return {
            "name": _clean(_lookup(row, "vendor_name") or _lookup(row, "name")),
            "license": _clean(_lookup(row, "license")),
            "contact_name": _clean(_lookup(row, "contact_name")),
            "contact_email": _clean(_lookup(row, "contact_email")),
            "contact_phone": _clean(_lookup(row, "contact_phone")),
            "external_id": _clean(_lookup(row, "external_id")),
        }
    if entity == "inventory":
        return {
            "product_name": _clean(_lookup(row, "name")),
            "sku": _clean(_lookup(row, "sku")),
            "package_id": _clean(_lookup(row, "package_id")),
            "lot_code": _clean(_lookup(row, "lot_code")),
            "quantity": max(0.0, _float(_lookup(row, "quantity"))),
            "unit": _clean(_lookup(row, "unit")) or "g",
            "unit_cost": max(0.0, _float(_lookup(row, "unit_cost"))),
            "location": _clean(_lookup(row, "location")) or "UNASSIGNED",
            "external_id": _clean(_lookup(row, "external_id")),
        }
    return {
        "product_name": _clean(_lookup(row, "name")),
        "sku": _clean(_lookup(row, "sku")),
        "sale_date": _date(_lookup(row, "sale_date")).isoformat() if _date(_lookup(row, "sale_date")) else "",
        "units": max(0.0, _float(_lookup(row, "units"))),
        "revenue": max(0.0, _float(_lookup(row, "revenue"))),
        "external_id": _clean(_lookup(row, "sale_id") or _lookup(row, "external_id")),
    }


class MigrationCenterService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @staticmethod
    def _scope(session, organization_id: str, facility_id: str) -> None:
        facility = session.get(Facility, facility_id)
        if not facility or facility.organization_id != organization_id:
            raise ValueError("The selected facility does not belong to the organization.")

    def stage_dataframe(
        self,
        *,
        organization_id: str,
        facility_id: str,
        frame: pd.DataFrame,
        entity_type: str,
        actor: str,
        source_system: str = "",
        filename: str = "",
        fingerprint: str = "",
    ) -> MigrationBatch:
        if frame is None or frame.empty:
            raise ValueError("The migration file contains no rows.")
        entity = _clean(entity_type).casefold()
        if entity not in ENTITY_TYPES:
            raise ValueError("Unsupported migration entity type.")
        source = _clean(source_system).casefold() or detect_source_system(frame.columns)
        if source not in SOURCE_SYSTEMS:
            source = "other"
        fingerprint = fingerprint or hashlib.sha256(frame.to_csv(index=False).encode("utf-8")).hexdigest()

        records: list[MigrationRecord] = []
        counts = {"auto_match": 0, "review_required": 0, "unmapped": 0, "conflict": 0}
        with self._sessions.begin() as session:
            self._scope(session, organization_id, facility_id)
            batch = MigrationBatch(
                organization_id=organization_id,
                facility_id=facility_id,
                source_system=source,
                entity_type=entity,
                filename=_clean(filename),
                fingerprint=fingerprint,
                status="staged",
                created_by=_clean(actor) or "system",
            )
            session.add(batch)
            session.flush()
            for index, raw in frame.reset_index(drop=True).iterrows():
                raw_dict = {str(key): (None if pd.isna(value) else value) for key, value in raw.to_dict().items()}
                normalized = normalize_import_row(raw_dict, entity)
                status, confidence, canonical_id, reason = self._match(session, organization_id, source, entity, normalized)
                counts[status] += 1
                external = _clean(normalized.get("external_id") or normalized.get("package_id"))
                record = MigrationRecord(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    batch_id=batch.id,
                    source_row_number=int(index) + 2,
                    source_external_id=external,
                    entity_type=entity,
                    source_json=json.dumps(raw_dict, default=str, sort_keys=True),
                    normalized_json=json.dumps(normalized, default=str, sort_keys=True),
                    match_status=status,
                    confidence=confidence,
                    canonical_entity_id=canonical_id,
                    match_reason=reason,
                    decision_action="accept" if status == "auto_match" else "pending",
                )
                session.add(record)
                records.append(record)
            batch.total_records = len(records)
            batch.matched_records = counts["auto_match"]
            batch.review_records = counts["review_required"]
            batch.unmapped_records = counts["unmapped"]
            batch.conflict_records = counts["conflict"]
            batch.status = "ready" if counts["review_required"] + counts["unmapped"] + counts["conflict"] == 0 else "review"
            session.flush()
            return batch

    def _match(self, session, organization_id: str, source: str, entity: str, row: Mapping[str, Any]) -> tuple[str, float, str, str]:
        if entity == "vendor":
            name = _clean(row.get("name"))
            if not name:
                return "unmapped", 0.0, "", "Vendor name is missing."
            matches = list(session.scalars(select(TradePartner).where(TradePartner.organization_id == organization_id, func.lower(TradePartner.name) == name.casefold())))
            if len(matches) == 1:
                return "auto_match", 1.0, matches[0].id, "Exact vendor name."
            if len(matches) > 1:
                return "conflict", 0.0, "", "Multiple vendor records share this name."
            return "unmapped", 0.0, "", "No exact vendor match."

        name = _clean(row.get("name") or row.get("product_name"))
        sku = _clean(row.get("sku"))
        upc = _clean(row.get("upc"))
        external = _clean(row.get("external_id"))
        candidates: dict[str, str] = {}
        if external:
            for product_id in session.scalars(select(ProductExternalMapping.product_id).where(ProductExternalMapping.organization_id == organization_id, ProductExternalMapping.system_name == source, ProductExternalMapping.external_id == external, ProductExternalMapping.active.is_(True))):
                candidates[str(product_id)] = "Exact external mapping."
        if sku:
            for product_id in session.scalars(select(Product.id).where(Product.organization_id == organization_id, func.lower(Product.sku) == sku.casefold(), Product.active.is_(True))):
                candidates[str(product_id)] = "Exact SKU."
        if upc:
            for product_id in session.scalars(select(Product.id).where(Product.organization_id == organization_id, Product.upc == upc, Product.active.is_(True))):
                candidates[str(product_id)] = "Exact UPC."
        if name:
            for product_id in session.scalars(select(Product.id).where(Product.organization_id == organization_id, func.lower(Product.name) == name.casefold(), Product.active.is_(True))):
                candidates[str(product_id)] = "Exact product name."
            normalized = normalize_alias(name)
            if normalized:
                for product_id in session.scalars(select(ProductAlias.product_id).where(ProductAlias.organization_id == organization_id, ProductAlias.normalized_alias == normalized, ProductAlias.active.is_(True))):
                    candidates[str(product_id)] = "Confirmed Product Master alias."
        if len(candidates) == 1:
            product_id, reason = next(iter(candidates.items()))
            return "auto_match", 1.0, product_id, reason
        if len(candidates) > 1:
            return "conflict", 0.0, "", "Exact identifiers resolve to different canonical products."
        if name:
            suggestions = search_product_master(self.engine, organization_id, name, limit=2)
            if len(suggestions) == 1:
                return "review_required", 0.6, _clean(suggestions[0].get("canonical_product_id")), "One non-exact Product Master candidate; human review required."
        return "unmapped", 0.0, "", "No deterministic canonical product match."

    def list_batches(self, organization_id: str, facility_id: str, *, limit: int = 50) -> list[MigrationBatch]:
        with self._sessions() as session:
            self._scope(session, organization_id, facility_id)
            return list(session.scalars(select(MigrationBatch).where(MigrationBatch.organization_id == organization_id, MigrationBatch.facility_id == facility_id).order_by(MigrationBatch.created_at.desc()).limit(max(1, min(limit, 200)))))

    def records(self, organization_id: str, facility_id: str, batch_id: str) -> list[MigrationRecord]:
        with self._sessions() as session:
            batch = session.get(MigrationBatch, batch_id)
            if not batch or batch.organization_id != organization_id or batch.facility_id != facility_id:
                raise ValueError("Migration batch was not found in the active facility.")
            return list(session.scalars(select(MigrationRecord).where(MigrationRecord.batch_id == batch_id).order_by(MigrationRecord.source_row_number)))

    def set_decision(self, *, organization_id: str, facility_id: str, record_id: str, action: str, actor: str, canonical_entity_id: str = "") -> MigrationRecord:
        action = _clean(action).casefold()
        if action not in {"accept", "create", "link", "skip"}:
            raise ValueError("Unsupported migration decision.")
        with self._sessions.begin() as session:
            record = session.get(MigrationRecord, record_id)
            if not record or record.organization_id != organization_id or record.facility_id != facility_id:
                raise ValueError("Migration record was not found in the active facility.")
            if action in {"accept", "link"} and canonical_entity_id:
                record.canonical_entity_id = canonical_entity_id
            if action in {"accept", "link"} and not record.canonical_entity_id:
                raise ValueError("Choose a canonical record before accepting this mapping.")
            record.decision_action = action
            record.reviewed_by = _clean(actor) or "system"
            record.reviewed_at = utc_now()
            if action == "skip":
                record.match_status = "skipped"
            return record

    def commit_batch(self, *, organization_id: str, facility_id: str, batch_id: str, actor: str) -> dict[str, int]:
        summary = {"committed": 0, "skipped": 0, "blocked": 0}
        with self._sessions.begin() as session:
            batch = session.get(MigrationBatch, batch_id)
            if not batch or batch.organization_id != organization_id or batch.facility_id != facility_id:
                raise ValueError("Migration batch was not found in the active facility.")
            self._scope(session, organization_id, facility_id)
            records = list(session.scalars(select(MigrationRecord).where(MigrationRecord.batch_id == batch.id).order_by(MigrationRecord.source_row_number)))
            for record in records:
                if record.match_status == "committed":
                    continue
                if record.decision_action == "skip" or record.match_status == "skipped":
                    summary["skipped"] += 1
                    continue
                if record.decision_action == "pending":
                    summary["blocked"] += 1
                    continue
                normalized = json.loads(record.normalized_json or "{}")
                try:
                    canonical_id = self._commit_record(session, batch, record, normalized, actor)
                except ValueError:
                    summary["blocked"] += 1
                    continue
                record.canonical_entity_id = canonical_id or record.canonical_entity_id
                record.match_status = "committed"
                record.committed_at = utc_now()
                summary["committed"] += 1
            batch.committed_records = int(session.scalar(select(func.count(MigrationRecord.id)).where(MigrationRecord.batch_id == batch.id, MigrationRecord.match_status == "committed")) or 0) + summary["committed"]
            batch.status = "committed" if summary["blocked"] == 0 else "review"
            session.add(AuditEvent(organization_id=organization_id, facility_id=facility_id, entity_type="migration_batch", entity_id=batch.id, action="migration_committed", actor=_clean(actor) or "system", changes_json=json.dumps(summary, sort_keys=True)))
        return summary

    def _commit_record(self, session, batch: MigrationBatch, record: MigrationRecord, row: Mapping[str, Any], actor: str) -> str:
        if batch.entity_type == "vendor":
            if record.canonical_entity_id:
                partner = session.get(TradePartner, record.canonical_entity_id)
                if not partner or partner.organization_id != batch.organization_id:
                    raise ValueError("Selected vendor is outside this organization.")
                return partner.id
            if record.decision_action != "create" or not _clean(row.get("name")):
                raise ValueError("Vendor requires an accepted match or Create decision.")
            partner = TradePartner(organization_id=batch.organization_id, name=_clean(row.get("name")), partner_type="vendor", license_or_registration=_clean(row.get("license")), contact_name=_clean(row.get("contact_name")), contact_email=_clean(row.get("contact_email")), contact_phone=_clean(row.get("contact_phone")), active=True)
            session.add(partner); session.flush(); return partner.id

        product_id = record.canonical_entity_id
        if batch.entity_type == "product" and not product_id:
            if record.decision_action != "create" or not _clean(row.get("name")):
                raise ValueError("Product requires an accepted match or Create decision.")
            seed = _clean(row.get("external_id")) or _clean(row.get("name"))
            sku = _clean(row.get("sku")) or f"MIG-{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:10].upper()}"
            product = Product(organization_id=batch.organization_id, sku=sku, name=_clean(row.get("name")), item_type="cannabis", base_unit=_clean(row.get("unit")) or "unit", unit_cost=max(0.0, _float(row.get("unit_cost"))), retail_price=max(0.0, _float(row.get("retail_price"))), upc=_clean(row.get("upc")), external_product_id=_clean(row.get("external_id")), active=True)
            session.add(product); session.flush(); product_id = product.id
            session.add(ProductMasterProfile(product_id=product.id, organization_id=batch.organization_id, brand=_clean(row.get("brand")), category=_clean(row.get("category")), subcategory=_clean(row.get("subcategory")), strain=_clean(row.get("strain")), manufacturer=_clean(row.get("manufacturer")), product_format=_clean(row.get("product_format")), description="Imported during Buyer Dash cutover."))
        if not product_id:
            raise ValueError("A canonical product is required before this record can be committed.")
        product = session.get(Product, product_id)
        if not product or product.organization_id != batch.organization_id:
            raise ValueError("Canonical product is outside this organization.")

        if batch.entity_type == "product":
            external = _clean(row.get("external_id"))
            if external:
                mapping = session.scalar(select(ProductExternalMapping).where(ProductExternalMapping.organization_id == batch.organization_id, ProductExternalMapping.system_name == batch.source_system, ProductExternalMapping.external_id == external))
                if mapping and mapping.product_id != product.id:
                    raise ValueError("External product identifier is already linked elsewhere.")
                if mapping is None:
                    session.add(ProductExternalMapping(organization_id=batch.organization_id, product_id=product.id, system_name=batch.source_system, external_id=external, external_name=_clean(row.get("name")), active=True))
            if _clean(row.get("name")) and _clean(row.get("name")).casefold() != product.name.casefold():
                normalized = normalize_alias(_clean(row.get("name")))
                existing = session.scalar(select(ProductAlias).where(ProductAlias.organization_id == batch.organization_id, ProductAlias.normalized_alias == normalized)) if normalized else None
                if existing is None and normalized:
                    session.add(ProductAlias(organization_id=batch.organization_id, product_id=product.id, alias=_clean(row.get("name")), normalized_alias=normalized, source=f"migration:{batch.source_system}", active=True))
            for value_type, amount in (("unit_cost", _float(row.get("unit_cost"))), ("retail_price", _float(row.get("retail_price")))):
                if amount > 0:
                    session.add(ProductValueEvent(organization_id=batch.organization_id, product_id=product.id, partner_id=None, value_type=value_type, amount=amount, previous_amount=None, currency="USD", source=f"migration:{batch.source_system}", source_reference=record.source_external_id, actor=_clean(actor) or "system", effective_at=utc_now()))
                    if value_type == "unit_cost": product.unit_cost = amount
                    else: product.retail_price = amount
            return product.id

        if batch.entity_type == "inventory":
            package_id = _clean(row.get("package_id"))
            lot_code = _clean(row.get("lot_code")) or package_id or f"MIG-{record.id[:8]}"
            lot = session.scalar(select(InventoryLot).where(InventoryLot.facility_id == batch.facility_id, InventoryLot.lot_code == lot_code))
            if lot is None:
                lot = InventoryLot(organization_id=batch.organization_id, facility_id=batch.facility_id, product_id=product.id, lot_code=lot_code, compliance_package_id=package_id, external_inventory_id=_clean(row.get("external_id")), location_code=_clean(row.get("location")) or "UNASSIGNED", status="available", notes=f"Imported from {batch.source_system} cutover.")
                session.add(lot); session.flush()
            elif lot.product_id != product.id:
                raise ValueError("Existing lot code belongs to a different product.")
            current = float(session.scalar(select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(InventoryTransaction.lot_id == lot.id)) or 0.0)
            desired = max(0.0, _float(row.get("quantity")))
            delta = desired - current
            if abs(delta) > 1e-9:
                session.add(InventoryTransaction(organization_id=batch.organization_id, facility_id=batch.facility_id, lot_id=lot.id, transaction_type="migration_opening_balance", quantity_delta=delta, unit=_clean(row.get("unit")) or product.base_unit, production_order_id=None, commercial_order_id=None, commercial_order_line_id=None, reason=f"Cutover balance from {batch.source_system}", reference=record.id, actor=_clean(actor) or "system"))
            return lot.id

        sale_day = _date(row.get("sale_date"))
        external = _clean(row.get("external_id")) or f"{record.batch_id}:{record.source_row_number}"
        if sale_day is None:
            raise ValueError("Historical sale date is required.")
        existing = session.scalar(select(MigrationSalesHistory).where(MigrationSalesHistory.organization_id == batch.organization_id, MigrationSalesHistory.source_system == batch.source_system, MigrationSalesHistory.source_external_id == external))
        if existing is None:
            existing = MigrationSalesHistory(organization_id=batch.organization_id, facility_id=batch.facility_id, product_id=product.id, source_system=batch.source_system, source_external_id=external, sale_date=sale_day, units=max(0.0, _float(row.get("units"))), revenue=max(0.0, _float(row.get("revenue"))), source_record_id=record.id)
            session.add(existing); session.flush()
        return existing.id
