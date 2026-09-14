from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import zipfile
from xml.sax.saxutils import escape, quoteattr

from services.metrc_evaluation_workbook import (
    MA_REGULATOR_ACTION_TASKS,
    MA_WORKBOOK_TASKS,
    WORKBOOK_SHEETS,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "artifacts" / "metrc-evaluation" / "fill_workbook_results.py"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _inline_cell(reference: str, text: str) -> str:
    return f'<c r="{reference}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'


def _sheet_xml(name: str) -> bytes:
    rows: list[str] = []
    if name == "Permissions":
        permission_labels = [
            "Locations", "Strains", "Plant Batches / Plants", "Harvests", "Items", "Packages",
            "Sales", "Sales Deliveries", "Labs", "GET Transfers / Wholesale",
            "Transfer Template / External Incoming ",
        ]
        for row_number, label in enumerate(permission_labels, start=22):
            rows.append(f'<row r="{row_number}">{_inline_cell(f"B{row_number}", label)}<c r="C{row_number}"/><c r="D{row_number}"/></row>')
    tasks = [task for task in MA_REGULATOR_ACTION_TASKS if task.sheet == name]
    for index, task in enumerate(tasks):
        row_number = 5 + (index * 4)
        rows.append(
            f'<row r="{row_number}">{_inline_cell(f"A{row_number}", task.step)}'
            + "".join(f'<c r="{column}{row_number}"/>' for column in "BCDEFGH")
            + "</row>"
        )
    if tasks:
        protected_row = 5 + (len(tasks) * 4)
        rows.append(
            f'<row r="{protected_row}">{_inline_cell(f"A{protected_row}", "Metrc Use Only ")}'
            + "".join(f'<c r="{column}{protected_row}"/>' for column in "BCDEFGH")
            + "</row>"
        )
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{MAIN_NS}"><sheetData>{"".join(rows)}</sheetData></worksheet>'
    ).encode("utf-8")


def _build_template(path: Path) -> None:
    sheets = []
    relationships = []
    content_types = []
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, name in enumerate(WORKBOOK_SHEETS, start=1):
            sheets.append(f'<sheet name={quoteattr(name)} sheetId="{index}" r:id="rId{index}"/>')
            relationships.append(
                f'<Relationship Id="rId{index}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{index}.xml"/>'
            )
            content_types.append(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(name))
        archive.writestr(
            "xl/workbook.xml",
            (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<workbook xmlns="{MAIN_NS}" xmlns:r="{REL_NS}"><sheets>{"".join(sheets)}</sheets></workbook>'
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


def _write_evidence(directory: Path) -> None:
    directory.mkdir()
    for task in MA_WORKBOOK_TASKS:
        method, _, endpoint = task.current_endpoint.partition(" ")
        payload = {
            "task_number": task.number,
            "passed": True,
            "stage": "complete",
            "operation_type": task.operation_type,
            "state": "MA",
            "environment": "sandbox",
            "http_status": 200,
            "license_number": "SF-SBX-MA-4-11701",
            "provider_id": str(10000 + task.number),
            "last_modified": "2026-09-14T12:00:00-04:00",
            "request": {
                "method": method or "GET",
                "path": endpoint or task.current_endpoint,
                "query": {"licenseNumber": "SF-SBX-MA-4-11701"},
                "body": [{"Name": f"task-{task.number}"}] if method in {"POST", "PUT", "DELETE"} else None,
            },
            "records": [{"Id": 10000 + task.number, "Name": f"task-{task.number}", "LastModified": "2026-09-14T12:00:00-04:00"}],
        }
        (directory / f"task-{task.number:02d}-{task.operation_type}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )


def _sheet_path(sheet_name: str) -> str:
    return f"xl/worksheets/sheet{list(WORKBOOK_SHEETS).index(sheet_name) + 1}.xml"


def test_fill_workbook_results_populates_46_step_rows_and_permissions_without_metrc_use_only(tmp_path):
    source = tmp_path / "preserved.xlsx"
    output = tmp_path / "submission.xlsx"
    evidence = tmp_path / "evidence"
    _build_template(source)
    _write_evidence(evidence)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input", str(source),
            "--output", str(output),
            "--evidence-dir", str(evidence),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    manifest = json.loads(output.with_suffix(".results.manifest.json").read_text(encoding="utf-8"))
    assert manifest["regulator_action_rows_filled"] == 46
    assert manifest["expected_regulator_action_rows"] == 46
    assert manifest["task_result_cells_modified"] is True
    assert manifest["task_result_cells_modified_count"] == 46 * 7
    assert manifest["permissions_table_modified"] is True
    assert manifest["permissions_table_cells_modified_count"] == 22
    assert manifest["metrc_use_only_cells_modified"] is False
    assert manifest["secret_values_recorded"] is False

    with zipfile.ZipFile(output, "r") as archive:
        locations = archive.read(_sheet_path("Locations"))
        assert b">200<" in locations
        assert b"SF-SBX-MA-4-11701" in locations
        assert b"Metrc Use Only" in locations
        # The protected row exists but is never populated with the task evidence.
        protected_fragment = locations.split(b"Metrc Use Only", 1)[1]
        assert b"task-2" not in protected_fragment

        permissions = archive.read(_sheet_path("Permissions"))
        assert b">X<" in permissions
        transfers_row = permissions.split(b"GET Transfers / Wholesale", 1)[1].split(b"</row>", 1)[0]
        assert b'r="C31"' in transfers_row and b">X<" in transfers_row
        d31 = transfers_row.split(b'r="D31"', 1)[1].split(b"</c>", 1)[0]
        assert b">X<" not in d31


def test_fill_workbook_results_refuses_failed_evidence(tmp_path):
    source = tmp_path / "preserved.xlsx"
    output = tmp_path / "submission.xlsx"
    evidence = tmp_path / "evidence"
    _build_template(source)
    _write_evidence(evidence)
    failed_path = evidence / "task-17-plant_plantbatch_packages.json"
    failed = json.loads(failed_path.read_text(encoding="utf-8"))
    failed.update({"passed": False, "stage": "write", "http_status": 401})
    failed_path.write_text(json.dumps(failed), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input", str(source),
            "--output", str(output),
            "--evidence-dir", str(evidence),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2
    assert "Task 17" in result.stderr
    assert not output.exists()
