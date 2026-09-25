"""Wholesale CRM endpoints retain commercial access and explicit write permissions."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from modules.coman.models import Product
from modules.commercial.crm import CommercialCRM
from ..auth import RequestContext, get_commercial_context
from ..database import get_engine
from ..permissions import require_permission
from ..services.work import WorkService

router = APIRouter(prefix='/commercial/crm', tags=['commercial-crm'])

from modules.commercial.crm_contracts import AccountInput, OpportunityInput, ActivityInput, QuoteInput, FollowUpInput


def service(context: RequestContext = Depends(get_commercial_context), engine: Engine = Depends(get_engine)):
    return CommercialCRM(engine, context.organization_id, context.facility_id, context.user_id)


def writer(context: RequestContext = Depends(get_commercial_context), engine: Engine = Depends(get_engine)):
    if context.role.casefold() not in {'dev', 'admin', 'supervisor', 'buyer'}:
        raise HTTPException(403, 'Your role does not allow CRM changes.')
    require_permission(context, engine, 'wholesale.manage_crm')


def run(action):
    try:
        return action()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(409, 'This record changed or conflicts with an existing record. Refresh and retry.') from exc

@router.get('/customers')
def customers(search: str = Query('', max_length=120), offset: int = Query(0, ge=0), crm=Depends(service)):
    return crm.customers(search, offset)

@router.get('/pipeline')
def pipeline(offset: int = Query(0, ge=0), crm=Depends(service)):
    return crm.pipeline(offset)

@router.get('/products')
def products(search: str = Query('', max_length=120), crm=Depends(service)):
    with Session(crm.engine) as s:
        return [dict(id=p.id, name=p.name, sku=p.sku, base_unit=p.base_unit)
            for p in s.scalars(select(Product).where(Product.organization_id == crm.org, Product.active.is_(True), Product.name.ilike('%'+search+'%')).order_by(Product.name, Product.id).limit(50))]

@router.get('/customers/{partner_id}')
def detail(partner_id: str, crm=Depends(service)):
    return run(lambda: crm.detail(partner_id))

@router.post('/customers/{partner_id}/account', dependencies=[Depends(writer)])
def account(partner_id: str, payload: AccountInput, crm=Depends(service)):
    return run(lambda: crm.save_account(partner_id, payload.model_dump()))

@router.post('/customers/{partner_id}/opportunities', dependencies=[Depends(writer)], status_code=201)
def opportunity(partner_id: str, payload: OpportunityInput, crm=Depends(service)):
    return run(lambda: crm.opportunity(partner_id, payload.model_dump()))

@router.post('/customers/{partner_id}/opportunities/{opportunity_id}', dependencies=[Depends(writer)])
def update_opportunity(partner_id: str, opportunity_id: str, payload: OpportunityInput, crm=Depends(service)):
    return run(lambda: crm.opportunity(partner_id, payload.model_dump(), opportunity_id))

@router.post('/customers/{partner_id}/activities', dependencies=[Depends(writer)], status_code=201)
def activity(partner_id: str, payload: ActivityInput, crm=Depends(service)):
    return run(lambda: crm.activity(partner_id, payload.model_dump()))

@router.post('/customers/{partner_id}/quotes', dependencies=[Depends(writer)], status_code=201)
def quote(partner_id: str, payload: QuoteInput, crm=Depends(service)):
    return run(lambda: crm.quote(partner_id, **payload.model_dump()))

@router.post('/quotes/{quote_id}/convert', dependencies=[Depends(writer)])
def convert(quote_id: str, crm=Depends(service)):
    return run(lambda: crm.convert(quote_id))


@router.get('/owners')
def owners(search: str = Query('', max_length=120), offset: int = Query(0, ge=0), crm=Depends(service)):
    return crm.owners(search, offset)


@router.post('/customers/{partner_id}/follow-ups', dependencies=[Depends(writer)], status_code=201)
def follow_up(partner_id: str, payload: FollowUpInput, crm=Depends(service),
              context: RequestContext = Depends(get_commercial_context)):
    return run(lambda: crm.follow_up(partner_id, payload.model_dump(), WorkService(crm.engine, context)))
