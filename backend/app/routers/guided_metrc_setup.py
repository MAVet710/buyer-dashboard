"""In-wizard setup without an alternate credential or regulatory transaction store."""
import json
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.guided_metrc_setup import GuidedMetrcSetup

router=APIRouter(prefix='/integration-wizard/metrc-setup',tags=['integrations'])

class LinkInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    license_number:str=Field(min_length=1,max_length=160)
    create_new:bool=False
    preview_id:str=Field(pattern='^[a-f0-9]{64}$')
    confirmed:Literal[True]

class ImportInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirmed:Literal[True]

def service(context:RequestContext=Depends(get_request_context),engine:Engine=Depends(get_engine),settings:Settings=Depends(get_settings)):
    return GuidedMetrcSetup(engine,settings,context)


def call(s,method,*args):
    try:
        return getattr(s,method)(*args)
    except HTTPException:
        raise
    except (SQLAlchemyError,RuntimeError):
        raise HTTPException(503,'Connection evidence is temporarily unavailable. No new provider action was confirmed.') from None
    except (ValueError,TypeError,KeyError):
        raise HTTPException(422,'Review the selected facility and connection settings.') from None

@router.get('')
def status(s=Depends(service)):
    return call(s,'read')

@router.post('/credentials')
async def save_key(request:Request,s=Depends(service)):
    # Reject before parsing a credential, and never echo submitted values on 422.
    await run_in_threadpool(s.authorize,write=True)
    content=bytearray()
    async for part in request.stream():
        content.extend(part)
        if len(content)>8192:
            raise HTTPException(413,'Connection settings are too large.')
    try:
        body=json.loads(content)
        if not isinstance(body,dict) or set(body)!={'state','api_key'}:
            raise ValueError()
    except (ValueError,UnicodeDecodeError):
        raise HTTPException(422,'Supply the state and current user API key.') from None
    return await run_in_threadpool(call,s,'save_key',body['state'],body['api_key'])

@router.post('/preview')
def preview(s=Depends(service)):
    return call(s,'preview')

@router.post('/link')
def link(payload:LinkInput,s=Depends(service)):
    return call(s,'link',payload.license_number,payload.preview_id,payload.create_new)

@router.post('/import',status_code=202)
def import_records(payload:ImportInput,s=Depends(service)):
    from ..services.guided_metrc_jobs import start_import
    return start_import(s)

@router.post('/platform-vendor')
async def save_platform_vendor(request:Request,s=Depends(service)):
    await run_in_threadpool(s.authorize,write=True)
    if s.context.role.casefold()!='dev':
        raise HTTPException(403,'Platform administrator required.')
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>8192:raise HTTPException(413,'Connection settings are too large.')
    try:
        body=json.loads(data)
        if not isinstance(body,dict) or set(body)!={'state','environment','api_key'}:raise ValueError()
    except (ValueError,UnicodeDecodeError):
        raise HTTPException(422,'Supply the supported state, environment and integrator key.') from None
    return await run_in_threadpool(call,s,'save_platform_key',body['state'],body['environment'],body['api_key'])
