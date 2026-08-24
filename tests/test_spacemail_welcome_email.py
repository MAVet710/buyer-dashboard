from backend.app.config import Settings
from backend.app.services import spacemail


class FakeSMTP:
    instances = []

    def __init__(self, host, port, *, timeout, context):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.login_args = None
        self.message = None
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.message = message


def _settings(**overrides):
    values = {
        "spacemail_smtp_password": "server-only-mailbox-password",
    }
    values.update(overrides)
    return Settings(**values)


def test_welcome_email_authenticates_primary_mailbox_and_sends_from_support_alias(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(spacemail.smtplib, "SMTP_SSL", FakeSMTP)
    settings = _settings()

    delivery = spacemail.send_welcome_email(
        settings,
        recipient="new.user@example.com",
        display_name="New User",
        username="new.user",
        temporary_password="Temporary!234",
    )

    assert delivery.sent is True
    assert delivery.recipient == "new.user@example.com"
    assert delivery.sender == "support@doobielogic.io"
    assert len(FakeSMTP.instances) == 1
    smtp = FakeSMTP.instances[0]
    assert smtp.host == "mail.spacemail.com"
    assert smtp.port == 465
    assert smtp.login_args == ("nelson@doobielogic.io", "server-only-mailbox-password")
    assert smtp.message["From"] == "DoobieLogic Support <support@doobielogic.io>"
    assert smtp.message["Reply-To"] == "support@doobielogic.io"
    assert smtp.message["To"] == "new.user@example.com"


def test_welcome_email_matches_doobielogic_brand_and_contains_login_credentials():
    message = spacemail.build_welcome_message(
        _settings(),
        recipient="new.user@example.com",
        display_name="New User",
        username="new.user",
        temporary_password="Temporary!234",
    )
    plain = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()

    assert "https://ops.doobielogic.io/" in plain
    assert "new.user" in plain
    assert "Temporary!234" in plain
    assert "required to change" in plain
    assert "#080b0d" in html
    assert "#ef7427" in html
    assert "Doobie" in html and "Logic" in html
    assert "support@doobielogic.io" in html
    assert "Temporary!234" in html


def test_welcome_email_escapes_html_credentials_and_names():
    message = spacemail.build_welcome_message(
        _settings(),
        recipient="new.user@example.com",
        display_name="<Admin & User>",
        username="user<one>",
        temporary_password="Temp<Pass>&123",
    )
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "&lt;Admin &amp; User&gt;" in html
    assert "user&lt;one&gt;" in html
    assert "Temp&lt;Pass&gt;&amp;123" in html


def test_welcome_email_fails_closed_without_server_password():
    settings = _settings(spacemail_smtp_password="")
    try:
        spacemail.send_welcome_email(
            settings,
            recipient="new.user@example.com",
            display_name="New User",
            username="new.user",
            temporary_password="Temporary!234",
        )
    except spacemail.SpacemailError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("welcome email must fail closed when SMTP is not configured")
