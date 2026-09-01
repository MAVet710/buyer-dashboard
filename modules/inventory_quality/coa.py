"""Durable, package-keyed COA parsing and normalization.

The normalized shape intentionally follows the Cannlytics COA vocabulary for
sample metadata and analyte results, while keeping DoobieLogic provider-neutral.
PDF text/tables are parsed deterministically first. OCR or an LLM is never a
silent compliance dependency; image-only or ambiguous certificates remain a
review/fallback case.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import re
import zlib
from typing import Any, Iterable

from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryLot, utc_now

from .models import CoaAnalyteResult, CoaDocument
from .service import LotQualityService


MAX_COA_BYTES = 15 * 1024 * 1024
PARSER_NAME = "doobielogic-coa"
PARSER_VERSION = "1"

_METRC_RE = re.compile(r"\b1A[A-Z0-9]{18,30}\b", re.IGNORECASE)
_NUMBER_RE = r"(?:ND|N/D|<\s*(?:LOQ|LOD)|-?\d+(?:\.\d+)?)"
_UNIT_RE = r"(?:%|mg\s*/\s*g|mg\s*/\s*unit|mg\s*/\s*serving|ug\s*/\s*g|µg\s*/\s*g|ppm|ppb)?"

# key, display name, analysis, aliases. Longer/specific aliases come first.
_ANALYTES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("thca", "THCA", "cannabinoids", ("THCA", "THC-A", "Tetrahydrocannabinolic Acid")),
    ("delta_9_thc", "Delta-9 THC", "cannabinoids", ("Delta-9 THC", "D9 THC", "Δ9-THC", "THC9", "THC")),
    ("delta_8_thc", "Delta-8 THC", "cannabinoids", ("Delta-8 THC", "D8 THC", "Δ8-THC")),
    ("thcva", "THCVA", "cannabinoids", ("THCVA", "THCV-A")),
    ("thcv", "THCV", "cannabinoids", ("THCV",)),
    ("cbda", "CBDA", "cannabinoids", ("CBDA", "CBD-A")),
    ("cbd", "CBD", "cannabinoids", ("CBD",)),
    ("cbga", "CBGA", "cannabinoids", ("CBGA", "CBG-A")),
    ("cbg", "CBG", "cannabinoids", ("CBG",)),
    ("cbca", "CBCA", "cannabinoids", ("CBCA", "CBC-A")),
    ("cbc", "CBC", "cannabinoids", ("CBC",)),
    ("cbn", "CBN", "cannabinoids", ("CBN",)),
    ("alpha_pinene", "Alpha-Pinene", "terpenes", ("Alpha-Pinene", "A-Pinene", "α-Pinene", "a-Pinene")),
    ("beta_pinene", "Beta-Pinene", "terpenes", ("Beta-Pinene", "B-Pinene", "β-Pinene", "b-Pinene")),
    ("beta_myrcene", "Beta-Myrcene", "terpenes", ("Beta-Myrcene", "B-Myrcene", "β-Myrcene", "Myrcene")),
    ("limonene", "Limonene", "terpenes", ("D-Limonene", "Limonene")),
    ("linalool", "Linalool", "terpenes", ("Linalool",)),
    ("beta_caryophyllene", "Beta-Caryophyllene", "terpenes", ("Beta-Caryophyllene", "B-Caryophyllene", "β-Caryophyllene", "Caryophyllene")),
    ("alpha_humulene", "Alpha-Humulene", "terpenes", ("Alpha-Humulene", "A-Humulene", "Humulene")),
    ("terpinolene", "Terpinolene", "terpenes", ("Terpinolene",)),
    ("ocimene", "Ocimene", "terpenes", ("Beta-Ocimene", "B-Ocimene", "Ocimene")),
    ("bisabolol", "Bisabolol", "terpenes", ("Alpha-Bisabolol", "A-Bisabolol", "Bisabolol")),
    ("camphene", "Camphene", "terpenes", ("Camphene",)),
    ("geraniol", "Geraniol", "terpenes", ("Geraniol",)),
    ("nerolidol", "Nerolidol", "terpenes", ("Trans-Nerolidol", "Cis-Nerolidol", "Nerolidol")),
    ("fenchol", "Fenchol", "terpenes", ("Fenchol",)),
    ("borneol", "Borneol", "terpenes", ("Borneol",)),
)


def _normalized_tag(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _clean_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if text.upper() in {"ND", "N/D", "<LOQ", "<LOD", "LOQ", "LOD"}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _percent(value: Any) -> float | None:
    number = _float(value)
    if number is None or number < 0 or number > 100:
        return None
    return round(number, 6)


def _date(value: Any) -> datetime | None:
    text = _clean_space(value)
    if not text:
        return None
    cleaned = re.sub(r"(?i)\b(?:EST|EDT|PST|PDT|UTC)\b", "", text).strip()
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _extract_labeled(text: str, labels: Iterable[str], *, max_length: int = 512) -> str:
    for label in labels:
        match = re.search(rf"(?im)^\s*(?:{label})\s*(?:[:#]|\-|\|)\s*([^\n\r]+)", text)
        if match:
            return _clean_space(match.group(1))[:max_length]
    return ""


def _extract_date(text: str, labels: Iterable[str]) -> datetime | None:
    value = _extract_labeled(text, labels, max_length=80)
    if value:
        # Keep just the leading date token when a time/status follows it.
        match = re.search(r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", value)
        return _date(match.group(0) if match else value)
    for label in labels:
        match = re.search(rf"(?i)(?:{label})\s*[:#\-]?\s*(\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}})", text)
        if match:
            return _date(match.group(1))
    return None


def _extract_total(text: str, labels: Iterable[str]) -> float | None:
    for label in labels:
        match = re.search(rf"(?i)(?:{label})\s*(?:[:|=\-])?\s*(\d+(?:\.\d+)?)\s*%?", text)
        if match:
            return _percent(match.group(1))
    return None


def _extract_pdf(payload: bytes) -> tuple[str, list[str]]:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - production dependency contract
        raise ValueError("PDF COA parsing requires pdfplumber.") from exc

    text_parts: list[str] = []
    table_lines: list[str] = []
    try:
        with pdfplumber.open(BytesIO(payload)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                if page_text:
                    text_parts.append(page_text)
                try:
                    tables = page.extract_tables() or []
                except Exception:
                    tables = []
                for table in tables:
                    for row in table or []:
                        cells = [_clean_space(cell) for cell in (row or []) if _clean_space(cell)]
                        if cells:
                            table_lines.append(" | ".join(cells))
    except Exception as exc:
        raise ValueError("The uploaded COA PDF could not be read.") from exc
    text = "\n".join(text_parts).strip()
    if not text and not table_lines:
        raise ValueError("No readable text was found in the COA PDF. Use a text-based certificate or a reviewed OCR workflow.")
    return text, table_lines


def _alias_pattern(alias: str) -> str:
    escaped = re.escape(alias)
    escaped = escaped.replace(r"\ ", r"\s*")
    escaped = escaped.replace(r"\-", r"[-\s]*")
    return escaped


def _parse_analyte_line(line: str) -> dict[str, Any] | None:
    clean = _clean_space(line)
    if not clean or re.search(r"(?i)\b(total|tac)\b", clean):
        return None
    for key, display, analysis, aliases in _ANALYTES:
        alias_group = "|".join(_alias_pattern(alias) for alias in aliases)
        match = re.search(
            rf"(?i)(?:^|[|:\s])(?:{alias_group})(?:\s|\||:|=|-)*({_NUMBER_RE})\s*({_UNIT_RE})",
            clean,
        )
        if not match:
            continue
        raw_value = re.sub(r"\s+", "", match.group(1)).upper()
        units = _clean_space(match.group(2)).replace(" ", "") or ("%" if analysis in {"cannabinoids", "terpenes"} else "")
        number = _float(raw_value)
        return {
            "analysis": analysis,
            "key": key,
            "name": display,
            "value": number,
            "value_text": raw_value,
            "units": units,
            "mg_g": number if units.casefold() == "mg/g" else None,
            "limit": None,
            "lod": None,
            "loq": None,
            "status": "",
        }
    return None


def _parse_results(text: str, table_lines: list[str]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    candidates = [*text.splitlines(), *table_lines]
    for line in candidates:
        result = _parse_analyte_line(line)
        if not result or result["key"] in seen:
            continue
        seen.add(str(result["key"]))
        results.append(result)
    return results


def parse_coa_pdf(payload: bytes, *, expected_package_id: str = "") -> dict[str, Any]:
    """Parse one PDF into a Cannlytics-compatible normalized sample shape.

    When ``expected_package_id`` is supplied, any METRC IDs discovered in the
    document must include that exact tag. A certificate with a different tag is
    rejected before it can affect inventory or a label.
    """

    if not payload:
        raise ValueError("The uploaded COA is empty.")
    if len(payload) > MAX_COA_BYTES:
        raise ValueError("The COA exceeds the 15 MB upload limit.")
    if not payload.startswith(b"%PDF"):
        raise ValueError("COA fallback currently accepts PDF certificates only.")

    text, table_lines = _extract_pdf(payload)
    all_text = "\n".join([text, *table_lines])
    metrc_ids = list(dict.fromkeys(_normalized_tag(value) for value in _METRC_RE.findall(all_text)))
    metrc_source = _extract_labeled(
        all_text,
        (r"METRC\s+Source(?:\s+Package)?(?:\s+ID)?", r"Source\s+Package(?:\s+ID)?", r"METRC\s+Package(?:\s+ID)?"),
        max_length=255,
    )
    metrc_source_match = _METRC_RE.search(metrc_source)
    metrc_source_id = _normalized_tag(metrc_source_match.group(0)) if metrc_source_match else ""
    metrc_lab = _extract_labeled(all_text, (r"METRC\s+Lab(?:\s+Sample)?(?:\s+ID)?", r"METRC\s+Sample(?:\s+ID)?"), max_length=255)
    metrc_lab_match = _METRC_RE.search(metrc_lab)
    metrc_lab_id = _normalized_tag(metrc_lab_match.group(0)) if metrc_lab_match else ""
    for value in (metrc_source_id, metrc_lab_id):
        if value and value not in metrc_ids:
            metrc_ids.append(value)

    expected = _normalized_tag(expected_package_id)
    if expected and metrc_ids and expected not in metrc_ids:
        shown = ", ".join(metrc_ids[:4])
        raise ValueError(f"COA METRC tag mismatch. Selected package {expected} but the certificate references {shown}.")

    results = _parse_results(text, table_lines)
    result_by_key = {str(row["key"]): row for row in results}
    total_cannabinoids = _extract_total(all_text, (r"Total\s+Cannabinoids", r"TAC"))
    total_thc = _extract_total(all_text, (r"Total\s+THC",))
    total_cbd = _extract_total(all_text, (r"Total\s+CBD",))
    total_terpenes = _extract_total(all_text, (r"Total\s+Terpenes?",))

    status = _extract_labeled(all_text, (r"Overall\s+Status", r"Test\s+Status", r"Status"), max_length=32)
    normalized_status = status.casefold()
    if "pass" in normalized_status:
        status = "pass"
    elif "fail" in normalized_status:
        status = "fail"
    elif len(status) > 16:
        status = ""

    verification_state = "unverified"
    if expected:
        verification_state = "matched" if expected in metrc_ids else "operator_confirmation_required"
    elif metrc_source_id or metrc_ids:
        verification_state = "tag_extracted"

    sample = {
        "product_name": _extract_labeled(all_text, (r"Product\s+Name", r"Sample\s+Name", r"Product")),
        "product_type": _extract_labeled(all_text, (r"Product\s+Type", r"Matrix", r"Category"), max_length=255),
        "strain_name": _extract_labeled(all_text, (r"Strain(?:\s+Name)?",), max_length=255),
        "batch_number": _extract_labeled(all_text, (r"Batch(?:\s+Number|\s+No\.?|\s+ID)?", r"Lot(?:\s+Number|\s+No\.?|\s+ID)?"), max_length=255),
        "lab_name": _extract_labeled(all_text, (r"Testing\s+Laboratory", r"Laboratory", r"Lab\s+Name"), max_length=255),
        "lab_license_number": _extract_labeled(all_text, (r"Lab(?:oratory)?\s+License(?:\s+Number)?",), max_length=255),
        "lab_id": _extract_labeled(all_text, (r"Lab(?:oratory)?\s+ID", r"Sample\s+ID", r"Certificate\s+(?:ID|Number)"), max_length=255),
        "metrc_ids": metrc_ids,
        "metrc_source_id": metrc_source_id or (expected if expected in metrc_ids else ""),
        "metrc_lab_id": metrc_lab_id,
        "date_tested": _extract_date(all_text, (r"Date\s+Tested", r"Tested", r"Test\s+Date", r"Analysis\s+Date", r"Date\s+of\s+Analysis")),
        "date_collected": _extract_date(all_text, (r"Date\s+Collected", r"Collected", r"Collection\s+Date")),
        "date_received": _extract_date(all_text, (r"Date\s+Received", r"Received", r"Receipt\s+Date")),
        "status": status,
        "total_thc": total_thc,
        "total_cbd": total_cbd,
        "total_cannabinoids": total_cannabinoids,
        "total_terpenes": total_terpenes,
        "results": results,
        "thca": result_by_key.get("thca", {}).get("value"),
        "verification_state": verification_state,
    }
    return sample


class CoaDocumentService:
    """Persist, match and expose package-specific COA evidence."""

    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def _package_id(lot: InventoryLot) -> str:
        return _normalized_tag(lot.compliance_package_id)

    @staticmethod
    def _find_lot_for_package(session: Session, organization_id: str, facility_id: str, package_id: str) -> InventoryLot | None:
        if not package_id:
            return None
        return session.scalar(
            select(InventoryLot).where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
                InventoryLot.compliance_package_id == package_id,
            )
        )

    def ingest_for_lot(
        self,
        organization_id: str,
        facility_id: str,
        lot_id: str,
        *,
        payload: bytes,
        filename: str,
        content_type: str,
        actor: str,
        source: str = "label_studio_fallback",
    ) -> dict[str, Any]:
        with Session(self.engine) as session, session.begin():
            lot = session.get(InventoryLot, lot_id)
            if lot is None or lot.organization_id != organization_id or lot.facility_id != facility_id:
                raise ValueError("Inventory batch was not found in the active facility.")
            package_id = self._package_id(lot)
            if not package_id:
                raise ValueError("A METRC package/tag is required before a COA can be attached to Label Studio.")
            parsed = parse_coa_pdf(payload, expected_package_id=package_id)
            row = self._persist(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                lot=lot,
                package_id=package_id,
                payload=payload,
                filename=filename,
                content_type=content_type,
                actor=actor,
                source=source,
                parsed=parsed,
            )
            if row.verification_state == "matched":
                self._apply_to_lot(session, lot, row)
            session.flush()
            return self._payload(session, row)

    def ingest_library(
        self,
        organization_id: str,
        facility_id: str,
        *,
        payload: bytes,
        filename: str,
        content_type: str,
        actor: str,
    ) -> dict[str, Any]:
        parsed = parse_coa_pdf(payload)
        parsed_ids = [str(value) for value in parsed.get("metrc_ids") or [] if value]
        package_id = _normalized_tag(parsed.get("metrc_source_id") or (parsed_ids[0] if parsed_ids else ""))
        if not package_id:
            raise ValueError("The COA library requires a readable METRC source/package tag so it can be matched automatically later.")
        with Session(self.engine) as session, session.begin():
            lot = self._find_lot_for_package(session, organization_id, facility_id, package_id)
            row = self._persist(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                lot=lot,
                package_id=package_id,
                payload=payload,
                filename=filename,
                content_type=content_type,
                actor=actor,
                source="coa_library",
                parsed=parsed,
            )
            if lot is not None:
                self._apply_to_lot(session, lot, row)
            session.flush()
            return self._payload(session, row)

    def confirm_for_lot(self, organization_id: str, facility_id: str, lot_id: str, document_id: str, *, actor: str) -> dict[str, Any]:
        with Session(self.engine) as session, session.begin():
            lot = session.get(InventoryLot, lot_id)
            row = session.get(CoaDocument, document_id)
            if lot is None or lot.organization_id != organization_id or lot.facility_id != facility_id:
                raise ValueError("Inventory batch was not found in the active facility.")
            if row is None or row.organization_id != organization_id or row.facility_id != facility_id:
                raise ValueError("COA document was not found in the active facility.")
            package_id = self._package_id(lot)
            if not package_id or _normalized_tag(row.package_id) != package_id:
                raise ValueError("The COA is not associated with the selected METRC package tag.")
            row.lot_id = lot.id
            row.verification_state = "operator_confirmed"
            row.status = "parsed"
            row.verified_at = utc_now()
            row.imported_by = actor
            self._apply_to_lot(session, lot, row)
            session.flush()
            return self._payload(session, row)

    def resolve_for_lot(self, session: Session, lot: InventoryLot) -> tuple[CoaDocument | None, list[CoaAnalyteResult]]:
        package_id = self._package_id(lot)
        if not package_id:
            return None, []
        row = session.scalar(
            select(CoaDocument)
            .where(
                CoaDocument.organization_id == lot.organization_id,
                CoaDocument.facility_id == lot.facility_id,
                CoaDocument.status == "parsed",
                CoaDocument.verification_state.in_(("matched", "tag_extracted", "operator_confirmed")),
                or_(CoaDocument.package_id == package_id, CoaDocument.metrc_source_id == package_id),
            )
            .order_by(CoaDocument.verified_at.desc().nullslast(), CoaDocument.created_at.desc())
        )
        if row is None:
            return None, []
        results = list(session.scalars(select(CoaAnalyteResult).where(CoaAnalyteResult.coa_document_id == row.id).order_by(CoaAnalyteResult.sort_order, CoaAnalyteResult.name)))
        return row, results

    def get_document(self, organization_id: str, facility_id: str, document_id: str) -> dict[str, Any]:
        with Session(self.engine) as session:
            row = session.get(CoaDocument, document_id)
            if row is None or row.organization_id != organization_id or row.facility_id != facility_id:
                raise ValueError("COA document was not found in the active facility.")
            return self._payload(session, row)

    def list_documents(self, organization_id: str, facility_id: str, *, limit: int = 250) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = list(session.scalars(select(CoaDocument).where(CoaDocument.organization_id == organization_id, CoaDocument.facility_id == facility_id).order_by(CoaDocument.created_at.desc()).limit(limit)))
            return [self._payload(session, row) for row in rows]

    def document_bytes(self, organization_id: str, facility_id: str, document_id: str) -> tuple[bytes, str, str]:
        with Session(self.engine) as session:
            row = session.get(CoaDocument, document_id)
            if row is None or row.organization_id != organization_id or row.facility_id != facility_id:
                raise ValueError("COA document was not found in the active facility.")
            return zlib.decompress(row.payload_compressed), row.filename, row.content_type

    def _persist(
        self,
        session: Session,
        *,
        organization_id: str,
        facility_id: str,
        lot: InventoryLot | None,
        package_id: str,
        payload: bytes,
        filename: str,
        content_type: str,
        actor: str,
        source: str,
        parsed: dict[str, Any],
    ) -> CoaDocument:
        fingerprint = sha256(payload).hexdigest()
        existing = session.scalar(
            select(CoaDocument).where(
                CoaDocument.organization_id == organization_id,
                CoaDocument.facility_id == facility_id,
                CoaDocument.fingerprint == fingerprint,
            )
        )
        if existing is not None:
            if _normalized_tag(existing.package_id) != _normalized_tag(package_id):
                raise ValueError("This COA was already stored for a different METRC package tag.")
            if existing.lot_id is None and lot is not None:
                existing.lot_id = lot.id
            return existing

        verification = str(parsed.get("verification_state") or "unverified")
        row = CoaDocument(
            organization_id=organization_id,
            facility_id=facility_id,
            lot_id=lot.id if lot else None,
            package_id=_normalized_tag(package_id),
            source=source,
            status="needs_confirmation" if verification == "operator_confirmation_required" else "parsed",
            verification_state=verification,
            filename=(filename or "coa.pdf")[:512],
            content_type=(content_type or "application/pdf")[:255],
            fingerprint=fingerprint,
            payload_compressed=zlib.compress(payload, level=9),
            payload_size=len(payload),
            parser_name=PARSER_NAME,
            parser_version=PARSER_VERSION,
            product_name=_clean_space(parsed.get("product_name"))[:512],
            product_type=_clean_space(parsed.get("product_type"))[:255],
            strain_name=_clean_space(parsed.get("strain_name"))[:255],
            batch_number=_clean_space(parsed.get("batch_number"))[:255],
            lab_name=_clean_space(parsed.get("lab_name"))[:255],
            lab_license_number=_clean_space(parsed.get("lab_license_number"))[:255],
            lab_id=_clean_space(parsed.get("lab_id"))[:255],
            metrc_source_id=_normalized_tag(parsed.get("metrc_source_id")),
            metrc_lab_id=_normalized_tag(parsed.get("metrc_lab_id")),
            metrc_ids_json=json.dumps(list(parsed.get("metrc_ids") or [])),
            date_tested=parsed.get("date_tested"),
            date_collected=parsed.get("date_collected"),
            date_received=parsed.get("date_received"),
            overall_status=_clean_space(parsed.get("status"))[:32],
            total_thc_percent=_percent(parsed.get("total_thc")),
            total_cbd_percent=_percent(parsed.get("total_cbd")),
            total_cannabinoids_percent=_percent(parsed.get("total_cannabinoids")),
            total_terpenes_percent=_percent(parsed.get("total_terpenes")),
            raw_payload_json=json.dumps(self._json_safe(parsed), sort_keys=True),
            imported_by=actor,
            verified_at=utc_now() if verification in {"matched", "tag_extracted"} else None,
        )
        session.add(row)
        session.flush()
        for position, result in enumerate(parsed.get("results") or []):
            session.add(
                CoaAnalyteResult(
                    coa_document_id=row.id,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    analysis=_clean_space(result.get("analysis"))[:96],
                    analyte_key=_clean_space(result.get("key"))[:160],
                    name=_clean_space(result.get("name"))[:255],
                    value=_float(result.get("value")),
                    value_text=_clean_space(result.get("value_text"))[:64],
                    units=_clean_space(result.get("units"))[:64],
                    mg_g=_float(result.get("mg_g")),
                    limit_value=_float(result.get("limit")),
                    lod=_float(result.get("lod")),
                    loq=_float(result.get("loq")),
                    status=_clean_space(result.get("status"))[:32],
                    sort_order=position,
                )
            )
        return row

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): CoaDocumentService._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [CoaDocumentService._json_safe(item) for item in value]
        return value

    @staticmethod
    def _coa_reference(row: CoaDocument) -> str:
        return row.lab_id or row.filename or row.fingerprint[:12]

    def _apply_to_lot(self, session: Session, lot: InventoryLot, row: CoaDocument) -> None:
        results = list(session.scalars(select(CoaAnalyteResult).where(CoaAnalyteResult.coa_document_id == row.id)))
        values = {item.analyte_key: item.value for item in results}
        current = LotQualityService.read(session, lot.id)
        state = row.overall_status
        if state.casefold() == "pass":
            state = "Passed"
        elif state.casefold() == "fail":
            state = "Failed"
        else:
            state = current.lab_testing_state if current else ""
        LotQualityService.set_evidence(
            session,
            lot_id=lot.id,
            lab_testing_state=state,
            coa_reference=self._coa_reference(row),
            coa_url=f"/api/v1/label-printing/coas/{row.id}/file",
            coa_document_id=row.id,
            thca_percent=values.get("thca"),
            tac_percent=row.total_cannabinoids_percent,
            total_thc_percent=row.total_thc_percent,
            total_cbd_percent=row.total_cbd_percent,
            total_cannabinoids_percent=row.total_cannabinoids_percent,
            total_terpenes_percent=row.total_terpenes_percent,
            evidence_source=f"coa:{row.source}",
            actor=row.imported_by,
        )

    def _payload(self, session: Session, row: CoaDocument) -> dict[str, Any]:
        results = list(session.scalars(select(CoaAnalyteResult).where(CoaAnalyteResult.coa_document_id == row.id).order_by(CoaAnalyteResult.sort_order, CoaAnalyteResult.name)))
        return {
            "id": row.id,
            "lot_id": row.lot_id,
            "package_id": row.package_id,
            "source": row.source,
            "status": row.status,
            "verification_state": row.verification_state,
            "filename": row.filename,
            "content_type": row.content_type,
            "fingerprint": row.fingerprint,
            "product_name": row.product_name,
            "product_type": row.product_type,
            "strain_name": row.strain_name,
            "batch_number": row.batch_number,
            "lab_name": row.lab_name,
            "lab_license_number": row.lab_license_number,
            "lab_id": row.lab_id,
            "metrc_source_id": row.metrc_source_id,
            "metrc_lab_id": row.metrc_lab_id,
            "metrc_ids": json.loads(row.metrc_ids_json or "[]"),
            "date_tested": row.date_tested,
            "date_collected": row.date_collected,
            "date_received": row.date_received,
            "overall_status": row.overall_status,
            "total_thc": row.total_thc_percent,
            "total_cbd": row.total_cbd_percent,
            "total_cannabinoids": row.total_cannabinoids_percent,
            "total_terpenes": row.total_terpenes_percent,
            "coa_reference": self._coa_reference(row),
            "file_url": f"/api/v1/label-printing/coas/{row.id}/file",
            "results": [
                {
                    "analysis": item.analysis,
                    "key": item.analyte_key,
                    "name": item.name,
                    "value": item.value,
                    "value_text": item.value_text,
                    "units": item.units,
                    "mg_g": item.mg_g,
                    "limit": item.limit_value,
                    "lod": item.lod,
                    "loq": item.loq,
                    "status": item.status,
                }
                for item in results
            ],
            "verified_at": row.verified_at,
            "created_at": row.created_at,
        }
