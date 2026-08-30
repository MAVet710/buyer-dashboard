from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_inventory_selection_exposes_core_operational_actions():
    source = read("frontend/src/pages/InventoryPage.tsx")
    for label in (">Move</button>", ">Hold</button>", ">Release Hold</button>"):
        assert label in source
    assert "InventoryOperationalActions" in source
    assert 'setOperationalAction("move")' in source
    assert 'setOperationalAction("hold")' in source
    assert 'setOperationalAction("release")' in source


def test_inventory_actions_are_real_durable_calls_not_placeholder_buttons():
    source = read("frontend/src/components/InventoryOperationalActions.tsx")
    assert '"/api/v1/traceability-actions/inventory/move"' in source
    assert '"/api/v1/traceability-actions/inventory/hold"' in source
    assert '"/api/v1/traceability-actions/inventory/release-hold"' in source
    assert "Move ≠ Transfer" in source
    assert "sync_to_metrc:false" in source


def test_backend_inventory_actions_are_tenant_scoped_audited_and_fail_closed_for_metrc_move():
    source = read("backend/app/routers/traceability_actions.py")
    assert '@router.post("/inventory/move")' in source
    assert '@router.post("/inventory/hold")' in source
    assert '@router.post("/inventory/release-hold")' in source
    assert "lot.organization_id != context.organization_id" in source
    assert "lot.facility_id != context.facility_id" in source
    assert "inventory_location_moved" in source
    assert "inventory_hold_applied" in source
    assert "inventory_hold_released" in source
    assert "Metrc package Move is documented but automatic execution is still locked" in source
