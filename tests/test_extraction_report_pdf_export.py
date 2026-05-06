import ast
from datetime import datetime
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
from io import BytesIO


def _load_function_source(name: str) -> str:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node)
    raise AssertionError(f"Function {name} not found")


def _safe_report_df(value, empty_message="No data available") -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if value is None:
        return pd.DataFrame([{"Message": empty_message}])
    return pd.DataFrame(value)


def test_extraction_executive_report_pdf_empty_payload_returns_pdf_bytes():
    fn_src = _load_function_source("_build_extraction_executive_report_pdf")
    ns = {
        "BytesIO": BytesIO,
        "canvas": canvas,
        "letter": letter,
        "colors": colors,
        "Table": Table,
        "TableStyle": TableStyle,
        "datetime": datetime,
        "pd": pd,
        "_safe_report_df": _safe_report_df,
    }
    exec(fn_src, ns)
    pdf_bytes = ns["_build_extraction_executive_report_pdf"]({})
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert bytes(pdf_bytes).startswith(b"%PDF")
