"""CRM safety and continuity against real database services, isolated from production."""
from datetime import date
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from alembic.migration import MigrationContext
from alembic.operations import Operations

from modules.coman.models import Base, AuditEvent, CommercialOrder, CommercialOrderLine, Product
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.commercial.crm import CommercialCRM
from modules.commercial.crm_models import CommercialQuote, CommercialOpportunity
from modules.commercial_finance.models import CustomerPriceRule, CommercialInvoice, CommercialPayment, CommercialShipment
from modules.commerce_storefronts.models import CommerceStorefront, CommerceStorefrontOrderRequest
from backend.app.routers.commercial_crm import router
from backend.app.auth import get_commercial_context
from backend.app.database import get_engine

@pytest.fixture
def env():
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    repo = CommercialRepository(engine)
    org = coman.create_organization('CRM test')
    facility = coman.create_facility(org.id, 'Main', 'MAIN')
    other_facility = coman.create_facility(org.id, 'Other', 'OTHER')
    partner = repo.create_trade_partner(org.id, name='Retail account', partner_type='customer', actor='test')
    product = coman.create_product(org.id, sku='CRM', name='Flower', item_type='finished_good', base_unit='unit', unit_cost=5, actor='test')
    with Session(engine) as s, s.begin():
        s.get(Product, product.id).retail_price = 20
    crm = CommercialCRM(engine, org.id, facility.id, 'sales-rep')
    return SimpleNamespace(engine=engine, coman=coman, repo=repo, org=org, facility=facility, other_facility=other_facility, partner=partner, product=product, crm=crm)

def quote(e, **kw):
    return e.crm.quote(e.partner.id, 'Opening order', [{'product_id': e.product.id, 'quantity': 4}], **kw)

def test_owner_next_action_and_opportunity_lifecycle_are_durable_and_audited(env):
    e = env
    account = e.crm.save_account(e.partner.id, {'owner': 'Nelson', 'status': 'active', 'next_action': 'Call buyer', 'next_action_date': date(2026, 10, 1)})
    assert account['owner'] == 'Nelson'
    assert e.crm.customers()['items'][0]['relationship']['next_action_date'] == '2026-10-01'
    opportunity = e.crm.opportunity(e.partner.id, {'title': 'Fall restock', 'owner': 'Nelson', 'estimated_value': 1250, 'source': 'Trade show'})
    for stage in ['qualified', 'quoted', 'negotiating', 'won', 'lost', 'lead']:
        updated = e.crm.opportunity(e.partner.id, {'title': 'Fall restock', 'stage': stage, 'owner': 'Nelson', 'next_action': 'Follow up'}, opportunity['id'])
        assert updated['stage'] == stage
    assert e.crm.pipeline()['items'][0]['next_action'] == 'Follow up'
    with Session(e.engine) as s:
        audits = list(s.scalars(select(AuditEvent).where(AuditEvent.facility_id == e.facility.id)))
        assert len(audits) == 8
        assert all(json.loads(a.changes_json)['_event']['after'] for a in audits)
    with pytest.raises(ValueError):
        e.crm.opportunity(e.partner.id, {'title': 'Invalid', 'stage': 'made_up'})


