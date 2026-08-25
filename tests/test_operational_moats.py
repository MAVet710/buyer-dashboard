from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from modules.coman.models import Base, MachineModel, RetailSale
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance.models import CustomerPriceRule
from modules.operational_moats.intelligence import profitability_360
from modules.operational_moats.service import OperationalMoatService, evaluate_label_rules


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    organization = coman.create_organization("Operational Moat QA")
    facility = coman.create_facility(organization.id, "Main", "MAIN")
    return engine, coman, organization, facility


def test_labelguard_is_deterministic_and_surfaces_failures():
    findings = evaluate_label_rules(
        {"product_name": "GMO 3.5g", "warning_text": "Keep away from children", "thc_mg": 100},
        [
            {"key": "identity", "kind": "required_field", "field": "product_name"},
            {"key": "license", "kind": "required_field", "field": "license_number", "severity": "fail"},
            {"key": "warning", "kind": "contains", "field": "warning_text", "value": "children", "severity": "warning"},
            {"key": "potency", "kind": "numeric_max", "field": "thc_mg", "value": 100},
        ],
    )

    assert [row["status"] for row in findings] == ["pass", "fail", "pass", "pass"]
    assert findings[1]["field"] == "license_number"


def test_sop_versions_acknowledgements_and_deviations_stay_tenant_scoped():
    engine, coman, organization, facility = _setup()
    other = coman.create_organization("Other Tenant")
    service = OperationalMoatService(engine)

    first = service.create_sop(
        organization_id=organization.id,
        facility_id=facility.id,
        code="SOP-QA-001",
        title="QA Release",
        body_text="QA approval is required before release.",
        actor="qa",
        activate=True,
    )
    second = service.create_sop(
        organization_id=organization.id,
        facility_id=facility.id,
        code="SOP-QA-001",
        title="QA Release",
        body_text="QA approval and COA verification are required before release.",
        actor="qa",
        activate=True,
    )
    acknowledgement = service.acknowledge_sop(organization.id, facility.id, second.id, "operator-1")
    deviation = service.record_deviation(
        organization_id=organization.id,
        facility_id=facility.id,
        sop_id=second.id,
        entity_type="production_output",
        entity_id="OUT-1",
        rule_key="qa-before-release",
        severity="high",
        evidence={"released_at": "14:14", "qa_at": "14:47"},
        explanation="Output was released before QA approval.",
        actor="system",
    )

    rows = service.list_sops(organization.id, facility.id)
    assert [row.version for row in rows] == [2, 1]
    assert second.status == "active"
    assert service.list_sops(organization.id, facility.id)[1].status == "retired"
    assert acknowledgement.user_id == "operator-1"
    assert service.list_deviations(organization.id, facility.id)[0].id == deviation.id
    assert service.list_sops(other.id) == []


def test_partner_portal_uses_server_side_inventory_and_customer_pricing():
    engine, coman, organization, facility = _setup()
    product = coman.create_product(
        organization.id,
        sku="FG-1",
        name="Live Resin 1g",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=6,
        retail_price=20,
        actor="dev",
    )
    coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="LOT-1",
        actor="dev",
        opening_quantity=50,
        unit="unit",
    )
    partner = CommercialRepository(engine).create_trade_partner(
        organization.id,
        name="Retail Partner",
        partner_type="customer",
        actor="dev",
        payment_terms="Net 30",
    )
    with Session(engine) as session:
        session.add(
            CustomerPriceRule(
                organization_id=organization.id,
                partner_id=partner.id,
                product_id=product.id,
                price_usd=12,
                discount_pct=0,
                updated_by="dev",
            )
        )
        session.commit()

    service = OperationalMoatService(engine)
    access, token = service.issue_partner_portal_access(
        organization_id=organization.id,
        facility_id=facility.id,
        partner_id=partner.id,
        actor="dev",
    )
    resolved = service.resolve_partner_portal(token)
    catalog = service.partner_catalog(resolved)

    assert resolved.id == access.id
    assert catalog["partner"]["name"] == "Retail Partner"
    assert catalog["catalog"] == [
        {
            "product_id": product.id,
            "sku": "FG-1",
            "name": "Live Resin 1g",
            "unit": "unit",
            "available": 50.0,
            "price_usd": 12.0,
        }
    ]


