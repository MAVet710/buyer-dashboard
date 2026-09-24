"""Explicit release gate: disposable loopback PostgreSQL, real JWT/tenant dependencies.
Not collected by the normal tests/ suite. No provider or production credentials.
"""
from datetime import date, datetime, timezone
import json
import os
import secrets
import time
from uuid import uuid4

import jwt
import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.auth import get_authorization_engine
from backend.app.config import Settings, get_settings
from backend.app.database import get_engine
from modules.coman.models import (AppUser, AppUserFacilityRole, Facility, InventoryLot,
                                 InventoryTransaction, Organization, Product)
from modules.commercial.repository import CommercialRepository
from modules.label_studio_workflow import LabelProductionRun


@pytest.fixture(scope="module")
def release_case():
    raw = os.environ.get("DOOBIELOGIC_TEST_POSTGRES_URL", "")
    assert os.environ.get("DOOBIELOGIC_PG_RELEASE_TEST") == "1", "Explicit isolated test opt-in is required"
    url = make_url(raw)
    assert url.drivername == "postgresql+psycopg" and url.host in {"127.0.0.1", "localhost"}
    assert url.database == "doobielogic_release_test", "Refusing a non-test database"
    engine = create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=0)
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT current_database()")) == "doobielogic_release_test"
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        expected = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == expected
        capacity = conn.scalar(text("SELECT character_maximum_length FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='alembic_version' AND column_name='version_num'"))
        assert capacity is None or capacity >= 33
        assert conn.scalar(select(func.count()).select_from(InventoryTransaction)) == 0
    org, other, facility, sibling, alien = [str(uuid4()) for _ in range(5)]
    buyer, reader, foreign, label_operator = [str(uuid4()) for _ in range(4)]
    product, foreign_product, label, foreign_label, lot, foreign_lot = [str(uuid4()) for _ in range(6)]
    tag = "1A4000000000000000007001"
    snapshot = {"product":{"name":"Saved QA label","sku":"PG-QA"},"label":{"product_name":"Saved QA label"},
                "source":{"package_id":"QA-SOURCE","label":{"batch_number":"PG-QA"},"coa":{"lab_name":"QA only"}},
                "print_layout":{"layout":"compact_single","width_in":3.5,"height_in":2.1,"source_count":1},"quantity":24}
    with Session(engine) as session, session.begin():
        session.add_all([Organization(id=org,name="Release QA",slug="release-qa"),
                         Organization(id=other,name="Other QA",slug="release-qa-other")]); session.flush()
        session.add_all([Facility(id=f,organization_id=o,name=f,code=f[:8],retail_enabled=True,production_enabled=True)
                         for f,o in [(facility,org),(sibling,org),(alien,other)]]); session.flush()
        for user,organization,fac,role in [(buyer,org,facility,"buyer"),(reader,org,facility,"read_only"),(foreign,other,alien,"buyer"),(label_operator,org,facility,"operator")]:
            session.add(AppUser(id=user,organization_id=organization,username=user,normalized_username=user,
                                password_hash="not-a-login-password",email=f"{user}@example.test",role=role,
                                must_change_password=False,active=True)); session.flush()
            session.add(AppUserFacilityRole(user_id=user,organization_id=organization,facility_id=fac,role=role))
        for pid,organization in [(product,org),(foreign_product,other)]:
            session.add(Product(id=pid,organization_id=organization,sku=pid[:8],name="QA stock",item_type="finished_good",base_unit="unit",unit_cost=12.5))
        session.flush()
        for lid,organization,fac,pid,n in [(lot,org,facility,product,10),(foreign_lot,other,alien,foreign_product,77)]:
            session.add(InventoryLot(id=lid,organization_id=organization,facility_id=fac,product_id=pid,lot_code=lid,
                                     compliance_package_id=f"QA-{lid}",status="available")); session.flush()
            session.add(InventoryTransaction(organization_id=organization,facility_id=fac,lot_id=lid,
                                             transaction_type="receive",quantity_delta=n,unit="unit",actor="QA"))
        for lid,organization,fac,pid,t in [(label,org,facility,product,tag),(foreign_label,other,alien,foreign_product,"1A4000000000000000007002")]:
            session.add(LabelProductionRun(id=lid,organization_id=organization,facility_id=fac,product_id=pid,
                        quantity=24,status="printed",metrc_package_tag=t,label_snapshot_json=json.dumps(snapshot),
                        created_by="QA",printed_by="QA",printed_at=datetime.now(timezone.utc)))
    repo = CommercialRepository(engine)
    vendor = repo.create_trade_partner(org,name="QA vendor",partner_type="both",actor="QA")
    order = repo.create_order(organization_id=org,facility_id=facility,partner_id=vendor.id,
                order_number="PO-RELEASE-QA",order_type="purchase",order_date=date.today(),due_date=None,
                lines=[{"product_id":product,"quantity":3,"unit":"unit","unit_price":12.5,"description":"Original description"}],actor="QA")
    secret = secrets.token_urlsafe(48)
    settings = Settings(_env_file=None,app_env="production",database_url=raw,
                supabase_url="https://release-qa.example.test",supabase_jwks_url="",supabase_jwt_secret=secret,
                supabase_publishable_key="test-only",integration_encryption_key=secrets.token_urlsafe(32))
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    app.dependency_overrides[get_settings] = lambda: settings
    def headers(user=buyer, organization=org, fac=facility):
        token = jwt.encode({"sub":user,"iss":settings.supabase_url+"/auth/v1","aud":settings.supabase_jwt_audience,
                            "iat":int(time.time()),"exp":int(time.time())+600},secret,algorithm="HS256")
        return {"Authorization":"Bearer "+token,"X-Organization-Id":organization,"X-Facility-Id":fac}
    client = TestClient(app)  # Deliberately do not enter startup/seed lifespan.
    try:
        yield dict(client=client,engine=engine,headers=headers,org=org,other=other,facility=facility,
                   sibling=sibling,alien=alien,buyer=buyer,reader=reader,foreign=foreign,label_operator=label_operator,product=product,
                   label=label,foreign_label=foreign_label,tag=tag,snapshot=snapshot,lot=lot,order=order.id)
    finally:
        client.close(); app.dependency_overrides.clear(); app.dependency_overrides.update(previous); engine.dispose()


