from types import SimpleNamespace

import pytest

from backend.scripts.migrate_legacy_auth import UserMigrationPlan, _plan_user, _print_preflight


def _user(**overrides):
    values = {
        "id": "11111111-1111-4111-8111-111111111111",
        "username": "LegacyUser",
        "normalized_username": "legacyuser",
        "display_name": "Legacy User",
        "email": "",
        "password_hash": "$2b$12$abcdefghijklmnopqrstuv012345678901234567890123456789",
        "role": "buyer",
        "organization_id": "org-retail",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _facility(facility_id: str, organization_id: str):
    return SimpleNamespace(id=facility_id, organization_id=organization_id, active=True)


def test_dev_without_org_bootstraps_to_default_facility_without_grant_rows():
    plan = _plan_user(
        _user(role="dev", organization_id=""),
        default_organization_id="dev-sandbox",
        assignment=None,
        active_facilities=[
            _facility("sandbox-facility", "dev-sandbox"),
            _facility("retail-facility", "org-retail"),
        ],
        existing_auth_id=None,
    )

    assert plan.organization_id == "dev-sandbox"
    assert plan.facility_id == "sandbox-facility"
    assert plan.facility_role_ids == ()
    assert plan.email == "legacyuser@users.doobielogic.io"


def test_org_scoped_buyer_without_assignment_gets_only_org_facilities():
    plan = _plan_user(
        _user(role="buyer", organization_id="org-retail"),
        default_organization_id="dev-sandbox",
        assignment=None,
        active_facilities=[
            _facility("sandbox-facility", "dev-sandbox"),
            _facility("retail-a", "org-retail"),
            _facility("retail-b", "org-retail"),
        ],
        existing_auth_id=None,
    )

    assert plan.organization_id == "org-retail"
    assert plan.facility_id == "retail-a"
    assert plan.facility_role_ids == ("retail-a", "retail-b")


def test_existing_assignment_remains_the_default_facility():
    assignment = SimpleNamespace(facility_id="retail-b")
    plan = _plan_user(
        _user(role="operator", organization_id="org-retail"),
        default_organization_id="dev-sandbox",
        assignment=assignment,
        active_facilities=[
            _facility("retail-a", "org-retail"),
            _facility("retail-b", "org-retail"),
        ],
        existing_auth_id="11111111-1111-4111-8111-111111111111",
    )

    assert plan.facility_id == "retail-b"
    assert plan.facility_role_ids == ()
    assert plan.existing_auth_id is not None


def test_nonportable_password_hash_blocks_preflight():
    with pytest.raises(RuntimeError, match="portable bcrypt"):
        _plan_user(
            _user(password_hash="not-bcrypt"),
            default_organization_id="dev-sandbox",
            assignment=None,
            active_facilities=[_facility("retail-a", "org-retail")],
            existing_auth_id=None,
        )


def test_preflight_output_is_aggregate_and_does_not_log_usernames_or_hashes(capsys):
    plan = UserMigrationPlan(
        user_id="11111111-1111-4111-8111-111111111111",
        username="SensitiveUsername",
        role="buyer",
        organization_id="org-retail",
        facility_id="retail-a",
        facility_role_ids=("retail-a",),
        email="sensitiveusername@users.doobielogic.io",
        display_name="Sensitive Name",
        password_hash="$2b$12$secretmaterial",
        existing_auth_id=None,
    )

    _print_preflight([plan], dry_run=True)
    output = capsys.readouterr().out

    assert "users=1" in output
    assert "create=1" in output
    assert "facility_roles_to_add=1" in output
    assert "SensitiveUsername" not in output
    assert "secretmaterial" not in output
