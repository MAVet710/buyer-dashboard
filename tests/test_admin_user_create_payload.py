from backend.app.main import app
from backend.app.routers.admin_user_create import UserCreate


def test_create_user_accepts_optional_nulls_from_refreshing_web_context():
    payload = UserCreate.model_validate(
        {
            "username": "  New.Operator  ",
            "display_name": None,
            "email": None,
            "password": "temporary-password-123",
            "role": " BUYER ",
            "organization_id": "  org-123  ",
            "facility_ids": [" facility-a ", None, "", "facility-b"],
            "must_change_password": True,
        }
    )

    assert payload.username == "New.Operator"
    assert payload.display_name == ""
    assert payload.email == ""
    assert payload.role == "buyer"
    assert payload.organization_id == "org-123"
    assert payload.facility_ids == ["facility-a", "facility-b"]


def test_create_user_accepts_single_facility_id_and_normalizes_it():
    payload = UserCreate.model_validate(
        {
            "username": "operator.one",
            "password": "temporary-password-123",
            "facility_ids": "facility-a",
        }
    )

    assert payload.facility_ids == ["facility-a"]


def test_create_user_literal_post_route_precedes_dynamic_user_update_route():
    create_index = next(
        index
        for index, route in enumerate(app.routes)
        if getattr(route, "path", "") == "/api/v1/admin/users/create"
        and "POST" in (getattr(route, "methods", set()) or set())
    )
    dynamic_index = next(
        index
        for index, route in enumerate(app.routes)
        if getattr(route, "path", "") == "/api/v1/admin/users/{user_id}"
        and "POST" in (getattr(route, "methods", set()) or set())
    )

    assert create_index < dynamic_index