@pytest.fixture(autouse=True)
def no_external_provider_requests(monkeypatch):
    def blocked(*args,**kwargs):
        raise AssertionError("Release acceptance must not contact an external provider")
    monkeypatch.setattr(requests.sessions.Session,"request",blocked)


def test_production_auth_and_persisted_facility_membership(release_case):
    x=release_case; client=x["client"]
    paths=["/api/v1/label-printing/history","/api/v1/purchasing/purchase-orders","/api/v1/buyer-parity/current-inventory"]
    for path in paths:
        assert client.get(path,headers={"X-Organization-Id":x["org"],"X-Facility-Id":x["facility"],"X-User-Role":"dev"}).status_code==401
        assert client.get(path,headers={**x["headers"](),"Authorization":"Bearer invalid"}).status_code==401
        assert client.get(path,headers=x["headers"](fac=x["sibling"])).status_code==403
        assert client.get(path,headers=x["headers"](organization=x["other"],fac=x["alien"])).status_code==403
    assert client.get("/api/v1/advisory/admin/leads",headers={**x["headers"](),"X-User-Role":"dev"}).status_code==403


def test_saved_labels_reprint_without_stock_or_identity_mutation(release_case):
    x=release_case; client=x["client"]; h=x["headers"](user=x["label_operator"]); path=f'/api/v1/label-printing/production-runs/{x["label"]}'
    page=client.get("/api/v1/label-printing/history",headers=h)
    assert page.status_code==200 and [r["id"] for r in page.json()["items"]]==[x["label"]]
    before=client.get(path,headers=h); assert before.status_code==200
    assert client.get(f'/api/v1/label-printing/production-runs/{x["foreign_label"]}',headers=h).status_code==404
    with Session(x["engine"]) as session: count=session.scalar(select(func.count()).select_from(InventoryTransaction))
    response=client.post(path+"/print",headers=h,json={"copies":2,"reason":"Damaged labels"}); assert response.status_code==200
    after=client.get(path,headers=h).json()
    assert after["metrc_package_tag"]==x["tag"] and after["quantity"]==24
    assert after["snapshot"]==before.json()["snapshot"]
    assert any(e["event_type"]=="reprinted" and e["details"]["copies"]==2 for e in after["events"])
    assert client.post(path+"/print",headers={**x["headers"](user=x["reader"]),"X-User-Role":"dev"},json={"copies":1,"reason":"No write access"}).status_code==403
    with Session(x["engine"]) as session: assert session.scalar(select(func.count()).select_from(InventoryTransaction))==count


