"""Human-authorized radio selection. No raw frame, key or command endpoints."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, field_validator
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from modules.cultivation.intelligence_service import Input
from modules.cultivation.radio.codecs import profiles
from modules.cultivation.radio.config import RadioConfigError
from modules.cultivation.radio.runtime import RadioStateError
from modules.cultivation.radio.service import RadioService
from modules.cultivation.telemetry import TelemetryConflict
from ..auth import RequestContext, get_request_context
from ..database import get_engine
from ..services.cultivation_radio_runtime import get_radio_runtime

router = APIRouter(prefix='/cultivation-radio', tags=['cultivation'])

class ScanInput(Input):
    receiver_id: str = Field(min_length=1, max_length=32, pattern=r'^[a-z0-9_-]+$')
    authorized: Literal[True]

class ConnectInput(Input):
    scan_id: str = Field(min_length=1, max_length=36)
    candidate_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    room_id: str = Field(min_length=1, max_length=36)
    zone_id: str | None = Field(default=None, min_length=1, max_length=36)
    display_name: str = Field(min_length=1, max_length=64)
    ownership_confirmed: Literal[True]
    @field_validator('display_name')
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value or any(not c.isprintable() or c in '<>' for c in value):
            raise ValueError('Use a readable device name.')
        return value

class VersionInput(Input):
    version: int = Field(ge=1, strict=True)

def service(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return RadioService(engine, context, get_radio_runtime())

def call(s, name, *args):
    try:
        return getattr(s, name)(*args)
    except HTTPException:
        raise
    except LookupError:
        raise HTTPException(404, 'The requested radio setup is not available.') from None
    except (RadioStateError, TelemetryConflict):
        raise HTTPException(409, 'Radio setup changed or is unavailable. Refresh and review the device.') from None
    except RadioConfigError:
        raise HTTPException(503, 'The local receiver configuration needs administrator review.') from None
    except IntegrityError:
        raise HTTPException(409, 'This device is already linked or its configuration changed.') from None
    except SQLAlchemyError:
        raise HTTPException(503, 'Radio authorization or configuration is temporarily unavailable.') from None
    except ValueError:
        raise HTTPException(422, 'Check the selected device, room and zone.') from None

@router.get('/status')
def status(s=Depends(service)):
    return call(s, 'status')

@router.get('/profiles')
def supported_profiles(s=Depends(service)):
    s.authorize()
    return profiles()

@router.post('/scans')
def start_scan(payload: ScanInput, s=Depends(service)):
    return call(s, 'start_scan', payload)

@router.get('/scans/{identity}')
def scan(identity: str, s=Depends(service)):
    return call(s, 'scan', identity)

@router.post('/scans/{identity}/stop')
def stop_scan(identity: str, s=Depends(service)):
    return call(s, 'scan', identity, True)

@router.get('/connections')
def connections(s=Depends(service)):
    return call(s, 'connections')

@router.post('/connections')
def connect(payload: ConnectInput, s=Depends(service)):
    return call(s, 'connect', payload)

@router.post('/connections/{identity}/disconnect')
def disconnect(identity: str, payload: VersionInput, s=Depends(service)):
    return call(s, 'disconnect', identity, payload.version)
