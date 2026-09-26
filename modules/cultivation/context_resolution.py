"""Bounded historical attribution for an already authorized scope; no authorization impersonation."""
from datetime import datetime, timedelta
from sqlalchemy import select
from .intelligence_models import (CultivationDevice, CultivationSensor, DeviceMapping, CropCycleRoom, CropCycle, CultivationRecipe, CultivationRecipeStage, CultivationRecipeTarget)
from .telemetry import utc

def build_resolver(s, authorized_scope, *, max_gap_seconds=300):
    """Eight bounded set queries, then deterministic in-memory resolution per row."""
    connection_id=authorized_scope.connection_id
    org=authorized_scope.organization_id
    facility=authorized_scope.facility_id
    def bounded(model,condition,limit=5000):
        rows=s.scalars(select(model).where(model.organization_id==org,model.facility_id==facility,condition).limit(limit+1)).all()
        if len(rows)>limit:raise ValueError('Mapping context exceeds bounded import capacity.')
        return rows
    devices=bounded(CultivationDevice,CultivationDevice.connection_id==connection_id,500)
    device_ids=[d.id for d in devices]
    sensors=bounded(CultivationSensor,CultivationSensor.device_id.in_(device_ids))
    mappings=bounded(DeviceMapping,DeviceMapping.device_id.in_(device_ids))
    room_ids=list({m.room_id for m in mappings})
    occupancy=bounded(CropCycleRoom,CropCycleRoom.room_id.in_(room_ids))
    cycles=bounded(CropCycle,CropCycle.id.in_([o.cycle_id for o in occupancy]))
    recipes=bounded(CultivationRecipe,CultivationRecipe.id.in_([c.recipe_id for c in cycles if c.recipe_id]))
    stages=bounded(CultivationRecipeStage,CultivationRecipeStage.id.in_([o.stage_id for o in occupancy if o.stage_id]))
    targets=bounded(CultivationRecipeTarget,CultivationRecipeTarget.stage_id.in_([stage.id for stage in stages]))
    device_by_source={d.source_device_id:d for d in devices if d.active}
    sensor_map={(r.device_id,r.source_channel,r.source_metric,r.source_unit):r for r in sensors}
    mapping_map={};occupancy_map={}
    for row in mappings:mapping_map.setdefault(row.device_id,[]).append(row)
    for values in mapping_map.values():values.sort(key=lambda r:utc(r.effective_at))
    for row in occupancy:occupancy_map.setdefault(row.room_id,[]).append(row)
    cycle_map={r.id:r for r in cycles};recipe_map={r.id:r for r in recipes};stage_map={r.id:r for r in stages}
    target_map={(r.stage_id,r.metric):r for r in targets}
    hold_seconds=max_gap_seconds
    if not 1<=hold_seconds<=86400:raise ValueError('Invalid local evidence gap configuration.')
    def resolve(scope,raw):
        if scope != authorized_scope:raise ValueError('Mapping scope mismatch.')
        try:
            at=raw['observed_at']
            if isinstance(at,str):at=datetime.fromisoformat(at.replace('Z','+00:00'))
            if at.tzinfo is None:return None
            at=utc(at)
            device=device_by_source.get(raw.get('source_device_id'))
            sensor=sensor_map.get((device.id,raw.get('source_channel'),raw.get('source_metric'),raw.get('unit'))) if device else None
            if sensor is None:return None
            revisions=mapping_map.get(device.id,[])
            applicable=[m for m in revisions if utc(m.effective_at)<=at]
            if not applicable:return None
            mapping=applicable[-1]
            begin=utc(mapping.effective_at)
            end=at+timedelta(seconds=hold_seconds)
            for revision in revisions:
                if utc(revision.effective_at)>at:end=min(end,utc(revision.effective_at))
            rooms=[o for o in occupancy_map.get(mapping.room_id,[]) if o.zone_id is None or o.zone_id==mapping.zone_id]
            active=[o for o in rooms if utc(o.entered_at)<=at and (o.exited_at is None or at<utc(o.exited_at))]
            # Every stage/occupancy boundary limits attribution, including an upcoming ambiguity.
            for o in rooms:
                for bound in (o.entered_at,o.exited_at):
                    if bound and utc(bound)>at:end=min(end,utc(bound))
                    elif bound:begin=max(begin,utc(bound))
            snapshot={'organization_id':org,'facility_id':facility,'connection_id':connection_id,'room_id':mapping.room_id,'zone_id':mapping.zone_id,'device_id':device.id,'sensor_id':sensor.id,'mapping_revision':mapping.id,'metric':sensor.metric,'effective_from':begin.isoformat(),'effective_to':end.isoformat(),'cycle_id':None,'stage_id':None}
            if len(active)==1:
                interval=active[0];cycle=cycle_map[interval.cycle_id]
                snapshot['cycle_id']=cycle.id
                stage=stage_map.get(interval.stage_id)
                recipe=recipe_map.get(cycle.recipe_id)
                if stage and recipe and stage.recipe_id==recipe.id and recipe.status=='approved' and recipe.approved_at:
                    approved_at=utc(recipe.approved_at)
                    if at<approved_at:snapshot['effective_to']=min(end,approved_at).isoformat()
                    else:snapshot['effective_from']=max(begin,approved_at).isoformat()
                if stage and recipe and stage.recipe_id==recipe.id and recipe.status=='approved' and recipe.approved_at and utc(recipe.approved_at)<=at:
                    snapshot.update(stage_id=stage.id,recipe_revision=recipe.id)
                    target=target_map.get((stage.id,sensor.metric))
                    if target:
                        snapshot.update(target_min=target.minimum,target_max=target.maximum)
                        if target.threshold_seconds is not None:snapshot['threshold_seconds']=target.threshold_seconds
            # Zero or multiple applicable cycles retain room evidence without guessing.
            return snapshot
        except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
            return None
    return resolve
