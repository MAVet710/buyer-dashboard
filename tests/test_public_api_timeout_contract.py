from pathlib import Path


def test_public_post_has_a_bounded_request_timeout():
    source = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")
    assert "PUBLIC_POST_TIMEOUT_MS" in source
    assert "controller.abort()" in source
    assert "Storefront request timed out" in source
