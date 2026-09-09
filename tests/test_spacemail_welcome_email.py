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
        return {}


class FakeIMAP:
    instances = []

    def __init__(self, host, port, *, ssl_context, timeout):
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.timeout = timeout
        self.login_args = None
        self.append_args = None
        self.logged_out = False
        self.__class__.instances.append(self)

    def login(self, username, password):
        self.login_args = (username, password)
        return "OK", [b"authenticated"]

    def list(self):
        return "OK", [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren \\Sent) "/" "Sent"',
        ]

    def append(self, mailbox, flags, date_time, message):
        self.append_args = (mailbox, flags, date_time, message)
        return "OK", [b"append completed"]

    def logout(self):
        self.logged_out = True
        return "BYE", [b"logout"]


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


def _settings(**overrides):
    values = {
        "spacemail_smtp_password": "server-only-mailbox-password",
    }
    values.update(overrides)
    return Settings(**values)


def test_welcome_email_authenticates_primary_mailbox_sends_alias_and_archives_sent_copy(monkeypatch):
    FakeSMTP.instances.clear()
    FakeIMAP.instances.clear()
    monkeypatch.setattr(spacemail.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(spacemail.imaplib, "IMAP4_SSL", FakeIMAP)
    settings = _settings()

    delivery = spacemail.send_welcome_email(
        settings,
        recipient="new.user@example.com",
        display_name="New User",
        username="new.user",
        temporary_password="Temporary!234",
    )

    assert delivery.sent is True
    assert delivery.sent_copy_saved is True
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
    assert smtp.message["Date"]
    assert smtp.message["Message-ID"].endswith("@doobielogic.io>")

    assert len(FakeIMAP.instances) == 1
    imap = FakeIMAP.instances[0]
    assert imap.host == "mail.spacemail.com"
    assert imap.port == 993
    assert imap.login_args == ("nelson@doobielogic.io", "server-only-mailbox-password")
    assert imap.append_args is not None
    assert imap.append_args[0] == "Sent"
    assert imap.append_args[1] == r"(\Seen)"
    assert b"Welcome to DoobieLogic" in imap.append_args[3]
    assert imap.logged_out is True


def test_render_compatible_resend_https_transport_does_not_require_smtp(monkeypatch):
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        return FakeResponse(200)

    monkeypatch.setattr(spacemail.requests, "post", fake_post)
    settings = _settings(
        resend_api_key="server-only-resend-key",
        spacemail_smtp_password="",
    )

    delivery = spacemail.send_welcome_email(
        settings,
        recipient="new.user@example.com",
        display_name="New User",
        username="new.user",
        temporary_password="Temporary!234",
    )

    assert delivery.sent is True
    assert delivery.sent_copy_saved is False
    assert delivery.recipient == "new.user@example.com"
    assert len(calls) == 1
    url, headers, payload, timeout = calls[0]
    assert url == "https://api.resend.com/emails"
    assert headers["Authorization"] == "Bearer server-only-resend-key"
    assert payload["from"] == "DoobieLogic Support <support@doobielogic.io>"
    assert payload["to"] == ["new.user@example.com"]
    assert payload["reply_to"] == ["support@doobielogic.io"]
    assert "Welcome to DoobieLogic" in payload["subject"]
    assert "Temporary!234" in payload["text"]
    assert "Temporary!234" in payload["html"]
    assert timeout == 12.0


def test_resend_provider_failure_is_generic_and_does_not_echo_provider_body(monkeypatch):
    def fake_post(*args, **kwargs):
        return FakeResponse(403)

    monkeypatch.setattr(spacemail.requests, "post", fake_post)
    settings = _settings(resend_api_key="server-only-resend-key", spacemail_smtp_password="")

    try:
        spacemail.send_welcome_email(
            settings,
            recipient="new.user@example.com",
            display_name="New User",
            username="new.user",
            temporary_password="Temporary!234",
        )
    except spacemail.SpacemailError as exc:
        assert str(exc) == "Transactional email provider rejected the message."
        assert "server-only-resend-key" not in str(exc)
    else:
        raise AssertionError("provider rejection must fail closed")


def test_welcome_email_delivery_survives_sent_copy_archive_failure(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(spacemail.smtplib, "SMTP_SSL", FakeSMTP)

    def broken_imap(*args, **kwargs):
        raise OSError("imap unavailable")

    monkeypatch.setattr(spacemail.imaplib, "IMAP4_SSL", broken_imap)
    delivery = spacemail.send_welcome_email(
        _settings(),
        recipient="new.user@example.com",
        display_name="New User",
        username="new.user",
        temporary_password="Temporary!234",
    )

    assert delivery.sent is True
    assert delivery.sent_copy_saved is False


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


def test_welcome_email_fails_closed_without_any_server_transport():
    settings = _settings(spacemail_smtp_password="", resend_api_key="")
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
        raise AssertionError("welcome email must fail closed when no server mail transport is configured")