def test_saved_purchase_order_and_pdf_keep_original_values(release_case):
    x=release_case; client=x["client"]; h=x["headers"](); path=f'/api/v1/purchasing/purchase-orders/{x["order"]}'
    first=client.get(path,headers=h); assert first.status_code==200 and first.json()["total"]=="37.50"
    with Session(x["engine"]) as session,session.begin(): session.get(Product,x["product"]).unit_cost=999
    reopened=client.get(path,headers=h); assert reopened.json()["lines"]==first.json()["lines"] and reopened.json()["total"]=="37.50"
    pdf=client.get(path+"/pdf",headers=h); assert pdf.status_code==200 and pdf.content.startswith(b"%PDF")
    assert client.get(path,headers=x["headers"](user=x["foreign"],organization=x["other"],fac=x["alien"])).status_code==404


def test_buyer_current_stock_matches_inventory_on_postgres(release_case):
    x=release_case; client=x["client"]; h=x["headers"]()
    inventory=client.get("/api/v1/inventory/retail/packages",headers=h); assert inventory.status_code==200
    buyer=client.get("/api/v1/buyer-parity/current-inventory",headers=h); assert buyer.status_code==200
    assert buyer.json()["sales_sources"]["state"]=="missing"
    actual={r["id"]:r for r in buyer.json()["items"]}
    expected={r["id"]:r for r in inventory.json()["items"]}
    assert set(actual)==set(expected)=={x["lot"]}
    for key in ["unit","on_hand","available","reserved","package_id","product_id"]:
        assert actual[x["lot"]][key]==expected[x["lot"]][key]
    assert actual[x["lot"]]["on_hand"]==10



def test_extraction_batched_reads_and_single_connection_metrics(release_case):
    """Exercise the repaired read model on migrated PostgreSQL with real auth."""
    from modules.extraction.models import ExtractionRun
    from modules.extraction.performance import ExtractionPerformanceService
    from modules.extraction.performance_models import ExtractionResourceEvent
    from modules.extraction.overview import load_extraction_overview
    x = release_case
    rid, other_rid = str(uuid4()), str(uuid4())
    with Session(x['engine']) as session, session.begin():
        for run_id, org, fac in [(rid, x['org'], x['facility']), (other_rid, x['other'], x['alien'])]:
            session.add(ExtractionRun(id=run_id, organization_id=org, facility_id=fac,
                batch_number='PG-QA-'+run_id, method='Ethanol', workflow_key='ethanol_crude',
                created_by='QA', updated_by='QA', manual_input_weight_g=100,
                manual_finished_output_g=20, manual_cogs_usd=45, estimated_revenue_usd=140))
        session.flush()
        session.add(ExtractionResourceEvent(organization_id=x['org'], facility_id=x['facility'],
            run_id=rid, resource_type='solvent', resource_name='Synthetic', quantity=10,
            recovered_quantity=8, unit='g', cost_usd=5, actor='QA'))
    single = create_engine(x['engine'].url, pool_size=1, max_overflow=0, pool_timeout=0.1)
    try:
        rows, facts = load_extraction_overview(single, x['org'], x['facility'])
        assert [row.id for row in rows] == [rid] and other_rid not in facts
        metrics = ExtractionPerformanceService(single).run_metrics(x['org'], x['facility'], rid)
        assert metrics['resource_cost'] == 5 and metrics['solvent_recovery_pct'] == 80
        assert single.pool.checkedout() == 0
    finally:
        single.dispose()
    path = '/api/v1/extraction-parity/overview'
    response = x['client'].get(path, headers=x['headers'](user=x['label_operator']))
    assert response.status_code == 200
    row = response.json()['runs'][0]
    assert row['id'] == rid and row['cogs_usd'] == 45 and row['est_revenue_usd'] == 140
    assert x['client'].get(path).status_code == 401
    assert x['client'].get(path, headers=x['headers'](user=x['label_operator'], fac=x['alien'])).status_code == 403
