"""Operator choices only. No executable, URL, topic or provider payload input."""
from typing import Literal
from pydantic import Field,ConfigDict,BaseModel

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')

class ConnectionInput(Input):
    adapter:Literal['aranet_cloud','things_stack']
    label:str=Field(min_length=1,max_length=100)
    options:dict[str,str]=Field(default_factory=dict,max_length=4)
    expected_interval_seconds:int=Field(default=60,ge=60,le=3600)
    stale_after_seconds:int=Field(default=600,ge=120,le=86400)

class Choice(Input):
    source_channel:str=Field(min_length=1,max_length=120)
    metric:str=Field(min_length=1,max_length=64)

class DeviceChoice(Input):
    source_id:str=Field(min_length=1,max_length=100)
    room_id:str=Field(min_length=1,max_length=36)
    zone_id:str|None=Field(default=None,max_length=36)
    streams:list[Choice]=Field(min_length=1,max_length=32)

class ApproveInput(Input):
    preview_id:str=Field(min_length=36,max_length=36)
    devices:list[DeviceChoice]=Field(min_length=1,max_length=100)
    confirmed:Literal[True]

class VersionInput(Input):
    version:int=Field(ge=1)

class ActiveInput(VersionInput):
    enabled:bool


def checked_options(adapter,options):
    from .contracts import NetworkError,tts_addresses,tts_id
    if adapter=='aranet_cloud':
        if options:raise NetworkError('unsupported_options')
        return {}
    if set(options)-{'deployment','region','tenant','application_id'}:raise NetworkError('unsupported_options')
    tts_addresses(options);tts_id(options.get('application_id'))
    return dict(options)
