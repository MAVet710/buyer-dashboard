from pathlib import Path

import pandas as pd

import services.inventory_check as inventory_check


def _product_frame():
    return pd.DataFrame(
        [
            {
                "product_name": "Demo State Labs Orchard Haze Vape 1g (VP)",
                "subcategory": "Vapes",
                "packagesize": "1g",
                "onhandunits": 2,
                "unitssold": 64,
                "avgunitsperday": 64 / 60,
                "daysonhand": 1.875,
            },
            {
                "product_name": "Test Batch Co. Sleep Mode Gummies 100mg (ED)",
                "subcategory": "Edibles",
                "packagesize": "100mg",
                "onhandunits": 70,
                "unitssold": 3,
                "avgunitsperday": 3 / 60,
                "daysonhand": 1400,
            },
        ]
    )


def _aggregate_frame():
    return pd.DataFrame(
        [
            {
                "subcategory": "Vapes",
                "packagesize": "1g",
                "strain_type": "sativa",
                "onhandunits": 2,
                "unitssold": 64,
                "avgunitsperday": 64 / 60,
                "daysonhand": 1.875,
                "reorderqty": 21,
                "reorderpriority": "1 – Reorder ASAP",
            }
        ]
    )


def test_deterministic_inventory_check_names_real_products(monkeypatch):
    monkeypatch.setattr(inventory_check, "resolve_gemini_api_key", lambda: "")
    result = inventory_check.generate_inventory_check(
        _aggregate_frame(), product_view=_product_frame(), doh_threshold=21, data_source="Sandbox"
    )
    assert "Demo State Labs Orchard Haze Vape 1g (VP)" in result
    assert "2.0 on hand" in result
    assert "64 sold" in result
    assert "Test Batch Co. Sleep Mode Gummies 100mg (ED)" in result
    assert "Overstock / slow watch" in result


def test_generic_rules_response_is_rejected(monkeypatch):
    class FakeAgent:
        def __init__(self, *args, **kwargs):
            self.enabled = True

        def run(self, *args, **kwargs):
            return "Close assortment gaps. Shopify Retail Open-to-Buy Guide. [buyer:inventory_logic.metrics] AI: rules"

    monkeypatch.setattr(inventory_check, "GeminiWorkspaceAgent", FakeAgent)
    monkeypatch.setattr(inventory_check, "resolve_gemini_api_key", lambda: "sandbox-key")
    result = inventory_check.generate_inventory_check(
        _aggregate_frame(), product_view=_product_frame(), doh_threshold=21, data_source="Sandbox"
    )
    assert "Demo State Labs Orchard Haze Vape 1g (VP)" in result
    assert "Shopify Retail Open-to-Buy Guide" not in result
    assert "[buyer:" not in result
    assert "AI: rules" not in result
    assert "Gemini inventory interpretation" not in result


def test_specific_gemini_response_is_appended(monkeypatch):
    class FakeAgent:
        def __init__(self, *args, **kwargs):
            self.enabled = True

        def run(self, *args, **kwargs):
            return (
                "**Do this first**\n"
                "1. Demo State Labs Orchard Haze Vape 1g (VP): 2 on hand, 64 sold, 1.9 days cover."
            )

    monkeypatch.setattr(inventory_check, "GeminiWorkspaceAgent", FakeAgent)
    monkeypatch.setattr(inventory_check, "resolve_gemini_api_key", lambda: "sandbox-key")
    result = inventory_check.generate_inventory_check(
        _aggregate_frame(), product_view=_product_frame(), doh_threshold=21, data_source="Sandbox"
    )
    assert "Gemini inventory interpretation" in result
    assert "Demo State Labs Orchard Haze Vape 1g (VP)" in result


def test_app_inventory_check_no_longer_calls_legacy_doobie_inventory_endpoint():
    source = Path("app.py").read_text(encoding="utf-8")
    start = source.index("def ai_inventory_check(")
    end = source.index("\ndef _feature_enabled(", start)
    block = source[start:end]
    assert "generate_inventory_check(" in block
    assert "client.inventory_check(" not in block


def test_inventory_ui_no_longer_requires_doobie_connection():
    source = Path("app.py").read_text(encoding="utf-8")
    marker = 'st.markdown("### 🤖 AI Inventory Check (Optional)")'
    start = source.index(marker)
    block = source[start : start + 900]
    assert 'st.button("Run AI check on current view")' in block
    assert "_doobie_ai_access_enabled()" not in block
    assert "_doobie_ai_status()" not in block
