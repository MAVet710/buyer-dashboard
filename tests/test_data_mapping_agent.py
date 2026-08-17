from services.data_mapping_agent import suggest_column_mapping


def test_header_mapper_finds_unusual_but_clear_inventory_headers(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = suggest_column_mapping(
        ["Item Description", "Department", "Available Qty", "Vendor"],
        {
            "Product": ("product", "product name", "item", "item name", "name"),
            "Category": ("category", "subcategory", "department"),
            "On hand": ("available", "on hand", "quantity", "qty", "inventory available"),
        },
        dataset_label="Inventory",
    )
    mapped = {row["required_field"]: row["source_column"] for row in result["proposals"]}

    assert mapped["Product"] == "Item Description"
    assert mapped["Category"] == "Department"
    assert mapped["On hand"] == "Available Qty"
    assert result["provider"] == "header matcher"
    assert "row values were not sent" in result["privacy_note"]


def test_mapper_preserves_existing_match_and_does_not_reuse_column(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = suggest_column_mapping(
        ["Product Name", "Qty Sold", "Department"],
        {
            "Product": ("product", "product name", "item", "item name", "name"),
            "Units sold": ("quantity sold", "qty sold", "units sold", "items sold"),
            "Category": ("category", "department"),
        },
        existing_matches={"Product": "Product Name"},
        dataset_label="Product Sales",
    )
    mapped = {row["required_field"]: row["source_column"] for row in result["proposals"]}

    assert "Product" not in mapped
    assert mapped["Units sold"] == "Qty Sold"
    assert mapped["Category"] == "Department"
    assert len(set(mapped.values())) == len(mapped)


def test_mapper_does_not_guess_weak_headers(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = suggest_column_mapping(
        ["Alpha", "Beta", "Gamma"],
        {"Revenue": ("net sales", "gross sales", "revenue", "total sales")},
        dataset_label="Sales / Pricing Detail",
    )

    assert result["proposals"] == []
    assert result["unresolved"] == ["Revenue"]
