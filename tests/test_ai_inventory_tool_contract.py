from dataclasses import replace

import pandas as pd
import pytest

from backend.app.services.ai_inventory import inventory_source_version
from services.ai.datasets import DatasetAccessContext, DatasetRegistry, DatasetSpec, LoadedDataset
from services.ai.inventory_contract import CURRENT_TOOLS, SALES_TOOLS
from services.ai.runtime import AgentRuntime
from services.ai.tools import ToolRegistry


ACCESS = DatasetAccessContext("org", "facility", "reader", "buyer", frozenset({"retail"}))


def package_frame():
    return pd.DataFrame([
        {"id": "grams-1", "product_id": "product-g", "sku": "G", "product_name": "Same name", "package_id": "TAG-G1", "on_hand": 100.0, "available": 85.0, "reserved": 15.0, "unit": "g", "status": "Available", "unit_cost": 2.0, "received_at": "2026-09-01", "expiration_at": "2026-12-01", "age_days": 22.0, "days_to_expiry": 69.0},
        {"id": "grams-2", "product_id": "product-g", "sku": "G", "product_name": "Same name", "package_id": "TAG-G2", "on_hand": 50.0, "available": 40.0, "reserved": 10.0, "unit": "g", "status": "Available", "unit_cost": 2.0, "received_at": "2026-09-02", "expiration_at": "2026-11-01", "age_days": 21.0, "days_to_expiry": 39.0},
        {"id": "units-1", "product_id": "product-u", "sku": "U", "product_name": "Same name", "package_id": "TAG-U1", "on_hand": 8.0, "available": 0.0, "reserved": 0.0, "unit": "unit", "status": "Hold", "unit_cost": 10.0, "received_at": "2026-09-03", "expiration_at": "2026-10-01", "age_days": 20.0, "days_to_expiry": 8.0},
    ])


def dataset(key, frame):
    spec = DatasetSpec(key=key, domain="retail", description=key, loader=lambda _access: frame, allowed_agents=("inventory",), allowed_columns=tuple(frame.columns) or ("id",))
    return LoadedDataset(spec, frame, "fixture")


def loaded_current(state="available", with_sales=False):
    result = {"inventory_evidence": dataset("inventory_evidence", pd.DataFrame([{"state": state, "row_count": 3 if state == "available" else 0 if state == "empty" else None}]))}
    if state in {"available", "empty"}:
        result["inventory"] = dataset("inventory", package_frame() if state == "available" else pd.DataFrame())
    if with_sales:
        result["sales"] = dataset("sales", pd.DataFrame([{"product name": "Old uploaded product", "sku": "G", "units sold": 60}]))
        result["buyer_inventory_snapshot"] = dataset("buyer_inventory_snapshot", pd.DataFrame([{"product name": "Old uploaded product", "sku": "G", "available": 9999.0, "unit cost": 1.0}]))
    return result


def version(frame, **overrides):
    options = {"scope": ("org", "facility"), "state": "available", "observed_day": "2026-09-23"}
    return inventory_source_version(frame, **{**options, **overrides})


@pytest.mark.parametrize("column,new_value", [("on_hand", 90.0), ("available", 75.0), ("reserved", 25.0), ("unit", "kg"), ("status", "Hold"), ("unit_cost", 3.0), ("expiration_at", "2026-10-01")])
def test_same_row_count_business_changes_invalidate_source_version(column, new_value):
    original = package_frame()
    changed = original.copy()
    changed.loc[0, column] = new_value
    assert len(changed) == len(original)
    assert version(changed) != version(original)


def test_source_version_is_order_stable_and_ages_daily_not_every_instant():
    original = package_frame()
    changed = original.iloc[::-1].copy()
    changed["age_days"] += .0001
    changed["days_to_expiry"] -= .0001
    assert version(changed) == version(original)
    assert version(original, observed_day="2026-09-24") != version(original)
    assert version(original, scope=("org", "sibling")) != version(original)
    assert version(None, state="unavailable") != version(pd.DataFrame(), state="empty")


def registry_version(frame):
    source = frame.copy()
    source.attrs["source_version"] = version(source)
    registry = DatasetRegistry()
    registry.register(dataset("inventory", source).spec)
    return AgentRuntime._source_version(registry.load_for_agent("inventory", ACCESS))


def test_real_runtime_cache_key_includes_content_even_when_row_count_is_unchanged():
    original = package_frame()
    changed = original.copy()
    changed.loc[0, "available"] = 75
    assert registry_version(original) == registry_version(original.copy())
    assert registry_version(changed) != registry_version(original)


