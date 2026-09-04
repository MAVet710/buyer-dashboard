from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.config import Settings
from backend.app.routers.analytics import get_insights, get_product_profitability, get_supply_chain_margin
from backend.app.routers.integrations import integrations
from backend.app.routers.retail_insights import slow_movers
from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product, utc_now
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance.service import CommercialFinanceService


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _operation(engine):
    with Session(engine) as session, session.begin():
        organization = Organization(name="Alpha Crash QA", slug="alpha-crash-qa")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Integrated Alpha",
            code="ALPHA",
            retail_enabled=True,
            production_enabled=True,
            commercial_enabled=True,
        )
        session.add(facility)
        session.flush()
        product = Product(
            organization_id=organization.id,
            sku="ALPHA-FLOWER",
            name="Alpha Flower",
            item_type="finished_good",
            base_unit="unit",
            unit_cost=10,
            retail_price=25,
        )
        session.add(product)
        session.flush()
        ids = organization.id, facility.id, product.id
    return ids


def test_profitability_analytics_use_current_invoice_and_product_cost_schema():
    engine = _engine()
    organization_id, facility_id, product_id = _operation(engine)
    repo = CommercialRepository(engine)
    customer = repo.create_trade_partner(
        organization_id,
        name="Alpha Customer",
        partner_type="customer",
        actor="alpha",
    )
    order = repo.create_order(
        organization_id=organization_id,
        facility_id=facility_id,
        partner_id=customer.id,
        order_number="SO-ALPHA-1",
        order_type="sales",
        order_date=date.today(),
        due_date=date.today(),
        lines=[{
            "product_id": product_id,
            "description": "Alpha Flower",
            "quantity": 10,
            "unit": "unit",
            "unit_price": 20,
        }],
        actor="alpha",
    )
    CommercialFinanceService(engine).create_invoice_from_order(
        organization_id=organization_id,
        facility_id=facility_id,
        order_id=order.id,
        invoice_number="INV-ALPHA-1",
        actor="alpha",
    )
    context = RequestContext("alpha", organization_id, facility_id, role="dev")

    margin = get_supply_chain_margin(30, context, engine)
    profitability = get_product_profitability(30, context, engine)
    insights = get_insights(30, context, engine)

    assert margin["total_revenue"] == 200.0
    assert profitability == [{
        "product_id": product_id,
        "product_name": "Alpha Flower",
        "sku": "ALPHA-FLOWER",
        "units_sold": 10.0,
        "revenue": 200.0,
        "cogs": 100.0,
        "margin": 100.0,
        "margin_pct": 50.0,
    }]
    assert insights["period_days"] == 30


def test_integrations_get_returns_local_alpha_metrc_status_without_crashing_without_encryption_key():
    engine = _engine()
    organization_id, facility_id, _ = _operation(engine)
    context = RequestContext("alpha", organization_id, facility_id, role="admin")
    settings = Settings(app_env="development", integration_encryption_key="")

    result = integrations(context, engine, settings)

    assert result["metrc"]["configured"] is False
    assert result["metrc"]["status"] == "not_connected"
    assert result["metrc"]["facility_id"] == facility_id
    assert result["metrc"]["facility_scoped"] is True
    assert "doobielogic sandbox is active" in result["metrc"]["message"].casefold()


def test_slow_movers_normalizes_sqlite_naive_received_timestamp():
    engine = _engine()
    organization_id, facility_id, product_id = _operation(engine)
    with Session(engine) as session, session.begin():
        lot = InventoryLot(
            organization_id=organization_id,
            facility_id=facility_id,
            product_id=product_id,
            lot_code="ALPHA-OLD-LOT",
            status="available",
            received_at=utc_now() - timedelta(days=90),
        )
        session.add(lot)
        session.flush()
        session.add(InventoryTransaction(
            organization_id=organization_id,
            facility_id=facility_id,
            lot_id=lot.id,
            transaction_type="receipt",
            quantity_delta=25,
            unit="unit",
            actor="alpha",
        ))
    context = RequestContext("alpha", organization_id, facility_id, role="dev")

    result = slow_movers(30, 60, context, engine)

    assert result["summary"]["product_count"] == 1
    assert result["items"][0]["product_id"] == product_id
    assert result["items"][0]["oldest_age_days"] >= 89
