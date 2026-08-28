from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.cultivation.models import CultivationPlant


class CultivationMetrcReconciliationService:
    """Compare tagged DoobieLogic plants to read-only Metrc plant records.

    Metrc plant batches and harvests are intentionally not forced into the local
    individual-plant model. Only vegetative and flowering plant tags have a
    direct identity/phase comparison here. Batch and harvest resources remain
    visible as separate regulatory snapshot counts.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def reconcile(
        self,
        organization_id: str,
        facility_id: str,
        *,
        jurisdiction_code: str,
        license_number: str,
        environment: str,
        vegetative_records: list[dict[str, Any]],
        flowering_records: list[dict[str, Any]],
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        local_rows, immature_local, retired_local = self._local_rows(organization_id, facility_id)
        local_by_tag: dict[str, list[dict[str, Any]]] = {}
        for row in local_rows:
            key = _tag_key(row.get("plant_tag"))
            if key:
                local_by_tag.setdefault(key, []).append(row)

        metrc_by_tag: dict[str, list[dict[str, Any]]] = {}
        ignored_metrc = 0
        for phase, records in (("vegetative", vegetative_records), ("flowering", flowering_records)):
            for record in records:
                tag = _metrc_tag(record)
                key = _tag_key(tag)
                if not key:
                    ignored_metrc += 1
                    continue
                projected = dict(record)
                projected["operational_phase"] = phase
                metrc_by_tag.setdefault(key, []).append(projected)

        discrepancies: list[dict[str, Any]] = []
        matched = 0
        for key in sorted(set(local_by_tag) | set(metrc_by_tag)):
            local_matches = local_by_tag.get(key, [])
            metrc_matches = metrc_by_tag.get(key, [])
            display_tag = (
                str((local_matches[0] if local_matches else {}).get("plant_tag") or "")
                or _metrc_tag(metrc_matches[0] if metrc_matches else {})
                or key
            )
            if len(local_matches) > 1:
                discrepancies.append(_issue(
                    code="duplicate_local_plant_tag",
                    severity="high",
                    plant_tag=display_tag,
                    local=local_matches[0],
                    metrc=metrc_matches[0] if metrc_matches else None,
                    message=f"{len(local_matches)} DoobieLogic plants use the same traceability plant tag.",
                ))
                continue
            if len(metrc_matches) > 1:
                discrepancies.append(_issue(
                    code="duplicate_metrc_plant_tag",
                    severity="high",
                    plant_tag=display_tag,
                    local=local_matches[0] if local_matches else None,
                    metrc=metrc_matches[0],
                    message=f"{len(metrc_matches)} Metrc plant records resolved to the same plant tag.",
                ))
                continue

            local = local_matches[0] if local_matches else None
            metrc = metrc_matches[0] if metrc_matches else None
            if local is None and metrc is not None:
                discrepancies.append(_issue(
                    code="missing_in_doobielogic",
                    severity="high",
                    plant_tag=display_tag,
                    local=None,
                    metrc=metrc,
                    message="Metrc shows an active tagged plant that is not represented in this DoobieLogic cultivation facility.",
                ))
                continue
            if local is not None and metrc is None:
                discrepancies.append(_issue(
                    code="missing_in_metrc",
                    severity="high",
                    plant_tag=display_tag,
                    local=local,
                    metrc=None,
                    message="DoobieLogic shows an active tagged plant that was not returned by the matching Metrc plant reads.",
                ))
                continue
            if local is None or metrc is None:
                continue

            pair_issues = _compare_pair(display_tag, local, metrc)
            if pair_issues:
                discrepancies.extend(pair_issues)
            else:
                matched += 1

        severity_counts = {"high": 0, "medium": 0, "info": 0}
        code_counts: dict[str, int] = {}
        for row in discrepancies:
            severity = str(row.get("severity") or "info")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            code = str(row.get("code") or "unknown")
            code_counts[code] = code_counts.get(code, 0) + 1

        return {
            "provider": "metrc",
            "jurisdiction_code": jurisdiction_code,
            "license_number": license_number,
            "environment": environment,
            "read_only": True,
            "compared_at": datetime.now(timezone.utc).isoformat(),
            "evidence": evidence or {},
            "summary": {
                "status": "clean" if not discrepancies else "attention",
                "local_tagged_active_count": sum(len(rows) for rows in local_by_tag.values()),
                "metrc_tagged_active_count": sum(len(rows) for rows in metrc_by_tag.values()),
                "matched_plant_count": matched,
                "discrepancy_count": len(discrepancies),
                "high_count": severity_counts.get("high", 0),
                "medium_count": severity_counts.get("medium", 0),
                "info_count": severity_counts.get("info", 0),
                "local_immature_unreconciled_count": immature_local,
                "local_retired_count": retired_local,
                "ignored_metrc_record_count": ignored_metrc,
                "by_code": code_counts,
            },
            "discrepancies": discrepancies,
        }

    def _local_rows(self, organization_id: str, facility_id: str) -> tuple[list[dict[str, Any]], int, int]:
        statement = select(CultivationPlant).where(
            CultivationPlant.organization_id == organization_id,
            CultivationPlant.facility_id == facility_id,
        )
        with Session(self.engine) as session:
            plants = list(session.scalars(statement))

        active: list[dict[str, Any]] = []
        immature = 0
        retired = 0
        for plant in plants:
            if plant.phase in {"clone", "seedling"}:
                immature += 1
                continue
            if plant.phase in {"harvested", "destroyed"}:
                retired += 1
                continue
            active.append({
                "plant_id": plant.id,
                "plant_tag": plant.plant_tag,
                "strain_name": plant.strain_name,
                "phase": plant.phase,
                "room_code": plant.room_code,
                "mother_plant_tag": plant.mother_plant_tag,
            })
        return active, immature, retired


def _compare_pair(plant_tag: str, local: dict[str, Any], metrc: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    local_phase = _normalized(local.get("phase"))
    metrc_phase = _normalized(metrc.get("operational_phase"))
    if local_phase and metrc_phase and local_phase != metrc_phase:
        output.append(_issue(
            code="phase_mismatch",
            severity="high",
            plant_tag=plant_tag,
            local=local,
            metrc=metrc,
            message="DoobieLogic and Metrc report different active growth phases for this plant tag.",
        ))

    local_room = _normalized(local.get("room_code"))
    metrc_room = _normalized(_source_value(metrc, "LocationName", "RoomName", "Location"))
    if local_room and metrc_room and local_room != metrc_room:
        output.append(_issue(
            code="room_mismatch",
            severity="medium",
            plant_tag=plant_tag,
            local=local,
            metrc=metrc,
            message="DoobieLogic and Metrc report different plant rooms or locations.",
        ))

    local_strain = _normalized(local.get("strain_name"))
    metrc_strain = _normalized(metrc.get("name") or _source_value(metrc, "StrainName", "Strain"))
    if local_strain and metrc_strain and local_strain != metrc_strain:
        output.append(_issue(
            code="strain_mismatch",
            severity="medium",
            plant_tag=plant_tag,
            local=local,
            metrc=metrc,
            message="DoobieLogic and Metrc report different strain names for this plant tag.",
        ))
    return output


def _issue(
    *,
    code: str,
    severity: str,
    plant_tag: str,
    local: dict[str, Any] | None,
    metrc: dict[str, Any] | None,
    message: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "plant_tag": plant_tag,
        "local_plant_id": str((local or {}).get("plant_id") or ""),
        "local_phase": str((local or {}).get("phase") or ""),
        "metrc_phase": str((metrc or {}).get("operational_phase") or ""),
        "local_room": str((local or {}).get("room_code") or ""),
        "metrc_room": str(_source_value(metrc or {}, "LocationName", "RoomName", "Location") or ""),
        "local_strain": str((local or {}).get("strain_name") or ""),
        "metrc_strain": str((metrc or {}).get("name") or _source_value(metrc or {}, "StrainName", "Strain") or ""),
        "message": message,
    }


def _source_value(record: dict[str, Any], *keys: str) -> Any:
    source = record.get("source")
    if not isinstance(source, dict):
        source = {}
    for key in keys:
        value = source.get(key)
        if value is not None and str(value).strip():
            if isinstance(value, dict):
                return value.get("Name") or value.get("name") or ""
            return value
    return None


def _metrc_tag(record: dict[str, Any]) -> str:
    return str(record.get("label") or _source_value(record, "Label", "PlantLabel", "Tag") or "").strip()


def _tag_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").strip().upper())


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())
