from __future__ import annotations

from sqlalchemy import create_engine

from backend.app.config import Settings
from backend.app.routers import beta


class _FakeSMTP:
    sent_message = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def login(self, username, password):
        assert username == "nelson@doobielogic.io"
        assert password == "secret"

    def send_message(self, message):
        _FakeSMTP.sent_message = message
        return {}


def test_beta_application_routes_from_info_to_nelson(monkeypatch):
    monkeypatch.setattr(beta.smtplib, "SMTP_SSL", _FakeSMTP)
    settings = Settings(
        spacemail_smtp_username="nelson@doobielogic.io",
        spacemail_smtp_password="secret",
        spacemail_from_email="support@doobielogic.io",
        spacemail_info_email="info@doobielogic.io",
    )
    payload = beta.BetaApplication(
        name="Test Operator",
        email="operator@example.com",
        company="Test Cannabis Co",
        role="Operations Manager",
        operation="Vertically Integrated",
        facilities="2–3",
        stack="Dutchie",
        state="MA",
        pain="We need better operational visibility across facilities.",
        must_have="One place to see inventory, production, and compliance.",
        consent=True,
    )

    result = beta.submit_beta_application(
        payload,
        engine=create_engine("sqlite+pysqlite:///:memory:", future=True),
        settings=settings,
    )

    message = _FakeSMTP.sent_message
    assert result == {"accepted": True}
    assert message is not None
    assert message["From"] == "DoobieLogic Beta <info@doobielogic.io>"
    assert message["To"] == "nelson@doobielogic.io"
    assert message["Reply-To"] == "operator@example.com"
    assert "Test Cannabis Co" in message["Subject"]
