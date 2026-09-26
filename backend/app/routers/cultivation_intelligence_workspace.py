"""Strict authenticated HTTP boundary for cultivation intelligence."""
from fastapi import APIRouter, Depends, HTTPException, Response
from datetime import datetime
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from modules.cultivation.intelligence_service import (IntelligenceService, CycleInput, OccupancyInput, MembersInput, HarvestInput, RecipeInput, VersionInput, EventInput, ConnectionInput, DeviceInput, MappingInput, SensorInput)
from modules.cultivation.metrics import public_registry
from modules.cultivation.telemetry import TelemetryConflict
from modules.cultivation.adapters.base import AdapterMalformedResponse
from modules.cultivation.gateway import TelemetryGatewayService, ImportPreview, ImportCommit, DrainInput, WindowInput, RetentionInput
from modules.cultivation.intelligence_service import OccupancyCloseInput, ZoneInput
from ..auth import RequestContext, get_request_context
from ..database import get_engine
from modules.cultivation.ingress import IngressGrantService, GrantInput

router=APIRouter(prefix='/cultivation-intelligence',tags=['cultivation'])

def service(context:RequestContext=Depends(get_request_context),engine:Engine=Depends(get_engine)):
    return TelemetryGatewayService(engine,context)

def grant_service(context:RequestContext=Depends(get_request_context),engine:Engine=Depends(get_engine)):
    return IngressGrantService(engine,context)

@router.get('/connections/{identity}/ingress-grants')
def grants(identity:str,s=Depends(grant_service)):return call(s,'grants',identity)

@router.post('/connections/{identity}/ingress-grants')
def issue_grant(identity:str,payload:GrantInput,response:Response,s=Depends(grant_service)):
    response.headers['Cache-Control']='no-store'
    return call(s,'issue_grant',identity,payload)

@router.post('/connections/{identity}/ingress-grants/{grant_id}/revoke')
def revoke_grant(identity:str,grant_id:str,payload:VersionInput,s=Depends(grant_service)):return call(s,'revoke_grant',identity,grant_id,payload)

def call(s,method,*args):
    try:return getattr(s,method)(*args)
    except HTTPException:raise
    except AdapterMalformedResponse:raise HTTPException(422,
        "Export could not be parsed. Check the format, columns and row limits.") from None
    except LookupError as exc:raise HTTPException(404,str(exc)) from None
    except TelemetryConflict as exc:raise HTTPException(409,str(exc)) from None
    except IntegrityError:raise HTTPException(409,'A scoped record or version conflicts with existing evidence.') from None
    except ValueError as exc:raise HTTPException(422,str(exc)) from None

@router.get('/workspace')
def workspace(s=Depends(service)):return call(s,'workspace')

@router.get('/rooms/{room_id}')
def room(room_id:str,start:datetime|None=None,end:datetime|None=None,s=Depends(service)):return call(s,'room',room_id,start,end)

@router.get('/cycles/{cycle_id}')
def cycle(cycle_id:str,start:datetime|None=None,end:datetime|None=None,s=Depends(service)):return call(s,'cycle',cycle_id,start,end)

@router.post('/cycles')
def create_cycle(payload:CycleInput,s=Depends(service)):return call(s,'create_cycle',payload)

@router.post('/cycles/{identity}/occupancy')
def occupancy(identity:str,payload:OccupancyInput,s=Depends(service)):return call(s,'occupancy',identity,payload)

@router.post('/cycles/{identity}/members')
def members(identity:str,payload:MembersInput,s=Depends(service)):return call(s,'members',identity,payload)

@router.post('/cycles/{identity}/harvest')
def harvest(identity:str,payload:HarvestInput,s=Depends(service)):return call(s,'link_harvest',identity,payload)

@router.get('/recipes')
def recipes(s=Depends(service)):return call(s,'recipes')

@router.post('/recipes')
def create_recipe(payload:RecipeInput,s=Depends(service)):return call(s,'create_recipe',payload)

@router.post('/recipes/{identity}/approve')
def approve(identity:str,payload:VersionInput,s=Depends(service)):return call(s,'approve_recipe',identity,payload)

@router.post('/events')
def event(payload:EventInput,s=Depends(service)):return call(s,'event',payload)

@router.get('/plants/{identity}/exposure')
def exposure(identity:str,s=Depends(service)):return call(s,'exposure',identity)

@router.get('/metrics')
def metrics(s=Depends(service)):
    s.authorize()
    return {'metrics':public_registry()}

@router.get('/connections')
def connections(s=Depends(service)):return call(s,'connections')

@router.post('/connections')
def create_connection(payload:ConnectionInput,s=Depends(service)):return call(s,'create_connection',payload)

@router.post('/connections/{identity}/revoke')
def revoke(identity:str,payload:VersionInput,s=Depends(service)):return call(s,'revoke',identity,payload)

@router.get('/connections/{identity}/devices')
def devices(identity:str,s=Depends(service)):return call(s,'devices',identity)

@router.post('/connections/{identity}/devices')
def create_device(identity:str,payload:DeviceInput,s=Depends(service)):return call(s,'create_device',identity,payload)

@router.post('/devices/{identity}/mapping')
def mapping(identity:str,payload:MappingInput,s=Depends(service)):return call(s,'map_device',identity,payload)

@router.post('/devices/{identity}/sensors')
def sensor(identity:str,payload:SensorInput,s=Depends(service)):return call(s,'create_sensor',identity,payload)

@router.post('/connections/{identity}/imports/preview')
def preview(identity:str,payload:ImportPreview,s=Depends(service)):return call(s,'preview',identity,payload)

@router.post('/connections/{identity}/imports')
def import_content(identity:str,payload:ImportCommit,s=Depends(service)):return call(s,'import_content',identity,payload)

@router.post('/connections/{identity}/drain')
def drain(identity:str,payload:DrainInput,s=Depends(service)):return call(s,'drain',identity,payload)

@router.get('/connections/{identity}/health')
def health(identity:str,s=Depends(service)):return call(s,'health',identity)

@router.post('/cycles/{identity}/occupancy/{occupancy_id}/close')
def close_occupancy(identity:str,occupancy_id:str,payload:OccupancyCloseInput,s=Depends(service)):return call(s,'close_occupancy',identity,occupancy_id,payload)

@router.post('/rooms/{room_id}/zones')
def create_zone(room_id:str,payload:ZoneInput,s=Depends(service)):return call(s,'create_zone',room_id,payload)

@router.get('/rooms/{room_id}/zones')
def zones(room_id:str,s=Depends(service)):return call(s,'zones',room_id)

@router.get('/devices/{identity}/mapping')
def mappings(identity:str,s=Depends(service)):return call(s,'device_mappings',identity)

@router.get('/devices/{identity}/sensors')
def sensors(identity:str,s=Depends(service)):return call(s,'sensors',identity)

@router.post('/connections/{identity}/rollup')
def rollup(identity:str,payload:WindowInput,s=Depends(service)):return call(s,'rollup',identity,payload)

@router.get('/connections/{identity}/maintenance')
def maintenance(identity:str,s=Depends(service)):return call(s,'maintenance',identity)

@router.post('/connections/{identity}/archive')
def archive(identity:str,payload:DrainInput,s=Depends(service)):return call(s,'archive',identity,payload)

@router.get('/connections/{identity}/evidence')
def evidence(identity:str,limit:int=100,after:str='',s=Depends(service)):return call(s,'evidence',identity,limit,after)

@router.post('/connections/{identity}/retention')
def retention(identity:str,payload:RetentionInput,s=Depends(service)):return call(s,'retention',identity,payload)