def test_machine_telemetry_and_harvest_summary_use_facility_assets():
    engine, coman, organization, facility = _setup()
    with Session(engine) as session:
        model = MachineModel(
            manufacturer="Doobie Test",
            model="Filler 1",
            category="filling",
            published_max_rate=100,
        )
        session.add(model)
        session.commit()
        session.refresh(model)
    machine = coman.create_facility_machine(
        organization_id=organization.id,
        facility_id=facility.id,
        machine_model_id=model.id,
        asset_code="FILL-01",
        display_name="Filling Line 1",
        effective_rate=80,
        actor="dev",
    )
    service = OperationalMoatService(engine)
    service.record_telemetry(
        organization_id=organization.id,
        facility_id=facility.id,
        machine_id=machine.id,
        event_type="cycle",
        actor="operator",
        state="running",
        external_event_id="evt-1",
    )
    duplicate = service.record_telemetry(
        organization_id=organization.id,
        facility_id=facility.id,
        machine_id=machine.id,
        event_type="cycle",
        actor="operator",
        state="running",
        external_event_id="evt-1",
    )
    service.create_harvest(
        organization_id=organization.id,
        facility_id=facility.id,
        harvest_code="HARV-1",
        strain="GMO",
        actor="cultivator",
        room="Flower 1",
        plant_count=10,
        wet_weight_g=1000,
        dry_weight_g=250,
        status="completed",
    )

    telemetry = service.telemetry_summary(organization.id, facility.id)
    harvest = service.harvest_summary(organization.id, facility.id)
    assert duplicate.external_event_id == "evt-1"
    assert telemetry["event_count"] == 1
    assert telemetry["machines"][0]["cycles"] == 1
    assert harvest["completed_dry_g"] == 250
    assert harvest["dry_to_wet_pct"] == 25
    assert harvest["by_strain"][0]["dry_g_per_plant"] == 25


def test_profitability_360_combines_retail_and_fulfilled_wholesale_without_cross_tenant_data():
    engine, coman, organization, facility = _setup()
    product = coman.create_product(
        organization.id,
        sku="FG-MARGIN",
        name="Margin Product",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=5,
        retail_price=20,
        actor="dev",
    )
    other = coman.create_organization("Hidden Tenant")
    other_facility = coman.create_facility(other.id, "Other", "OTHER")
    other_product = coman.create_product(
        other.id,
        sku="HIDDEN",
        name="Hidden Product",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=1,
        retail_price=100,
        actor="dev",
    )
    commercial = CommercialRepository(engine)
    customer = commercial.create_trade_partner(organization.id, name="Buyer", partner_type="customer", actor="dev")
    order = commercial.create_order(
        organization_id=organization.id,
        facility_id=facility.id,
        partner_id=customer.id,
        order_number="SO-MARGIN",
        order_type="sales",
        order_date=datetime.now(timezone.utc).date(),
        due_date=None,
        lines=[{"product_id": product.id, "quantity": 3, "unit_price": 10, "unit": "unit"}],
        actor="dev",
    )
    line = commercial.list_order_lines(organization.id, order_id=order.id)[0]
    # Only fulfilled wholesale quantity is realized revenue. Keep one unit open.
    with Session(engine) as session:
        saved = session.get(type(line), line.id)
        saved.fulfilled_quantity = 2
        session.add_all(
            [
                RetailSale(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    product_id=product.id,
                    source_system="test",
                    source_record_id="sale-1",
                    sku=product.sku,
                    product_name=product.name,
                    quantity=2,
                    net_sales=40,
                    sold_at=datetime.now(timezone.utc),
                    imported_by="dev",
                ),
                RetailSale(
                    organization_id=other.id,
                    facility_id=other_facility.id,
                    product_id=other_product.id,
                    source_system="test",
                    source_record_id="hidden-sale",
                    sku=other_product.sku,
                    product_name=other_product.name,
                    quantity=99,
                    net_sales=9900,
                    sold_at=datetime.now(timezone.utc),
                    imported_by="dev",
                ),
            ]
        )
        session.commit()

    result = profitability_360(engine, organization.id, facility.id)
    assert result["summary"]["revenue"] == 60
    assert result["summary"]["standard_cogs"] == 20
    assert result["summary"]["gross_profit"] == 40
    assert [row["product_name"] for row in result["products"]] == ["Margin Product"]
