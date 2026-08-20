"""Tenant-safe Buyer Dash retail register and sale execution repository."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Facility, InventoryLot, InventoryTransaction, Product, utc_now
from .models import RetailRegister, RetailShift, RetailTender, RetailTransaction, RetailTransactionLine


def _clean(value: Any) -> str:
    return str(value or "").strip()


class RetailPosRepository:
    """Durable register ledger with inventory-safe sale completion."""

    def __init__(self, engine: Engine):
        self._session_factory = sessionmaker(
            bind=engine,
            expire_on_commit=False,
            future=True,
        )

    def create_register(
        self,
        *,
        organization_id: str,
        facility_id: str,
        code: str,
        name: str,
    ) -> RetailRegister:
        clean_code = _clean(code).upper()
        clean_name = _clean(name)
        if not clean_code or not clean_name:
            raise ValueError("Register code and name are required.")
        with self._session_factory.begin() as session:
            self._require_facility(session, organization_id, facility_id)
            register = RetailRegister(
                organization_id=organization_id,
                facility_id=facility_id,
                code=clean_code,
                name=clean_name,
            )
            session.add(register)
            session.flush()
            return register

    def open_shift(
        self,
        *,
        organization_id: str,
        facility_id: str,
        register_id: str,
        actor: str,
        opening_cash: float = 0.0,
        notes: str = "",
    ) -> RetailShift:
        if opening_cash < 0:
            raise ValueError("Opening cash cannot be negative.")
        clean_actor = _clean(actor)
        if not clean_actor:
            raise ValueError("An actor is required to open a register shift.")
        with self._session_factory.begin() as session:
            register = self._require_register(session, organization_id, facility_id, register_id)
            existing = session.scalar(
                select(RetailShift).where(
                    RetailShift.organization_id == organization_id,
                    RetailShift.facility_id == facility_id,
                    RetailShift.register_id == register.id,
                    RetailShift.status == "open",
                )
            )
            if existing is not None:
                raise ValueError("This register already has an open shift.")
            shift = RetailShift(
                organization_id=organization_id,
                facility_id=facility_id,
                register_id=register.id,
                opening_cash=float(opening_cash),
                expected_cash=float(opening_cash),
                opened_by=clean_actor,
                notes=_clean(notes),
            )
            session.add(shift)
            session.flush()
            return shift

    def start_sale(
        self,
        *,
        organization_id: str,
        facility_id: str,
        shift_id: str,
        transaction_number: str,
        actor: str,
        customer_reference: str = "",
    ) -> RetailTransaction:
        clean_number = _clean(transaction_number).upper()
        clean_actor = _clean(actor)
        if not clean_number or not clean_actor:
            raise ValueError("Transaction number and actor are required.")
        with self._session_factory.begin() as session:
            shift = self._require_open_shift(session, organization_id, facility_id, shift_id)
            transaction = RetailTransaction(
                organization_id=organization_id,
                facility_id=facility_id,
                register_id=shift.register_id,
                shift_id=shift.id,
                transaction_number=clean_number,
                customer_reference=_clean(customer_reference),
                started_by=clean_actor,
            )
            session.add(transaction)
            session.flush()
            return transaction

    def add_line(
        self,
        *,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
        product_id: str,
        lot_id: str,
        quantity: float,
        unit_price: float,
        discount_amount: float = 0.0,
        tax_amount: float = 0.0,
        description: str = "",
    ) -> RetailTransactionLine:
        quantity = float(quantity)
        unit_price = float(unit_price)
        discount_amount = float(discount_amount)
        tax_amount = float(tax_amount)
        if quantity <= 0:
            raise ValueError("Sale quantity must be greater than zero.")
        if unit_price < 0 or discount_amount < 0 or tax_amount < 0:
            raise ValueError("Price, discount, and tax values cannot be negative.")
        gross = quantity * unit_price
        if discount_amount > gross + tax_amount:
            raise ValueError("Line discount cannot exceed the gross line value plus tax.")
        line_total = max(0.0, gross - discount_amount + tax_amount)

        with self._session_factory.begin() as session:
            transaction = self._require_draft_transaction(
                session, organization_id, facility_id, transaction_id
            )
            product = session.get(Product, product_id)
            if not product or product.organization_id != organization_id or not product.active:
                raise ValueError("Sale line must use an active organization product.")
            lot = session.get(InventoryLot, lot_id)
            if (
                not lot
                or lot.organization_id != organization_id
                or lot.facility_id != facility_id
                or lot.product_id != product.id
            ):
                raise ValueError("Sale line package does not match the selected facility/product.")
            if str(lot.status or "").casefold() not in {"available", "released"}:
                raise ValueError("The selected package is not in a sellable inventory status.")

            position = int(
                session.scalar(
                    select(func.coalesce(func.max(RetailTransactionLine.position), 0)).where(
                        RetailTransactionLine.transaction_id == transaction.id
                    )
                )
                or 0
            ) + 1
            line = RetailTransactionLine(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                product_id=product.id,
                lot_id=lot.id,
                position=position,
                description=_clean(description) or product.name,
                sku_snapshot=product.sku,
                external_package_id=lot.compliance_package_id or lot.lot_code,
                quantity=quantity,
                unit=product.base_unit or "unit",
                unit_price=unit_price,
                discount_amount=discount_amount,
                tax_amount=tax_amount,
                line_total=line_total,
            )
            session.add(line)
            session.flush()
            self._refresh_transaction_totals(session, transaction)
            return line

    def add_tender(
        self,
        *,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
        tender_type: str,
        amount: float,
        provider: str = "",
        provider_reference: str = "",
        approved: bool | None = None,
    ) -> RetailTender:
        normalized_type = _clean(tender_type).casefold()
        if normalized_type not in {"cash", "external"}:
            raise ValueError("Tender type must be cash or external.")
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Tender amount must be greater than zero.")
        if normalized_type == "cash":
            status = "approved"
        elif approved is True:
            status = "approved"
        elif approved is False:
            status = "declined"
        else:
            status = "pending"

        with self._session_factory.begin() as session:
            transaction = self._require_draft_transaction(
                session, organization_id, facility_id, transaction_id
            )
            position = int(
                session.scalar(
                    select(func.coalesce(func.max(RetailTender.position), 0)).where(
                        RetailTender.transaction_id == transaction.id
                    )
                )
                or 0
            ) + 1
            tender = RetailTender(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                position=position,
                tender_type=normalized_type,
                provider=_clean(provider),
                provider_reference=_clean(provider_reference),
                amount=amount,
                status=status,
                approved_at=utc_now() if status == "approved" else None,
            )
            session.add(tender)
            session.flush()
            self._refresh_transaction_totals(session, transaction)
            return tender

    def record_external_tender_result(
        self,
        *,
        organization_id: str,
        facility_id: str,
        tender_id: str,
        approved: bool,
        provider_reference: str = "",
    ) -> RetailTender:
        with self._session_factory.begin() as session:
            tender = session.get(RetailTender, tender_id)
            if (
                not tender
                or tender.organization_id != organization_id
                or tender.facility_id != facility_id
                or tender.tender_type != "external"
            ):
                raise ValueError("External tender was not found in the active facility.")
            transaction = self._require_draft_transaction(
                session, organization_id, facility_id, tender.transaction_id
            )
            tender.status = "approved" if approved else "declined"
            tender.provider_reference = _clean(provider_reference) or tender.provider_reference
            tender.approved_at = utc_now() if approved else None
            session.flush()
            self._refresh_transaction_totals(session, transaction)
            return tender

    def complete_sale(
        self,
        *,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
        actor: str,
    ) -> RetailTransaction:
        clean_actor = _clean(actor)
        if not clean_actor:
            raise ValueError("An actor is required to complete a sale.")

        with self._session_factory.begin() as session:
            transaction = self._require_draft_transaction(
                session, organization_id, facility_id, transaction_id
            )
            self._require_open_shift(
                session, organization_id, facility_id, transaction.shift_id
            )
            lines = list(
                session.scalars(
                    select(RetailTransactionLine)
                    .where(RetailTransactionLine.transaction_id == transaction.id)
                    .order_by(RetailTransactionLine.position)
                )
            )
            if not lines:
                raise ValueError("A sale must contain at least one line item.")
            self._refresh_transaction_totals(session, transaction)
            tenders = list(
                session.scalars(
                    select(RetailTender)
                    .where(RetailTender.transaction_id == transaction.id)
                    .order_by(RetailTender.position)
                )
            )
            approved = [tender for tender in tenders if tender.status == "approved"]
            pending = [tender for tender in tenders if tender.status == "pending"]
            if pending:
                raise ValueError("All external tenders must resolve before the sale can complete.")
            approved_total = sum(float(tender.amount) for tender in approved)
            if approved_total + 1e-9 < transaction.total:
                raise ValueError("Approved tenders do not cover the transaction total.")
            overage = max(0.0, approved_total - transaction.total)
            if overage > 1e-9 and not any(tender.tender_type == "cash" for tender in approved):
                raise ValueError("External tenders cannot overpay the transaction total.")

            required_by_lot: dict[str, float] = defaultdict(float)
            for line in lines:
                required_by_lot[line.lot_id] += float(line.quantity)
            for lot_id, required in required_by_lot.items():
                balance = self._inventory_balance(session, lot_id)
                if balance + 1e-9 < required:
                    raise ValueError(
                        f"Package {lot_id} has {balance:g} available but the sale requires {required:g}."
                    )

            for line in lines:
                session.add(
                    InventoryTransaction(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        lot_id=line.lot_id,
                        transaction_type="retail_sale",
                        quantity_delta=-float(line.quantity),
                        unit=line.unit,
                        reason="Retail sale",
                        reference=transaction.transaction_number,
                        actor=clean_actor,
                    )
                )

            transaction.tendered_total = approved_total
            transaction.change_due = overage
            transaction.status = "completed"
            transaction.completed_by = clean_actor
            transaction.completed_at = utc_now()
            session.flush()
            return transaction

    def close_shift(
        self,
        *,
        organization_id: str,
        facility_id: str,
        shift_id: str,
        actor: str,
        closing_cash: float,
        notes: str = "",
    ) -> RetailShift:
        closing_cash = float(closing_cash)
        if closing_cash < 0:
            raise ValueError("Closing cash cannot be negative.")
        clean_actor = _clean(actor)
        if not clean_actor:
            raise ValueError("An actor is required to close a register shift.")

        with self._session_factory.begin() as session:
            shift = self._require_open_shift(session, organization_id, facility_id, shift_id)
            draft_count = int(
                session.scalar(
                    select(func.count(RetailTransaction.id)).where(
                        RetailTransaction.shift_id == shift.id,
                        RetailTransaction.status == "draft",
                    )
                )
                or 0
            )
            if draft_count:
                raise ValueError("Complete or void all draft transactions before closing the shift.")

            cash_received = float(
                session.scalar(
                    select(func.coalesce(func.sum(RetailTender.amount), 0.0))
                    .join(RetailTransaction, RetailTransaction.id == RetailTender.transaction_id)
                    .where(
                        RetailTransaction.shift_id == shift.id,
                        RetailTransaction.status == "completed",
                        RetailTender.tender_type == "cash",
                        RetailTender.status == "approved",
                    )
                )
                or 0.0
            )
            change_paid = float(
                session.scalar(
                    select(func.coalesce(func.sum(RetailTransaction.change_due), 0.0)).where(
                        RetailTransaction.shift_id == shift.id,
                        RetailTransaction.status == "completed",
                    )
                )
                or 0.0
            )
            expected = float(shift.opening_cash) + cash_received - change_paid
            shift.expected_cash = expected
            shift.closing_cash = closing_cash
            shift.cash_variance = closing_cash - expected
            shift.status = "closed"
            shift.closed_by = clean_actor
            shift.closed_at = utc_now()
            if _clean(notes):
                shift.notes = (shift.notes + "\n" + _clean(notes)).strip()
            session.flush()
            return shift

    def transaction_lines(
        self,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
    ) -> list[RetailTransactionLine]:
        with self._session_factory() as session:
            self._require_transaction(session, organization_id, facility_id, transaction_id)
            return list(
                session.scalars(
                    select(RetailTransactionLine)
                    .where(RetailTransactionLine.transaction_id == transaction_id)
                    .order_by(RetailTransactionLine.position)
                )
            )

    def transaction_tenders(
        self,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
    ) -> list[RetailTender]:
        with self._session_factory() as session:
            self._require_transaction(session, organization_id, facility_id, transaction_id)
            return list(
                session.scalars(
                    select(RetailTender)
                    .where(RetailTender.transaction_id == transaction_id)
                    .order_by(RetailTender.position)
                )
            )

    def inventory_balance(
        self,
        organization_id: str,
        facility_id: str,
        lot_id: str,
    ) -> float:
        with self._session_factory() as session:
            lot = session.get(InventoryLot, lot_id)
            if not lot or lot.organization_id != organization_id or lot.facility_id != facility_id:
                raise ValueError("Inventory package was not found in the active facility.")
            return self._inventory_balance(session, lot_id)

    @staticmethod
    def _refresh_transaction_totals(session, transaction: RetailTransaction) -> None:
        subtotal, discount_total, tax_total, total = session.execute(
            select(
                func.coalesce(func.sum(RetailTransactionLine.quantity * RetailTransactionLine.unit_price), 0.0),
                func.coalesce(func.sum(RetailTransactionLine.discount_amount), 0.0),
                func.coalesce(func.sum(RetailTransactionLine.tax_amount), 0.0),
                func.coalesce(func.sum(RetailTransactionLine.line_total), 0.0),
            ).where(RetailTransactionLine.transaction_id == transaction.id)
        ).one()
        tendered = float(
            session.scalar(
                select(func.coalesce(func.sum(RetailTender.amount), 0.0)).where(
                    RetailTender.transaction_id == transaction.id,
                    RetailTender.status == "approved",
                )
            )
            or 0.0
        )
        transaction.subtotal = float(subtotal or 0.0)
        transaction.discount_total = float(discount_total or 0.0)
        transaction.tax_total = float(tax_total or 0.0)
        transaction.total = float(total or 0.0)
        transaction.tendered_total = tendered
        transaction.change_due = max(0.0, tendered - transaction.total)

    @staticmethod
    def _inventory_balance(session, lot_id: str) -> float:
        return float(
            session.scalar(
                select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                    InventoryTransaction.lot_id == lot_id
                )
            )
            or 0.0
        )

    @staticmethod
    def _require_facility(session, organization_id: str, facility_id: str) -> Facility:
        facility = session.get(Facility, facility_id)
        if not facility or facility.organization_id != organization_id:
            raise ValueError("Facility does not belong to the organization.")
        return facility

    @staticmethod
    def _require_register(
        session,
        organization_id: str,
        facility_id: str,
        register_id: str,
    ) -> RetailRegister:
        register = session.get(RetailRegister, register_id)
        if (
            not register
            or register.organization_id != organization_id
            or register.facility_id != facility_id
            or not register.active
        ):
            raise ValueError("Active register was not found in the selected facility.")
        return register

    @staticmethod
    def _require_open_shift(
        session,
        organization_id: str,
        facility_id: str,
        shift_id: str,
    ) -> RetailShift:
        shift = session.get(RetailShift, shift_id)
        if (
            not shift
            or shift.organization_id != organization_id
            or shift.facility_id != facility_id
            or shift.status != "open"
        ):
            raise ValueError("An open register shift was not found in the active facility.")
        return shift

    @staticmethod
    def _require_transaction(
        session,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
    ) -> RetailTransaction:
        transaction = session.get(RetailTransaction, transaction_id)
        if (
            not transaction
            or transaction.organization_id != organization_id
            or transaction.facility_id != facility_id
        ):
            raise ValueError("Retail transaction was not found in the active facility.")
        return transaction

    @classmethod
    def _require_draft_transaction(
        cls,
        session,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
    ) -> RetailTransaction:
        transaction = cls._require_transaction(
            session, organization_id, facility_id, transaction_id
        )
        if transaction.status != "draft":
            raise ValueError("Only draft retail transactions can be changed.")
        return transaction
