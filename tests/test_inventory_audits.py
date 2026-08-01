from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from modules.coman.models import Base
from modules.coman.repository import ComanRepository
from modules.inventory_audit.repository import InventoryAuditRepository


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    audits = InventoryAuditRepository(engine)
    organization = coman.create_organization("Audit QA")
    facility = coman.create_facility(organization.id, "Main", "MAIN")
    product = coman.create_product(
        organization.id,
        sku="FG-35",
        name="Blue Dream Flower 3.5g",
        item_type="finished_good",
        base_unit="unit",
        actor="dev",
    )
    lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="BD-24001",
        compliance_package_id="1A4FF030000000000000101",
        location_code="VAULT-A1",
        opening_quantity=100,
        unit="unit",
        actor="dev",
    )
    return coman, audits, organization, facility, product, lot


def test_audit_snapshots_expected_balance_and_saves_partial_counts():
    coman, audits, organization, facility, _product, lot = _setup()
    second = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=_product.id,
        lot_code="BD-24002",
        opening_quantity=25,
        unit="unit",
        actor="dev",
    )
    audit = audits.create_audit(
        organization.id,
        facility.id,
        audit_number="AUD-001",
        scope_label="Vault cycle count",
        actor="dev",
    )
    lines = audits.list_lines(organization.id, audit.id)

    assert {line.expected_quantity for line in lines} == {100, 25}
    first_line = next(line for line in lines if line.lot_id == lot.id)
    audits.save_counts(
        organization.id,
        facility.id,
        audit.id,
        counts=[{"line_id": first_line.id, "counted_quantity": 98, "reason": "Sample usage"}],
        actor="counter",
    )
    updated = audits.list_lines(organization.id, audit.id)
    assert next(line for line in updated if line.id == first_line.id).variance_quantity == -2
    assert next(item for item in audits.list_audits(organization.id, facility.id) if item.id == audit.id).status == "in_progress"

    with pytest.raises(ValueError, match="Count every lot"):
        audits.complete_audit(
            organization.id,
            facility.id,
            audit.id,
            actor="dev",
            post_adjustments=True,
        )
    assert coman.inventory_balance(organization.id, second.id) == 25


def test_completion_posts_append_only_adjustment_to_live_balance():
    coman, audits, organization, facility, _product, lot = _setup()
    audit = audits.create_audit(
        organization.id,
        facility.id,
        audit_number="AUD-002",
        actor="dev",
        lot_ids=[lot.id],
    )
    audits.record_scanned_count(
        organization.id,
        facility.id,
        audit.id,
        raw_code="1A4FF030000000000000101",
        quantity=94,
        reason="Count variance",
        actor="counter",
    )
    # A shipment after the snapshot changes the live balance to 90. Completion must
    # post +6, rather than the stale -4 snapshot variance, to reconcile to 96.
    coman.post_inventory_transaction(
        organization.id,
        facility.id,
        lot_id=lot.id,
        transaction_type="shipment",
        quantity_delta=-10,
        unit="unit",
        actor="shipping",
    )
    audits.record_scanned_count(
        organization.id,
        facility.id,
        audit.id,
        raw_code="1A4FF030000000000000101",
        quantity=96,
        reason="Count variance",
        actor="recount-user",
        recount=True,
    )
    completed = audits.complete_audit(
        organization.id,
        facility.id,
        audit.id,
        actor="manager",
        post_adjustments=True,
    )

    assert completed.status == "completed"
    assert coman.inventory_balance(organization.id, lot.id) == 96
    transactions = coman.list_inventory_transactions(organization.id, facility.id)
    adjustment = next(item for item in transactions if item.reference == "AUD-002")
    assert adjustment.quantity_delta == 6
    assert adjustment.reason == "Count variance"
    assert audits.list_lines(organization.id, audit.id)[0].adjustment_transaction_id == adjustment.id


def test_audits_are_tenant_and_facility_scoped():
    _coman, audits, organization, facility, _product, lot = _setup()
    audit = audits.create_audit(
        organization.id,
        facility.id,
        audit_number="AUD-003",
        actor="dev",
        lot_ids=[lot.id],
    )
    other_coman, _, other_org, other_facility, _, _ = _setup()
    del other_coman

    assert audits.list_audits(other_org.id, other_facility.id) == []
    with pytest.raises(ValueError, match="not found"):
        audits.list_lines(other_org.id, audit.id)
    with pytest.raises(ValueError, match="facility"):
        audits.save_counts(
            organization.id,
            other_facility.id,
            audit.id,
            counts=[],
            actor="dev",
        )


def test_completed_audit_can_close_without_adjusting_ledger():
    coman, audits, organization, facility, _product, lot = _setup()
    audit = audits.create_audit(
        organization.id,
        facility.id,
        audit_number="AUD-004",
        actor="dev",
        lot_ids=[lot.id],
    )
    line = audits.list_lines(organization.id, audit.id)[0]
    audits.save_counts(
        organization.id,
        facility.id,
        audit.id,
        counts=[{"line_id": line.id, "counted_quantity": 95}],
        actor="counter",
    )
    audits.record_scanned_count(
        organization.id,
        facility.id,
        audit.id,
        raw_code="1A4FF030000000000000101",
        quantity=95,
        actor="recount-user",
        recount=True,
    )
    audits.complete_audit(
        organization.id,
        facility.id,
        audit.id,
        actor="manager",
        post_adjustments=False,
    )
    assert coman.inventory_balance(organization.id, lot.id) == 100

    with pytest.raises(ValueError, match="closed"):
        audits.complete_audit(
            organization.id,
            facility.id,
            audit.id,
            actor="manager",
            post_adjustments=True,
        )


