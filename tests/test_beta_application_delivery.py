from __future__ import annotations

from sqlalchemy import create_engine

from backend.app.config import Settings
from backend.app.routers import beta


def test_beta_application_routes_from_info_to_nelson_through_shared_transport(monkeypatch):
    captured = {}

    def fake_send(settings, message):
        captured["settings"] = settings
        captured["message"] = message
        return "resend"

    monkeypatch.setattr(beta, "send_transactional_message", fake_send)
    settings = Settings(
        resend_api_key="server-only-resend-key",
        spacemail_smtp_password="",
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

    message = captured["message"]
    assert result == {"accepted": True}
    assert captured["settings"].resend_api_key == "server-only-resend-key"
    assert message["From"] == "DoobieLogic Beta <info@doobielogic.io>"
    assert message["To"] == "nelson@doobielogic.io"
    assert message["Reply-To"] == "operator@example.com"
    assert "Test Cannabis Co" in message["Subject"]
    assert "We need better operational visibility" in message.get_content()
