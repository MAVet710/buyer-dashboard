from modules.buyer_assistant import detect_module


def test_detect_module_coa():
    assert detect_module("Show me terpene and potency trends from coa docs") == "coa"


def test_detect_module_extraction():
    assert detect_module("How do we improve rosin yield this week?") == "extraction"


def test_detect_module_compliance():
    assert detect_module("What packaging regulation applies in MA?") == "compliance"


def test_detect_module_buyer_default():
    assert detect_module("Which categories are under-assorted right now?") == "buyer"
