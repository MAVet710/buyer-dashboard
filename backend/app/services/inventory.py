import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent, InventoryLot, InventoryTransaction, MaterialReservation, Product, RetailSale, TradePartner, utc_now
from modules.product_master.models import ProductMasterProfile, ProductVendorLink

from ..schemas.inventory import (
    InventoryFacets,
    InventoryPackage,
    InventoryResponse,
    InventoryReceiptCreate,
    InventoryReceiptHistoryItem,
    InventoryReceiptResult,
    InventoryAdjustmentCreate,
    InventoryAdjustmentResult,
    InventorySummary,
    ProductOption,
    RetailSalesImport,
    RetailSalesImportResult,
)


class InventoryQueryService:
    """Read durable package inventory without depending on Streamlit state."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def list_packages(
        self,
        organization_id: str,
        facility_id: str,
        *,
        operation: str,
        search: str = "",
        status: str = "",
        material_type: str = "",
        location: str = "",
        source: str = "",
        view: str = "all",
    ) -> InventoryResponse:
        balance = (
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
        reservations = (
            select(
                MaterialReservation.lot_id.label("lot_id"),
                func.coalesce(func.sum(MaterialReservation.quantity), 0.0).label("reserved"),
            )
            .where(
                MaterialReservation.organization_id == organization_id,
                MaterialReservation.facility_id == facility_id,
                MaterialReservation.status == "reserved",
            )
            .group_by(MaterialReservation.lot_id)
            .subquery()
        )
        sales = (
            select(
                RetailSale.product_id.label("product_id"),
                func.coalesce(func.sum(RetailSale.quantity), 0.0).label("sold_30d"),
            )
            .where(
                RetailSale.organization_id == organization_id,
                RetailSale.facility_id == facility_id,
                RetailSale.sold_at >= utc_now() - timedelta(days=30),
                RetailSale.product_id.is_not(None),
            )
            .group_by(RetailSale.product_id)
            .subquery()
        )
        query = (
            select(
                InventoryLot,
                Product,
                func.coalesce(balance.c.balance, 0.0),
                func.coalesce(reservations.c.reserved, 0.0),
                func.coalesce(sales.c.sold_30d, 0.0),
            )
            .join(Product, Product.id == InventoryLot.product_id)
            .outerjoin(balance, balance.c.lot_id == InventoryLot.id)
            .outerjoin(reservations, reservations.c.lot_id == InventoryLot.id)
            .outerjoin(sales, sales.c.product_id == Product.id)
            .where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
                Product.organization_id == organization_id,
            )
            .order_by(Product.name, InventoryLot.received_at.desc().nullslast())
        )
        with Session(self.engine) as session:
            rows = session.execute(query).all()
            product_ids = {product.id for _, product, *_ in rows}
            profiles = {
                row.product_id: row
                for row in session.scalars(
                    select(ProductMasterProfile).where(
                        ProductMasterProfile.organization_id == organization_id,
                        ProductMasterProfile.product_id.in_(product_ids),
                    )
                )
            } if product_ids else {}
            vendor_rows = session.execute(
                select(ProductVendorLink.product_id, TradePartner.name)
                .join(TradePartner, TradePartner.id == ProductVendorLink.partner_id)
                .where(
                    ProductVendorLink.organization_id == organization_id,
                    ProductVendorLink.product_id.in_(product_ids),
                    ProductVendorLink.active.is_(True),
                    ProductVendorLink.is_primary.is_(True),
                )
            ).all() if product_ids else []
            primary_vendors = {product_id: name for product_id, name in vendor_rows}

        rows = [
            row for row in rows
            if row[1].id not in profiles
            or (
                operation == "retail" and profiles[row[1].id].retail_enabled
            )
            or (
                operation == "production" and profiles[row[1].id].production_enabled
            )
        ]
        items = [
            self._package(
                lot,
                product,
                float(available),
                float(reserved),
                float(sold_30d),
                operation,
                material_type=(
                    profiles[product.id].category
                    or profiles[product.id].product_format
                    if product.id in profiles else ""
                ),
                primary_vendor=primary_vendors.get(product.id, ""),
            )
            for lot, product, available, reserved, sold_30d in rows
        ]
        facets = InventoryFacets(
            statuses=sorted({item.status for item in items}),
            material_types=sorted({item.material_type for item in items}),
            locations=sorted({item.location for item in items}),
            sources=sorted({item.source_name for item in items if item.source_name}),
        )
        items = self._filter(items, search, status, material_type, location, source, view)
        return InventoryResponse(
            operation=operation,
            items=items,
            facets=facets,
            summary=InventorySummary(
                package_count=len(items),
                available_quantity=sum(item.available for item in items),
                reserved_quantity=sum(item.reserved for item in items),
                hold_count=sum(item.attention == "Hold" for item in items),
                low_balance_count=sum(item.attention == "Low balance" for item in items),
            ),
        )

    def list_production_packages(self, organization_id: str, facility_id: str, **filters) -> InventoryResponse:
        return self.list_packages(
            organization_id,
            facility_id,
            operation="production",
            **filters,
        )

    def list_retail_packages(self, organization_id: str, facility_id: str, **filters) -> InventoryResponse:
        """Read the same durable ledger through the retail operating projection.

        The facility/license context separates retail inventory from production;
        product item type must not be used as a proxy because sellable flower can
        still be a cannabis item.
        """
        return self.list_packages(
            organization_id,
            facility_id,
            operation="retail",
            **filters,
        )

    @staticmethod
    def _package(
        lot: InventoryLot,
        product: Product,
        available: float,
        reserved: float,
        sold_30d: float,
        operation: str,
        *,
        material_type: str = "",
        primary_vendor: str = "",
    ) -> InventoryPackage:
        usable = max(0.0, available - reserved)
        status = str(lot.status or "available")
        if any(token in status.casefold() for token in ("hold", "quarantine", "failed")):
            attention = "Hold"
        elif available <= 0:
            attention = "Empty"
        elif usable <= 10:
            attention = "Low balance"
        else:
            attention = "Production ready"
        velocity = sold_30d / 30.0 if operation == "retail" else 0.0
        price = float(product.retail_price or 0)
        cost = float(product.unit_cost or 0)
        try:
            metadata = json.loads(lot.notes or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        now = datetime.now(timezone.utc)
        received_at = lot.received_at
        expiration_at = lot.expiration_at
        if received_at is not None and received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)
        if expiration_at is not None and expiration_at.tzinfo is None:
            expiration_at = expiration_at.replace(tzinfo=timezone.utc)
        return InventoryPackage(
            id=lot.id,
            package_id=lot.compliance_package_id or lot.lot_code,
            lot_code=lot.lot_code,
            product_id=product.id,
            sku=product.sku,
            product_name=product.name,
            material_type=(material_type or product.item_type.replace("_", " ")).title(),
            location=lot.location_code,
            status=status.replace("_", " ").title(),
            source_name=str(metadata.get("source_name") or primary_vendor or ""),
            available=available,
            reserved=reserved,
            usable=usable,
            unit=product.base_unit,
            received_at=lot.received_at,
            expiration_at=lot.expiration_at,
            attention=attention,
            sold_30d=sold_30d if operation == "retail" else 0.0,
            daily_velocity=velocity,
            days_on_hand=available / velocity if velocity > 0 else None,
            unit_cost=cost,
            retail_price=price,
            margin_pct=((price - cost) / price * 100) if price > 0 else None,
            age_days=max(0.0, (now - received_at).total_seconds() / 86400.0) if received_at else None,
            days_to_expiry=(expiration_at - now).total_seconds() / 86400.0 if expiration_at else None,
        )

    @staticmethod
    def _filter(
        items: list[InventoryPackage],
        search: str,
        status: str,
        material_type: str,
        location: str,
        source: str,
        view: str,
    ) -> list[InventoryPackage]:
        needle = search.strip().casefold()
        result = items
        if needle:
            result = [item for item in result if needle in " ".join((item.product_name, item.sku, item.package_id, item.lot_code, item.location, item.source_name, item.material_type)).casefold()]
        if status:
            result = [item for item in result if item.status.casefold() == status.casefold()]
        if material_type:
            result = [item for item in result if item.material_type.casefold() == material_type.casefold()]
        if location:
            result = [item for item in result if item.location.casefold() == location.casefold()]
        if source:
            result = [item for item in result if item.source_name.casefold() == source.casefold()]
        view_key = view.casefold().replace("_", "-")
        if view_key == "bulk-flower":
            result = [item for item in result if "flower" in item.material_type.casefold()]
        elif view_key == "biomass-trim":
            result = [item for item in result if any(token in item.material_type.casefold() for token in ("biomass", "trim"))]
        elif view_key == "extraction-input":
            result = [item for item in result if any(token in item.material_type.casefold() for token in ("flower", "trim", "biomass", "fresh frozen", "material"))]
        elif view_key == "wip":
            result = [item for item in result if any(token in item.material_type.casefold() for token in ("wip", "work in process", "crude", "oil", "distillate", "concentrate"))]
        elif view_key == "finished-bulk":
            result = [item for item in result if any(token in item.material_type.casefold() for token in ("finished", "distillate", "rosin", "resin", "concentrate"))]
        elif view_key == "production-ready":
            result = [item for item in result if item.attention == "Production ready"]
        elif view_key == "low-balance":
            result = [item for item in result if 0 < item.available <= 10]
        elif view_key in {"hold", "quarantine-hold"}:
            result = [item for item in result if item.attention == "Hold"]
        elif view_key == "low-stock":
            result = [item for item in result if (item.days_on_hand is not None and item.days_on_hand <= 7) or item.available <= 0]
        elif view_key == "under-14-doh":
            result = [item for item in result if item.days_on_hand is not None and item.days_on_hand <= 14]
        elif view_key == "slow-movers":
            result = [item for item in result if item.available > 0 and (item.sold_30d <= 2 or (item.age_days is not None and item.age_days >= 60) or (item.days_on_hand is not None and item.days_on_hand >= 60))]
        elif view_key == "expiring-90-days":
            result = [item for item in result if item.days_to_expiry is not None and 0 <= item.days_to_expiry <= 90]
        elif view_key == "bulk-packages":
            bulk_units = {"g", "gram", "grams", "kg", "oz", "ounce", "ounces", "lb", "pound", "pounds"}
            result = [item for item in result if item.unit.casefold() in bulk_units or any(token in item.material_type.casefold() for token in ("bulk", "flower", "material"))]
        return result

    def list_products(self, organization_id: str) -> list[ProductOption]:
        with Session(self.engine) as session:
            products = session.scalars(
                select(Product).where(
                    Product.organization_id == organization_id,
                    Product.active.is_(True),
                ).order_by(Product.name)
            ).all()
        return [ProductOption(id=p.id, sku=p.sku, name=p.name, item_type=p.item_type, base_unit=p.base_unit) for p in products]

    def receive(
        self,
        organization_id: str,
        facility_id: str,
        *,
        operation: str,
        payload: InventoryReceiptCreate,
        actor: str,
    ) -> InventoryReceiptResult:
        if operation not in {"retail", "production"}:
            raise ValueError("Unsupported inventory operation.")
        lot_code = (payload.lot_code or payload.package_id).strip()
        package_id = payload.package_id.strip()
        if not lot_code:
            raise ValueError("A package or lot identifier is required.")
        unit = payload.unit.strip()
        if not unit:
            raise ValueError("A unit of measure is required.")
        metadata = {
            "operation": operation,
            "source_name": payload.source_name.strip(),
            "manifest_reference": payload.manifest_reference.strip(),
            "lab_testing_state": payload.lab_testing_state.strip(),
            "coa_reference": payload.coa_reference.strip(),
            "notes": payload.notes.strip(),
        }
        lab_state = payload.lab_testing_state.casefold().replace(" ", "")
        lot_status = "available" if lab_state in {"", "testpassed", "passed", "released"} else "hold"
        with Session(self.engine) as session, session.begin():
            product = session.get(Product, payload.product_id)
            if not product or product.organization_id != organization_id or not product.active:
                raise ValueError("Product was not found in the active organization.")
            duplicate_conditions = [InventoryLot.lot_code == lot_code]
            if package_id:
                duplicate_conditions.append(InventoryLot.compliance_package_id == package_id)
            duplicate = session.scalar(select(InventoryLot.id).where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
                or_(*duplicate_conditions),
            ))
            if duplicate:
                raise ValueError("That package or lot already exists in the active facility.")
            lot = InventoryLot(
                organization_id=organization_id,
                facility_id=facility_id,
                product_id=product.id,
                lot_code=lot_code,
                compliance_package_id=package_id,
                external_inventory_id=package_id,
                barcode_value=package_id or lot_code,
                location_code=payload.location.strip() or "RECEIVING",
                status=lot_status,
                received_at=utc_now(),
                expiration_at=payload.expiration_at,
                notes=json.dumps(metadata, sort_keys=True),
            )
            session.add(lot)
            session.flush()
            transaction = InventoryTransaction(
                organization_id=organization_id,
                facility_id=facility_id,
                lot_id=lot.id,
                transaction_type="receive",
                quantity_delta=payload.quantity,
                unit=unit,
                reason=f"{operation.title()} inventory received",
                reference=payload.manifest_reference.strip() or package_id or lot_code,
                actor=actor,
            )
            session.add(transaction)
            session.flush()
            session.add(AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="inventory_lot",
                entity_id=lot.id,
                action=f"{operation}_inventory_received",
                actor=actor,
                changes_json=json.dumps({**metadata, "quantity": payload.quantity, "unit": unit}, sort_keys=True),
            ))
            result = InventoryReceiptResult(lot_id=lot.id, transaction_id=transaction.id, operation=operation, status=lot_status)
        return result

    def receive_history(self, organization_id: str, facility_id: str, operation: str, limit: int = 100) -> list[InventoryReceiptHistoryItem]:
        query = (
            select(InventoryTransaction, InventoryLot, Product)
            .join(InventoryLot, InventoryLot.id == InventoryTransaction.lot_id)
            .join(Product, Product.id == InventoryLot.product_id)
            .where(
                InventoryTransaction.organization_id == organization_id,
                InventoryTransaction.facility_id == facility_id,
                InventoryTransaction.transaction_type.in_(("receive", "receipt")),
            )
            .order_by(InventoryTransaction.occurred_at.desc())
            .limit(min(limit * 3, 1500))
        )
        with Session(self.engine) as session:
            rows = session.execute(query).all()
        history = []
        for transaction, lot, product in rows:
            try:
                metadata = json.loads(lot.notes or "{}")
            except (TypeError, json.JSONDecodeError):
                metadata = {}
            recorded_operation = str(metadata.get("operation") or "").casefold()
            if recorded_operation and recorded_operation != operation.casefold():
                continue
            history.append(InventoryReceiptHistoryItem(
                transaction_id=transaction.id,
                lot_id=lot.id,
                product_name=product.name,
                package_id=lot.compliance_package_id or lot.lot_code,
                quantity=float(transaction.quantity_delta),
                unit=transaction.unit,
                manifest_reference=str(metadata.get("manifest_reference") or transaction.reference or ""),
                source_name=str(metadata.get("source_name") or ""),
                actor=transaction.actor,
                received_at=transaction.occurred_at,
            ))
            if len(history) >= limit:
                break
        return history

    def import_retail_sales(
        self,
        organization_id: str,
        facility_id: str,
        payload: RetailSalesImport,
        actor: str,
    ) -> RetailSalesImportResult:
        source = payload.source_system.strip().casefold()
        if not source:
            raise ValueError("A sales source system is required.")
        imported = skipped = unmapped = 0
        with Session(self.engine) as session, session.begin():
            products = session.scalars(select(Product).where(Product.organization_id == organization_id, Product.active.is_(True))).all()
            by_id = {product.id: product for product in products}
            by_sku = {product.sku.casefold(): product for product in products if product.sku}
            incoming_ids = [line.source_record_id.strip() for line in payload.lines]
            if any(not value for value in incoming_ids) or len(incoming_ids) != len(set(incoming_ids)):
                raise ValueError("Sales source record IDs must be present and unique within an import.")
            existing = set(session.scalars(select(RetailSale.source_record_id).where(
                RetailSale.organization_id == organization_id,
                RetailSale.facility_id == facility_id,
                RetailSale.source_system == source,
                RetailSale.source_record_id.in_(incoming_ids),
            )))
            for line in payload.lines:
                record_id = line.source_record_id.strip()
                if record_id in existing:
                    skipped += 1
                    continue
                product = by_id.get(line.product_id or "") or by_sku.get(line.sku.strip().casefold())
                if product is None:
                    unmapped += 1
                session.add(RetailSale(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    product_id=product.id if product else None,
                    source_system=source,
                    source_record_id=record_id,
                    import_batch_id=payload.import_batch_id.strip(),
                    sku=line.sku.strip() or (product.sku if product else ""),
                    product_name=line.product_name.strip() or (product.name if product else "Unknown product"),
                    quantity=float(line.quantity),
                    net_sales=float(line.net_sales),
                    sold_at=line.sold_at,
                    imported_by=actor,
                ))
                imported += 1
            session.add(AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="retail_sales_import",
                entity_id=payload.import_batch_id.strip() or source,
                action="retail_sales_imported",
                actor=actor,
                changes_json=json.dumps({"source": source, "imported": imported, "skipped": skipped, "unmapped": unmapped}, sort_keys=True),
            ))
        return RetailSalesImportResult(imported=imported, skipped_duplicates=skipped, unmapped_products=unmapped)

    def adjust_inventory(
        self,
        organization_id: str,
        facility_id: str,
        payload: InventoryAdjustmentCreate,
        actor: str,
    ) -> InventoryAdjustmentResult:
        reason = payload.reason.strip()
        if not reason:
            raise ValueError("An adjustment reason is required.")
        with Session(self.engine) as session, session.begin():
            lot = session.get(InventoryLot, payload.lot_id)
            if not lot or lot.organization_id != organization_id or lot.facility_id != facility_id:
                raise ValueError("Inventory lot was not found in the active facility.")
            previous = float(session.scalar(select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                InventoryTransaction.organization_id == organization_id,
                InventoryTransaction.facility_id == facility_id,
                InventoryTransaction.lot_id == lot.id,
            )) or 0.0)
            reserved = float(session.scalar(select(func.coalesce(func.sum(MaterialReservation.quantity), 0.0)).where(
                MaterialReservation.organization_id == organization_id,
                MaterialReservation.facility_id == facility_id,
                MaterialReservation.lot_id == lot.id,
                MaterialReservation.status == "reserved",
            )) or 0.0)
            final = previous + payload.quantity if payload.adjustment_type == "incremental" else payload.quantity
            if final < 0:
                raise ValueError("Final inventory quantity cannot be negative.")
            if final + 1e-9 < reserved:
                raise ValueError(f"Final inventory quantity cannot be below {reserved:g} reserved.")
            delta = final - previous
            if abs(delta) <= 1e-9:
                raise ValueError("The adjustment does not change inventory quantity.")
            unit = session.scalar(select(InventoryTransaction.unit).where(InventoryTransaction.lot_id == lot.id).order_by(InventoryTransaction.occurred_at.desc()).limit(1)) or "unit"
            transaction = InventoryTransaction(
                organization_id=organization_id,
                facility_id=facility_id,
                lot_id=lot.id,
                transaction_type="inventory_adjustment",
                quantity_delta=delta,
                unit=unit,
                reason=reason,
                reference=payload.reason_note.strip()[:255],
                actor=actor,
            )
            session.add(transaction)
            session.flush()
            changes = {
                "previous_quantity": previous, "delta": delta, "final_quantity": final,
                "reserved_quantity": reserved, "unit": unit, "reason": reason,
                "reason_note": payload.reason_note.strip(), "transaction_id": transaction.id,
            }
            session.add(AuditEvent(
                organization_id=organization_id, facility_id=facility_id,
                entity_type="inventory_lot", entity_id=lot.id,
                action="inventory_adjusted", actor=actor,
                changes_json=json.dumps(changes, sort_keys=True),
            ))
            result = InventoryAdjustmentResult(transaction_id=transaction.id, lot_id=lot.id, **{key: changes[key] for key in ("previous_quantity", "delta", "final_quantity", "reserved_quantity", "unit", "reason")})
        return result
