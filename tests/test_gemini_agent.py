import pandas as pd

from services.gemini_agent import BuyerDataTools


def test_sensitive_columns_are_not_exposed():
    tools = BuyerDataTools({"inventory": pd.DataFrame({
        "Product Name": ["Glue"],
        "Quantity": [10],
        "Customer Email": ["private@example.com"],
        "API Key": ["secret"],
    })})
    preview = tools.preview_dataset("inventory")
    assert preview["rows"][0]["Product Name"] == "Glue"
    assert "Customer Email" not in preview["rows"][0]
    assert "API Key" not in preview["rows"][0]


def test_reorder_candidates_are_read_only_calculation():
    inventory = pd.DataFrame({
        "Product Name": ["Glue 3.5g", "Sour 3.5g"],
        "Quantity": [2, 50],
    })
    sales = pd.DataFrame({
        "Product Name": ["Glue 3.5g", "Sour 3.5g"],
        "Units Sold": [60, 30],
    })
    result = BuyerDataTools({"inventory": inventory, "sales": sales}).inventory_reorder_candidates(days_cover=14)
    assert result["candidates"]
    assert result["candidates"][0]["product"] == "Glue 3.5g"
    assert result["candidates"][0]["suggested_reorder"] > 0
