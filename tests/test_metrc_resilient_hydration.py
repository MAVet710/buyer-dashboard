from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, Organization
from modules.integrations.hydration_checkpoints import IntegrationHydrationPageCheckpoint
from services.metrc_resilient_bootstrap import ResilientSnapshottingMetrcFacilityBootstrapService


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org-resume", name="Resume", slug="resume"))
        session.add(Facility(id="fac-resume", organization_id="org-resume", name="Resume Facility", code="RESUME"))
    return engine


def _service(engine):
    service = ResilientSnapshottingMetrcFacilityBootstrapService(engine)
    service._hydration_scope = {
        "organization_id": "org-resume",
        "facility_id": "fac-resume",
        "environment": "sandbox",
        "license_number": "MP281234",
    }
    return service


def _ok(page: int, total: int, value: str):
    return {
        "ok": True,
        "http_status": 200,
        "payload": {"Data": [{"Id": value}], "TotalPages": total},
        "records": [{"provider_id": value, "source": {"Id": value}}],
        "page": page,
    }


def _rows(result):
    return [dict(row) for row in result.get("records", [])]


def _total(result):
    return int((result.get("payload") or {}).get("TotalPages") or 1)


def test_interrupted_hydration_resumes_from_last_completed_page_after_anchor_validation():
    engine = _engine()
    first_service = _service(engine)
    calls: list[int] = []

    def first_read(page: int):
        calls.append(page)
        if page == 1:
            return _ok(1, 3, "A")
        if page == 2:
            return _ok(2, 3, "B")
        return {"ok": False, "http_status": 503, "status": "provider_error", "message": "temporary"}

    failed = first_service._read_paginated(
        resource_key="normalized:MP281234:packages_active",
        environment="sandbox",
        resume=None,
        read=first_read,
        rows=_rows,
        total_pages=_total,
    )
    assert failed["ok"] is False
    assert failed["checkpoint"]["status"] == "incomplete_resumable"
    assert failed["checkpoint"]["last_completed_page"] == 2
    assert failed["checkpoint"]["next_page"] == 3
    assert calls == [1, 2, 3]

    with Session(engine) as session:
        pages = list(session.scalars(select(IntegrationHydrationPageCheckpoint).order_by(IntegrationHydrationPageCheckpoint.page_number)))
        assert [row.page_number for row in pages] == [1, 2]

    second_service = _service(engine)
    resume = second_service.checkpoints.latest_incomplete(
        organization_id="org-resume",
        facility_id="fac-resume",
        provider="metrc",
        environment="sandbox",
        resource_key="normalized:MP281234:packages_active",
    )
    assert resume is not None
    assert resume["next_page"] == 3
    second_calls: list[int] = []

    def second_read(page: int):
        second_calls.append(page)
        if page == 1:
            return _ok(1, 3, "A")
        if page == 3:
            return _ok(3, 3, "C")
        raise AssertionError(f"checkpointed page {page} should not be re-read")

    completed = second_service._read_paginated(
        resource_key="normalized:MP281234:packages_active",
        environment="sandbox",
        resume=resume,
        read=second_read,
        rows=_rows,
        total_pages=_total,
    )
    assert completed["ok"] is True
    assert completed["truncated"] is False
    assert completed["checkpoint"]["resumed"] is True
    assert second_calls == [1, 3]
    assert [row["provider_id"] for row in completed["records"]] == ["A", "B", "C"]


def test_changed_page_one_anchor_discards_old_generation_and_restarts():
    engine = _engine()
    service = _service(engine)
    generation = service.checkpoints.new_generation()
    for page, value in ((1, "A"), (2, "B")):
        service.checkpoints.save_page(
            organization_id="org-resume",
            facility_id="fac-resume",
            provider="metrc",
            environment="sandbox",
            resource_key="normalized:MP281234:plants_flowering",
            generation_id=generation,
            page_number=page,
            total_pages=3,
            records=[{"provider_id": value, "source": {"Id": value}}],
        )
    resume = service.checkpoints.latest_incomplete(
        organization_id="org-resume",
        facility_id="fac-resume",
        provider="metrc",
        environment="sandbox",
        resource_key="normalized:MP281234:plants_flowering",
    )
    calls: list[int] = []

    def read(page: int):
        calls.append(page)
        return _ok(page, 3, {1: "A-CHANGED", 2: "B-NEW", 3: "C-NEW"}[page])

    result = service._read_paginated(
        resource_key="normalized:MP281234:plants_flowering",
        environment="sandbox",
        resume=resume,
        read=read,
        rows=_rows,
        total_pages=_total,
    )
    assert result["ok"] is True
    assert result["checkpoint"]["resumed"] is False
    assert calls == [1, 2, 3]
    assert [row["provider_id"] for row in result["records"]] == ["A-CHANGED", "B-NEW", "C-NEW"]
    assert result["checkpoint"]["generation_id"] != generation


def test_total_pages_change_fails_closed_instead_of_promoting_mixed_snapshot():
    engine = _engine()
    service = _service(engine)

    def read(page: int):
        if page == 1:
            return _ok(1, 3, "A")
        return _ok(page, 4, "B")

    result = service._read_paginated(
        resource_key="normalized:MP281234:harvests_active",
        environment="sandbox",
        resume=None,
        read=read,
        rows=_rows,
        total_pages=_total,
    )
    assert result["ok"] is False
    assert result["status"] == "snapshot_changed_during_hydration"
    assert result["checkpoint"]["status"] == "invalidated_provider_changed"