def test_quote_uses_customer_pricing_and_conversion_is_atomic_and_idempotent(env, monkeypatch):
    e = env
    with Session(e.engine) as s, s.begin():
        s.add(CustomerPriceRule(organization_id=e.org.id, partner_id=e.partner.id, product_id=e.product.id, price_usd=12, discount_pct=50, updated_by='test'))
    q = quote(e)
    assert json.loads(q['lines_json'])[0]['unit_price'] == 12
    original_audit = e.crm.audit
    def fail(s, row, action, before=None):
        if action == 'quote_converted':
            raise RuntimeError('Injected commit failure')
        return original_audit(s, row, action, before)
    monkeypatch.setattr(e.crm, 'audit', fail)
    with pytest.raises(RuntimeError):
        e.crm.convert(q['id'])
    with Session(e.engine) as s:
        assert s.scalar(select(func.count()).select_from(CommercialOrder)) == 0
        assert s.get(CommercialQuote, q['id']).commercial_order_id is None
    monkeypatch.setattr(e.crm, 'audit', original_audit)
    converted = e.crm.convert(q['id'])
    assert e.crm.convert(q['id']) == converted
    with Session(e.engine) as s:
        order = s.get(CommercialOrder, converted['id'])
        line = s.scalar(select(CommercialOrderLine).where(CommercialOrderLine.commercial_order_id == order.id))
        assert order.partner_id == e.partner.id and order.status == 'draft' and order.order_type == 'sales'
        assert line.quantity == 4 and line.unit_price == 12 and line.fulfilled_quantity == 0
        assert s.scalar(select(func.count()).select_from(CommercialOrder)) == 1
        created = s.scalar(select(AuditEvent).where(AuditEvent.entity_id == order.id))
        assert json.loads(created.changes_json)['_event']['correlation_id'] == q['id']
    with Session(e.engine) as s, s.begin():
        rule = s.scalar(select(CustomerPriceRule))
        rule.price_usd, rule.discount_pct = 0, 25
    assert json.loads(quote(e)['lines_json'])[0]['unit_price'] == 15
    assert json.loads(e.crm.quote(e.partner.id, 'Override', [{'product_id': e.product.id, 'quantity': 1, 'unit_price': 0}])['lines_json'])[0]['unit_price'] == 0


def test_tenant_and_facility_isolation_for_all_crm_writes_and_reads(env):
    e = env
    e.crm.save_account(e.partner.id, {'owner': 'private'})
    op = e.crm.opportunity(e.partner.id, {'title': 'Private deal'})
    q = quote(e)
    e.crm.activity(e.partner.id, {'kind': 'note', 'body': 'Private note'})
    other = CommercialCRM(e.engine, e.org.id, e.other_facility.id, 'other')
    detail = other.detail(e.partner.id)
    assert detail['relationship'] is None
    assert all(detail[k] == [] for k in ['quotes', 'activities', 'opportunities', 'timeline'])
    assert other.pipeline()['items'] == []
    with pytest.raises(ValueError): other.convert(q['id'])
    with pytest.raises(ValueError): other.opportunity(e.partner.id, {'title': 'Hijack'}, op['id'])
    with pytest.raises(ValueError): other.quote(e.partner.id, 'Hijack', [{'product_id': e.product.id, 'quantity': 1}], op['id'])
    org2 = e.coman.create_organization('Foreign')
    f2 = e.coman.create_facility(org2.id, 'Foreign', 'F')
    foreign = CommercialCRM(e.engine, org2.id, f2.id, 'foreign')
    assert foreign.customers()['items'] == []
    for action in [lambda: foreign.detail(e.partner.id), lambda: foreign.save_account(e.partner.id, {}), lambda: foreign.opportunity(e.partner.id, {'title': 'Bad'}), lambda: foreign.activity(e.partner.id, {'body': 'Bad'}), lambda: foreign.convert(q['id'])]:
        with pytest.raises(ValueError): action()
    foreign_product = e.coman.create_product(org2.id, sku='X', name='X', item_type='finished_good', base_unit='unit', actor='test')
    with pytest.raises(ValueError): e.crm.quote(e.partner.id, 'Bad product', [{'product_id': foreign_product.id, 'quantity': 1}])


