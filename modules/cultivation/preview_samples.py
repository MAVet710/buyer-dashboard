"""Bounded display-only samples. Never opens an edge database or writes evidence."""
from datetime import datetime, timezone
import re

from sqlalchemy import select

from .edge_store import _finite, _timestamp, _token
from .intelligence_models import EnvironmentalZone, CropCycle
from .models import CultivationRoom
from .metrics import normalize_metric_value


def safe_label(value):
    if not isinstance(value, str) or re.search(
        r"(?i)(dla_|bearer|password|secret|api[_ -]?key|access[_ -]?token|eyJ|://|[A-Za-z0-9_-]{40,})", value
    ):
        return None
    try:
        return _token(value)
    except ValueError:
        return None


def sample_rows(session, service, readings, hints, resolved):
    """Three scoped set lookups for at most twenty actual resolved destinations."""
    snapshots = [item for item in resolved[:20] if item]
    labels = []
    for model, field, fallback in ((CultivationRoom, 'room_id', 'room_code'),
                                   (EnvironmentalZone, 'zone_id', 'zone_code'),
                                   (CropCycle, 'cycle_id', 'cycle_code')):
        ids = {item.get(field) for item in snapshots if item.get(field)}
        labels.append({item.id: safe_label(item.display_name or getattr(item, fallback))
                       for item in session.scalars(select(model).where(
                           *service.scope(model), model.id.in_(ids)).limit(20))})
    result = []
    for index, (raw, hint, snapshot) in enumerate(zip(readings[:20], hints, resolved)):
        snap = snapshot or {}
        row = dict(row_index=index, **{key: safe_label(raw.get(key)) for key in
                   ('source_device_id', 'source_channel', 'source_metric')},
                   original_value=None, original_unit=safe_label(raw.get('unit')),
                   normalized_value=None, normalized_unit=None, metric=snap.get('metric'),
                   observed_at=None, room_id=snap.get('room_id'),
                   room_name=labels[0].get(snap.get('room_id')),
                   zone_id=snap.get('zone_id'), zone_name=labels[1].get(snap.get('zone_id')),
                   cycle_id=snap.get('cycle_id'), cycle_name=labels[2].get(snap.get('cycle_id')), status='pending_mapping')
        try:
            _finite(raw.get('value'))
            if isinstance(raw.get('value'), str) and (len(raw['value']) > 80 or
                    not re.fullmatch(r'[+\-\d.eE ]+', raw['value'])):
                raise ValueError('invalid_number')
            row['original_value'] = raw['value']
            at = _timestamp(raw.get('observed_at'))
            if at > datetime.now(timezone.utc).timestamp():
                raise ValueError('future_observation')
            row['observed_at'] = datetime.fromtimestamp(at, timezone.utc).isoformat()
            if raw.get('received_at') is not None:
                _timestamp(raw['received_at'])
            if raw.get('quality', 'valid') != 'valid':
                raise ValueError('invalid_quality')
            if any(safe_label(raw.get(key)) is None for key in
                   ('event_id', 'source_device_id', 'source_channel', 'source_metric', 'unit')):
                raise ValueError('unsafe_field')
            if snapshot and hint:
                if snapshot['metric'] != hint['metric']:
                    row['status'] = 'metric_conflict'
                else:
                    metric, value, unit = normalize_metric_value(snapshot['metric'], raw['value'], raw['unit'])
                    row.update(metric=metric, normalized_value=value, normalized_unit=unit,
                               status='normalized_not_committed')
        except (ValueError, TypeError, OverflowError):
            row['status'] = 'invalid_measurement'
        result.append(row)
    return result
