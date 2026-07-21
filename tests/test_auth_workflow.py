from services.auth_workflow import (
    apply_authenticated_session,
    authenticate_any_role,
    clear_authenticated_session,
)


def test_authenticate_any_role_identifies_admin_and_standard_accounts():
    def authenticate(username, password, require_admin):
        if username == "God" and require_admin:
            return True, "God"
        if username == "operator" and not require_admin:
            return True, "operator"
        return False, ""
    assert authenticate_any_role(authenticate, "God", "secret") == (True, "God", True)
    assert authenticate_any_role(authenticate, "operator", "secret") == (True, "operator", False)


def test_auth_session_helpers_set_and_clear_identity_context():
    state = {"auth_user_role": "dev", "active_facility_id": "facility-1"}
    apply_authenticated_session(state, "God", True)
    assert state["is_admin"] is True
    assert state["admin_user"] == "God"
    clear_authenticated_session(state)
    assert state["is_admin"] is False
    assert state["admin_user"] is None
    assert state["auth_user_role"] is None
    assert state["active_facility_id"] is None
