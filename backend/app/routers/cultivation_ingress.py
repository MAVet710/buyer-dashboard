"""Bounded normalized receiver. Never route machine tokens through human auth."""
import asyncio
import json
import sqlite3
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect
from modules.cultivation.ingress import MAX_BYTES, authenticate, commit_batch, fail, limiter, validate_envelope
from modules.cultivation.gateway import configured_edge
from modules.cultivation.edge_store import EdgeError, validate_source_identity
from ..database import get_engine

router=APIRouter(prefix='/external/v1/cultivation-telemetry',tags=['cultivation'])


def edge_factory():
    return configured_edge()


def _authorize(engine,token,connection_id,headers):
    with Session(engine) as session:
        return authenticate(session,token,connection_id,headers).scope


def _object(pairs):
    result={}
    for key,value in pairs:
        if key in result:fail(422,'duplicate_field')
        result[key]=value
    return result


def _parse(body):
    # Bound nesting before JSON recursion/allocation. Legal shape is only
    # envelope -> readings array -> reading object, with scalar leaves.
    depth=0;quoted=False;escape=False
    for byte in body:
        if quoted:
            if escape:escape=False
            elif byte==92:escape=True
            elif byte==34:quoted=False
        elif byte==34:quoted=True
        elif byte in (91,123):
            depth+=1
            if depth>3:fail(422,'invalid_structure')
        elif byte in (93,125):depth-=1
    try:
        data=json.loads(body,object_pairs_hook=_object,parse_constant=lambda _:fail(400,'malformed_json'))
    except (ValueError,UnicodeError,RecursionError):fail(400,'malformed_json')
    return validate_envelope(data)


@router.post('/{connection_id}/batches')
async def batches(connection_id:str,request:Request,engine=Depends(get_engine)):
    try:
        with limiter.slot():
            try:validate_source_identity(connection_id)
            except EdgeError:fail(403,'ingress_forbidden')
            authorization=request.headers.get('authorization','')
            scheme,_,token=authorization.partition(' ')
            if scheme.lower()!='bearer':fail(401,'invalid_credential')
            scope=await run_in_threadpool(_authorize,engine,token,connection_id,request.headers)
            limiter.admit(scope)
            if request.headers.get('content-type','').split(';',1)[0].strip().lower()!='application/json' or request.headers.get('content-encoding') is not None:fail(415,'unsupported_media')
            declared=request.headers.get('content-length')
            if declared is not None:
                try:length=int(declared)
                except ValueError:fail(400,'invalid_length')
                if length<0:fail(400,'invalid_length')
                if length>MAX_BYTES:fail(413,'body_limit')
            body=bytearray()
            async with asyncio.timeout(15):
                async for chunk in request.stream():
                    if len(body)+len(chunk)>MAX_BYTES:fail(413,'body_limit')
                    body.extend(chunk)
            data=_parse(body)
            return await run_in_threadpool(commit_batch,engine,token,connection_id,request.headers,data,edge_factory)
    except HTTPException:raise
    except (SQLAlchemyError,sqlite3.Error,OSError,EdgeError,ValueError):fail(503,'ingress_unavailable')
    except (TimeoutError,ClientDisconnect):fail(400,'incomplete_body')
