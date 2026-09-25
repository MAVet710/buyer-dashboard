"""Bounded CRM reads and transactional, audited commercial relationship writes."""
import json
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session
from modules.coman.models import Facility, TradePartner, Product, CommercialOrder, CommercialOrderLine, AuditEvent
from modules.coman.audit import record_audit_event
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance.models import CommercialInvoice, CommercialPayment, CommercialShipment, CustomerPriceRule
from modules.commerce_storefronts.models import CommerceStorefrontOrderRequest
from .crm_contracts import AccountInput, OpportunityInput, ActivityInput, QuoteInput
from .crm_models import CustomerRelationship, CommercialOpportunity, CommercialActivity, CommercialQuote


def data(row):
    return {c.name: (getattr(row, c.name).isoformat() if isinstance(getattr(row, c.name), (date, datetime))
                     else float(getattr(row, c.name)) if isinstance(getattr(row, c.name), Decimal)
                     else getattr(row, c.name)) for c in row.__table__.columns}


class CommercialCRM:
    def __init__(self, engine, organization_id, facility_id, actor):
        self.engine, self.org, self.facility, self.actor = engine, organization_id, facility_id, actor

    def scope(self, model):
        return (model.organization_id == self.org, model.facility_id == self.facility)

    def customer(self, session, partner_id):
        facility = session.get(Facility, self.facility)
        partner = session.get(TradePartner, partner_id)
        if not facility or facility.organization_id != self.org or not partner or partner.organization_id != self.org or partner.partner_type not in {'customer', 'both'}:
            raise ValueError('Customer was not found in the active organization and facility.')
        return partner

    def audit(self, session, row, action, before=None):
        session.flush()
        record_audit_event(session, organization_id=self.org, facility_id=self.facility,
            entity_type=row.__tablename__, entity_id=row.id, action=action, actor=self.actor,
            correlation_id=row.id, before=before, after=data(row))

    def save_account(self, partner_id, values):
        values = AccountInput.model_validate(values).model_dump()
        with Session(self.engine) as s, s.begin():
            # Serialize first creation and subsequent edits without a check/insert race.
            s.scalar(select(TradePartner).where(TradePartner.id == partner_id, TradePartner.organization_id == self.org).with_for_update())
            self.customer(s, partner_id)
            row = s.scalar(select(CustomerRelationship).where(*self.scope(CustomerRelationship), CustomerRelationship.partner_id == partner_id))
            before = data(row) if row else None
            if row is None:
                row = CustomerRelationship(organization_id=self.org, facility_id=self.facility, partner_id=partner_id)
                s.add(row)
            for k, v in values.items():
                setattr(row, k, v)
            self.audit(s, row, 'account_updated', before)
            return data(row)

    def opportunity(self, partner_id, values, opportunity_id=None):
        values = OpportunityInput.model_validate(values).model_dump()
        with Session(self.engine) as s, s.begin():
            self.customer(s, partner_id)
            row = None
            if opportunity_id:
                row = s.scalar(select(CommercialOpportunity).where(*self.scope(CommercialOpportunity), CommercialOpportunity.id == opportunity_id, CommercialOpportunity.partner_id == partner_id).with_for_update())
                if row is None:
                    raise ValueError('Opportunity was not found in this customer account.')
            before = data(row) if row else None
            if row is None:
                row = CommercialOpportunity(organization_id=self.org, facility_id=self.facility, partner_id=partner_id)
                s.add(row)
            for k, v in values.items():
                setattr(row, k, v)
            self.audit(s, row, 'opportunity_updated' if before else 'opportunity_created', before)
            return data(row)

    def activity(self, partner_id, values):
        values = ActivityInput.model_validate(values).model_dump()
        with Session(self.engine) as s, s.begin():
            self.customer(s, partner_id)
            row = CommercialActivity(organization_id=self.org, facility_id=self.facility, partner_id=partner_id, actor=self.actor, **values)
            s.add(row)
            self.audit(s, row, 'activity_recorded')
            return data(row)

    def quote(self, partner_id, title, lines, opportunity_id=None):
        validated = QuoteInput(title=title, lines=lines, opportunity_id=opportunity_id)
        title, lines = validated.title, [line.model_dump() for line in validated.lines]
        with Session(self.engine) as s, s.begin():
            self.customer(s, partner_id)
            if opportunity_id and not s.scalar(select(CommercialOpportunity).where(*self.scope(CommercialOpportunity), CommercialOpportunity.id == opportunity_id, CommercialOpportunity.partner_id == partner_id)):
                raise ValueError('Opportunity was not found in this customer account.')
            ids = {line['product_id'] for line in lines}
            products = {p.id: p for p in s.scalars(select(Product).where(Product.organization_id == self.org, Product.active.is_(True), Product.id.in_(ids)))}
            prices = {p.product_id: p for p in s.scalars(select(CustomerPriceRule).where(CustomerPriceRule.organization_id == self.org, CustomerPriceRule.partner_id == partner_id, CustomerPriceRule.active.is_(True), CustomerPriceRule.product_id.in_(ids)))}
            snapshots = []
            for line in lines:
                product = products.get(line['product_id'])
                if not product:
                    raise ValueError('Quote products must be active organization products.')
                rule = prices.get(product.id)
                price = line.get('unit_price')
                if price is None:
                    price = (float(rule.price_usd) if rule.price_usd > 0 else float(product.retail_price) * (1 - float(rule.discount_pct) / 100)) if rule else product.retail_price
                snapshots.append(dict(product_id=product.id, description=product.name, unit=product.base_unit,
                    quantity=line['quantity'], unit_price=round(float(price), 2)))
            row = CommercialQuote(organization_id=self.org, facility_id=self.facility, partner_id=partner_id,
                title=title, opportunity_id=opportunity_id, lines_json=json.dumps(snapshots), created_by=self.actor)
            s.add(row)
            self.audit(s, row, 'quote_created')
            return data(row)

    def convert(self, quote_id):
        with Session(self.engine) as s, s.begin():
            quote = s.scalar(select(CommercialQuote).where(*self.scope(CommercialQuote), CommercialQuote.id == quote_id).with_for_update())
            if not quote:
                raise ValueError('Quote was not found in this facility.')
            if quote.commercial_order_id:
                return {'id': quote.commercial_order_id, 'status': 'converted'}
            before = data(quote)
            order = CommercialRepository(self.engine).create_order(organization_id=self.org, facility_id=self.facility,
                partner_id=quote.partner_id, order_number='Q-' + quote.id, order_type='sales', order_date=date.today(),
                due_date=None, lines=json.loads(quote.lines_json), actor=self.actor, external_reference=quote.id,
                notes=quote.title, session=s, correlation_id=quote.id)
            quote.commercial_order_id, quote.status = order.id, 'converted'
            self.audit(s, quote, 'quote_converted', before)
            return {'id': order.id, 'status': 'converted'}

    def customers(self, search='', offset=0):
        with Session(self.engine) as s:
            statement = select(TradePartner, CustomerRelationship).outerjoin(CustomerRelationship, and_(
                CustomerRelationship.partner_id == TradePartner.id, *self.scope(CustomerRelationship))).where(
                TradePartner.organization_id == self.org, TradePartner.partner_type.in_(['customer', 'both']),
                TradePartner.name.ilike('%' + search + '%')).order_by(TradePartner.name, TradePartner.id).offset(offset).limit(51)
            rows = list(s.execute(statement))
            return {'items': [{**data(p), 'relationship': data(r) if r else None} for p, r in rows[:50]], 'has_more': len(rows) > 50}

    def pipeline(self, offset=0):
        with Session(self.engine) as s:
            rows = list(s.execute(select(CommercialOpportunity, TradePartner.name).join(TradePartner,
                and_(TradePartner.id == CommercialOpportunity.partner_id, TradePartner.organization_id == self.org))
                .where(*self.scope(CommercialOpportunity)).order_by(CommercialOpportunity.created_at.desc(), CommercialOpportunity.id).offset(offset).limit(51)))
            return {'items': [{**data(r), 'customer_name': name} for r, name in rows[:50]], 'has_more': len(rows) > 50}

    def detail(self, partner_id):
        with Session(self.engine) as s:
            partner = self.customer(s, partner_id)
            def rows(model, *conditions):
                return list(s.scalars(select(model).where(*self.scope(model), *conditions).order_by(model.created_at.desc(), model.id).limit(50)))
            orders = select(CommercialOrder.id).where(*self.scope(CommercialOrder), CommercialOrder.partner_id == partner_id)
            invoices = select(CommercialInvoice.id).where(*self.scope(CommercialInvoice), CommercialInvoice.partner_id == partner_id)
            collections = {
                'orders': rows(CommercialOrder, CommercialOrder.partner_id == partner_id),
                'shipments': rows(CommercialShipment, CommercialShipment.commercial_order_id.in_(orders)),
                'invoices': rows(CommercialInvoice, CommercialInvoice.partner_id == partner_id),
                'storefront_requests': rows(CommerceStorefrontOrderRequest, CommerceStorefrontOrderRequest.partner_id == partner_id),
                'activities': rows(CommercialActivity, CommercialActivity.partner_id == partner_id),
                'opportunities': rows(CommercialOpportunity, CommercialOpportunity.partner_id == partner_id),
                'quotes': rows(CommercialQuote, CommercialQuote.partner_id == partner_id),
            }
            collections['payments'] = list(s.scalars(select(CommercialPayment).where(*self.scope(CommercialPayment), CommercialPayment.invoice_id.in_(invoices)).order_by(CommercialPayment.recorded_at.desc(), CommercialPayment.id).limit(50)))
            pricing = list(s.scalars(select(CustomerPriceRule).where(CustomerPriceRule.organization_id == self.org, CustomerPriceRule.partner_id == partner_id, CustomerPriceRule.active.is_(True)).order_by(CustomerPriceRule.id).limit(50)))
            account = s.scalar(select(CustomerRelationship).where(*self.scope(CustomerRelationship), CustomerRelationship.partner_id == partner_id))
            balance = s.scalar(select(func.coalesce(func.sum(CommercialInvoice.balance_usd), 0)).where(*self.scope(CommercialInvoice), CommercialInvoice.partner_id == partner_id, CommercialInvoice.status != 'void'))
            sales = s.scalar(select(func.coalesce(func.sum(CommercialOrderLine.quantity * CommercialOrderLine.unit_price), 0)).join(CommercialOrder, CommercialOrder.id == CommercialOrderLine.commercial_order_id).where(*self.scope(CommercialOrder), CommercialOrder.partner_id == partner_id, CommercialOrder.order_type == 'sales', CommercialOrder.status != 'cancelled', CommercialOrderLine.organization_id == self.org))
            timeline = []
            for kind, items in collections.items():
                for item in items:
                    d = data(item)
                    timeline.append({'id': d['id'], 'kind': kind, 'at': d.get('created_at', d.get('recorded_at')),
                        'text': d.get('body') or d.get('title') or d.get('order_number') or d.get('invoice_number') or d.get('shipment_number') or d.get('reference') or d.get('purchase_order_reference') or kind,
                        'status': d.get('status', d.get('stage', d.get('kind', ''))), 'actor': d.get('actor', d.get('created_by', d.get('recorded_by', '')))})
            # Audit history captures owner, stage and next-action edits, including prior values.
            related = []
            for model in (CustomerRelationship, CommercialOpportunity, CommercialQuote):
                ids = select(model.id).where(*self.scope(model), model.partner_id == partner_id)
                related.append(and_(AuditEvent.entity_type == model.__tablename__, AuditEvent.entity_id.in_(ids)))
            audits = s.scalars(select(AuditEvent).where(*self.scope(AuditEvent), or_(*related))
                .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id).limit(50))
            for audit in audits:
                payload = json.loads(audit.changes_json).get('_event', {})
                after = payload.get('after', {})
                timeline.append({'id': audit.id, 'kind': 'account_history', 'at': audit.occurred_at.isoformat(),
                    'text': audit.action.replace('_', ' ') + ': ' + (after.get('title') or after.get('next_action') or after.get('status', '')),
                    'status': after.get('stage', after.get('status', '')), 'actor': audit.actor,
                    'before': payload.get('before'), 'after': after})
            return {'customer': data(partner), 'relationship': data(account) if account else None,
                'sales_value': sales, 'open_balance': balance, 'pricing': [data(p) for p in pricing],
                **{k: [data(r) for r in v] for k, v in collections.items()},
                'timeline': sorted(timeline, key=lambda e: (e['at'], e['id']), reverse=True)[:50]}
