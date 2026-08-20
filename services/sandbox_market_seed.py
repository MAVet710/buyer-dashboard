"""Durable parity seed for the DEV Sandbox market-takeover surfaces.

The living demo historically populated session DataFrames and core Co-Man tables.
This layer fills the newer durable modules so every licensed surface has realistic
synthetic records. It refuses to write outside the canonical ``dev-sandbox`` /
``SANDBOX`` tenant.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from typing import Any, Mapping, MutableMapping

import pandas as pd
from sqlalchemy import Engine, delete, func, inspect, select
from sqlalchemy.orm import sessionmaker

from modules.benchmarks.models import BenchmarkObservation, BenchmarkSetting
from modules.coman.db import create_coman_engine
from modules.coman.demo_data import DEMO_FACILITY_CODE, DEMO_ORGANIZATION_SLUG
from modules.coman.models import (
    CommercialOrder,
    CommercialOrderLine,
    Facility,
    InventoryLot,
    Organization,
    Product,
    ProductionOrder,
    TradePartner,
    utc_now,
)
from modules.commercial_finance.models import (
    CommercialInvoice,
    CommercialInvoiceLine,
    CommercialPayment,
    CommercialShipment,
    CustomerPriceRule,
)
from modules.design_partners.models import (
    DesignPartnerAccount,
    DesignPartnerFeedback,
    DesignPartnerMetric,
)
from modules.doobie_actions.models import ActionExecution, ActionProposal
from modules.extraction.models import (
    ExtractionCostEvent,
    ExtractionQAEvent,
    ExtractionRun,
    ExtractionRunInput,
    ExtractionRunOutput,
    ExtractionStageEvent,
    ExtractionTollJob,
)
from modules.extraction.performance_models import ExtractionResourceEvent
from modules.extraction.workflows import get_extraction_workflow
from modules.migration_center.models import (
    MigrationBatch,
    MigrationRecord,
    MigrationSalesHistory,
)
from modules.product_master.models import (
    ProductAlias,
    ProductExternalMapping,
    ProductMasterProfile,
    ProductValueEvent,
    ProductVendorLink,
)
from modules.product_master.repository import normalize_alias
from modules.production_erp.models import (
    ProductionCostEvent,
    ProductionQAEvent,
    ProductionRunEvent,
    ProductionRunOutput,
)
from modules.traceability.models import (
    TraceabilityStatusEvent,
    TraceabilityTransaction,
    TraceabilityTransactionAttempt,
)

SANDBOX_MARKET_VERSION = "ux-cohesion-market-parity-v1"

REQUIRED_MARKET_TABLES = (
    "product_master_profiles",
    "migration_batches",
    "production_run_events",
    "commercial_invoices",
    "action_proposals",
    "benchmark_observations",
    "design_partner_accounts",
    "extraction_runs",
    "traceability_transactions",
)


def _catalog_rows(state: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if state is None:
        return {}
    frame = state.get("demo_catalog_df")
    if not isinstance(frame, pd.DataFrame) or frame.empty or "sku" not in {str(c).casefold() for c in frame.columns}:
        # The simulator normally uses lowercase ``sku``; accept the common
        # title-case export too without coupling this seed to one CSV layout.
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            return {}
    columns = {str(column).strip().casefold(): str(column) for column in frame.columns}
    sku_col = columns.get("sku")
    if not sku_col:
        return {}
    return {
        str(row.get(sku_col) or "").strip().upper(): row.to_dict()
        for _, row in frame.iterrows()
        if str(row.get(sku_col) or "").strip()
    }


def _value(row: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    normalized = {str(key).strip().casefold(): value for key, value in row.items()}
    for key in keys:
        if key.casefold() in normalized and normalized[key.casefold()] not in (None, ""):
            return normalized[key.casefold()]
    return default


def _assert_sandbox_scope(session: Any, organization_id: str, facility_id: str) -> tuple[Organization, Facility]:
    organization = session.get(Organization, organization_id)
    facility = session.get(Facility, facility_id)
    if (
        organization is None
        or facility is None
        or facility.organization_id != organization.id
        or organization.slug != DEMO_ORGANIZATION_SLUG
        or facility.code != DEMO_FACILITY_CODE
    ):
        raise ValueError("Sandbox parity seed refused a non-DEV Sandbox tenant.")
    return organization, facility


def _seed_product_master(
    session: Any,
    organization_id: str,
    products: list[Product],
    vendor: TradePartner | None,
    catalog: Mapping[str, Mapping[str, Any]],
    actor: str,
) -> None:
    for product in products[:40]:
        source = dict(catalog.get(str(product.sku or "").upper()) or {})
        profile = session.get(ProductMasterProfile, product.id)
        if profile is None:
            category = str(_value(source, "category", default=product.item_type.replace("_", " ").title()))
            profile = ProductMasterProfile(
                product_id=product.id,
                organization_id=organization_id,
                brand=str(_value(source, "brand", "vendor", default="Sandbox House")),
                category=category,
                subcategory=str(_value(source, "subcategory", default="")),
                strain=str(_value(source, "strain", default="")),
                manufacturer=str(_value(source, "manufacturer", default="DEV Sandbox Manufacturing")),
                product_format=str(_value(source, "product_format", "format", default=category)),
                description="Synthetic canonical Product Master identity for DEV Sandbox testing.",
            )
            session.add(profile)

        if vendor is not None:
            link = session.scalar(
                select(ProductVendorLink).where(
                    ProductVendorLink.product_id == product.id,
                    ProductVendorLink.partner_id == vendor.id,
                )
            )
            if link is None:
                existing_primary = session.scalar(
                    select(ProductVendorLink).where(
                        ProductVendorLink.product_id == product.id,
                        ProductVendorLink.is_primary.is_(True),
                        ProductVendorLink.active.is_(True),
                    )
                )
                session.add(
                    ProductVendorLink(
                        organization_id=organization_id,
                        product_id=product.id,
                        partner_id=vendor.id,
                        vendor_sku=f"SBX-{str(product.sku or product.id[:8]).upper()}",
                        is_primary=existing_primary is None,
                        lead_time_days=7,
                        minimum_order_quantity=12.0,
                        case_pack=6.0,
                        active=True,
                    )
                )

        external_id = f"DEMO-METRC-{str(product.sku or product.id[:10]).upper()}"[:255]
        mapping = session.scalar(
            select(ProductExternalMapping).where(
                ProductExternalMapping.organization_id == organization_id,
                ProductExternalMapping.system_name == "metrc",
                ProductExternalMapping.external_id == external_id,
            )
        )
        if mapping is None:
            session.add(
                ProductExternalMapping(
                    organization_id=organization_id,
                    product_id=product.id,
                    system_name="metrc",
                    external_id=external_id,
                    external_name=product.name,
                    active=True,
                )
            )

        alias_text = f"{product.name} sandbox"
        normalized = normalize_alias(alias_text)
        if normalized and session.scalar(
            select(ProductAlias.id).where(
                ProductAlias.organization_id == organization_id,
                ProductAlias.normalized_alias == normalized,
            )
        ) is None:
            session.add(
                ProductAlias(
                    organization_id=organization_id,
                    product_id=product.id,
                    alias=alias_text,
                    normalized_alias=normalized,
                    source="sandbox",
                    active=True,
                )
            )

        if session.scalar(
            select(ProductValueEvent.id).where(
                ProductValueEvent.organization_id == organization_id,
                ProductValueEvent.product_id == product.id,
                ProductValueEvent.value_type == "wholesale_price",
                ProductValueEvent.source == "sandbox",
            )
        ) is None:
            wholesale = max(float(product.unit_cost or 0) * 1.55, float(product.retail_price or 0) * 0.52, 1.0)
            session.add(
                ProductValueEvent(
                    organization_id=organization_id,
                    product_id=product.id,
                    partner_id=vendor.id if vendor else None,
                    value_type="wholesale_price",
                    amount=round(wholesale, 2),
                    previous_amount=None,
                    currency="USD",
                    source="sandbox",
                    source_reference=SANDBOX_MARKET_VERSION,
                    actor=actor,
                    effective_at=utc_now(),
                )
            )


def _seed_migration_center(
    session: Any,
    organization_id: str,
    facility_id: str,
    products: list[Product],
    actor: str,
) -> None:
    if not products:
        return
    filename = "sandbox-cutover-products.csv"
    batch = session.scalar(
        select(MigrationBatch).where(
            MigrationBatch.organization_id == organization_id,
            MigrationBatch.facility_id == facility_id,
            MigrationBatch.filename == filename,
        )
    )
    if batch is not None:
        current_ids = {row.id for row in products}
        records = list(session.scalars(select(MigrationRecord).where(MigrationRecord.batch_id == batch.id)))
        stale = any(row.canonical_entity_id and row.canonical_entity_id not in current_ids for row in records)
        if stale:
            session.delete(batch)
            session.flush()
            batch = None
    if batch is not None:
        return

    sample = products[:3]
    batch = MigrationBatch(
        organization_id=organization_id,
        facility_id=facility_id,
        source_system="dutchie",
        entity_type="product",
        filename=filename,
        fingerprint="sandbox-product-cutover-v1",
        status="review",
        total_records=len(sample),
        matched_records=max(0, len(sample) - 1),
        review_records=1 if sample else 0,
        unmapped_records=0,
        conflict_records=0,
        committed_records=0,
        created_by=actor,
        notes="Synthetic competitor cutover waiting on one human review.",
    )
    session.add(batch)
    session.flush()
    for index, product in enumerate(sample, start=1):
        review = index == len(sample)
        source = {
            "Product Name": product.name if not review else f"{product.name} legacy",
            "SKU": product.sku,
            "Unit Cost": float(product.unit_cost or 0),
            "Retail Price": float(product.retail_price or 0),
        }
        normalized = {
            "name": source["Product Name"],
            "sku": product.sku,
            "unit_cost": float(product.unit_cost or 0),
            "retail_price": float(product.retail_price or 0),
        }
        session.add(
            MigrationRecord(
                organization_id=organization_id,
                facility_id=facility_id,
                batch_id=batch.id,
                source_row_number=index,
                source_external_id=f"DUTCHIE-DEMO-{index:04d}",
                entity_type="product",
                source_json=json.dumps(source, sort_keys=True),
                normalized_json=json.dumps(normalized, sort_keys=True),
                match_status="review_required" if review else "auto_match",
                confidence=0.72 if review else 1.0,
                canonical_entity_id=product.id,
                match_reason="Name changed upstream; confirm before cutover." if review else "Exact SKU match",
                decision_action="pending" if review else "accept",
                reviewed_by="" if review else actor,
                reviewed_at=None if review else utc_now(),
            )
        )


def _resolve_order_product(session: Any, organization_id: str, order: ProductionOrder) -> Product | None:
    if order.sku:
        product = session.scalar(
            select(Product).where(
                Product.organization_id == organization_id,
                func.lower(Product.sku) == str(order.sku).casefold(),
            )
        )
        if product:
            return product
    return session.scalar(
        select(Product).where(
            Product.organization_id == organization_id,
            func.lower(Product.name) == str(order.product_name).casefold(),
        )
    )


def _seed_production_erp(
    session: Any,
    organization_id: str,
    facility_id: str,
    actor: str,
) -> None:
    orders = list(
        session.scalars(
            select(ProductionOrder)
            .where(
                ProductionOrder.organization_id == organization_id,
                ProductionOrder.facility_id == facility_id,
            )
            .order_by(ProductionOrder.created_at)
            .limit(3)
        )
    )
    for index, order in enumerate(orders):
        if session.scalar(
            select(ProductionRunEvent.id).where(ProductionRunEvent.production_order_id == order.id)
        ) is None:
            session.add(
                ProductionRunEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    production_order_id=order.id,
                    stage_key=("packaging", "qa", "execution")[index % 3],
                    event_type=("measurement", "hold", "started")[index % 3],
                    quantity=float(order.requested_units or 0) * (0.82 if index == 0 else 0.45),
                    unit="unit",
                    waste_quantity=3.0 if index == 0 else 0.0,
                    labor_hours=4.5 + index,
                    machine_hours=3.0 + index,
                    notes="Synthetic production execution event for sandbox parity.",
                    actor=actor,
                )
            )
        product = _resolve_order_product(session, organization_id, order)
        output = session.scalar(
            select(ProductionRunOutput).where(ProductionRunOutput.production_order_id == order.id)
        )
        if output is None and product is not None:
            planned = float(order.requested_units or 0)
            actual = round(planned * (0.91 if index == 0 else 0.62), 2)
            output = ProductionRunOutput(
                organization_id=organization_id,
                facility_id=facility_id,
                production_order_id=order.id,
                product_id=product.id,
                lot_id=None,
                position=1,
                label=product.name,
                planned_quantity=planned,
                actual_quantity=actual,
                unit=product.base_unit or "unit",
                status="released" if index == 0 else ("quarantine" if index == 1 else "planned"),
                created_by=actor,
            )
            session.add(output)
            session.flush()
        if session.scalar(
            select(ProductionCostEvent.id).where(ProductionCostEvent.production_order_id == order.id)
        ) is None:
            session.add_all(
                [
                    ProductionCostEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        production_order_id=order.id,
                        category="labor",
                        amount_usd=145.0 + index * 35,
                        source_type="sandbox",
                        source_id=SANDBOX_MARKET_VERSION,
                        notes="Synthetic labor COGS",
                        actor=actor,
                    ),
                    ProductionCostEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        production_order_id=order.id,
                        category="machine",
                        amount_usd=80.0 + index * 20,
                        source_type="sandbox",
                        source_id=SANDBOX_MARKET_VERSION,
                        notes="Synthetic machine overhead",
                        actor=actor,
                    ),
                ]
            )
        if session.scalar(
            select(ProductionQAEvent.id).where(ProductionQAEvent.production_order_id == order.id)
        ) is None and output is not None:
            session.add(
                ProductionQAEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    production_order_id=order.id,
                    output_id=output.id,
                    event_type="release" if index == 0 else "hold",
                    result="passed" if index == 0 else "pending",
                    document_reference=f"SANDBOX-COA-{index + 1:03d}",
                    notes="Synthetic QA event for workflow testing.",
                    actor=actor,
                )
            )


def _seed_commercial_finance(
    session: Any,
    organization_id: str,
    facility_id: str,
    products: list[Product],
    actor: str,
) -> None:
    orders = list(
        session.scalars(
            select(CommercialOrder)
            .where(
                CommercialOrder.organization_id == organization_id,
                CommercialOrder.facility_id == facility_id,
                CommercialOrder.order_type == "sales",
            )
            .order_by(CommercialOrder.order_date)
            .limit(3)
        )
    )
    today = date.today()
    for index, order in enumerate(orders):
        invoice = session.scalar(
            select(CommercialInvoice).where(CommercialInvoice.commercial_order_id == order.id)
        )
        lines = list(
            session.scalars(
                select(CommercialOrderLine)
                .where(CommercialOrderLine.commercial_order_id == order.id)
                .order_by(CommercialOrderLine.position)
            )
        )
        if invoice is None and lines:
            subtotal = sum(float(line.quantity or 0) * float(line.unit_price or 0) for line in lines)
            paid = round(subtotal * 0.40, 2) if index == 1 else 0.0
            status = "overdue" if index == 0 else ("partial" if index == 1 else "sent")
            due = today - timedelta(days=12) if index == 0 else today + timedelta(days=7 + index)
            invoice = CommercialInvoice(
                organization_id=organization_id,
                facility_id=facility_id,
                commercial_order_id=order.id,
                partner_id=order.partner_id,
                invoice_number=f"INV-SANDBOX-{index + 1:04d}",
                status=status,
                issue_date=today - timedelta(days=20 - index),
                due_date=due,
                currency=order.currency or "USD",
                subtotal_usd=subtotal,
                discount_usd=0.0,
                tax_usd=0.0,
                total_usd=subtotal,
                balance_usd=max(0.0, subtotal - paid),
                notes="Synthetic sandbox invoice.",
                created_by=actor,
            )
            session.add(invoice)
            session.flush()
            for line in lines:
                session.add(
                    CommercialInvoiceLine(
                        organization_id=organization_id,
                        invoice_id=invoice.id,
                        commercial_order_line_id=line.id,
                        product_id=line.product_id,
                        position=line.position,
                        description=line.description,
                        quantity=float(line.quantity),
                        unit=line.unit,
                        unit_price_usd=float(line.unit_price),
                        line_total_usd=float(line.quantity) * float(line.unit_price),
                    )
                )
            if paid > 0:
                session.add(
                    CommercialPayment(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        invoice_id=invoice.id,
                        amount_usd=paid,
                        payment_date=today - timedelta(days=1),
                        method="ach",
                        reference="SANDBOX-PAYMENT",
                        notes="Synthetic partial payment.",
                        recorded_by=actor,
                    )
                )

        if session.scalar(
            select(CommercialShipment.id).where(CommercialShipment.commercial_order_id == order.id)
        ) is None:
            session.add(
                CommercialShipment(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    commercial_order_id=order.id,
                    shipment_number=f"SHIP-SANDBOX-{index + 1:04d}",
                    status=("manifested", "shipped", "planned")[index % 3],
                    manifest_reference=f"MANIFEST-SBX-{index + 1:04d}",
                    carrier="Sandbox Transport",
                    tracking_reference=f"SBX-{7100 + index}",
                    shipped_at=utc_now() if index == 1 else None,
                    notes="Synthetic shipment lifecycle.",
                    created_by=actor,
                )
            )

    if orders and products:
        partner_id = orders[0].partner_id
        product = products[0]
        if session.scalar(
            select(CustomerPriceRule.id).where(
                CustomerPriceRule.partner_id == partner_id,
                CustomerPriceRule.product_id == product.id,
            )
        ) is None:
            session.add(
                CustomerPriceRule(
                    organization_id=organization_id,
                    partner_id=partner_id,
                    product_id=product.id,
                    price_usd=round(max(1.0, float(product.unit_cost or 0) * 1.7), 2),
                    discount_pct=0.0,
                    active=True,
                    notes="Synthetic negotiated wholesale price.",
                    updated_by=actor,
                )
            )


def _seed_doobie_actions(
    session: Any,
    organization_id: str,
    facility_id: str,
    products: list[Product],
    actor: str,
) -> None:
    if not products:
        return
    product = products[0]
    specs = (
        ("sandbox:replenish", "proposed", "Build replenishment batch", 2450.0, "medium"),
        ("sandbox:capacity", "approved", "Recover tomorrow's production shortfall", 1800.0, "high"),
        ("sandbox:margin", "proposed", "Protect margin before reorder", 925.0, "low"),
    )
    for index, (key, status, title, impact, risk) in enumerate(specs):
        if session.scalar(
            select(ActionProposal.id).where(
                ActionProposal.organization_id == organization_id,
                ActionProposal.idempotency_key == key,
            )
        ) is not None:
            continue
        payload = {
            "order_number": f"DOOBIE-SBX-{index + 1:03d}",
            "product_name": product.name,
            "product_format": "Sandbox finished good",
            "requested_units": 120 + index * 30,
            "sku": product.sku,
        }
        session.add(
            ActionProposal(
                organization_id=organization_id,
                facility_id=facility_id,
                idempotency_key=key,
                action_type="create_production_order",
                title=title,
                rationale="Synthetic sandbox recommendation with deterministic preview and human approval.",
                payload_json=json.dumps(payload, sort_keys=True),
                preview_json=json.dumps({"creates": "production order", "units": payload["requested_units"]}, sort_keys=True),
                financial_impact_usd=impact,
                risk_level=risk,
                status=status,
                source_type="sandbox",
                source_id=SANDBOX_MARKET_VERSION,
                created_by="doobie-sandbox",
                approved_by=actor if status == "approved" else "",
                approved_at=utc_now() if status == "approved" else None,
            )
        )


def _seed_benchmarks(
    session: Any,
    organization_id: str,
    facility_id: str,
    actor: str,
) -> None:
    setting = session.scalar(
        select(BenchmarkSetting).where(BenchmarkSetting.organization_id == organization_id)
    )
    if setting is None:
        setting = BenchmarkSetting(
            organization_id=organization_id,
            share_anonymized_aggregates=False,
            minimum_cohort_size=5,
            updated_by=actor,
        )
        session.add(setting)
    else:
        # Sandbox data must never enter the real anonymous network.
        setting.share_anonymized_aggregates = False
        setting.updated_by = actor

    start = date.today() - timedelta(days=29)
    end = date.today()
    observations = (
        ("extraction_yield_pct", "extraction:bho_cured", 18.7, "pct", 8),
        ("extraction_cost_per_output", "extraction:bho_cured", 4.22, "usd_per_unit", 8),
        ("production_attainment_pct", "production:all", 93.4, "pct", 14),
        ("production_cost_per_unit", "production:all", 2.81, "usd_per_unit", 14),
        ("sales_units_per_day", "sales:all", 47.3, "units_per_day", 30),
    )
    for metric, cohort, value, unit, samples in observations:
        existing = session.scalar(
            select(BenchmarkObservation).where(
                BenchmarkObservation.facility_id == facility_id,
                BenchmarkObservation.metric_key == metric,
                BenchmarkObservation.cohort_key == cohort,
                BenchmarkObservation.period_start == start,
                BenchmarkObservation.period_end == end,
            )
        )
        if existing is None:
            session.add(
                BenchmarkObservation(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    metric_key=metric,
                    cohort_key=cohort,
                    value=value,
                    unit=unit,
                    sample_count=samples,
                    period_start=start,
                    period_end=end,
                )
            )


def _seed_design_partner(
    session: Any,
    organization_id: str,
    actor: str,
) -> None:
    account = session.scalar(
        select(DesignPartnerAccount).where(DesignPartnerAccount.organization_id == organization_id)
    )
    if account is None:
        account = DesignPartnerAccount(
            organization_id=organization_id,
            status="pilot",
            champion_name="Sandbox Operations Lead",
            champion_email="sandbox@example.invalid",
            pain_profile="Too many disconnected systems, spreadsheets and duplicate entry.",
            success_targets_json=json.dumps({"hours_saved_per_week": 5, "inventory_accuracy_pct": 98, "cogs_coverage_pct": 90}, sort_keys=True),
            started_at=date.today() - timedelta(days=45),
            target_case_study_date=date.today() + timedelta(days=30),
            notes="Synthetic design-partner account for admin workflow testing.",
            updated_by=actor,
        )
        session.add(account)
        session.flush()
    metrics = (
        ("hours_saved_per_week", 0.0, 7.5, "hours", "higher"),
        ("inventory_accuracy_pct", 91.0, 99.1, "%", "higher"),
        ("cogs_coverage_pct", 24.0, 96.0, "%", "higher"),
    )
    for key, baseline, current, unit, direction in metrics:
        if session.scalar(
            select(DesignPartnerMetric.id).where(
                DesignPartnerMetric.account_id == account.id,
                DesignPartnerMetric.metric_key == key,
            )
        ) is None:
            session.add(
                DesignPartnerMetric(
                    organization_id=organization_id,
                    account_id=account.id,
                    metric_key=key,
                    baseline_value=baseline,
                    current_value=current,
                    unit=unit,
                    direction=direction,
                    evidence="Synthetic sandbox before/after measurement.",
                    updated_by=actor,
                )
            )
    if session.scalar(
        select(DesignPartnerFeedback.id).where(DesignPartnerFeedback.account_id == account.id)
    ) is None:
        session.add(
            DesignPartnerFeedback(
                organization_id=organization_id,
                account_id=account.id,
                area="Mobile workflow",
                severity="high",
                feedback="Routine floor updates must be completable without scrolling.",
                status="planned",
                submitted_by="sandbox-operator",
            )
        )


def _seed_extraction(
    session: Any,
    organization_id: str,
    facility_id: str,
    actor: str,
) -> None:
    lots = list(
        session.scalars(
            select(InventoryLot)
            .where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
            )
            .order_by(InventoryLot.created_at)
            .limit(3)
        )
    )
    if not lots:
        return
    products_by_id = {
        row.id: row
        for row in session.scalars(
            select(Product).where(Product.organization_id == organization_id)
        )
    }
    workflow = get_extraction_workflow("bho_cured")
    stage_keys = [stage.key for stage in workflow.stages]
    current_keys = [
        stage_keys[min(1, len(stage_keys) - 1)],
        stage_keys[min(2, len(stage_keys) - 1)],
        "qa" if workflow.has_stage("qa") else stage_keys[-1],
    ]
    statuses = ["active", "hold", "qa"]
    for index in range(3):
        batch = f"SANDBOX-EXT-{index + 1:03d}"
        run = session.scalar(
            select(ExtractionRun).where(
                ExtractionRun.organization_id == organization_id,
                ExtractionRun.batch_number == batch,
            )
        )
        if run is None:
            run = ExtractionRun(
                organization_id=organization_id,
                facility_id=facility_id,
                batch_number=batch,
                method=workflow.method,
                workflow_key=workflow.key,
                current_stage_key=current_keys[index],
                status=statuses[index],
                release_status="pending" if statuses[index] == "qa" else "blocked",
                product_family="BHO concentrate",
                strain=("GMO", "Super Lemon Haze", "White Truffle")[index],
                toll_processing=False,
                compliance_provider="metrc",
                license_number="MP-DEMO-0001",
                operator=f"Sandbox Operator {index + 1}",
                notes="Synthetic durable extraction run for Run 360 testing.",
                started_at=utc_now() - timedelta(hours=10 + index * 5),
                created_by=actor,
                updated_by=actor,
            )
            session.add(run)
            session.flush()
        lot = lots[index % len(lots)]
        if session.scalar(select(ExtractionRunInput.id).where(ExtractionRunInput.run_id == run.id)) is None:
            session.add(
                ExtractionRunInput(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    run_id=run.id,
                    lot_id=lot.id,
                    role="primary_input",
                    planned_quantity=500.0,
                    reserved_quantity=500.0,
                    consumed_quantity=500.0,
                    unit="g",
                    unit_cost_snapshot=float(products_by_id.get(lot.product_id).unit_cost or 0) if products_by_id.get(lot.product_id) else 0.0,
                    input_cost_usd=500.0 * (float(products_by_id.get(lot.product_id).unit_cost or 0) if products_by_id.get(lot.product_id) else 0.0),
                    source_reference="sandbox",
                    status="consumed",
                    reserved_by=actor,
                )
            )
        if session.scalar(select(ExtractionStageEvent.id).where(ExtractionStageEvent.run_id == run.id)) is None:
            session.add(
                ExtractionStageEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    run_id=run.id,
                    stage_key=run.current_stage_key,
                    event_type="hold" if run.status == "hold" else "measurement",
                    input_weight_g=500.0,
                    output_weight_g=92.0 - index * 7,
                    loss_weight_g=8.0 + index,
                    loss_reason="Synthetic process variance" if index else "",
                    operator=run.operator,
                    notes="Synthetic stage event visible in Run 360.",
                )
            )
        product = products_by_id.get(lot.product_id)
        output = session.scalar(select(ExtractionRunOutput).where(ExtractionRunOutput.run_id == run.id))
        if output is None and product is not None:
            output = ExtractionRunOutput(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run.id,
                product_id=product.id,
                lot_id=None,
                position=1,
                output_label=f"{run.strain} sandbox concentrate",
                quantity=92.0 - index * 7,
                unit="g",
                status="released" if index == 0 else "quarantine",
                coa_status="passed" if index == 0 else ("failed" if index == 1 else "pending"),
                compliance_package_id=f"1A4-SANDBOX-OUT-{index + 1:03d}" if index == 0 else "",
                output_cost_usd=430.0 + index * 65,
                notes="Synthetic extraction output.",
                created_by=actor,
            )
            session.add(output)
            session.flush()
        if session.scalar(select(ExtractionCostEvent.id).where(ExtractionCostEvent.run_id == run.id)) is None:
            session.add_all(
                [
                    ExtractionCostEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        run_id=run.id,
                        category="labor",
                        amount_usd=165.0 + index * 20,
                        source_type="sandbox",
                        source_id=SANDBOX_MARKET_VERSION,
                        notes="Synthetic extraction labor COGS",
                        actor=actor,
                    ),
                    ExtractionCostEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        run_id=run.id,
                        category="processing",
                        amount_usd=95.0 + index * 10,
                        source_type="sandbox",
                        source_id=SANDBOX_MARKET_VERSION,
                        notes="Synthetic extraction processing COGS",
                        actor=actor,
                    ),
                ]
            )
        if session.scalar(select(ExtractionResourceEvent.id).where(ExtractionResourceEvent.run_id == run.id)) is None:
            session.add(
                ExtractionResourceEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    run_id=run.id,
                    stage_key=run.current_stage_key,
                    resource_type="solvent",
                    resource_name="Sandbox hydrocarbon blend",
                    quantity=12.0 + index,
                    unit="lb",
                    recovered_quantity=10.8 + index * 0.7,
                    cost_usd=58.0 + index * 5,
                    source_reference="sandbox",
                    notes="Synthetic solvent usage/recovery.",
                    actor=actor,
                )
            )
        if index == 1 and session.scalar(select(ExtractionQAEvent.id).where(ExtractionQAEvent.run_id == run.id)) is None:
            session.add(
                ExtractionQAEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    run_id=run.id,
                    output_id=output.id if output else None,
                    event_type="hold",
                    result="failed",
                    coa_reference="SANDBOX-COA-FAIL-002",
                    deviation_code="SBX-QA-002",
                    notes="Synthetic QA hold for Operations Inbox testing.",
                    actor=actor,
                )
            )
        if index == 0 and session.scalar(
            select(TraceabilityTransaction.id).where(
                TraceabilityTransaction.organization_id == organization_id,
                TraceabilityTransaction.idempotency_key == "sandbox:extraction:verified",
            )
        ) is None:
            session.add(
                TraceabilityTransaction(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    provider="metrc",
                    license_number=run.license_number,
                    operation_type="package_create",
                    entity_type="extraction_run",
                    entity_id=run.id,
                    idempotency_key="sandbox:extraction:verified",
                    status="verified",
                    request_payload_json=json.dumps({"synthetic": True}),
                    response_payload_json=json.dumps({"accepted": True}),
                    external_reference="1A4-SANDBOX-OUT-001",
                    attempt_count=1,
                    reason="Synthetic verified package creation.",
                    requested_by=actor,
                    approved_by=actor,
                    requested_at=utc_now() - timedelta(hours=2),
                    submitted_at=utc_now() - timedelta(hours=2),
                    completed_at=utc_now() - timedelta(hours=1),
                )
            )


def market_sandbox_readiness(engine: Engine, organization_id: str, facility_id: str) -> dict[str, Any]:
    """Return durable surface counts used by tests and the DEV Sandbox banner."""
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions() as session:
        _assert_sandbox_scope(session, organization_id, facility_id)
        counts = {
            "products": int(session.scalar(select(func.count(ProductMasterProfile.product_id)).where(ProductMasterProfile.organization_id == organization_id)) or 0),
            "switch_center": int(session.scalar(select(func.count(MigrationBatch.id)).where(MigrationBatch.organization_id == organization_id, MigrationBatch.facility_id == facility_id)) or 0),
            "production": int(session.scalar(select(func.count(ProductionRunEvent.id)).where(ProductionRunEvent.organization_id == organization_id, ProductionRunEvent.facility_id == facility_id)) or 0),
            "wholesale_finance": int(session.scalar(select(func.count(CommercialInvoice.id)).where(CommercialInvoice.organization_id == organization_id, CommercialInvoice.facility_id == facility_id)) or 0),
            "doobie_actions": int(session.scalar(select(func.count(ActionProposal.id)).where(ActionProposal.organization_id == organization_id, ActionProposal.facility_id == facility_id)) or 0),
            "benchmarks": int(session.scalar(select(func.count(BenchmarkObservation.id)).where(BenchmarkObservation.organization_id == organization_id, BenchmarkObservation.facility_id == facility_id)) or 0),
            "design_partner": int(session.scalar(select(func.count(DesignPartnerAccount.id)).where(DesignPartnerAccount.organization_id == organization_id)) or 0),
            "extraction": int(session.scalar(select(func.count(ExtractionRun.id)).where(ExtractionRun.organization_id == organization_id, ExtractionRun.facility_id == facility_id)) or 0),
            "traceability": int(session.scalar(select(func.count(TraceabilityTransaction.id)).where(TraceabilityTransaction.organization_id == organization_id, TraceabilityTransaction.facility_id == facility_id)) or 0),
        }
    return {
        "version": SANDBOX_MARKET_VERSION,
        "ready": all(value > 0 for value in counts.values()),
        "counts": counts,
        "missing": [name for name, value in counts.items() if value <= 0],
    }


def seed_market_sandbox(
    engine: Engine,
    organization_id: str,
    facility_id: str,
    *,
    actor: str = "sandbox",
    state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Idempotently populate every newer durable surface inside DEV Sandbox."""
    missing_tables = [name for name in REQUIRED_MARKET_TABLES if not inspect(engine).has_table(name)]
    if missing_tables:
        return {
            "version": SANDBOX_MARKET_VERSION,
            "ready": False,
            "missing_tables": missing_tables,
            "counts": {},
        }

    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        _assert_sandbox_scope(session, organization_id, facility_id)
        products = list(
            session.scalars(
                select(Product)
                .where(Product.organization_id == organization_id, Product.active.is_(True))
                .order_by(Product.name)
            )
        )
        vendor = session.scalar(
            select(TradePartner)
            .where(
                TradePartner.organization_id == organization_id,
                TradePartner.partner_type.in_(("vendor", "both")),
                TradePartner.active.is_(True),
            )
            .order_by(TradePartner.name)
            .limit(1)
        )
        _seed_product_master(session, organization_id, products, vendor, _catalog_rows(state), actor)
        _seed_migration_center(session, organization_id, facility_id, products, actor)
        _seed_production_erp(session, organization_id, facility_id, actor)
        _seed_commercial_finance(session, organization_id, facility_id, products, actor)
        _seed_doobie_actions(session, organization_id, facility_id, products, actor)
        _seed_benchmarks(session, organization_id, facility_id, actor)
        _seed_design_partner(session, organization_id, actor)
        _seed_extraction(session, organization_id, facility_id, actor)

    return market_sandbox_readiness(engine, organization_id, facility_id)


