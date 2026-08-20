from types import SimpleNamespace

import pandas as pd
import pytest

import modules.inventory_adjustments as adjustments


def _state():
    return {
        "auth_user_role": "admin",
        "auth_user_id": "admin-1",
        "active_organization_id": "org-1",
        "active_facility_id": "fac-1",
    }


def _credentials():
    return SimpleNamespace(
        configured=True,
        state="MA",
        user_api_key="runtime-user",
        integrator_api_key="runtime-integrator",
        license_number="MR123",
    )


def _patch_retail(monkeypatch, *, local_calls):
    monkeypatch.setattr(
        adjustments,
        "_retail_current_and_row",
        lambda package_id: (pd.DataFrame(), 0, 10.0, 0.0, "unit"),
    )

    def local_apply(state, package_id, final_quantity):
        local_calls.append((package_id, final_quantity))
        return final_quantity - 10.0, "unit"

    monkeypatch.setattr(adjustments, "_apply_retail_local", local_apply)
    monkeypatch.setattr(adjustments, "_append_journal", lambda *args, **kwargs: None)
    monkeypatch.setattr(adjustments, "_credentials", lambda state: _credentials())


def test_inventory_adjustment_routes_metrc_sync_through_tracked_lifecycle(monkeypatch):
    local_calls = []
    tracked = {}
    _patch_retail(monkeypatch, local_calls=local_calls)

    def fake_tracked(**kwargs):
        tracked.update(kwargs)
        delta, unit = kwargs["local_apply"]()
        return delta, unit, "traceability-123"

    monkeypatch.setattr(adjustments, "run_tracked_metrc_adjustment", fake_tracked)
    entry = adjustments.apply_inventory_adjustment(
        _state(),
        operation_mode="Retail Ops",
        package_id="PKG-1",
        durable_lot_id="",
        adjustment_type="Incremental",
        entered_quantity=-2.0,
        reason="Inventory count correction",
        reason_note="Counted twice",
        sync_to_metrc=True,
        bypass_state_system=False,
    )

    assert tracked["organization_id"] == "org-1"
    assert tracked["facility_id"] == "fac-1"
    assert tracked["package_id"] == "PKG-1"
    assert tracked["adjustment_type"] == "incremental"
    assert tracked["quantity"] == -2.0
    assert tracked["unit"] == "unit"
    assert local_calls == [("PKG-1", 8.0)]
    assert entry["metrc_status"] == "synced"
    assert entry["traceability_transaction_id"] == "traceability-123"
    assert entry["final_quantity"] == 8.0


def test_tracked_provider_failure_blocks_local_inventory_change(monkeypatch):
    local_calls = []
    _patch_retail(monkeypatch, local_calls=local_calls)
    monkeypatch.setattr(
        adjustments,
        "run_tracked_metrc_adjustment",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("Metrc outcome requires reconciliation.")),
    )

    with pytest.raises(RuntimeError, match="reconciliation"):
        adjustments.apply_inventory_adjustment(
            _state(),
            operation_mode="Retail Ops",
            package_id="PKG-1",
            durable_lot_id="",
            adjustment_type="Incremental",
            entered_quantity=-2.0,
            reason="Inventory count correction",
            reason_note="",
            sync_to_metrc=True,
            bypass_state_system=False,
        )
    assert local_calls == []


def test_admin_bypass_preserves_local_only_behavior_without_traceability_transaction(monkeypatch):
    local_calls = []
    _patch_retail(monkeypatch, local_calls=local_calls)

    def should_not_run(**kwargs):
        raise AssertionError("Tracked Metrc lifecycle must not run for explicit state-system bypass")

    monkeypatch.setattr(adjustments, "run_tracked_metrc_adjustment", should_not_run)
    entry = adjustments.apply_inventory_adjustment(
        _state(),
        operation_mode="Retail Ops",
        package_id="PKG-1",
        durable_lot_id="",
        adjustment_type="Set Quantity",
        entered_quantity=7.0,
        reason="Entry error",
        reason_note="State system already corrected separately",
        sync_to_metrc=False,
        bypass_state_system=True,
    )

    assert local_calls == [("PKG-1", 7.0)]
    assert entry["metrc_status"] == "bypassed"
    assert entry["traceability_transaction_id"] == ""
