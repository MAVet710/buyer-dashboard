from types import SimpleNamespace

import pytest

from backend.scripts.migrate_legacy_metrc import (
    DurableUser,
    FacilityAssignment,
    FacilityCandidate,
    LegacyMetrcRecord,
    MetrcMigrationPlan,
    _parse_facility_maps,
    _print_preflight,
    _resolve_facility,
    _summary,
)


def _user(**overrides):
    values = {
        "user_id": "user-1",
        "normalized_username": "legacyuser",
        "role": "buyer",
        "organization_id": "org-1",
    }
    values.update(overrides)
    return DurableUser(**values)


def _facility(facility_id: str, organization_id: str = "org-1", license_number: str = ""):
    return FacilityCandidate(
        facility_id=facility_id,
        organization_id=organization_id,
        license_number=license_number,
    )


def test_single_authorized_facility_is_resolved_without_guessing():
    facility = _resolve_facility(
        user=_user(),
        legacy_license="",
        facilities=[_facility("facility-1"), _facility("sandbox", "org-sandbox")],
        assignments=[],
        default_organization_id="org-sandbox",
    )
    assert facility is not None
    assert facility.facility_id == "facility-1"


def test_multiple_facilities_require_license_match_or_explicit_map():
    facilities = [
        _facility("retail", license_number="MR123"),
        _facility("production", license_number="MP456"),
    ]
    assignments = [
        FacilityAssignment(user_id="user-1", facility_id="retail"),
        FacilityAssignment(user_id="user-1", facility_id="production"),
    ]

    assert _resolve_facility(
        user=_user(),
        legacy_license="",
        facilities=facilities,
        assignments=assignments,
        default_organization_id="org-sandbox",
    ) is None

    matched = _resolve_facility(
        user=_user(),
        legacy_license="MP456",
        facilities=facilities,
        assignments=assignments,
        default_organization_id="org-sandbox",
    )
    assert matched is not None
    assert matched.facility_id == "production"


def test_explicit_map_cannot_escape_users_authorized_facilities():
    with pytest.raises(RuntimeError, match="outside the user's authorized"):
        _resolve_facility(
            user=_user(),
            legacy_license="",
            facilities=[_facility("facility-1"), _facility("other-org", "org-2")],
            assignments=[],
            default_organization_id="org-sandbox",
            explicit_facility_id="other-org",
        )


def test_dev_without_org_uses_same_default_org_rule_as_auth_migration():
    facility = _resolve_facility(
        user=_user(role="dev", organization_id=""),
        legacy_license="",
        facilities=[
            _facility("sandbox", "org-sandbox"),
            _facility("retail", "org-retail"),
        ],
        assignments=[],
        default_organization_id="org-sandbox",
    )
    assert facility is not None
    assert facility.facility_id == "sandbox"


def test_facility_map_parser_normalizes_usernames_and_rejects_conflicts():
    assert _parse_facility_maps([" LegacyUser =facility-1"]) == {"legacyuser": "facility-1"}
    with pytest.raises(RuntimeError, match="two different facilities"):
        _parse_facility_maps(["legacyuser=facility-1", "LEGACYUSER=facility-2"])


def test_legacy_record_requires_all_three_metrc_fields_for_execution():
    unconfigured = LegacyMetrcRecord("legacyuser", "", "", "")
    partial = LegacyMetrcRecord("legacyuser", "MA", "MR123", "")
    complete = LegacyMetrcRecord("legacyuser", "MA", "MR123", "secret")

    assert unconfigured.configured is False
    assert unconfigured.complete is False
    assert partial.configured is True
    assert partial.complete is False
    assert complete.complete is True


def test_preflight_output_is_aggregate_and_never_logs_identity_license_or_secret(capsys):
    plans = [
        MetrcMigrationPlan(
            action="create",
            user_id="private-user-id",
            organization_id="private-org-id",
            facility_id="private-facility-id",
            state="MA",
            license_number="MR-PRIVATE-LICENSE",
            api_key="super-secret-api-key",
        ),
        MetrcMigrationPlan(action="ambiguous"),
    ]

    _print_preflight(plans, execute=False, global_metrc_present=True)
    output = capsys.readouterr().out

    assert "records=2" in output
    assert "create=1" in output
    assert "ambiguous=1" in output
    assert "manual_reconciliation_required" in output
    assert "private-user-id" not in output
    assert "MR-PRIVATE-LICENSE" not in output
    assert "super-secret-api-key" not in output


def test_summary_separates_safe_idempotent_and_blocking_states():
    counts = _summary(
        [
            MetrcMigrationPlan(action="create"),
            MetrcMigrationPlan(action="already_migrated"),
            MetrcMigrationPlan(action="skip_unconfigured"),
            MetrcMigrationPlan(action="conflict"),
            MetrcMigrationPlan(action="incomplete"),
            MetrcMigrationPlan(action="orphan"),
        ]
    )
    assert counts["create"] == 1
    assert counts["already_migrated"] == 1
    assert counts["skip_unconfigured"] == 1
    assert counts["conflict"] == 1
    assert counts["incomplete"] == 1
    assert counts["orphan"] == 1
