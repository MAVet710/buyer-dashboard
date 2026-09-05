from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
from xml.sax.saxutils import escape, quoteattr

from services.metrc_evaluation_submission import (
    COMPANY_INFORMATION_OPTIONAL_FIELDS,
    COMPANY_INFORMATION_REQUIRED_FIELDS,
    SECRET_WORKBOOK_FIELDS,
)
from services.metrc_evaluation_workbook import WORKBOOK_SHEETS


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "artifacts" / "metrc-evaluation" / "preserve_workbook.py"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _company() -> dict[str, str]:
    return {
        field: f"value for {field}"
        for field in COMPANY_INFORMATION_REQUIRED_FIELDS
        if field not in SECRET_WORKBOOK_FIELDS
    }


def _sheet_xml(labels: list[str] | None = None, marker: str = "") -> bytes:
    rows: list[str] = []
    for index, label in enumerate(labels or [], start=1):
        rows.append(
            f'<row r="{index}">'
            f'<c r="A{index}" t="inlineStr"><is><t>{escape(label)}</t></is></c>'
            f'<c r="B{index}" s="1"/>'
            "</row>"
        )
    if marker:
        rows.append(
            f'<row r="99"><c r="A99" t="inlineStr"><is><t>{escape(marker)}</t></is></c></row>'
        )
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{MAIN_NS}"><sheetData>{"".join(rows)}</sheetData></worksheet>'
    ).encode("utf-8")


def _build_template(path: Path, *, sheet_names=WORKBOOK_SHEETS) -> None:
    sheets = []
    relationships = []
    content_types = []
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, name in enumerate(sheet_names, start=1):
            sheets.append(
                f'<sheet name={quoteattr(name)} sheetId="{index}" r:id="rId{index}"/>'
            )
            relationships.append(
                f'<Relationship Id="rId{index}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{index}.xml"/>'
            )
            content_types.append(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
            labels = (
                list(COMPANY_INFORMATION_REQUIRED_FIELDS) + list(COMPANY_INFORMATION_OPTIONAL_FIELDS)
                if name == "CompanyInformation"
                else None
            )
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _sheet_xml(labels, marker=f"unchanged-{index}" if index == 2 else ""),
            )

        archive.writestr(
            "xl/workbook.xml",
            (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<workbook xmlns="{MAIN_NS}" xmlns:r="{REL_NS}"><sheets>'
                f'{"".join(sheets)}</sheets></workbook>'
            ).encode("utf-8"),
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<Relationships xmlns="{PKG_REL_NS}">{"".join(relationships)}</Relationships>'
            ).encode("utf-8"),
        )
        archive.writestr(
            "[Content_Types].xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Override PartName="/xl/workbook.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                f'{"".join(content_types)}</Types>'
            ).encode("utf-8"),
        )


def test_preserve_workbook_fills_only_company_information_and_keeps_22_sheet_structure(tmp_path):
    source = tmp_path / "source.xlsx"
    output = tmp_path / "submission.local.xlsx"
    company_path = tmp_path / "company.local.json"
    _build_template(source)
    company_path.write_text(json.dumps(_company()), encoding="utf-8")

    with zipfile.ZipFile(source, "r") as archive:
        untouched_before = archive.read("xl/worksheets/sheet2.xml")

    env = os.environ.copy()
    env["METRC_INTEGRATOR_API_KEY"] = "vendor-test-key"
    env["METRC_USER_API_KEY"] = "user-test-key"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(source),
            "--output",
            str(output),
            "--company-info",
            str(company_path),
            "--with-secret-keys",
            "--require-complete",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    manifest_path = output.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["sheet_count"] == 22
    assert manifest["sheet_names"] == list(WORKBOOK_SHEETS)
    assert manifest["missing_labels"] == []
    assert manifest["missing_values"] == []
    assert manifest["secret_fields_filled"] == {
        "Vendor Key Used": True,
        "User Key Used": True,
    }
    assert manifest["secret_values_recorded"] is False
    assert manifest["task_result_cells_modified"] is False
    assert manifest["metrc_use_only_cells_modified"] is False
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert "vendor-test-key" not in manifest_text
    assert "user-test-key" not in manifest_text

    with zipfile.ZipFile(output, "r") as archive:
        company_xml = archive.read("xl/worksheets/sheet1.xml")
        assert b"vendor-test-key" in company_xml
        assert b"user-test-key" in company_xml
        assert archive.read("xl/worksheets/sheet2.xml") == untouched_before


def test_preserve_workbook_rejects_wrong_sheet_structure(tmp_path):
    source = tmp_path / "wrong.xlsx"
    output = tmp_path / "submission.local.xlsx"
    company_path = tmp_path / "company.local.json"
    _build_template(source, sheet_names=WORKBOOK_SHEETS[:-1])
    company_path.write_text(json.dumps(_company()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(source),
            "--output",
            str(output),
            "--company-info",
            str(company_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2
    assert "sheet structure does not match" in result.stderr
    assert not output.exists()
