import ast
from pathlib import Path


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _read_app_text() -> str:
    return APP_PATH.read_text(encoding="utf-8")


def test_market_price_map_contains_required_keys():
    tree = ast.parse(_read_app_text())
    market_map = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MARKET_PRICE_MAP":
                    market_map = ast.literal_eval(node.value)
                    break
    assert isinstance(market_map, dict)
    required = {
        "bho",
        "live_resin",
        "badder",
        "shatter",
        "rosin",
        "rosin_jam",
        "distillate",
        "rso",
        "co2_oil",
        "vape",
        "bulk_oil",
        "concentrate",
    }
    assert required.issubset(set(market_map.keys()))


def test_extraction_traceability_fields_present_in_app_code():
    source = _read_app_text()
    for field_name in [
        "source_inventory_batch_ids",
        "source_inventory_metrc_ids",
        "allocated_input_weight_g",
        "allocated_input_cost_total",
        "inventory_linked",
    ]:
        assert field_name in source


def test_executive_overview_contains_required_upgrade_sections():
    source = _read_app_text()
    required_sections = [
        "Output by Method",
        "Yield Trend Over Time",
        "Revenue vs COGS Trend",
        "Batch Status Breakdown",
        "COA / QA Risk Breakdown",
        "Output by Product Type",
        "Method Efficiency Comparison",
        "Inventory Pressure Snapshot",
        "Top At-Risk Batches",
        "Top Aging Material Lots",
        "Executive Risk Summary",
        "Value & Profitability Analysis",
    ]
    for section in required_sections:
        assert section in source
