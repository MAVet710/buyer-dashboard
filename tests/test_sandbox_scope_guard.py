from services.sandbox_scope_guard import (
    SANDBOX_SCOPE_MARKER,
    sandbox_demo_enabled_for_state,
)


def test_demo_bootstrap_requires_dev_role_and_verified_sandbox_scope():
    assert sandbox_demo_enabled_for_state(
        {"auth_user_role": "dev", SANDBOX_SCOPE_MARKER: True}
    ) is True

    assert sandbox_demo_enabled_for_state(
        {"auth_user_role": "dev", SANDBOX_SCOPE_MARKER: False}
    ) is False
    assert sandbox_demo_enabled_for_state(
        {"auth_user_role": "dev"}
    ) is False
    assert sandbox_demo_enabled_for_state(
        {"auth_user_role": "admin", SANDBOX_SCOPE_MARKER: True}
    ) is False
    assert sandbox_demo_enabled_for_state(
        {"auth_user_role": "buyer", SANDBOX_SCOPE_MARKER: True}
    ) is False
