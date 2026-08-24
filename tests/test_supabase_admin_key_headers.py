from backend.app.config import Settings
from backend.app.routers.admin_user_create import _service_headers


def test_modern_supabase_secret_key_is_not_sent_as_bearer_token():
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="sb_secret_backend_test",
    )

    headers = _service_headers(settings)

    assert headers["apikey"] == "sb_secret_backend_test"
    assert "Authorization" not in headers
    assert headers["Content-Type"] == "application/json"


def test_legacy_service_role_jwt_keeps_bearer_header():
    legacy_key = "eyJhbGciOiJIUzI1NiJ9.service-role.signature"
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key=legacy_key,
    )

    headers = _service_headers(settings)

    assert headers["apikey"] == legacy_key
    assert headers["Authorization"] == f"Bearer {legacy_key}"


def test_publishable_key_cannot_be_used_for_admin_user_creation():
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="sb_publishable_browser_test",
    )

    try:
        _service_headers(settings)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
        assert "server secret key" in str(getattr(exc, "detail", ""))
    else:
        raise AssertionError("Publishable keys must never authorize admin user creation")
