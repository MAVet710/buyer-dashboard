from datetime import date

import pytest

from modules.regulatory.write_registry import get_metrc_write_contract, require_metrc_write_contract
from services.metrc_native import MetrcNativeError, validate_metrc_action


def test_package_move_builds_reviewed_v2_payload_without_extra_fields():
    result = validate_metrc_action(
        operation_type="package_move",
        entity_id="1A4000000000000000000001",
        payload={
            "destination_location": "Vault A",
            "sublocation": "Shelf 3",
            "move_date": "2026-08-30",
            "ignored": "must-not-leak",
        },
    )
    assert result == {
        "operation": "package_move",
        "body": [{
            "Label": "1A4000000000000000000001",
            "Location": "Vault A",
            "MoveDate": "2026-08-30",
            "Sublocation": "Shelf 3",
        }],
    }


def test_package_move_defaults_move_date_and_omits_blank_sublocation():
    result = validate_metrc_action(
        operation_type="package_move",
        entity_id="PKG-1",
        payload={"destination_location": "Secure Storage", "sublocation": "   "},
    )
    assert result["body"] == [{
        "Label": "PKG-1",
        "Location": "Secure Storage",
        "MoveDate": date.today().isoformat(),
    }]


def test_package_unfinish_builds_label_only_payload():
    result = validate_metrc_action(
        operation_type="package_unfinish",
        entity_id="PKG-2",
        payload={"actual_date": "should-not-be-forwarded"},
    )
    assert result == {"operation": "package_unfinish", "body": [{"Label": "PKG-2"}]}


def test_package_item_update_builds_label_item_payload():
    result = validate_metrc_action(
        operation_type="package_item_update",
        entity_id="PKG-3",
        payload={"item": "Bulk Flower - Garlic Breath", "note": "ignored"},
    )
    assert result == {
        "operation": "package_item_update",
        "body": [{"Label": "PKG-3", "Item": "Bulk Flower - Garlic Breath"}],
    }


def test_package_note_update_uses_package_label_field():
    result = validate_metrc_action(
        operation_type="package_note_update",
        entity_id="PKG-4",
        payload={"note": "Cycle count verified by supervisor"},
    )
    assert result == {
        "operation": "package_note_update",
        "body": [{"PackageLabel": "PKG-4", "Note": "Cycle count verified by supervisor"}],
    }


@pytest.mark.parametrize(
    ("operation", "payload", "message"),
    [
        ("package_move", {}, "destination_location"),
        ("package_item_update", {}, "requires item"),
        ("package_note_update", {}, "requires note"),
    ],
)
def test_phase1b_package_payloads_fail_closed_on_missing_required_values(operation, payload, message):
    with pytest.raises(MetrcNativeError) as exc:
        validate_metrc_action(operation_type=operation, entity_id="PKG-X", payload=payload)
    assert message in str(exc.value)


def test_phase1b_payload_implementation_does_not_unlock_network_dispatch():
    for operation in (
        "package_move",
        "package_unfinish",
        "package_item_update",
        "package_note_update",
    ):
        contract = get_metrc_write_contract(operation)
        assert contract is not None
        assert contract.dispatch_enabled is False
        with pytest.raises(ValueError) as exc:
            require_metrc_write_contract(
                operation_type=operation,
                jurisdiction="MA",
                environment="sandbox",
            )
        assert "automatic execution is locked" in str(exc.value)
