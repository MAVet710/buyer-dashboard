"""Explicit host-owned radio capability. Absent configuration does nothing."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import os
import re

class RadioConfigError(ValueError):
    pass

def plain_path(value, *, directory=False):
    if not isinstance(value, str) or not value or any(c in value for c in ('\0', '\r', '\n')):
        raise RadioConfigError('invalid_radio_host_config')
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or value.startswith(('\\\\', '//')):
        raise RadioConfigError('invalid_radio_host_config')
    if os.name == 'nt' and ':' in value[2:]:
        raise RadioConfigError('invalid_radio_host_config')
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise RadioConfigError('invalid_radio_host_config')
    if directory:
        if not path.is_dir():
            raise RadioConfigError('invalid_radio_host_config')
    elif not path.is_file() or path.stat().st_nlink != 1:
        raise RadioConfigError('invalid_radio_host_config')
    return path

def unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise RadioConfigError('invalid_radio_host_config')
        out[key] = value
    return out

@dataclass(frozen=True)
class Receiver:
    id: str
    kind: str
    band: str
    executable: str
    executable_sha256: str
    packages: str = ''
    frequency: int = 0
    device_index: int = 0

    def verify(self):
        p = plain_path(self.executable)
        if hashlib.sha256(p.read_bytes()).hexdigest() != self.executable_sha256:
            raise RadioConfigError('receiver_binary_changed')
        if self.kind == 'ble':
            plain_path(self.packages, directory=True)
            if not (Path(self.packages) / 'bleak' / '__init__.py').is_file():
                raise RadioConfigError('bluetooth_runtime_missing')

@dataclass(frozen=True)
class RadioConfig:
    organization_id: str
    facility_id: str
    receivers: tuple[Receiver, ...]
    sample_seconds: int = 10

def load_config(path=None):
    value = path if path is not None else os.environ.get('CULTIVATION_RADIO_CONFIG', '')
    if not value:
        return None
    try:
        p = plain_path(value)
        if p.stat().st_size > 16384:
            raise RadioConfigError('invalid_radio_host_config')
        data = json.loads(p.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_object)
        if data == {'enabled': False}:
            return None
        if not isinstance(data, dict) or set(data) - {'enabled', 'organization_id', 'facility_id', 'receivers', 'sample_seconds'} or data.get('enabled') is not True:
            raise RadioConfigError('invalid_radio_host_config')
        for key in ('organization_id', 'facility_id'):
            if not isinstance(data.get(key), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,36}', data[key]):
                raise RadioConfigError('invalid_radio_host_config')
        interval = data.get('sample_seconds', 10)
        if type(interval) is not int or not 5 <= interval <= 60:
            raise RadioConfigError('invalid_radio_host_config')
        rows = data.get('receivers')
        if not isinstance(rows, list) or not 1 <= len(rows) <= 2:
            raise RadioConfigError('invalid_radio_host_config')
        receivers = []
        for row in rows:
            if not isinstance(row, dict) or set(row) - {'id', 'kind', 'executable', 'executable_sha256', 'packages', 'frequency', 'device_index'}:
                raise RadioConfigError('invalid_radio_host_config')
            kind = row.get('kind')
            if kind not in ('ble', 'rtl433') or row.get('id') != kind or kind in [x.kind for x in receivers]:
                raise RadioConfigError('invalid_radio_host_config')
            frequency = row.get('frequency', 0)
            device = row.get('device_index', 0)
            if type(frequency) is not int or type(device) is not int or not 0 <= device <= 9:
                raise RadioConfigError('invalid_radio_host_config')
            if kind == 'rtl433' and (frequency not in (433920000, 868300000, 915000000) or row.get('packages')):
                raise RadioConfigError('unsupported_receiver_band')
            if kind == 'ble' and (frequency != 0 or device != 0):
                raise RadioConfigError('invalid_radio_host_config')
            digest = row.get('executable_sha256', '')
            if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
                raise RadioConfigError('invalid_radio_host_config')
            receiver = Receiver(row['id'], kind, '2.4 GHz Bluetooth LE' if kind == 'ble' else f'{frequency / 1e6:g} MHz',
                                row['executable'], digest, row.get('packages', ''), frequency, device)
            receiver.verify()
            receivers.append(receiver)
        return RadioConfig(data['organization_id'], data['facility_id'], tuple(receivers), interval)
    except (KeyError, ValueError, TypeError, OSError):
        raise RadioConfigError('invalid_radio_host_config') from None
