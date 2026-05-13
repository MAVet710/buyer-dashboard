import importlib
import pandas as pd


def test_refactor_module_imports():
    modules = [
        "utils.constants",
        "utils.product_parsing",
        "utils.dataframe_helpers",
        "utils.formatting",
        "reports.report_style",
        "reports.buyer_report",
        "reports.extraction_report",
        "reports.white_label_report",
        "reports.retail_ops_report",
        "views.retail_ops_command_center",
    ]
    for name in modules:
        assert importlib.import_module(name) is not None


def test_product_parsing_public_helpers():
    mod = importlib.import_module("utils.product_parsing")
    assert mod.get_strain_database_size() > 0
    assert isinstance(mod.get_strain_lookup_cache_size(), int)


def test_dataframe_helper_numeric_mean():
    mod = importlib.import_module("utils.dataframe_helpers")
    df = pd.DataFrame({"x": [1, 2, 3]})
    assert mod._safe_numeric_mean(df, "x", default=0.0) == 2.0


def test_report_style_token_exists():
    style = importlib.import_module("reports.report_style")
    assert hasattr(style, "ACCENT_ORANGE")
