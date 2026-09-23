from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.purchase_order_continuity import get_saved_purchase_order, list_saved_purchase_orders
from modules.coman.models import Base, CommercialOrder, Facility, InventoryTransaction, Organization, Product
from modules.commercial.repository import CommercialRepository
# Register the canonical FK targets before create_all, including when this
# file is collected alone rather than after the full API test collection.
from modules.cultivation import models as _cultivation_models  # noqa: F401
from services.purchase_order_pdf import money_value, render_saved_purchase_order, saved_order_total


@pytest.fixture
def purchase_orders():
    engine=create_engine("sqlite+pysqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        org=Organization(name="PO test",slug="po-continuity")
        other=Organization(name="Other",slug="po-continuity-other")
        session.add_all([org,other]);session.flush()
        facility=Facility(organization_id=org.id,name="Retail",code="RETAIL",retail_enabled=True)
        sibling=Facility(organization_id=org.id,name="Other facility",code="OTHER",retail_enabled=True)
        product=Product(organization_id=org.id,sku="PO-ONE",name="Saved product",item_type="finished_good",base_unit="unit",unit_cost=12.5)
        session.add_all([facility,sibling,product]);session.flush()
        org_id,facility_id,sibling_id,other_id,product_id=org.id,facility.id,sibling.id,other.id,product.id
    repository=CommercialRepository(engine)
    vendor=repository.create_trade_partner(org_id,name="Continuity vendor",partner_type="both",actor="tester")
    order=repository.create_order(organization_id=org_id,facility_id=facility_id,partner_id=vendor.id,order_number="PO-CONTINUITY-001",order_type="purchase",order_date=date(2026,9,23),due_date=None,lines=[{"product_id":product_id,"quantity":3,"unit":"unit","unit_price":12.5,"description":"Saved product description"}],actor="tester",notes="Preserve this note")
    sibling_order=repository.create_order(organization_id=org_id,facility_id=sibling_id,partner_id=vendor.id,order_number="PO-SIBLING-001",order_type="purchase",order_date=date(2026,9,23),due_date=None,lines=[{"product_id":product_id,"quantity":1,"unit":"unit","unit_price":12.5,"description":"Sibling"}],actor="tester")
    sale=repository.create_order(organization_id=org_id,facility_id=facility_id,partner_id=vendor.id,order_number="SO-CONTINUITY-001",order_type="sales",order_date=date(2026,9,23),due_date=None,lines=[{"product_id":product_id,"quantity":1,"unit":"unit","unit_price":12.5,"description":"Sale"}],actor="tester")
    yield engine, (org_id,facility_id,sibling_id,other_id,product_id,order.id,sibling_order.id,sale.id)
    engine.dispose()


def test_saved_order_reopens_from_canonical_ledger_and_preserves_original_lines(purchase_orders):
    engine,(org,facility,_sibling,_other,product_id,order_id,*_)=purchase_orders
    first=get_saved_purchase_order(engine,org,facility,order_id)
    assert first["total"]=="37.50"
    assert first["lines"][0]["product_id"]==product_id
    assert first["order"]["notes"]=="Preserve this note"
    with Session(engine) as session, session.begin():
        product=session.get(Product,product_id)
        product.name="Changed catalog name"
        product.unit_cost=999
    reopened=get_saved_purchase_order(engine,org,facility,order_id)
    assert reopened["lines"]==first["lines"]
    assert reopened["total"]==first["total"]
    assert reopened["vendor_name"]=="Continuity vendor"
    assert render_saved_purchase_order(reopened).startswith(b"%PDF")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(CommercialOrder))==3
        assert session.scalar(select(func.count()).select_from(InventoryTransaction))==0


def test_saved_order_reads_exclude_other_facilities_and_sales(purchase_orders):
    engine,(org,facility,sibling,other,_product,order_id,sibling_id,sale_id)=purchase_orders
    page=list_saved_purchase_orders(engine,org,facility)
    assert page["total"]==1
    assert [row["id"] for row in page["items"]]==[order_id]
    assert list_saved_purchase_orders(engine,org,facility,search="Continuity vendor")["total"]==1
    assert list_saved_purchase_orders(engine,org,facility,search="PO-SIBLING")["total"]==0
    assert list_saved_purchase_orders(engine,org,facility,offset=1)["items"]==[]
    assert list_saved_purchase_orders(engine,org,facility,limit=1)["has_more"] is False
    for organization, facility_id, requested_id in ((org,sibling,order_id),(other,facility,order_id),(org,facility,sibling_id),(org,facility,sale_id)):
        with pytest.raises(ValueError):
            get_saved_purchase_order(engine,organization,facility_id,requested_id)
    assert list_saved_purchase_orders(engine,other,facility)["total"]==0


def test_pdf_totals_are_computed_from_lines_not_supplied_total():
    lines=[{"quantity":3,"unit_price":12.5,"total":0},{"quantity":1.25,"unit_price":3.14,"total":999999}]
    assert saved_order_total(lines)==Decimal("41.43")
    assert money_value("1.005")==Decimal("1.01")
    with pytest.raises(ValueError):
        money_value("NaN")
    with pytest.raises(ValueError):
        render_saved_purchase_order({"order":{"order_number":"PO-EMPTY","status":"draft"},"lines":[]})


def test_saved_order_lists_reject_unbounded_or_unscoped_requests(purchase_orders):
    engine,(org,facility,*_)=purchase_orders
    for kwargs in ({"offset":-1},{"limit":0},{"limit":101}):
        with pytest.raises(ValueError):
            list_saved_purchase_orders(engine,org,facility,**kwargs)
    with pytest.raises(ValueError):
        list_saved_purchase_orders(engine,"",facility)
