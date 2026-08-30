from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_inventory_exposes_next_tier_operational_actions():
    actions = read("frontend/src/components/InventoryOperationalActions.tsx")
    for label in (
        "Split / Package Studio",
        "Finish",
        "Unfinish",
        "Change Item",
        "Change Note",
        "Allocate to Production",
        "Transfer / Manifest",
        "Waste / Destroy",
    ):
        assert f">{label}</button>" in actions
    assert 'operation_type:"package_finish"' in actions
    assert 'operation_type:"package_unfinish"' in actions
    assert 'operation_type:"package_item_update"' in actions
    assert 'operation_type:"package_note_update"' in actions
    assert 'operation_type:"transfer_create"' in actions
    assert 'operation_type:"waste_record"' in actions
    assert 'window.location.assign("/compliance/actions")' in actions
    assert 'window.location.assign("/production")' in actions
    assert 'window.location.assign("/production/package-studio")' in actions


def test_traceability_actions_accept_inventory_prefill():
    page = read("frontend/src/pages/TraceabilityActionsPage.tsx")
    assert 'buyer-dash-traceability-prefill' in page
    assert "Inventory action loaded." in page
    assert "setEntityId(prefill.entity_id)" in page
    assert "setReason(prefill.reason)" in page
    assert "setFields(prefill.fields)" in page
    assert "sessionStorage.removeItem(PREFILL_KEY)" in page
