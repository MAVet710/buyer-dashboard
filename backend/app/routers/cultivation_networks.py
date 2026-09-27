"""Customer-owned cloud sensor networks, with explicit read-only authorization."""
import json
from fastapi import APIRouter,Depends,HTTPException,Request
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from ..auth import RequestContext,get_request_context
from ..config import Settings,get_settings
from ..database import get_engine
from ..services.cultivation_network_runtime import get_network_runtime
from modules.cultivation.network.service import NetworkService
from modules.cultivation.network.contracts import NetworkError
from modules.cultivation.network.schemas import ApproveInput,ActiveInput

router=APIRouter(prefix='/cultivation-networks',tags=['cultivation-integrations'])

def service(context:RequestContext=Depends(get_request_context),engine:Engine=Depends(get_engine),settings:Settings=Depends(get_settings)):
    return NetworkService(engine,context,settings.integration_encryption_key,get_network_runtime())

def call(s,method,*args):
    try:return getattr(s,method)(*args)
    except HTTPException:raise
    except NetworkError as exc:
        raise HTTPException(409,{'code':exc.code,'message':'The connection is not ready. Review its setup and current evidence.'}) from None
    except (ValueError,TypeError,KeyError):
        raise HTTPException(422,'Review the supported provider, device and room selections.') from None
    except SQLAlchemyError:
        raise HTTPException(503,'Connection evidence is temporarily unavailable.') from None

@router.get('')
def status(s=Depends(service)):
    return call(s,'status')

@router.post('/connections',status_code=201)
async def create(request:Request,s=Depends(service)):
    await run_in_threadpool(s.manager)
    content=bytearray()
    async for part in request.stream():
        content.extend(part)
        if len(content)>16384:raise HTTPException(413,'Connection settings are too large.')
    try:
        body=json.loads(content)
        if not isinstance(body,dict) or 'api_key' not in body:raise ValueError()
        key=body.pop('api_key')
    except (ValueError,UnicodeDecodeError,RecursionError):
        raise HTTPException(422,'Supply supported connection settings and the customer-owned API key.') from None
    return await run_in_threadpool(call,s,'create',body,key)

@router.post('/{identity}/discover',status_code=202)
def discover(identity:str,s=Depends(service)):
    return call(s,'discover',identity)

@router.get('/{identity}/previews/{preview_id}')
def preview(identity:str,preview_id:str,s=Depends(service)):
    return call(s,'preview',identity,preview_id)

@router.post('/{identity}/approve')
def approve(identity:str,payload:ApproveInput,s=Depends(service)):
    return call(s,'approve',identity,payload)

@router.post('/{identity}/active')
def active(identity:str,payload:ActiveInput,s=Depends(service)):
    return call(s,'active',identity,payload.version,payload.enabled)

@router.post('/{identity}/credential')
async def replace_credential(identity:str,request:Request,s=Depends(service)):
    await run_in_threadpool(s.manager)
    content=bytearray()
    async for part in request.stream():
        content.extend(part)
        if len(content)>8192:raise HTTPException(413,'Connection settings are too large.')
    try:
        body=json.loads(content)
        if not isinstance(body,dict) or set(body)!={'version','api_key'} or type(body['version']) is not int or body['version']<1:raise ValueError()
    except (ValueError,UnicodeDecodeError,RecursionError):
        raise HTTPException(422,'Supply the current version and replacement customer API key.') from None
    return await run_in_threadpool(call,s,'rotate_key',identity,body['version'],body['api_key'])
