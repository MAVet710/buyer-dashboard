import py_compile
from pathlib import Path

from views.extraction_perfect_view_v2 import _compute_health_score


def test_extraction_perfect_view_v2_compiles_without_syntax_errors():
    view_path = Path(__file__).resolve().parents[1] / "views" / "extraction_perfect_view_v2.py"
    py_compile.compile(str(view_path), doraise=True)


def test_compute_health_score_bounds_and_penalties():
    assert _compute_health_score(alert_count=0, avg_yield=18.0, qa_holds=0, at_risk_batches=0) == 100.0
    assert _compute_health_score(alert_count=30, avg_yield=4.0, qa_holds=10, at_risk_batches=10) == 0.0


def test_compute_health_score_intermediate_penalties():
    assert _compute_health_score(alert_count=2, avg_yield=15.0, qa_holds=0, at_risk_batches=0) == 84.0
    assert _compute_health_score(alert_count=0, avg_yield=15.0, qa_holds=1, at_risk_batches=0) == 88.0
    assert _compute_health_score(alert_count=0, avg_yield=14.0, qa_holds=0, at_risk_batches=1) == 92.0