def reset_market_sandbox_dataset(
    *,
    database_url: str | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Delete extension rows before the legacy Co-Man sandbox deletes base FKs."""
    db_engine = engine or create_coman_engine(database_url)
    sessions = sessionmaker(bind=db_engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        organization = session.scalar(
            select(Organization).where(Organization.slug == DEMO_ORGANIZATION_SLUG)
        )
        if organization is None:
            return {"deleted": False, "reason": "not_found"}
        facility = session.scalar(
            select(Facility).where(
                Facility.organization_id == organization.id,
                Facility.code == DEMO_FACILITY_CODE,
            )
        )
        if facility is None:
            return {"deleted": False, "reason": "facility_not_found"}
        _assert_sandbox_scope(session, organization.id, facility.id)
        models = (
            TraceabilityStatusEvent,
            TraceabilityTransactionAttempt,
            TraceabilityTransaction,
            ExtractionResourceEvent,
            ExtractionQAEvent,
            ExtractionCostEvent,
            ExtractionRunOutput,
            ExtractionStageEvent,
            ExtractionRunInput,
            ExtractionTollJob,
            ExtractionRun,
            ProductionQAEvent,
            ProductionCostEvent,
            ProductionRunOutput,
            ProductionRunEvent,
            CommercialPayment,
            CommercialInvoiceLine,
            CommercialInvoice,
            CommercialShipment,
            CustomerPriceRule,
            ActionExecution,
            ActionProposal,
            BenchmarkObservation,
            BenchmarkSetting,
            DesignPartnerFeedback,
            DesignPartnerMetric,
            DesignPartnerAccount,
            MigrationSalesHistory,
            MigrationRecord,
            MigrationBatch,
            ProductValueEvent,
            ProductAlias,
            ProductExternalMapping,
            ProductVendorLink,
            ProductMasterProfile,
        )
        for model in models:
            organization_column = getattr(model, "organization_id", None)
            if organization_column is not None:
                session.execute(delete(model).where(organization_column == organization.id))
    return {"deleted": True}


def _install_reset_guard() -> None:
    """Teach the old sandbox reset about extension-table foreign keys."""
    import modules.coman.demo_data as coman_demo

    original = coman_demo.reset_coman_demo_dataset
    if getattr(original, "_market_sandbox_wrapper", False):
        return

    def reset_with_extensions(*args: Any, **kwargs: Any) -> dict[str, Any]:
        database_url = kwargs.get("database_url")
        engine = kwargs.get("engine")
        try:
            reset_market_sandbox_dataset(database_url=database_url, engine=engine)
        except Exception:
            # Let the canonical reset report its own result; a failed extension
            # cleanup should not turn the reset button into an app-start crash.
            pass
        return original(*args, **kwargs)

    reset_with_extensions._market_sandbox_wrapper = True
    coman_demo.reset_coman_demo_dataset = reset_with_extensions


def install_sandbox_market_runtime(st: Any) -> None:
    """Seed durable DEV Sandbox extensions after the living demo has hydrated."""
    _install_reset_guard()
    try:
        from services.demo_data import demo_enabled_for_state

        if not demo_enabled_for_state(st.session_state):
            return
        organization_id = str(st.session_state.get("active_organization_id") or "").strip()
        facility_id = str(st.session_state.get("active_facility_id") or "").strip()
        if not organization_id or not facility_id:
            return
        actor = str(
            st.session_state.get("auth_username")
            or st.session_state.get("admin_user")
            or "sandbox"
        )
        readiness = seed_market_sandbox(
            create_coman_engine(),
            organization_id,
            facility_id,
            actor=actor,
            state=st.session_state,
        )
        st.session_state["demo_sandbox_market_readiness"] = readiness
        if readiness.get("ready"):
            st.session_state.pop("_sandbox_market_seed_error", None)
        else:
            st.session_state["_sandbox_market_seed_error"] = (
                "Durable sandbox parity is incomplete: "
                + ", ".join(readiness.get("missing") or readiness.get("missing_tables") or [])
            )
    except Exception as exc:
        st.session_state["_sandbox_market_seed_error"] = f"{type(exc).__name__}: {exc}"
