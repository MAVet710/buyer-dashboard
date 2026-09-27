"""Host-owned allowlist and optional isolated MQTT runtime, never browser paths."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import os
import re
from ..radio.config import plain_path,unique_object
from .contracts import NetworkError

@dataclass(frozen=True)
class NetworkHostConfig:
    scopes:tuple[tuple[str,str],...]
    python:str=''
    python_sha256:str=''
    packages:str=''
    mqtt_sha256:str=''
    interval_seconds:int=60
    max_connections:int=8

    def matches(self,organization_id,facility_id):
        return (organization_id,facility_id) in self.scopes

    def verify_mqtt(self):
        try:
            executable=plain_path(self.python)
            packages=plain_path(self.packages,directory=True)
            module=plain_path(str(packages/'paho'/'mqtt'/'client.py'))
            if hashlib.sha256(executable.read_bytes()).hexdigest()!=self.python_sha256 or hashlib.sha256(module.read_bytes()).hexdigest()!=self.mqtt_sha256:
                raise ValueError()
        except (ValueError,OSError):raise NetworkError('mqtt_runtime_unavailable') from None


def load_config(path=None):
    value=path if path is not None else os.environ.get('CULTIVATION_NETWORK_CONFIG','')
    if not value:return None
    try:
        file=plain_path(value)
        if file.stat().st_size>16384:raise ValueError()
        data=json.loads(file.read_text(encoding='utf-8-sig'),object_pairs_hook=unique_object)
        if data=={'enabled':False}:return None
        allowed={'enabled','scopes','python','python_sha256','packages','mqtt_sha256','interval_seconds','max_connections'}
        if not isinstance(data,dict) or set(data)-allowed or data.get('enabled') is not True:raise ValueError()
        scopes=data.get('scopes')
        if not isinstance(scopes,list) or not 1<=len(scopes)<=32:raise ValueError()
        values=[]
        for scope in scopes:
            if not isinstance(scope,dict) or set(scope)!={'organization_id','facility_id'}:raise ValueError()
            pair=tuple(scope[key] for key in ('organization_id','facility_id'))
            if any(not isinstance(x,str) or not re.fullmatch('[A-Za-z0-9_-]{1,36}',x) for x in pair):raise ValueError()
            values.append(pair)
        interval=data.get('interval_seconds',60);maximum=data.get('max_connections',8)
        if type(interval) is not int or not 60<=interval<=3600 or type(maximum) is not int or not 1<=maximum<=8:raise ValueError()
        return NetworkHostConfig(tuple(values),**{k:data.get(k,'') for k in ('python','python_sha256','packages','mqtt_sha256')},interval_seconds=interval,max_connections=maximum)
    except (ValueError,TypeError,KeyError,OSError):
        raise NetworkError('invalid_host_network_configuration') from None
