from modules.regulatory.write_registry import get_metrc_write_contract
from backend.app.routers.traceability_actions import ACTION_CATALOG


def test_inventory_action_catalog_contains_contextual_move_operations():
    assert "package_move" in ACTION_CATALOG
    assert ACTION_CATALOG["package_move"]["required"] == ("destination_location",)
    assert "plant_move" in ACTION_CATALOG
    assert "plant_batch_move" in ACTION_CATALOG
    assert "harvest_move" in ACTION_CATALOG


def test_package_move_metrc_contract_is_documented_but_fail_closed():
    contract = get_metrc_write_contract("package_move")
    assert contract is not None
    assert contract.method == "PUT"
    assert contract.path == "packages/v2/location"
    assert contract.dispatch_enabled is False


def test_other_inventory_location_contracts_remain_fail_closed_until_payload_verified():
    plant_batch = get_metrc_write_contract("plant_batch_location_update")
    harvest = get_metrc_write_contract("harvest_location_update")
    assert plant_batch is not None and plant_batch.path == "plantbatches/v2/location"
    assert harvest is not None and harvest.path == "harvests/v2/location"
    assert not plant_batch.dispatch_enabled
    assert not harvest.dispatch_enabled


def test_package_correction_contracts_are_known_without_automatic_dispatch():
    for operation, path in {
        "package_unfinish": "packages/v2/unfinish",
        "package_item_update": "packages/v2/item",
        "package_note_update": "packages/v2/note",
    }.items():
        contract = get_metrc_write_contract(operation)
        assert contract is not None
        assert contract.path == path
        assert contract.dispatch_enabled is False
