#!/usr/bin/env python3
"""Populate regulator verification cells after all MA evaluation evidence passes.

This is intentionally a second step after ``preserve_workbook.py``. The
preservation step remains responsible for CompanyInformation and secrets. This
writer fills only:

- the Permissions request table GET / POST-PUT-DELETE selections; and
- B:H on each Massachusetts-applicable task's visible ``Step`` row.

It never writes the ``Metrc Use Only`` rows, never creates API evidence, never
changes a failed task into a pass, and never records API keys in its manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.metrc_evaluation_finalization import build_final_report  # noqa: E402
from services.metrc_evaluation_workbook import (  # noqa: E402
    MA_REGULATOR_ACTION_TASKS,
    WORKBOOK_SHEETS,
)


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN_NS, "r": REL_NS, "pr": PKG_REL_NS}
ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", REL_NS)
CELL_RE = re.compile(r"^([A-Z]+)(\d+)$")
MAX_CELL_TEXT = 32000

# DoobieLogic's full MA evaluation seeks the endpoint families needed by the
# workbook. GET Transfers/Wholesale is GET-only; the remaining families need
# both read access and their reviewed mutation family where the workbook asks it.
PERMISSION_REQUEST_METHODS: dict[str, tuple[bool, bool]] = {
    "Locations": (True, True),
    "Strains": (True, True),
    "Plant Batches / Plants": (True, True),
    "Harvests": (True, True),
    "Items": (True, True),
    "Packages": (True, True),
    "Sales": (True, True),
    "Sales Deliveries": (True, True),
    "Labs": (True, True),
    "GET Transfers / Wholesale": (True, False),
    "Transfer Template / External Incoming": (True, True),
}


class WorkbookResultError(RuntimeError):
    pass


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _column_number(token: str) -> int:
    value = 0
    for char in token:
        value = value * 26 + (ord(char) - 64)
    return value


def _column_name(number: int) -> str:
    chars: list[str] = []
    while number:
        number, remainder = divmod(number - 1, 26)
        chars.append(chr(65 + remainder))
    return "".join(reversed(chars))


def _cell_parts(reference: str) -> tuple[int, int]:
    match = CELL_RE.match(reference.upper())
    if not match:
        raise WorkbookResultError(f"Unsupported cell reference: {reference}")
    return _column_number(match.group(1)), int(match.group(2))


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        payload = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(payload)
    return [
        "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
        for item in root.findall("m:si", NS)
    ]


def _cell_text(cell: ET.Element | None, shared: list[str]) -> str:
    if cell is None:
        return ""
    kind = cell.get("t", "")
    if kind == "s":
        value = cell.find("m:v", NS)
        try:
            return shared[int(value.text or "0")] if value is not None else ""
        except (ValueError, IndexError):
            return ""
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))
    value = cell.find("m:v", NS)
    return value.text or "" if value is not None else ""


def _workbook_sheet_targets(archive: zipfile.ZipFile) -> tuple[list[str], dict[str, str]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    relationships = {
        row.get("Id", ""): row.get("Target", "")
        for row in rels.findall("pr:Relationship", NS)
    }
    names: list[str] = []
    targets: dict[str, str] = {}
    for sheet in workbook.findall("m:sheets/m:sheet", NS):
        name = sheet.get("name", "")
        rel_id = sheet.get(f"{{{REL_NS}}}id", "")
        target = relationships.get(rel_id, "")
        if not name or not target:
            raise WorkbookResultError("Workbook contains an unresolved worksheet relationship.")
        path = PurePosixPath(target)
        normalized = str(path).lstrip("/") if path.is_absolute() else str(PurePosixPath("xl") / path)
        names.append(name)
        targets[name] = normalized
    return names, targets


def _cells(root: ET.Element) -> dict[str, ET.Element]:
    return {
        cell.get("r", "").upper(): cell
        for cell in root.findall(".//m:sheetData/m:row/m:c", NS)
        if cell.get("r")
    }


def _row_element(root: ET.Element, row_number: int) -> ET.Element:
    sheet_data = root.find("m:sheetData", NS)
    if sheet_data is None:
        raise WorkbookResultError("Worksheet has no sheetData element.")
    for row in sheet_data.findall("m:row", NS):
        if int(row.get("r", "0") or 0) == row_number:
            return row
    new_row = ET.Element(f"{{{MAIN_NS}}}row", {"r": str(row_number)})
    for index, row in enumerate(list(sheet_data)):
        if int(row.get("r", "0") or 0) > row_number:
            sheet_data.insert(index, new_row)
            return new_row
    sheet_data.append(new_row)
    return new_row


def _get_or_create_cell(root: ET.Element, reference: str) -> ET.Element:
    existing = _cells(root).get(reference.upper())
    if existing is not None:
        return existing
    col, row_number = _cell_parts(reference)
    row = _row_element(root, row_number)
    new_cell = ET.Element(f"{{{MAIN_NS}}}c", {"r": reference.upper()})
    inserted = False
    for index, cell in enumerate(row.findall("m:c", NS)):
        cell_col, _ = _cell_parts(cell.get("r", "A1"))
        if cell_col > col:
            row.insert(index, new_cell)
            inserted = True
            break
    if not inserted:
        row.append(new_cell)
    return new_cell


def _set_inline_text(cell: ET.Element, value: object) -> None:
    if cell.find("m:f", NS) is not None:
        raise WorkbookResultError(f"Refusing to overwrite formula cell {cell.get('r')}.")
    for child in list(cell):
        if child.tag in {f"{{{MAIN_NS}}}v", f"{{{MAIN_NS}}}is"}:
            cell.remove(child)
    cell.set("t", "inlineStr")
    inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
    text = ET.SubElement(inline, f"{{{MAIN_NS}}}t")
    text.text = str(value or "")[:MAX_CELL_TEXT]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _step_rows(root: ET.Element, shared: list[str]) -> dict[str, int]:
    cells = _cells(root)
    result: dict[str, int] = {}
    for reference, cell in cells.items():
        col, row = _cell_parts(reference)
        if col != 1:
            continue
        text = _cell_text(cell, shared).strip()
        if text.casefold().startswith("step"):
            result[_norm(text)] = row
    return result


def _metrc_use_only_row(root: ET.Element, shared: list[str]) -> int | None:
    for reference, cell in _cells(root).items():
        col, row = _cell_parts(reference)
        if col == 1 and _norm(_cell_text(cell, shared)) == _norm("Metrc Use Only"):
            return row
    return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkbookResultError(f"Could not read evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkbookResultError(f"Evidence must be a JSON object: {path}")
    return value


def _find_nested(value: Any, keys: tuple[str, ...]) -> Any:
    wanted = {key.casefold() for key in keys}
    queue: list[Any] = [value]
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            marker = id(current)
            if marker in seen:
                continue
            seen.add(marker)
            for key, nested in current.items():
                if str(key).casefold() in wanted and nested not in (None, "", [], {}):
                    return nested
            queue.extend(current.values())
        elif isinstance(current, list):
            queue.extend(current[:20])
    return None


def _provider_id(payload: dict[str, Any]) -> str:
    direct = payload.get("provider_id") or payload.get("external_reference")
    if direct not in (None, ""):
        return str(direct)
    nested = _find_nested(payload.get("readback") or payload.get("records") or payload.get("response"), ("Id", "id", "ProviderId"))
    return str(nested or "")


def _last_modified(payload: dict[str, Any]) -> str:
    direct = payload.get("last_modified") or payload.get("lastModified")
    if direct not in (None, ""):
        return str(direct)
    nested = _find_nested(payload.get("readback") or payload.get("records") or payload.get("response"), ("LastModified", "last_modified", "lastModified"))
    return str(nested or "")


def _tag(payload: dict[str, Any]) -> str:
    nested = _find_nested(
        payload,
        (
            "PackageTag", "PlantLabel", "PackageLabel", "StartingTag", "Tag", "Label",
            "package_tag", "plant_label", "package_label", "tag", "label",
        ),
    )
    return str(nested or "")


def _request_sent(payload: dict[str, Any]) -> str:
    request = payload.get("request")
    if not isinstance(request, dict):
        return ""
    method = str(request.get("method") or "").strip().upper()
    path = str(request.get("path") or "").strip()
    query = request.get("query")
    suffix = ""
    if isinstance(query, dict) and query:
        suffix = "?" + "&".join(f"{key}={value}" for key, value in sorted(query.items()))
    return " ".join(token for token in (method, f"{path}{suffix}") if token).strip()


def _minified_json(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    try:
        text = json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)
    except TypeError:
        text = json.dumps(str(value), separators=(",", ":"), ensure_ascii=False)
    if len(text) > MAX_CELL_TEXT:
        raise WorkbookResultError(
            f"Minified verification JSON exceeds the Excel cell safety limit ({len(text)} characters). "
            "Reduce the evidence to the exact verification record instead of truncating it."
        )
    return text


def _json_evidence(payload: dict[str, Any]) -> str:
    request = payload.get("request")
    if isinstance(request, dict) and request.get("body") not in (None, "", [], {}):
        return _minified_json(request.get("body"))
    request_json = payload.get("request_json")
    if isinstance(request_json, str) and request_json.strip():
        try:
            return _minified_json(json.loads(request_json))
        except json.JSONDecodeError:
            if len(request_json) <= MAX_CELL_TEXT:
                return request_json
    records = payload.get("records")
    if isinstance(records, list) and records:
        # For GET tasks the workbook needs verifiable response evidence, not an
        # entire paginated dataset. Preserve the exact first bounded record.
        return _minified_json(records[0])
    for key in ("response", "readback"):
        if payload.get(key) not in (None, "", [], {}):
            try:
                return _minified_json(payload.get(key))
            except WorkbookResultError:
                nested = _find_nested(payload.get(key), ("Data", "data", "Results", "results"))
                if isinstance(nested, list) and nested:
                    return _minified_json(nested[0])
                raise
    return ""


def _verification_values(payload: dict[str, Any]) -> list[str]:
    try:
        code = str(int(payload.get("http_status") or 0))
    except (TypeError, ValueError):
        code = str(payload.get("http_status") or "")
    return [
        code,
        str(payload.get("license_number") or ""),
        _provider_id(payload),
        _last_modified(payload),
        _tag(payload),
        _request_sent(payload),
        _json_evidence(payload),
    ]


def _load_assignments(evidence_dir: Path) -> list[tuple[Any, dict[str, Any], Path]]:
    # Reuse the canonical fail-closed assignment logic. CompanyInformation is not
    # needed for task assignment, so an empty object is intentional here.
    report = build_final_report(evidence_directory=evidence_dir, company_information={})
    rows = {int(row["number"]): row for row in report.get("tasks") or []}
    assignments: list[tuple[Any, dict[str, Any], Path]] = []
    for task in MA_REGULATOR_ACTION_TASKS:
        row = rows.get(task.number)
        if not row or row.get("status") != "passed":
            raise WorkbookResultError(
                f"Task {task.number} ({task.operation_type}) is not passed in canonical evidence; refusing to populate the regulator workbook."
            )
        evidence_path = Path(str(row.get("evidence_file") or ""))
        if not evidence_path.exists():
            raise WorkbookResultError(f"Assigned evidence file is missing for task {task.number}: {evidence_path}")
        payload = _read_json(evidence_path)
        assignments.append((task, payload, evidence_path))
    return assignments


def _permissions_edits(root: ET.Element, shared: list[str]) -> list[dict[str, Any]]:
    cells = _cells(root)
    label_rows: dict[str, int] = {}
    for reference, cell in cells.items():
        col, row = _cell_parts(reference)
        if col == 2:
            text = _cell_text(cell, shared).strip()
            for label in PERMISSION_REQUEST_METHODS:
                if _norm(text) == _norm(label):
                    label_rows[label] = row
    missing = sorted(set(PERMISSION_REQUEST_METHODS) - set(label_rows))
    if missing:
        raise WorkbookResultError(f"Permissions sheet is missing expected request rows: {missing}")

    edits: list[dict[str, Any]] = []
    for label, (get_access, write_access) in PERMISSION_REQUEST_METHODS.items():
        row = label_rows[label]
        for column, enabled, method in (("C", get_access, "GET"), ("D", write_access, "POST/PUT/DELETE")):
            cell = _get_or_create_cell(root, f"{column}{row}")
            existing = _cell_text(cell, shared).strip()
            desired = "X" if enabled else ""
            if existing and existing != desired:
                raise WorkbookResultError(
                    f"Refusing to overwrite non-empty Permissions value at {column}{row} ({label} {method}): {existing!r}"
                )
            _set_inline_text(cell, desired)
            edits.append({"sheet": "Permissions", "cell": f"{column}{row}", "permission": label, "method": method, "requested": enabled})
    return edits


def fill_workbook_results(
    *,
    input_path: Path,
    output_path: Path,
    evidence_dir: Path,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    if input_path.resolve() == output_path.resolve():
        raise WorkbookResultError("Input and output workbook paths must be different.")
    if not input_path.exists():
        raise WorkbookResultError(f"Input workbook does not exist: {input_path}")
    assignments = _load_assignments(evidence_dir)

    changed_parts: dict[str, bytes] = {}
    result_edits: list[dict[str, Any]] = []
    permission_edits: list[dict[str, Any]] = []

    with zipfile.ZipFile(input_path, "r") as source:
        sheet_names, targets = _workbook_sheet_targets(source)
        if tuple(sheet_names) != tuple(WORKBOOK_SHEETS):
            raise WorkbookResultError(
                "Workbook sheet structure does not match the regulator 10.2025 template."
            )
        shared = _shared_strings(source)
        roots: dict[str, ET.Element] = {}

        def root_for(sheet_name: str) -> ET.Element:
            if sheet_name not in roots:
                roots[sheet_name] = ET.fromstring(source.read(targets[sheet_name]))
            return roots[sheet_name]

        for task, payload, evidence_path in assignments:
            root = root_for(task.sheet)
            step_rows = _step_rows(root, shared)
            row_number = step_rows.get(_norm(task.step))
            if row_number is None:
                raise WorkbookResultError(
                    f"Could not locate {task.sheet} {task.step} in the regulator workbook."
                )
            protected_row = _metrc_use_only_row(root, shared)
            if protected_row is not None and row_number >= protected_row:
                raise WorkbookResultError(
                    f"Refusing to write task {task.number}: resolved Step row {row_number} is inside/after Metrc Use Only row {protected_row}."
                )
            values = _verification_values(payload)
            if values[0] != "200":
                raise WorkbookResultError(f"Task {task.number} verification code is not HTTP 200.")
            for offset, value in enumerate(values, start=2):
                reference = f"{_column_name(offset)}{row_number}"
                cell = _get_or_create_cell(root, reference)
                existing = _cell_text(cell, shared).strip()
                if existing and existing != str(value).strip():
                    raise WorkbookResultError(
                        f"Refusing to overwrite non-empty task verification cell {task.sheet}!{reference}: {existing!r}"
                    )
                _set_inline_text(cell, value)
                result_edits.append({
                    "task_number": task.number,
                    "operation_type": task.operation_type,
                    "sheet": task.sheet,
                    "step": task.step,
                    "cell": reference,
                    "evidence_file": evidence_path.name,
                })

        permissions_root = root_for("Permissions")
        permission_edits = _permissions_edits(permissions_root, shared)

        for sheet_name, root in roots.items():
            changed_parts[targets[sheet_name]] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w") as destination:
            for info in source.infolist():
                destination.writestr(info, changed_parts.get(info.filename, source.read(info.filename)))

    # Verify physical sheet names again from the produced workbook.
    with zipfile.ZipFile(output_path, "r") as verify:
        names, _targets = _workbook_sheet_targets(verify)
        if tuple(names) != tuple(WORKBOOK_SHEETS):
            raise WorkbookResultError("Output workbook no longer preserves the exact 22-sheet structure.")

    manifest = {
        "schema_version": 1,
        "input_workbook": input_path.name,
        "output_workbook": output_path.name,
        "input_sha256": _sha256(input_path),
        "output_sha256": _sha256(output_path),
        "sheet_count": len(WORKBOOK_SHEETS),
        "sheet_names": list(WORKBOOK_SHEETS),
        "regulator_action_rows_filled": len(assignments),
        "expected_regulator_action_rows": len(MA_REGULATOR_ACTION_TASKS),
        "task_result_cells_modified": True,
        "task_result_cells_modified_count": len(result_edits),
        "permissions_table_modified": True,
        "permissions_table_cells_modified_count": len(permission_edits),
        "metrc_use_only_cells_modified": False,
        "secret_values_recorded": False,
        "result_edits": result_edits,
        "permission_edits": permission_edits,
    }
    target_manifest = manifest_path or output_path.with_suffix(".results.manifest.json")
    target_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--manifest", default="")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        manifest = fill_workbook_results(
            input_path=Path(args.input),
            output_path=Path(args.output),
            evidence_dir=Path(args.evidence_dir),
            manifest_path=Path(args.manifest) if args.manifest else None,
        )
    except WorkbookResultError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        "Workbook verification cells populated: "
        f"{manifest['regulator_action_rows_filled']} regulator actions; "
        f"{manifest['permissions_table_cells_modified_count']} permission cells reviewed."
    )
    print("Metrc Use Only cells modified: false")
    print("Secret values recorded in results manifest: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