def test_customer_timeline_aggregates_canonical_records_with_constant_query_count(env):
    e = env
    q = quote(e)
    order_id = e.crm.convert(q['id'])['id']
    with Session(e.engine) as s, s.begin():
        invoice = CommercialInvoice(organization_id=e.org.id, facility_id=e.facility.id, partner_id=e.partner.id, commercial_order_id=order_id, invoice_number='INV-CRM', due_date=date.today(), total_usd=80, balance_usd=60, created_by='test')
        s.add(invoice); s.flush()
        s.add(CommercialPayment(organization_id=e.org.id, facility_id=e.facility.id, invoice_id=invoice.id, amount_usd=20, recorded_by='test'))
        s.add(CommercialShipment(organization_id=e.org.id, facility_id=e.facility.id, commercial_order_id=order_id, shipment_number='SHIP-CRM', created_by='test'))
        # Storefront association is canonical partner_id, never buyer-email matching.
        storefront = CommerceStorefront(organization_id=e.org.id, facility_id=e.facility.id, display_name='Wholesale', slug='crm-test', subdomain='crm-test', created_by='test', updated_by='test')
        s.add(storefront); s.flush()
        s.add(CommerceStorefrontOrderRequest(organization_id=e.org.id, facility_id=e.facility.id, storefront_id=storefront.id, partner_id=e.partner.id, buyer_company='Retail', buyer_contact='Buyer', buyer_email='buyer@example.test'))
    e.crm.activity(e.partner.id, {'kind': 'call', 'body': 'Discussed reorder'})
    count = []
    def trace(*args): count.append(1)
    event.listen(e.engine, 'before_cursor_execute', trace)
    d = e.crm.detail(e.partner.id)
    baseline = len(count)
    event.remove(e.engine, 'before_cursor_execute', trace)
    assert d['sales_value'] == 80 and d['open_balance'] == 60
    assert {'orders', 'shipments', 'invoices', 'payments', 'storefront_requests', 'activities', 'quotes'} <= {r['kind'] for r in d['timeline']}
    for i in range(65): e.crm.activity(e.partner.id, {'body': f'Note {i}'})
    count.clear(); event.listen(e.engine, 'before_cursor_execute', trace)
    d = e.crm.detail(e.partner.id)
    event.remove(e.engine, 'before_cursor_execute', trace)
    assert len(count) == baseline and baseline <= 16
    assert len(d['activities']) == 50 and len(d['timeline']) == 50


def test_http_role_guard_validation_and_pagination(env):
    e = env
    app = FastAPI(); app.include_router(router)
    ctx = SimpleNamespace(organization_id=e.org.id, facility_id=e.facility.id, user_id='tester', role='read_only')
    app.dependency_overrides[get_commercial_context] = lambda: ctx
    app.dependency_overrides[get_engine] = lambda: e.engine
    with TestClient(app) as client:
        path = f'/commercial/crm/customers/{e.partner.id}'
        assert client.get(path).status_code == 200
        for suffix, payload in [('account', {}), ('activities', {'body': 'Denied'}), ('opportunities', {'title': 'Denied'}), ('quotes', {'title': 'Denied', 'lines': [{'product_id': e.product.id, 'quantity': 1}]})]:
            assert client.post(path + '/' + suffix, json=payload).status_code == 403
        assert client.post('/commercial/crm/quotes/missing/convert').status_code == 403
        ctx.role = 'buyer'
        assert client.post(path + '/account', json={'owner': 'Rep', 'next_action': 'Call'}).status_code == 200
        assert client.post(path + '/opportunities', json={'title': ' ', 'estimated_value': -1}).status_code == 422
        assert client.post(path + '/quotes', json={'title': 'Bad', 'lines': []}).status_code == 422
        assert client.post(path + '/activities', json={'body': 'Note', 'organization_id': 'foreign'}).status_code == 422
        assert client.get('/commercial/crm/customers?offset=-1').status_code == 422
    for i in range(55): e.repo.create_trade_partner(e.org.id, name=f'Customer {i:03}', partner_type='customer', actor='test')
    assert len(e.crm.customers()['items']) == 50 and e.crm.customers()['has_more']
    assert len(e.crm.customers(offset=50)['items']) == 6


def test_migration_upgrade_and_evidence_preserving_downgrade():
    path = Path('migrations/versions/0080_wholesale_crm.py')
    spec = importlib.util.spec_from_file_location('crm_migration', path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        tables = migration.TABLES
        connection.exec_driver_sql(f"INSERT INTO {tables[0]} (id,organization_id,facility_id,partner_id,status,owner,next_action,created_at,updated_at) VALUES ('1','o','f','p','active','','',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        with pytest.raises(RuntimeError): migration.downgrade()
        connection.exec_driver_sql(f'DELETE FROM {tables[0]}')
        migration.downgrade()
