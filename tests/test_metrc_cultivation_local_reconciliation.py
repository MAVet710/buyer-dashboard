from __future__ import annotations

from types import SimpleNamespace

from backend.app.services import metrc_cultivation_operator_service as subject


class FakeLinks:
    def __init__(self):
        self.created=[]
    def upsert_verified(self,**kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(**kwargs,id=f"link-{len(self.created)}",status="verified",mismatch_reason="",verified_at=None,last_seen_at=None)
    def payload(self,row):
        return {"entity_id":row.entity_id,"provider_id":row.provider_id,"provider_label":row.provider_label,"status":"verified"}


def test_vegetative_local_apply_moves_group_to_verified_destination_room(monkeypatch):
    assigned={
        "plants":[
            {"id":"local-1","metrc_plant_tag":"TAG-001"},
            {"id":"local-2","metrc_plant_tag":"TAG-002"},
        ]
    }
    moves=[]

    class FakeCompliance:
        def __init__(self,_engine): pass
        def assign_vegetative_tags(self,*args,**kwargs):
            assert kwargs["provider_confirmed"] is True
            assert kwargs["tag_labels"]==["TAG-001","TAG-002"]
            return assigned

    class FakeBatchService:
        def __init__(self,_engine): pass
        def transition_group(self,*args,**kwargs):
            moves.append(kwargs)
            return {"room_code":kwargs["room_code"]}

    monkeypatch.setattr(subject,"MetrcProcessComplianceService",FakeCompliance)
    monkeypatch.setattr(subject,"CultivationBatchService",FakeBatchService)

    service=subject.GovernedMetrcCultivationActionService.__new__(subject.GovernedMetrcCultivationActionService)
    service.engine=object()
    service.links=FakeLinks()
    service._room_by_id=lambda *_args,**_kwargs: SimpleNamespace(id="room-2",room_code="VEG-B")

    result=service._apply_local_verified_state(
        organization_id="org-1",facility_id="fac-1",actor="user-1",
        prepared={"operation_type":"plant_batch_vegetative","entity_id":"group-1","fingerprint_context":{"destination_room_id":"room-2"}},
        transaction_id="tx-1",
        verification={"plants":[{"provider_id":"101","label":"TAG-001"},{"provider_id":"102","label":"TAG-002"}]},
        state="MA",environment="sandbox",license_number="LIC-1",
    )

    assert moves==[{
        "actor":"user-1",
        "phase":None,
        "room_code":"VEG-B",
        "reason":"Verified Metrc vegetative growth-phase/location change",
        "notes":"Traceability transaction tx-1",
    }]
    assert result["phase"]=="vegetative"
    assert result["room_code"]=="VEG-B"
    assert result["plant_count"]==2
    assert {row["entity_id"] for row in result["plant_links"]}=={"local-1","local-2"}
