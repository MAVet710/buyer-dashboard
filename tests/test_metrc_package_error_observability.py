from __future__ import annotations

from pathlib import Path

from backend.app.services.metrc_package_eval_resume import _provider_error_summary


ROOT = Path(__file__).resolve().parents[1]


class _Response:
    def __init__(self, payload=None, *, text: str = ""):
        self._payload = payload
        self.text = text
        self.content = b"body" if payload is not None or text else b""

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def test_provider_error_summary_keeps_reason_and_redacts_exact_secrets() -> None:
    secret = "do-not-log-this-value"
    response = _Response({"Message": f"Request origin is not permitted for {secret}."})

    summary = _provider_error_summary(response, (secret, ""))

    assert "Request origin is not permitted" in summary
    assert secret not in summary
    assert "[REDACTED]" in summary
    assert len(summary) <= 500


def test_provider_error_summary_falls_back_to_bounded_text() -> None:
    response = _Response(text="provider rejected request " + ("x" * 1000))

    summary = _provider_error_summary(response, ())

    assert summary.startswith("provider rejected request")
    assert len(summary) == 500


def test_package_provider_get_preserves_sanitized_non_200_reason_without_retry_contract() -> None:
    source = (ROOT / "backend/app/services/metrc_package_eval_resume.py").read_text(encoding="utf-8")

    assert "detail = _provider_error_summary(" in source
    assert 'raise MetrcPackageResumeError(f"Read {path} returned HTTP {response.status_code}.{suffix}")' in source
    assert "requests.get(self.origin + \"/\" + path" in source
    provider_source = source[source.index("class _Provider:"):source.index("def _alternate_item")].casefold()
    assert "retry" not in provider_source
