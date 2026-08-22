from __future__ import annotations
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import Response
from sqlalchemy import Engine
from modules.data_hub_repository import DataHubRepository
from services.web_buyer_parity import read_tabular_bytes,records
from services.web_slow_movers_parity import build_slow_movers,export_excel,export_filename,filter_slow_movers,summary,tier_summary
from ..auth import RequestContext,get_request_context,get_retail_context
from ..database import get_engine

router=APIRouter(prefix="/slow-movers-parity",tags=["slow-movers-parity"],dependencies=[Depends(get_retail_context)])
def _frames(context,engine):
    sources={row.dataset_key:row for row in DataHubRepository(engine).list_active_sources(context.organization_id,context.facility_id)};inventory=sources.get("inventory") or sources.get("sandbox_buyer_inventory");sales=sources.get("product_sales") or sources.get("sandbox_buyer_sales") or sources.get("sandbox_delivery_sales")
    if inventory is None or sales is None:raise HTTPException(422,"Slow Movers needs active Inventory and Product Sales data in Data & Settings.")
    return read_tabular_bytes(inventory.payload,inventory.filename),read_tabular_bytes(sales.payload,sales.filename)
def _view(context,engine,velocity_days,min_doh,top_n,search,category,brand,sort_by,only_slow,exclude_zero):
    inventory,sales=_frames(context,engine)
    try:all_rows=build_slow_movers(inventory,sales,velocity_days)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    return all_rows,filter_slow_movers(all_rows,min_doh=min_doh,top_n=top_n,search=search,category=category,brand=brand,sort_by=sort_by,only_slow=only_slow,exclude_zero=exclude_zero)

@router.get("")
def slow_movers(velocity_days:int=Query(56),min_doh:float=Query(60,ge=1,le=999),top_n:int=Query(0,ge=0,le=500),search:str="",category:str="All",brand:str="All",sort_by:str="Days of Supply ↓",only_slow:bool=True,exclude_zero:bool=False,context:RequestContext=Depends(get_request_context),engine:Engine=Depends(get_engine)):
    if velocity_days not in {28,56,84}:raise HTTPException(422,"Velocity window must be 28, 56, or 84 days.")
    all_rows,view=_view(context,engine,velocity_days,min_doh,top_n,search,category,brand,sort_by,only_slow,exclude_zero);tiers=tier_summary(view)
    return {"controls":{"velocity_days":velocity_days,"min_doh":min_doh,"top_n":top_n,"search":search,"category":category,"brand":brand,"sort_by":sort_by,"only_slow":only_slow,"exclude_zero":exclude_zero},"facets":{"categories":sorted(all_rows.get("category",[]).dropna().astype(str).unique().tolist()) if "category" in all_rows else [],"brands":sorted(all_rows.get("brand",[]).dropna().astype(str).unique().tolist()) if "brand" in all_rows else []},"summary":summary(view,min_doh),"discount_tiers":records(tiers),"items":records(view),"display_columns":[column for column in ["sku","product_name","brand","category","onhandunits","avg_weekly_sales","days_of_supply","weeks_of_supply","dollars_on_hand","days_since_last_sale","action"] if column in view]}

@router.get("/export")
def slow_movers_export(velocity_days:int=56,min_doh:float=60,top_n:int=0,search:str="",category:str="All",brand:str="All",sort_by:str="Days of Supply ↓",only_slow:bool=True,exclude_zero:bool=False,context:RequestContext=Depends(get_request_context),engine:Engine=Depends(get_engine)):
    _all,view=_view(context,engine,velocity_days,min_doh,top_n,search,category,brand,sort_by,only_slow,exclude_zero);tiers=tier_summary(view);columns=[column for column in ["sku","product_name","brand","category","onhandunits","avg_weekly_sales","days_of_supply","weeks_of_supply","dollars_on_hand","days_since_last_sale","action"] if column in view];body=export_excel(view[columns],tiers,view);return Response(content=body,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f'attachment; filename="{export_filename()}"'})
