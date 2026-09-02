"""Massachusetts flower COA reference fixtures for the durable DEV Sandbox.

These records are intentionally DEV-only external references.  A fixture keeps the
real laboratory/sample/batch/tracking identity in COA provenance while the newly
seeded Sandbox Facility package remains the current physical package identity used
for Label Studio QR/Code128 output.

No network call is required during a sandbox reset.  The source URLs are retained so
operators can inspect the public source record used to build each fixture.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
import zlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from modules.coman.models import Facility, InventoryLot, utc_now
from modules.inventory_quality.models import CoaAnalyteResult, CoaDocument
from modules.inventory_quality.service import LotQualityService


DEV_MA_COA_SOURCE = "dev_ma_external_reference"
DEV_MA_COA_EVIDENCE = f"coa:{DEV_MA_COA_SOURCE}"
DEV_MA_INHERITED_EVIDENCE = f"inherited:{DEV_MA_COA_SOURCE}"


def _r(analysis: str, key: str, name: str, value: float | None, value_text: str, units: str = "%") -> dict[str, Any]:
    return {
        "analysis": analysis,
        "key": key,
        "name": name,
        "value": value,
        "value_text": value_text,
        "units": units,
        "status": "Pass",
    }


# Values below are copied from the cited Massachusetts public lab records.  The list
# contains the cannabinoid/terpene rows exposed by the source record used for the DEV
# fixture; it is not expanded with invented zeroes or inferred analytes.
MA_FLOWER_COA_FIXTURES: dict[str, dict[str, Any]] = {
    "Blue Dream": {
        "source_url": "https://opencoa.org/coa/019f42d8-d3be-70e6-ab42-559844f5ef76/ob5-110625-816",
        "source_state": "MA",
        "source_license_holder": "Holyoke Wilds, LLC",
        "product_name": "BLUE DREAM - BUD",
        "product_type": "Flower",
        "batch_number": "OB5-110625(816)",
        "lab_name": "Kaycha MA, LLC",
        "lab_license_number": "IL281349",
        "lab_id": "NA51229001-003",
        "metrc_source_id": "1A40A0300010D89000000821",
        "metrc_lab_id": "",
        "date_tested": "2025-12-31T00:00:00+00:00",
        "overall_status": "pass",
        "total_thc": 23.32,
        "total_cbd": None,
        "total_cannabinoids": 27.79,
        "total_terpenes": 0.92,
        "results": [
            _r("cannabinoids", "thca", "THCA", 26.30, "26.30"),
            _r("cannabinoids", "cbga", "CBGA", 1.11, "1.11"),
            _r("cannabinoids", "delta_9_thc", "Delta-9 THC", 0.25, "0.25"),
            _r("cannabinoids", "thcva", "THCVA", 0.13, "0.13"),
            _r("cannabinoids", "cbd", "CBD", None, "ND"),
            _r("cannabinoids", "cbda", "CBDA", None, "ND"),
            _r("terpenes", "limonene", "Limonene", 0.207, "0.207"),
            _r("terpenes", "beta_caryophyllene", "Beta-Caryophyllene", 0.162, "0.162"),
            _r("terpenes", "beta_myrcene", "Beta-Myrcene", 0.132, "0.132"),
            _r("terpenes", "alpha_humulene", "Alpha-Humulene", 0.065, "0.065"),
            _r("terpenes", "linalool", "Linalool", 0.042, "0.042"),
            _r("terpenes", "beta_pinene", "Beta-Pinene", 0.041, "0.041"),
            _r("terpenes", "farnesene", "Farnesene", 0.040, "0.040"),
            _r("terpenes", "alpha_terpineol", "Alpha-Terpineol", 0.029, "0.029"),
            _r("terpenes", "bisabolol", "Alpha-Bisabolol", 0.028, "0.028"),
            _r("terpenes", "alpha_pinene", "Alpha-Pinene", 0.028, "0.028"),
            _r("terpenes", "caryophyllene_oxide", "Caryophyllene Oxide", 0.026, "0.026"),
            _r("terpenes", "fenchol", "Fenchol", 0.026, "0.026"),
            _r("terpenes", "geraniol", "Geraniol", 0.024, "0.024"),
            _r("terpenes", "geranyl_acetate", "Geranyl Acetate", 0.024, "0.024"),
            _r("terpenes", "borneol", "Borneol", 0.022, "0.022"),
            _r("terpenes", "valencene", "Valencene", 0.021, "0.021"),
            _r("terpenes", "terpinolene", "Terpinolene", None, "ND"),
            _r("terpenes", "ocimene", "Ocimene", None, "ND"),
        ],
    },
    "GMO": {
        "source_url": "https://opencoa.org/coa/019fb7fc-b04e-71e8-a5d5-a8dec420951e/gmo9763700",
        "source_state": "MA",
        "source_license_holder": "Turnbuckle Consulting Inc.",
        "product_name": "GMO Cookies Flower",
        "product_type": "Flower",
        "batch_number": "GMO9763700",
        "lab_name": "Kaycha MA, LLC",
        "lab_license_number": "IL281349",
        "lab_id": "NA60723004-004",
        "metrc_source_id": "1A40A0300007595000009770",
        "metrc_lab_id": "",
        "date_tested": "2026-07-27T00:00:00+00:00",
        "overall_status": "pass",
        "total_thc": 31.40,
        "total_cbd": 0.19,
        "total_cannabinoids": 37.75,
        "total_terpenes": 1.51,
        "results": [
            _r("cannabinoids", "thca", "THCA", 35.01, "35.01"),
            _r("cannabinoids", "cbga", "CBGA", 1.07, "1.07"),
            _r("cannabinoids", "delta_9_thc", "Delta-9 THC", 0.70, "0.70"),
            _r("cannabinoids", "thcva", "THCVA", 0.17, "0.17"),
            _r("cannabinoids", "cbda", "CBDA", 0.10, "0.10"),
            _r("cannabinoids", "cbd", "CBD", 0.10, "0.10"),
            _r("cannabinoids", "cbdv", "CBDV", 0.10, "0.10"),
            _r("cannabinoids", "cbc", "CBC", 0.10, "0.10"),
            _r("cannabinoids", "thcv", "THCV", 0.10, "0.10"),
            _r("cannabinoids", "delta_8_thc", "Delta-8 THC", 0.10, "0.10"),
            _r("cannabinoids", "cbg", "CBG", 0.10, "0.10"),
            _r("cannabinoids", "cbn", "CBN", 0.10, "0.10"),
            _r("terpenes", "limonene", "Limonene", 0.405, "0.405"),
            _r("terpenes", "beta_caryophyllene", "Beta-Caryophyllene", 0.342, "0.342"),
            _r("terpenes", "beta_myrcene", "Beta-Myrcene", 0.301, "0.301"),
            _r("terpenes", "alpha_humulene", "Alpha-Humulene", 0.141, "0.141"),
            _r("terpenes", "beta_pinene", "Beta-Pinene", 0.078, "0.078"),
            _r("terpenes", "bisabolol", "Alpha-Bisabolol", 0.059, "0.059"),
            _r("terpenes", "fenchol", "Fenchol", 0.046, "0.046"),
            _r("terpenes", "linalool", "Linalool", 0.046, "0.046"),
            _r("terpenes", "alpha_pinene", "Alpha-Pinene", 0.043, "0.043"),
            _r("terpenes", "alpha_terpineol", "Alpha-Terpineol", 0.028, "0.028"),
            _r("terpenes", "terpinolene", "Terpinolene", 0.021, "0.021"),
        ],
    },
    "Motorbreath": {
        "source_url": "https://opencoa.org/coa/019f4e7a-ef4d-7056-819a-4ae4461614fb/mobr250813-2-6a1",
        "source_state": "MA",
        "source_license_holder": "I.N.S.A., Inc.",
        "product_name": "Motorbreath 15",
        "product_type": "Flower",
        "batch_number": "MOBR250813-2-6A1",
        "lab_name": "Kaycha MA, LLC",
        "lab_license_number": "IL281349",
        "lab_id": "NA50902001-004",
        "metrc_source_id": "1A40A030000012E000101613",
        "metrc_lab_id": "",
        "date_tested": "2025-09-04T00:00:00+00:00",
        "overall_status": "pass",
        "total_thc": 27.73,
        "total_cbd": None,
        "total_cannabinoids": 32.68,
        "total_terpenes": 3.79,
        "results": [
            _r("cannabinoids", "thca", "THCA", 31.44, "31.44"),
            _r("cannabinoids", "cbga", "CBGA", 0.91, "0.91"),
            _r("cannabinoids", "thcva", "THCVA", 0.17, "0.17"),
            _r("cannabinoids", "delta_9_thc", "Delta-9 THC", 0.16, "0.16"),
            _r("terpenes", "beta_myrcene", "Beta-Myrcene", 1.482, "1.482"),
            _r("terpenes", "limonene", "Limonene", 0.780, "0.780"),
            _r("terpenes", "beta_caryophyllene", "Beta-Caryophyllene", 0.460, "0.460"),
            _r("terpenes", "linalool", "Linalool", 0.207, "0.207"),
            _r("terpenes", "alpha_humulene", "Alpha-Humulene", 0.175, "0.175"),
            _r("terpenes", "beta_pinene", "Beta-Pinene", 0.136, "0.136"),
            _r("terpenes", "fenchol", "Fenchol", 0.099, "0.099"),
            _r("terpenes", "bisabolol", "Alpha-Bisabolol", 0.083, "0.083"),
            _r("terpenes", "alpha_pinene", "Alpha-Pinene", 0.082, "0.082"),
            _r("terpenes", "alpha_terpineol", "Alpha-Terpineol", 0.074, "0.074"),
            _r("terpenes", "nerolidol", "Trans-Nerolidol", 0.050, "0.050"),
            _r("terpenes", "camphene", "Camphene", 0.035, "0.035"),
            _r("terpenes", "terpinolene", "Terpinolene", 0.027, "0.027"),
            _r("terpenes", "borneol", "Borneol", 0.026, "0.026"),
            _r("terpenes", "valencene", "Valencene", 0.025, "0.025"),
            _r("terpenes", "farnesene", "Farnesene", 0.022, "0.022"),
            _r("terpenes", "isoborneol", "Isoborneol", 0.022, "0.022"),
        ],
    },
    "Permanent Marker": {
        "source_url": "https://opencoa.org/coa/019f4e80-f041-73e0-8ce5-bfc5c72ae4c2/prm-f3-08062025-cd",
        "source_state": "MA",
        "source_license_holder": "Flower Power Growers, Inc.",
        "product_name": "Permanent Marker Bulk Flower",
        "product_type": "Flower",
        "batch_number": "PRM-F3-08062025-CD",
        "lab_name": "Kaycha MA, LLC",
        "lab_license_number": "IL281349",
        "lab_id": "NA50903005-010",
        "metrc_source_id": "1A40A030000D805000002352",
        "metrc_lab_id": "",
        "date_tested": "2025-09-06T00:00:00+00:00",
        "overall_status": "pass",
        "total_thc": 24.23,
        "total_cbd": None,
        "total_cannabinoids": 28.39,
        "total_terpenes": 4.20,
        "results": [
            _r("cannabinoids", "thca", "THCA", 26.73, "26.73"),
            _r("cannabinoids", "delta_9_thc", "Delta-9 THC", 0.79, "0.79"),
            _r("cannabinoids", "cbga", "CBGA", 0.72, "0.72"),
            _r("cannabinoids", "thcva", "THCVA", 0.15, "0.15"),
            _r("terpenes", "alpha_pinene", "Alpha-Pinene", 1.180, "1.180"),
            _r("terpenes", "beta_myrcene", "Beta-Myrcene", 1.159, "1.159"),
            _r("terpenes", "beta_pinene", "Beta-Pinene", 0.524, "0.524"),
            _r("terpenes", "limonene", "Limonene", 0.353, "0.353"),
            _r("terpenes", "beta_caryophyllene", "Beta-Caryophyllene", 0.277, "0.277"),
            _r("terpenes", "linalool", "Linalool", 0.158, "0.158"),
            _r("terpenes", "ocimene", "Ocimene", 0.136, "0.136"),
            _r("terpenes", "alpha_humulene", "Alpha-Humulene", 0.090, "0.090"),
            _r("terpenes", "fenchol", "Fenchol", 0.053, "0.053"),
            _r("terpenes", "alpha_terpineol", "Alpha-Terpineol", 0.049, "0.049"),
            _r("terpenes", "camphene", "Camphene", 0.038, "0.038"),
            _r("terpenes", "bisabolol", "Alpha-Bisabolol", 0.037, "0.037"),
            _r("terpenes", "valencene", "Valencene", 0.030, "0.030"),
            _r("terpenes", "terpinolene", "Terpinolene", 0.029, "0.029"),
            _r("terpenes", "farnesene", "Farnesene", 0.028, "0.028"),
            _r("terpenes", "sabinene_hydrate", "Sabinene Hydrate", 0.028, "0.028"),
            _r("terpenes", "nerolidol", "Trans-Nerolidol", 0.027, "0.027"),
        ],
    },
    "Wedding Cake": {
        "source_url": "https://opencoa.org/coa/019f4e61-aa11-72e0-a5de-ea8de2ad34eb/weca-f6h4-2025-08-04-ph",
        "source_state": "MA",
        "source_license_holder": "Salisbury Cultivation and Production Manufacturing, LLC",
        "product_name": "Wedding Cake Flower",
        "product_type": "Flower",
        "batch_number": "WECA-F6H4-2025.08.04-PH",
        "lab_name": "Kaycha MA, LLC",
        "lab_license_number": "IL281349",
        "lab_id": "NA50822003-002",
        "metrc_source_id": "1A40A0300008C3D000021801",
        "metrc_lab_id": "",
        "date_tested": "2025-08-22T00:00:00+00:00",
        "overall_status": "pass",
        "total_thc": 23.98,
        "total_cbd": None,
        "total_cannabinoids": 28.43,
        "total_terpenes": 2.52,
        "selection_note": (
            "Selected the Aug 22, 2025 Massachusetts record because its reported terpene analytes "
            "are internally coherent with Total Terpenes. A newer Jul 22, 2026 OpenCOA Wedding "
            "Cake record reports beta-caryophyllene 4.580% while Total Terpenes is 1.81%, so it "
            "is not used as the DEV reference fixture."
        ),
        "results": [
            _r("cannabinoids", "thca", "THCA", 27.18, "27.18"),
            _r("cannabinoids", "cbga", "CBGA", 1.11, "1.11"),
            _r("cannabinoids", "delta_9_thc", "Delta-9 THC", 0.14, "0.14"),
            _r("terpenes", "beta_caryophyllene", "Beta-Caryophyllene", 0.627, "0.627"),
            _r("terpenes", "beta_myrcene", "Beta-Myrcene", 0.429, "0.429"),
            _r("terpenes", "limonene", "Limonene", 0.419, "0.419"),
            _r("terpenes", "linalool", "Linalool", 0.312, "0.312"),
            _r("terpenes", "alpha_humulene", "Alpha-Humulene", 0.215, "0.215"),
            _r("terpenes", "beta_pinene", "Beta-Pinene", 0.095, "0.095"),
            _r("terpenes", "fenchol", "Fenchol", 0.061, "0.061"),
            _r("terpenes", "alpha_pinene", "Alpha-Pinene", 0.058, "0.058"),
            _r("terpenes", "terpinolene", "Terpinolene", 0.053, "0.053"),
            _r("terpenes", "alpha_terpineol", "Alpha-Terpineol", 0.050, "0.050"),
            _r("terpenes", "bisabolol", "Alpha-Bisabolol", 0.046, "0.046"),
            _r("terpenes", "nerolidol", "Trans-Nerolidol", 0.046, "0.046"),
            _r("terpenes", "farnesene", "Farnesene", 0.030, "0.030"),
            _r("terpenes", "camphene", "Camphene", 0.028, "0.028"),
            _r("terpenes", "valencene", "Valencene", 0.025, "0.025"),
            _r("terpenes", "guaiol", "Guaiol", 0.023, "0.023"),
        ],
    },
    "Super Lemon Haze": {
        "source_url": "https://app.alleaves.com/api/inventory/batch/pioneer/coa/16060.pdf",
        "source_pdf_url": "https://app.alleaves.com/api/inventory/batch/pioneer/coa/16060.pdf",
        "source_state": "MA",
        "source_license_holder": "Evergreen Industries LLC",
        "source_license_number": "MC 283694",
        "product_name": "M00004237437: Super Lemon Haze Flower",
        "product_type": "Flower",
        "batch_number": "Super Lemon Haze 11.30.2025 Harvest 03",
        "lab_batch_id": "B-8793",
        "lab_name": "G7 Lab LLC",
        "lab_license_number": "",
        "lab_id": "FL-8372",
        "metrc_source_id": "1A40A030000E741000000109",
        "metrc_lab_id": "1A40A030000E741000000118",
        "date_received": "2025-12-23T13:06:00+00:00",
        "date_tested": "2025-12-29T16:36:00+00:00",
        "overall_status": "pass",
        "specification": "FLOWER MA REC. (Lab)",
        "total_thc": 24.87,
        "total_cbd": 0.0,
        "total_cannabinoids": 29.55,
        "total_terpenes": 1.69,
        "safety_summary": {
            "pesticides": "pass",
            "mycotoxins": "pass",
            "microbiology": "pass",
            "heavy_metals": "pass",
        },
        "results": [
            _r("cannabinoids", "cbdva", "CBDVA", None, "<LOQ"),
            _r("cannabinoids", "cbdv", "CBDV", None, "<LOQ"),
            _r("cannabinoids", "cbda", "CBDA", None, "<LOQ"),
            _r("cannabinoids", "cbga", "CBGA", 0.82, "0.82"),
            _r("cannabinoids", "cbg", "CBG", 0.25, "0.25"),
            _r("cannabinoids", "cbd", "CBD", None, "<LOQ"),
            _r("cannabinoids", "thcv", "THCV", None, "<LOQ"),
            _r("cannabinoids", "thcva", "THCVA", 0.23, "0.23"),
            _r("cannabinoids", "cbn", "CBN", None, "<LOQ"),
            _r("cannabinoids", "cbna", "CBNA", None, "<LOQ"),
            _r("cannabinoids", "delta_9_thc", "Delta-9 THC", 0.76, "0.76"),
            _r("cannabinoids", "delta_8_thc", "Delta-8 THC", None, "<LOQ"),
            _r("cannabinoids", "cbl", "CBL", None, "<LOQ"),
            _r("cannabinoids", "cbc", "CBC", None, "<LOQ"),
            _r("cannabinoids", "thca", "THCA", 27.49, "27.49"),
            _r("cannabinoids", "cbca", "CBCA", None, "<LOQ"),
            _r("terpenes", "alpha_pinene", "Alpha-Pinene", 0.17, "0.17"),
            _r("terpenes", "camphene", "Camphene", 0.02, "0.02"),
            _r("terpenes", "beta_myrcene", "Beta-Myrcene", 0.07, "0.07"),
            _r("terpenes", "beta_pinene", "Beta-Pinene", 0.18, "0.18"),
            _r("terpenes", "delta_3_carene", "Delta-3-Carene", 0.05, "0.05"),
            _r("terpenes", "alpha_terpinene", "Alpha-Terpinene", 0.05, "0.05"),
            _r("terpenes", "alpha_ocimene", "Alpha-Ocimene", 0.01, "0.01"),
            _r("terpenes", "limonene", "D-Limonene", 0.21, "0.21"),
            _r("terpenes", "p_cymene", "p-Cymene", 0.01, "0.01"),
            _r("terpenes", "eucalyptol", "Eucalyptol", 0.02, "0.02"),
            _r("terpenes", "gamma_terpinene", "Gamma-Terpinene", 0.05, "0.05"),
            _r("terpenes", "terpinolene", "Terpinolene", 0.40, "0.40"),
            _r("terpenes", "linalool", "Linalool", 0.03, "0.03"),
            _r("terpenes", "isopulegol", "Isopulegol", None, "<LOQ"),
            _r("terpenes", "geraniol", "Geraniol", None, "<LOQ"),
            _r("terpenes", "beta_caryophyllene", "Beta-Caryophyllene", 0.17, "0.17"),
            _r("terpenes", "alpha_humulene", "Alpha-Humulene", 0.13, "0.13"),
            _r("terpenes", "nerolidol", "Nerolidol", 0.10, "0.10"),
            _r("terpenes", "guaiol", "Guaiol", None, "<LOQ"),
            _r("terpenes", "caryophyllene_oxide", "Caryophyllene Oxide", 0.01, "0.01"),
            _r("terpenes", "bisabolol", "Alpha-Bisabolol", 0.01, "0.01"),
        ],
    },
}

MA_FLOWER_REFERENCE_STRAINS = frozenset(MA_FLOWER_COA_FIXTURES)
EXPECTED_MA_FLOWER_REFERENCE_COAS = len(MA_FLOWER_COA_FIXTURES)


def _normalized_tag(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _metadata(lot: InventoryLot) -> dict[str, Any]:
    raw = str(lot.notes or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"legacy_note": raw}
    return parsed if isinstance(parsed, dict) else {"legacy_note": raw}


def _source_url(payload: dict[str, Any]) -> str:
    return str(payload.get("source_pdf_url") or payload.get("source_url") or "").strip()


def _top_value(results: list[dict[str, Any]], key: str) -> float | None:
    for row in results:
        if row.get("key") == key:
            value = row.get("value")
            return float(value) if value is not None else None
    return None


def seed_dev_ma_flower_reference_coa(
    engine: Engine,
    organization_id: str,
    facility_id: str,
    lot_id: str,
    *,
    strain: str,
    actor: str,
) -> CoaDocument | None:
    """Replace synthetic root QA with one source-provenanced MA flower fixture when available."""

    fixture = MA_FLOWER_COA_FIXTURES.get(strain)
    if fixture is None:
        return None

    with Session(engine) as session, session.begin():
        lot = session.get(InventoryLot, lot_id)
        if lot is None or lot.organization_id != organization_id or lot.facility_id != facility_id:
            raise ValueError("DEV MA COA fixture lot was not found in the active sandbox facility.")
        package_id = _normalized_tag(lot.compliance_package_id)
        if not package_id:
            raise ValueError("DEV MA COA fixture requires the current sandbox package tag.")

        raw = deepcopy(fixture)
        raw["source"] = "Massachusetts external COA reference fixture"
        raw["strain_name"] = strain
        raw["metrc_ids"] = [
            value for value in (raw.get("metrc_source_id"), raw.get("metrc_lab_id")) if value
        ]
        raw["sandbox_mapping"] = {
            "purpose": "DEV Sandbox Label Studio matching-strain fixture",
            "mapping_type": "strain_match_external_reference",
            "sandbox_lot_id": lot.id,
            "current_sandbox_package_id": lot.compliance_package_id,
            "source_tracking_id": raw.get("metrc_source_id") or "",
            "source_sample_metrc_tag": raw.get("metrc_lab_id") or "",
            "identity_rule": (
                "sandbox package remains current physical package identity; source COA identifiers "
                "remain external tested-material reference"
            ),
        }
        raw["normalization_schema"] = {
            "reference": "cannlytics/cannabis_results",
            "url": "https://huggingface.co/datasets/cannlytics/cannabis_results",
            "license": "CC BY 4.0",
        }
        payload = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
        fingerprint = sha256(payload).hexdigest()
        existing = session.scalar(
            select(CoaDocument).where(
                CoaDocument.organization_id == organization_id,
                CoaDocument.facility_id == facility_id,
                CoaDocument.fingerprint == fingerprint,
            )
        )
        if existing is not None:
            document = existing
        else:
            document = CoaDocument(
                organization_id=organization_id,
                facility_id=facility_id,
                lot_id=lot.id,
                package_id=package_id,
                source=DEV_MA_COA_SOURCE,
                status="parsed",
                verification_state="operator_confirmed",
                filename=f"dev-ma-{re.sub(r'[^a-z0-9]+', '-', strain.casefold()).strip('-')}.json",
                content_type="application/json",
                fingerprint=fingerprint,
                payload_compressed=zlib.compress(payload, level=9),
                payload_size=len(payload),
                parser_name="doobielogic-dev-ma-fixture",
                parser_version="1",
                product_name=str(raw.get("product_name") or ""),
                product_type=str(raw.get("product_type") or "Flower"),
                strain_name=strain,
                batch_number=str(raw.get("batch_number") or ""),
                lab_name=str(raw.get("lab_name") or ""),
                lab_license_number=str(raw.get("lab_license_number") or ""),
                lab_id=str(raw.get("lab_id") or ""),
                metrc_source_id=_normalized_tag(raw.get("metrc_source_id")),
                metrc_lab_id=_normalized_tag(raw.get("metrc_lab_id")),
                metrc_ids_json=json.dumps(raw["metrc_ids"]),
                date_tested=_date(raw.get("date_tested")),
                date_received=_date(raw.get("date_received")),
                overall_status=str(raw.get("overall_status") or "pass"),
                total_thc_percent=raw.get("total_thc"),
                total_cbd_percent=raw.get("total_cbd"),
                total_cannabinoids_percent=raw.get("total_cannabinoids"),
                total_terpenes_percent=raw.get("total_terpenes"),
                raw_payload_json=json.dumps(raw, sort_keys=True),
                imported_by=actor,
                verified_at=utc_now(),
            )
            session.add(document)
            session.flush()
            for position, result in enumerate(raw.get("results") or []):
                session.add(
                    CoaAnalyteResult(
                        coa_document_id=document.id,
                        organization_id=organization_id,
                        facility_id=facility_id,
                        analysis=str(result.get("analysis") or ""),
                        analyte_key=str(result.get("key") or ""),
                        name=str(result.get("name") or ""),
                        value=result.get("value"),
                        value_text=str(result.get("value_text") or ""),
                        units=str(result.get("units") or ""),
                        status=str(result.get("status") or ""),
                        sort_order=position,
                    )
                )

        LotQualityService.set_evidence(
            session,
            lot_id=lot.id,
            lab_testing_state="Passed",
            coa_reference=document.lab_id or document.batch_number or document.filename,
            coa_url=f"/api/v1/label-printing/coas/{document.id}/file",
            coa_document_id=document.id,
            thca_percent=_top_value(raw.get("results") or [], "thca"),
            tac_percent=document.total_cannabinoids_percent,
            total_thc_percent=document.total_thc_percent,
            total_cbd_percent=document.total_cbd_percent,
            total_cannabinoids_percent=document.total_cannabinoids_percent,
            total_terpenes_percent=document.total_terpenes_percent,
            evidence_source=DEV_MA_COA_EVIDENCE,
            actor=actor,
        )
        meta = _metadata(lot)
        meta["source_coa_url"] = _source_url(raw)
        meta["harvest_date"] = lot.received_at.date().isoformat() if lot.received_at else ""
        lot.notes = json.dumps(meta, sort_keys=True)
        session.flush()
        session.expunge(document)
        return document


def annotate_dev_flower_label_metadata(
    engine: Engine,
    organization_id: str,
    facility_id: str,
    root_lot_id: str,
    child_lot_ids: list[str] | tuple[str, ...],
) -> None:
    """Add deterministic DEV harvest/package dates and responsible-party fields to flower packages."""

    with Session(engine) as session, session.begin():
        facility = session.get(Facility, facility_id)
        root = session.get(InventoryLot, root_lot_id)
        if (
            facility is None
            or facility.organization_id != organization_id
            or root is None
            or root.organization_id != organization_id
            or root.facility_id != facility_id
        ):
            raise ValueError("DEV flower label metadata scope could not be resolved.")
        harvest_date = root.received_at.date().isoformat() if root.received_at else ""
        root_quality = LotQualityService.read(session, root.id)
        source_url = ""
        if root_quality and root_quality.coa_document_id:
            document = session.get(CoaDocument, root_quality.coa_document_id)
            if document is not None:
                try:
                    source_url = _source_url(json.loads(document.raw_payload_json or "{}"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    source_url = ""

        for lot_id in child_lot_ids:
            lot = session.get(InventoryLot, lot_id)
            if lot is None or lot.organization_id != organization_id or lot.facility_id != facility_id:
                raise ValueError("DEV flower child lot escaped the active sandbox scope.")
            meta = _metadata(lot)
            package_date = lot.received_at.date().isoformat() if lot.received_at else ""
            meta.update(
                {
                    "harvest_date": harvest_date,
                    "manufacture_date": package_date,
                    "package_date": package_date,
                    "cultivated_by": facility.name,
                    "cultivator_license": facility.license_number,
                    "packaged_by": facility.name,
                    "packager_license": facility.license_number,
                    "sold_by": facility.name,
                    "seller_license": facility.license_number,
                }
            )
            if source_url:
                meta["source_coa_url"] = source_url
            lot.notes = json.dumps(meta, sort_keys=True)
