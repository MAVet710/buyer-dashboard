from fastapi import HTTPException
import pytest

from backend.app.routers.production_mutations import (
    PostHarvestMeasurement,
    _guard_reconciled_post_harvest,
    _normalized_post_harvest_measurements,
    _validate_post_harvest_stage_step,
)


def _current(*, dry_weight=250.0, wip=0.0, flower=180.0, trim=50.0, biomass=0.0, waste=20.0):
    return {
        "dry_weight_g": dry_weight,
        "current_weights": {
            "wip": wip,
            "finished_flower": flower,
            "trim": trim,
            "biomass": biomass,
            "waste": waste,
        },
    }


def test_post_harvest_api_requires_one_stage_at_a_time():
    assert _validate_post_harvest_stage_step("drying", "bucking") == "bucking"
    assert _validate_post_harvest_stage_step("drying", "drying") == "drying"

    with pytest.raises(HTTPException) as exc_info:
        _validate_post_harvest_stage_step("drying", "curing")
    assert exc_info.value.status_code == 422
    assert "one stage at a time" in str(exc_info.value.detail)

    with pytest.raises(HTTPException) as exc_info:
        _validate_post_harvest_stage_step("trimming", "drying")
    assert exc_info.value.status_code == 422


def test_final_reconciliation_requires_wip_to_be_physically_closed():
    with pytest.raises(HTTPException) as exc_info:
        _guard_reconciled_post_harvest(_current(wip=12.0))
    assert exc_info.value.status_code == 422
    assert "remaining/WIP" in str(exc_info.value.detail)

    _guard_reconciled_post_harvest(_current(wip=0.0))


def test_locked_correction_must_preserve_reconciliation_after_proposed_weights():
    current = _current(wip=0.0)
    safe = [
        {"weight_type": "finished_flower", "quantity_g": 181.0},
        {"weight_type": "waste", "quantity_g": 19.0},
    ]
    _guard_reconciled_post_harvest(current, safe)

    with pytest.raises(HTTPException) as exc_info:
        _guard_reconciled_post_harvest(current, [{"weight_type": "finished_flower", "quantity_g": 190.0}])
    assert exc_info.value.status_code == 422
    assert "not reconciled" in str(exc_info.value.detail)


def test_weight_update_rejects_duplicate_types_in_one_request():
    rows = [
        PostHarvestMeasurement(weight_type="trim", quantity_g=20),
        PostHarvestMeasurement(weight_type="TRIM", quantity_g=21),
    ]
    with pytest.raises(HTTPException) as exc_info:
        _normalized_post_harvest_measurements(rows)
    assert exc_info.value.status_code == 422
    assert "only one trim reading" in str(exc_info.value.detail)