def test_manual_sql_migration_enables_rls():
    sql = open("migrations/versions/0012_inventory_audits.sql", encoding="utf-8").read().lower()
    assert "alter table public.inventory_audits enable row level security" in sql
    assert "alter table public.inventory_audit_lines enable row level security" in sql
    assert "alter table public.inventory_audit_scans enable row level security" in sql


def test_scan_resolves_upc_and_requires_recount_for_variance():
    coman, audits, organization, facility, product, lot = _setup()
    product.upc = "012345678905"
    lot.barcode_value = "DUTCHIE-INVENTORY-901"
    # Detached ORM changes are not persisted, so create a second fully identified item.
    identified = coman.create_product(
        organization.id,
        sku="VAPE-1G",
        name="Live Resin Vape 1g",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=14,
        retail_price=42,
        upc="012345678905",
        external_product_id="DUTCHIE-PRODUCT-88",
        actor="dev",
    )
    identified_lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=identified.id,
        lot_code="VAPE-LOT-1",
        opening_quantity=20,
        external_inventory_id="DUTCHIE-INVENTORY-901",
        barcode_value="QR-VAPE-LOT-901",
        actor="dev",
    )
    audit = audits.create_audit(
        organization.id,
        facility.id,
        audit_number="RTL-001",
        actor="dev",
        operation_type="retail",
        lot_ids=[identified_lot.id],
    )
    first = audits.record_scanned_count(
        organization.id,
        facility.id,
        audit.id,
        raw_code='{"inventory_id":"DUTCHIE-INVENTORY-901"}',
        quantity=18,
        actor="retail-counter",
    )
    assert first.recount_required is True

    with pytest.raises(ValueError, match="Finish every required recount"):
        audits.complete_audit(
            organization.id,
            facility.id,
            audit.id,
            actor="manager",
            post_adjustments=False,
        )

    recounted = audits.record_scanned_count(
        organization.id,
        facility.id,
        audit.id,
        raw_code="012345678905",
        quantity=19,
        actor="second-counter",
        recount=True,
    )
    assert recounted.recount_quantity == 19
    assert recounted.recount_required is False
    assert len(audits.list_scans(organization.id, audit.id)) == 2


def test_unmatched_scans_are_retained_as_audit_exceptions():
    _coman, audits, organization, facility, _product, lot = _setup()
    audit = audits.create_audit(
        organization.id,
        facility.id,
        audit_number="RTL-002",
        actor="dev",
        operation_type="retail",
        lot_ids=[lot.id],
    )
    with pytest.raises(ValueError, match="No product"):
        audits.record_scanned_count(
            organization.id,
            facility.id,
            audit.id,
            raw_code="UNKNOWN-QR-999",
            quantity=1,
            actor="counter",
        )
    scans = audits.list_scans(organization.id, audit.id)
    assert len(scans) == 1
    assert scans[0].match_status == "unmatched"


def test_retail_snapshot_import_is_durable_and_append_only():
    coman, audits, organization, facility, _product, _lot = _setup()
    rows = [
        {
            "product_name": "Northern Lights Pre-Roll 5pk",
            "sku": "NL-PR-5",
            "upc": "850071099999",
            "external_product_id": "DUTCHIE-P-99",
            "external_inventory_id": "DUTCHIE-I-99",
            "lot_code": "NL-LOT-99",
            "compliance_package_id": "1A4FF030000000000000999",
            "barcode_value": "DUTCHIE-QR-99",
            "location_code": "Backstock A2",
            "quantity": "24 ea",
            "unit": "unit",
            "unit_cost": "$11.50",
            "retail_price": "$35.00",
        }
    ]
    first = audits.import_retail_snapshot(
        organization.id,
        facility.id,
        rows=rows,
        actor="retail-manager",
        reference="Dutchie export 1",
    )
    assert first == {"rows": 1, "products_created": 1, "lots_created": 1, "adjustments": 1}
    product = next(item for item in coman.list_products(organization.id) if item.sku == "NL-PR-5")
    lot = next(item for item in coman.list_inventory_lots(organization.id, facility.id) if item.lot_code == "NL-LOT-99")
    assert product.retail_price == 35
    assert product.upc == "850071099999"
    assert lot.barcode_value == "DUTCHIE-QR-99"
    assert coman.inventory_balance(organization.id, lot.id) == 24

    rows[0]["quantity"] = 21
    second = audits.import_retail_snapshot(
        organization.id,
        facility.id,
        rows=rows,
        actor="retail-manager",
        reference="Dutchie export 2",
    )
    assert second == {"rows": 1, "products_created": 0, "lots_created": 0, "adjustments": 1}
    assert coman.inventory_balance(organization.id, lot.id) == 21
