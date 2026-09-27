"""Small allowlisted decoders for public sensor formats, never equipment control.

BTHome v2: https://bthome.io/format/
WH31: consumes rtl_433's decoded JSON, NOT copied GPL demodulator code.
Radio identity/checksums are not authentication. All timestamps are receiver time.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re

BTHOME_UUID = '0000fcd2-0000-1000-8000-00805f9b34fb'


class RadioInputError(ValueError):
    pass


@dataclass(frozen=True)
class Measurement:
    metric: str
    value: float
    unit: str
    channel: str


@dataclass(frozen=True)
class Observation:
    profile: str
    address: str
    name: str
    measurements: tuple[Measurement, ...]
    received_at: datetime
    rssi: int | None = None
    reason: str | None = None
    packet_id: int | None = None

    @property
    def supported(self):
        return bool(self.measurements) and self.reason is None


def received(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RadioInputError('receiver_timestamp_required')
    return value.astimezone(timezone.utc)


def clean_name(value, fallback):
    # Names are untrusted radio input; no markup/control characters in UI/logs.
    if not isinstance(value, str) or len(value) > 64:
        return fallback
    return ''.join(c for c in value if c.isprintable() and c not in '<>')[:64] or fallback


def decode_bthome(address, payload, at, *, name='', rssi=None):
    if not isinstance(address, str) or not re.fullmatch(r'[0-9A-Fa-f]{12}', address):
        raise RadioInputError('invalid_source_identity')
    address = address.upper()
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= 128:
        raise RadioInputError('invalid_advertisement_length')
    at = received(at)
    label = clean_name(name, 'BTHome sensor ' + address[-4:])
    rssi = rssi if type(rssi) is int and -127 <= rssi <= 20 else None
    header = payload[0]
    if header >> 5 != 2 or header & 0x1A:
        return Observation('bthome_v2', address, label, (), at, rssi, 'unsupported_bthome_version')
    if header & 1:
        return Observation('bthome_v2', address, label, (), at, rssi, 'encrypted_requires_supported_pairing')
    # Object sizes are explicit. Unknown IDs cannot be skipped safely.
    objects = {0x00: (1, False, 1, None, None), 0x01: (1, False, 1, None, None),
               0x02: (2, True, .01, 'temperature', 'C'),
               0x03: (2, False, .01, 'relative_humidity', '%'),
               0x12: (2, False, 1, 'co2', 'ppm'),
               0x2E: (1, False, 1, 'relative_humidity', '%'),
               0x45: (2, True, .1, 'temperature', 'C'),
               0x57: (1, True, 1, 'temperature', 'C'),
               0x58: (1, True, .35, 'temperature', 'C'),
               0x0C: (2, False, 1, None, None),
               0xF0: (2, False, 1, None, None),
               0xF1: (4, False, 1, None, None),
               0xF2: (3, False, 1, None, None)}
    i = 1
    values = []
    seen = set()
    packet = None
    while i < len(payload):
        key = payload[i]
        i += 1
        if key not in objects:
            return Observation('bthome_v2', address, label, (), at, rssi, 'unsupported_bthome_object')
        size, signed, factor, metric, unit = objects[key]
        if i + size > len(payload) or key in seen:
            raise RadioInputError('malformed_bthome_object')
        seen.add(key)
        value = int.from_bytes(payload[i:i + size], 'little', signed=signed) * factor
        i += size
        if key == 0:
            packet = int(value)
        if metric:
            # Independent copies of the same semantic metric need explicit support.
            if any(v.metric == metric for v in values):
                raise RadioInputError('ambiguous_bthome_measurement')
            if metric == 'relative_humidity' and not 0 <= value <= 100:
                raise RadioInputError('invalid_humidity')
            if metric == 'temperature' and value < -273.15:
                raise RadioInputError('invalid_temperature')
            values.append(Measurement(metric, round(value, 6), unit, metric))
    reason = None if values else 'no_supported_environment_measurement'
    # Trigger-only advertisements do not imply continuous environmental sampling.
    if header & 4:
        reason = 'trigger_only_not_continuous_sensor'
        values = []
    return Observation('bthome_v2', address, label, tuple(values), at, rssi, reason, packet)


def decode_wh31(data, at):
    if not isinstance(data, dict) or data.get('model') not in {'AmbientWeather-WH31E', 'AmbientWeather-WH31B'} or data.get('mic') != 'CRC':
        raise RadioInputError('unsupported_or_unchecked_radio_frame')
    identity, channel = data.get('id'), data.get('channel')
    if type(identity) is not int or not 0 <= identity <= 0xFF or type(channel) is not int or not 1 <= channel <= 8:
        raise RadioInputError('invalid_source_identity')
    values = []
    for key, metric, unit, minimum, maximum in (
        ('temperature_C', 'temperature', 'C', -273.15, 200),
        ('humidity', 'relative_humidity', '%', 0, 100),
    ):
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not minimum <= value <= maximum:
            raise RadioInputError('invalid_wh31_measurement')
        values.append(Measurement(metric, float(value), unit, metric))
    return Observation('ambient_wh31', f'{data["model"]}-{identity:02X}-{channel}', f'WH31 sensor {identity:06X} / {channel}',
                       tuple(values), received(at))


def profiles():
    return {'profiles': [
        {'id': 'bthome_v2', 'name': 'BTHome v2 environmental advertisements', 'band_labels': ['2.4 GHz Bluetooth LE'],
         'supported': True, 'reason': 'Unencrypted temperature, humidity and CO2 objects only. Other objects need a reviewed decoder.',
         'metrics': [{'metric': m, 'unit': u} for m, u in [('temperature', 'C'), ('relative_humidity', '%'), ('co2', 'ppm')]]},
        {'id': 'ambient_wh31', 'name': 'Ambient Weather WH31E / WH31B temperature and humidity',
         'band_labels': ['915 MHz regional variant', '868 MHz regional variant', '433.92 MHz regional variant'],
         'supported': True, 'reason': 'Requires a separately installed compatible SDR receiver and pinned rtl_433 decoder 113.',
         'metrics': [{'metric': 'temperature', 'unit': 'C'}, {'metric': 'relative_humidity', 'unit': '%'}]},
    ]}
