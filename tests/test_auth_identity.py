from services.auth_identity import resolve_legacy_identity


def test_god_resolves_to_dev_case_insensitively():
    identity = resolve_legacy_identity(
        "god",
        dev_users={"God": "hash"},
        admin_users={"Admin": "hash"},
        standard_users={},
        require_admin=True,
    )
    assert identity is not None
    assert identity.username == "God"
    assert identity.role == "dev"


def test_admin_and_standard_user_roles_remain_separate():
    admin = resolve_legacy_identity(
        "jwin",
        dev_users={},
        admin_users={"Jwin": "admin-hash"},
        standard_users={"Jwin": "user-hash"},
        require_admin=True,
    )
    user = resolve_legacy_identity(
        "jwin",
        dev_users={},
        admin_users={"Jwin": "admin-hash"},
        standard_users={"Jwin": "user-hash"},
        require_admin=False,
    )
    assert admin.role == "admin"
    assert admin.stored_value == "admin-hash"
    assert user.role == "buyer"
    assert user.stored_value == "user-hash"
