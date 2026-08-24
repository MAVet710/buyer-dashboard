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
