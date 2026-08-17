import inspect

import pandas as pd

from services.agent_registry import PROFILES
from services.gemini_agent import ReadOnlyDataTools, _gemini_tool_functions, datasets_from_session


def test_sensitive_columns_are_not_exposed():
    tools = ReadOnlyDataTools({"inventory": pd.DataFrame({
        "Product Name": ["Glue"],
        "Quantity": [10],
        "Customer Email": ["private@example.com"],
        "API Key": ["secret"],
        "Created By": ["employee-name"],
    })})
    preview = tools.preview_dataset("inventory")
    assert preview["rows"][0]["Product Name"] == "Glue"
    assert "Customer Email" not in preview["rows"][0]
    assert "API Key" not in preview["rows"][0]
    assert "Created By" not in preview["rows"][0]


def test_reorder_candidates_are_read_only_calculation():
    inventory = pd.DataFrame({
        "Product Name": ["Glue 3.5g", "Sour 3.5g"],
        "Quantity": [2, 50],
    })
    sales = pd.DataFrame({
        "Product Name": ["Glue 3.5g", "Sour 3.5g"],
        "Units Sold": [60, 30],
    })
    result = ReadOnlyDataTools({"inventory": inventory, "sales": sales}).inventory_reorder_candidates(days_cover=14)
    assert result["candidates"]
    assert result["candidates"][0]["product"] == "Glue 3.5g"
    assert result["candidates"][0]["suggested_reorder"] > 0


def test_gemini_tool_annotations_are_runtime_types():
    functions = _gemini_tool_functions(ReadOnlyDataTools({}))
    assert functions
    for function in functions:
        signature = inspect.signature(function)
        for parameter in signature.parameters.values():
            assert not isinstance(parameter.annotation, str)
            if parameter.default is not inspect.Parameter.empty:
                assert parameter.annotation is not inspect.Parameter.empty
        assert not isinstance(signature.return_annotation, str)


def test_extraction_agent_only_loads_extraction_session_data():
    state = {
        "inv_raw_df": pd.DataFrame({"Product": ["Retail"]}),
        "ecc_run_log": pd.DataFrame({"batch_id_internal": ["RUN-1"], "yield_pct": [71.2]}),
    }
    datasets = datasets_from_session(state, profile=PROFILES["extraction"])
    assert "extraction_runs" in datasets
    assert "inventory" not in datasets


def test_repack_agent_builds_scenario_dataset():
    state = {
        "wl_strain_name": "Glue",
        "wl_bulk_total_cost_usd": 1000.0,
        "white_label_package_plan": [
            {"enabled": True, "package_size_g": 3.5, "allocation_pct": 100.0}
        ],
    }
    datasets = datasets_from_session(state, profile=PROFILES["repack"])
    assert "package_plan" in datasets
    assert "repack_scenario" in datasets