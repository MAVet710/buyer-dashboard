from pathlib import Path

from modules.coman.models import MachineModel


def test_purchasing_budget_category_rename_avoids_string_formatting_bug():
    source = Path("app.py").read_text(encoding="utf-8")
    assert '"%s":"Sales"%sales_col' not in source
    assert 'sales_col:"Sales Window Retail Sales"' in source


def test_coman_machine_library_uses_published_operator_field():
    source = Path("modules/coman/ui.py").read_text(encoding="utf-8")
    assert "model.minimum_operators" not in source
    assert "model.published_min_operators" in source
    assert hasattr(MachineModel, "published_min_operators")
