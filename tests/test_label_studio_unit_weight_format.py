from decimal import Decimal

from backend.app.services.label_studio import _unit_weight_text


def test_testing_label_unit_weight_keeps_whole_number_grams():
    assert _unit_weight_text(Decimal("10"), "g") == "10g"
    assert _unit_weight_text(Decimal("0.5"), "g") == "0.50g"
