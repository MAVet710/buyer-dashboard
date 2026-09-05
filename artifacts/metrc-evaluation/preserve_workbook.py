#!/usr/bin/env python3
"""Fill label-matched submission fields without redesigning the Metrc workbook.

The script edits the XLSX package directly so every untouched ZIP member remains
byte-for-byte unchanged. Only label-matched CompanyInformation value cells are
modified. It never writes evaluation PASS/FAIL values or touches "Metrc Use Only"
content.

Vendor/User API keys are accepted only through environment variables and are
never written to the JSON manifest:
  METRC_INTEGRATOR_API_KEY -> Vendor Key Used
  METRC_USER_API_KEY       -> User Key Used
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.metrc_evaluation_submission import (  # noqa: E402
    COMPANY_INFORMATION_OPTIONAL_FIELDS,
    COMPANY_INFORMATION_REQUIRED_FIELDS,
    SECRET_WORKBOOK_FIELDS,
)
from services.metrc_evaluation_workbook import WORKBOOK_SHEETS  # noqa: E402


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN_NS, "r": REL_NS, "pr": PKG_REL_NS}
ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", REL_NS)

SECRET_ENV = {
    "Vendor Key Used": "METRC_INTEGRATOR_API_KEY",
    "User Key Used": "METRC_USER_API_KEY",
}
CELL_RE = re.compile(r"^([A-Z]+)(\d+)$")


class WorkbookPreservationError(RuntimeError):
    pass


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _column_number(token: str) -> int:
    value = 0
    for char in token:
        value = value * 26 + (ord(char) - 64)
    return value


def _column_name(number: int) -> str:
    if number < 1:
        raise ValueError("Column number must be positive.")
    chars: list[str] = []
    while number:
        number, remainder = divmod(number - 1, 26)
        chars.append(chr(65 + remainder))
    return "".join(reversed(chars))


def _cell_parts(reference: str) -> tuple[int, int]:
    match = CELL_RE.match(reference.upper())
    if not match:
        raise WorkbookPreservationError(f"Unsupported cell reference: {reference}")
    return _column_number(match.group(1)), int(match.group(2))


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        payload = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(payload)
    values: list[str] = []
    for item in root.findall("m:si", NS):
        values.append("".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t")))
    return values


def _cell_text(cell: ET.Element, shared: list[str]) -> str:
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
            raise WorkbookPreservationError("Workbook contains a sheet without a resolvable relationship target.")
        path = PurePosixPath(target)
        if path.is_absolute():
            normalized = str(path).lstrip("/")
        else:
            normalized = str(PurePosixPath("xl") / path)
        names.append(name)
        targets[name] = normalized
    return names, targets


def _merged_ranges(root: ET.Element) -> list[tuple[int, int, int, int]]:
    merged: list[tuple[int, int, int, int]] = []
    node = root.find("m:mergeCells", NS)
    if node is None:
        return merged
    for item in node.findall("m:mergeCell", NS):
        token = item.get("ref", "")
        if ":" in token:
            start, end = token.split(":", 1)
        else:
            start = end = token
        start_col, start_row = _cell_parts(start)
        end_col, end_row = _cell_parts(end)
        merged.append((start_col, start_row, end_col, end_row))
    return merged


def _merge_containing(
    col: int,
    row: int,
    merged: list[tuple[int, int, int, int]],
) -> tuple[int, int, int, int] | None:
    for item in merged:
        if item[0] <= col <= item[2] and item[1] <= row <= item[3]:
            return item
    return None


def _cells(root: ET.Element) -> dict[str, ET.Element]:
    return {
        cell.get("r", "").upper(): cell
        for cell in root.findall(".//m:sheetData/m:row/m:c", NS)
        if cell.get("r")
    }


def _row_element(root: ET.Element, row_number: int) -> ET.Element:
    sheet_data = root.find("m:sheetData", NS)
    if sheet_data is None:
        raise WorkbookPreservationError("Worksheet has no sheetData element.")
    for row in sheet_data.findall("m:row", NS):
        if int(row.get("r", "0") or 0) == row_number:
            return row
    new_row = ET.Element(f"{{{MAIN_NS}}}row", {"r": str(row_number)})
    inserted = False
    for index, row in enumerate(list(sheet_data)):
        if int(row.get("r", "0") or 0) > row_number:
            sheet_data.insert(index, new_row)
            inserted = True
            break
    if not inserted:
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


def _set_inline_text(cell: ET.Element, value: str) -> None:
    if cell.find("m:f", NS) is not None:
        raise WorkbookPreservationError(f"Refusing to overwrite formula cell {cell.get('r')}.")
    for child in list(cell):
        if child.tag in {f"{{{MAIN_NS}}}v", f"{{{MAIN_NS}}}is"}:
            cell.remove(child)
    cell.set("t", "inlineStr")
    inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
    text = ET.SubElement(inline, f"{{{MAIN_NS}}}t")
    if value != value.strip():
        text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text.text = value


def _find_label_cells(root: ET.Element, shared: list[str]) -> dict[str, list[str]]:
    expected = {
        _norm(field): field
        for field in (*COMPANY_INFORMATION_REQUIRED_FIELDS, *COMPANY_INFORMATION_OPTIONAL_FIELDS)
    }
    found: dict[str, list[str]] = {field: [] for field in expected.values()}
    for reference, cell in _cells(root).items():
        field = expected.get(_norm(_cell_text(cell, shared)))
        if field:
            found[field].append(reference)
    return found


def _target_reference(
    *,
    root: ET.Element,
    label_reference: str,
    known_labels: set[str],
    shared: list[str],
) -> str:
    merged = _merged_ranges(root)
    label_col, label_row = _cell_parts(label_reference)
    label_merge = _merge_containing(label_col, label_row, merged)
    start_col = label_merge[2] + 1 if label_merge else label_col + 1
    cell_map = _cells(root)

    for col in range(start_col, start_col + 6):
        candidate = f"{_column_name(col)}{label_row}"
        candidate_merge = _merge_containing(col, label_row, merged)
        if candidate_merge:
            candidate = f"{_column_name(candidate_merge[0])}{candidate_merge[1]}"
            if candidate_merge[0] < start_col:
                continue
        cell = cell_map.get(candidate)
        if cell is not None:
            text = _cell_text(cell, shared).strip()
            if _norm(text) in known_labels:
                raise WorkbookPreservationError(
                    f"Could not identify a value cell after label {label_reference}; encountered another form label at {candidate}."
                )
            if cell.find("m:f", NS) is not None:
                continue
        return candidate
    raise WorkbookPreservationError(f"Could not identify a safe value cell after label {label_reference}.")


def _load_company(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkbookPreservationError(f"Could not read company information {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise WorkbookPreservationError("Company information file must contain one JSON object.")
    normalized = {_norm(key): str(value or "").strip() for key, value in raw.items()}
    for secret in SECRET_WORKBOOK_FIELDS:
        if normalized.get(_norm(secret)):
            raise WorkbookPreservationError(
                f"{secret} must not be stored in the company JSON. Supply it only through its METRC_* environment variable."
            )
    return normalized


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def preserve_workbook(
    *,
    input_path: Path,
    output_path: Path,
    company_path: Path | None = None,
    include_secret_keys: bool = False,
    overwrite_existing: bool = False,
    require_complete: bool = False,
) -> dict[str, object]:
    if input_path.resolve() == output_path.resolve():
        raise WorkbookPreservationError("Input and output workbook paths must be different.")
    if not input_path.exists():
        raise WorkbookPreservationError(f"Input workbook does not exist: {input_path}")

    company = _load_company(company_path)
    values: dict[str, str] = {}
    for field in (*COMPANY_INFORMATION_REQUIRED_FIELDS, *COMPANY_INFORMATION_OPTIONAL_FIELDS):
        if field in SECRET_WORKBOOK_FIELDS:
            continue
        clean = company.get(_norm(field), "")
        if clean:
            values[field] = clean
    if include_secret_keys:
        for field, env_name in SECRET_ENV.items():
            clean = os.getenv(env_name, "").strip()
            if clean:
                values[field] = clean

    with zipfile.ZipFile(input_path, "r") as source:
        names, targets = _workbook_sheet_targets(source)
        if tuple(names) != tuple(WORKBOOK_SHEETS):
            raise WorkbookPreservationError(
                "Workbook sheet structure does not match Generic_Evaluation_for_All_States_MASTER 10.2025. "
                f"Expected {list(WORKBOOK_SHEETS)!r}; observed {names!r}."
            )
        shared = _shared_strings(source)
        company_target = targets.get("CompanyInformation")
        if not company_target:
            raise WorkbookPreservationError("CompanyInformation sheet target is missing.")
        company_root = ET.fromstring(source.read(company_target))
        labels = _find_label_cells(company_root, shared)
        known_labels = {_norm(field) for field in labels}
        filled: list[dict[str, object]] = []
        missing_labels: list[str] = []
        missing_values: list[str] = []

        for field in COMPANY_INFORMATION_REQUIRED_FIELDS:
            matches = labels.get(field) or []
            if len(matches) != 1:
                missing_labels.append(field)
                continue
            value = values.get(field, "")
            if not value:
                missing_values.append(field)
                continue
            target = _target_reference(
                root=company_root,
                label_reference=matches[0],
                known_labels=known_labels,
                shared=shared,
            )
            cell = _get_or_create_cell(company_root, target)
            existing = _cell_text(cell, shared).strip()
            if existing and existing != value and not overwrite_existing:
                raise WorkbookPreservationError(
                    f"Refusing to overwrite existing CompanyInformation value at {target} for {field}. Use --overwrite-existing only after reviewing the template."
                )
            _set_inline_text(cell, value)
            filled.append({
                "field": field,
                "sheet": "CompanyInformation",
                "cell": target,
                "secret": field in SECRET_WORKBOOK_FIELDS,
            })

        for field in COMPANY_INFORMATION_OPTIONAL_FIELDS:
            value = values.get(field, "")
            if not value:
                continue
            matches = labels.get(field) or []
            if len(matches) != 1:
                missing_labels.append(field)
                continue
            target = _target_reference(
                root=company_root,
                label_reference=matches[0],
                known_labels=known_labels,
                shared=shared,
            )
            cell = _get_or_create_cell(company_root, target)
            existing = _cell_text(cell, shared).strip()
            if existing and existing != value and not overwrite_existing:
                raise WorkbookPreservationError(
                    f"Refusing to overwrite existing CompanyInformation value at {target} for {field}."
                )
            _set_inline_text(cell, value)
            filled.append({"field": field, "sheet": "CompanyInformation", "cell": target, "secret": False})

        if require_complete and (missing_labels or missing_values):
            raise WorkbookPreservationError(
                "Workbook is not submission-complete. "
                f"Missing labels: {missing_labels}; missing values: {missing_values}."
            )

        changed_xml = ET.tostring(company_root, encoding="utf-8", xml_declaration=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w") as destination:
            for info in source.infolist():
                payload = changed_xml if info.filename == company_target else source.read(info.filename)
                destination.writestr(info, payload)

    with zipfile.ZipFile(output_path, "r") as check:
        final_names, _targets = _workbook_sheet_targets(check)
    if tuple(final_names) != tuple(WORKBOOK_SHEETS):
        output_path.unlink(missing_ok=True)
        raise WorkbookPreservationError("Output workbook failed the 22-sheet structure verification.")

    return {
        "schema_version": 1,
        "input_file": input_path.name,
        "output_file": output_path.name,
        "input_sha256": _sha256(input_path),
        "output_sha256": _sha256(output_path),
        "sheet_count": len(final_names),
        "sheet_names": final_names,
        "filled_fields": filled,
        "filled_count": len(filled),
        "missing_labels": sorted(set(missing_labels)),
        "missing_values": sorted(set(missing_values)),
        "secret_fields_filled": {
            field: any(item["field"] == field for item in filled)
            for field in SECRET_WORKBOOK_FIELDS
        },
        "secret_values_recorded": False,
        "task_result_cells_modified": False,
        "metrc_use_only_cells_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--company-info", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--with-secret-keys", action="store_true")
    parser.add_argument("--overwrite-existing", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()

    try:
        manifest = preserve_workbook(
            input_path=args.input,
            output_path=args.output,
            company_path=args.company_info,
            include_secret_keys=args.with_secret_keys,
            overwrite_existing=args.overwrite_existing,
            require_complete=args.require_complete,
        )
    except WorkbookPreservationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    manifest_path = args.manifest or args.output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Preserved workbook: {args.output}")
    print(f"Structure: {manifest['sheet_count']} sheets; {manifest['filled_count']} fields filled")
    print(f"Manifest (redacted): {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