@pytest.mark.parametrize("metadata", ["unsafe metadata marker", "a" * 63, "A" * 64, None, {"credential": "synthetic"}])
def test_only_strict_fingerprint_metadata_crosses_registry_boundary(metadata):
    frame = package_frame()
    frame.attrs["source_version"] = metadata
    registry = DatasetRegistry()
    registry.register(dataset("inventory", frame).spec)
    loaded = registry.load_for_agent("inventory", ACCESS)
    assert loaded["inventory"].freshness == "live repository"


def test_availability_and_generic_numeric_totals_never_add_grams_to_units():
    tools = ToolRegistry(loaded_current())
    for name, args, quantity_key in (
        ("inventory_availability", {}, "on_hand"),
        ("summarize_numeric", {"dataset": "inventory", "column": "on_hand"}, "total"),
        ("group_summary", {"dataset": "inventory", "group_column": "product_name", "value_column": "on_hand", "operation": "sum"}, "on_hand"),
    ):
        result = tools.execute(name, args)
        assert "error" not in result
        assert result["unit_grouped"] is True and "total" not in result
        rows = {row["unit"]: row for row in result["rows"]}
        assert rows["g"][quantity_key] == 150 and rows["unit"][quantity_key] == 8
    available = {row["unit"]: row for row in tools.execute("inventory_availability")["rows"]}
    assert available["g"]["available"] == 125 and available["g"]["reserved"] == 25
    assert available["unit"]["available"] == 0


@pytest.mark.parametrize("name,args", [
    ("top_rows", {"dataset": "inventory", "sort_column": "on_hand"}),
    ("numeric_exceptions", {"dataset": "inventory", "column": "available", "threshold": 10}),
])
def test_quantity_rankings_and_thresholds_do_not_compare_unlike_units(name, args):
    result = ToolRegistry(loaded_current()).execute(name, args)
    assert result["state"] == "mixed_units" and result["missing_data"]
    assert "unlike inventory units" in AgentRuntime._format_deterministic(name, result)


@pytest.mark.parametrize("name", SALES_TOOLS)
def test_current_tools_do_not_join_uploaded_sales_by_accidental_sku_match(name):
    result = ToolRegistry(loaded_current(with_sales=True)).execute(name)
    assert result["state"] == "needs_sales_mapping"
    assert result["rows"] == [] and result["missing_data"]
    assert "verified product/unit mapping" in AgentRuntime._format_deterministic(name, result)
    assert "no matching exceptions" not in AgentRuntime._format_deterministic(name, result)


def test_aging_keeps_package_identity_and_does_not_require_sales():
    result = ToolRegistry(loaded_current()).execute("inventory_aging", {"limit": 2})
    assert "error" not in result and result["truncated"] is True
    assert result["total_result_rows"] == 3
    assert [row["id"] for row in result["rows"]] == ["units-1", "grams-2"]
    assert all("unit" in row and "product_id" in row for row in result["rows"])


@pytest.mark.parametrize("state", ["unavailable", "too_large"])
def test_unavailable_inventory_is_never_replaced_with_old_uploaded_stock(state):
    tools = ToolRegistry(loaded_current(state, with_sales=True))
    for name in CURRENT_TOOLS:
        result = tools.execute(name)
        assert result["state"] == "unavailable" and result["missing_data"]
        assert "uploaded snapshot was not substituted" in result["_agent_summary"]
    result = tools.execute("summarize_numeric", {"dataset": "inventory", "column": "on_hand"})
    assert "total" not in result and "count" not in result


def test_successful_empty_read_is_explained_as_empty_not_missing():
    result = ToolRegistry(loaded_current("empty")).execute("inventory_availability")
    assert result["state"] == "empty" and "missing_data" not in result
    assert "successful current inventory read" in result["_agent_summary"]


def test_uploaded_snapshot_calculation_remains_available_and_explicitly_historical():
    loaded = loaded_current(with_sales=True)
    expected = ToolRegistry({"inventory": loaded["buyer_inventory_snapshot"], "sales": loaded["sales"]}).execute("inventory_stockout_risk")
    actual = ToolRegistry(loaded).execute("uploaded_snapshot_inventory_stockout_risk")
    assert "error" not in actual
    assert actual["rows"] == expected["rows"]
    assert actual["rows"][0]["on_hand"] == 9999
    assert actual["basis"] == "uploaded_snapshot"
    assert any("not current stock" in value for value in actual["warnings"])


def test_unit_totals_remain_bounded_and_expose_truncation():
    result = ToolRegistry(loaded_current()).execute("inventory_availability", {"limit": 1})
    assert len(result["rows"]) == 1 and result["truncated"] is True
    assert result["total_result_rows"] == 2


def test_unrelated_generic_tools_keep_existing_behavior():
    loaded = loaded_current()
    loaded["other"] = dataset("other", pd.DataFrame([{"quantity": 2}, {"quantity": 3}]))
    result = ToolRegistry(loaded).execute("summarize_numeric", {"dataset": "other", "column": "quantity"})
    assert result["total"] == 5 and result["count"] == 2
