from pathlib import Path

from backend.app.routers.admin_user_create import UserCreate, router as admin_user_create_router


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


def test_create_user_router_exposes_literal_post_route():
    assert any(
        getattr(route, "path", "") == "/admin/users/create"
        and "POST" in (getattr(route, "methods", set()) or set())
        for route in admin_user_create_router.routes
    )


def test_create_user_router_is_registered_before_dynamic_admin_router():
    # Starlette resolves matching routes in registration order. Keep the literal
    # create endpoint ahead of /admin/users/{user_id} so "create" can never be
    # interpreted as a user ID again. Check the composition source directly so
    # this remains stable even when tests customize API_PREFIX/app construction.
    source = Path("backend/app/main.py").read_text(encoding="utf-8")
    create_registration = 'app.include_router(admin_user_create_router, prefix=settings.api_prefix)'
    dynamic_registration = 'app.include_router(admin_router, prefix=settings.api_prefix)'

    assert create_registration in source
    assert dynamic_registration in source
    assert source.index(create_registration) < source.index(dynamic_registration)
