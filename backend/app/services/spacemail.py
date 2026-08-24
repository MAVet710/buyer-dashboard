from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
import smtplib
import ssl

from sqlalchemy import Engine

from modules.integrations import IntegrationConfigurationService
from ..config import Settings


class SpacemailError(RuntimeError):
    """Raised when DoobieLogic cannot deliver a transactional email."""


@dataclass(frozen=True)
class WelcomeEmailDelivery:
    sent: bool
    recipient: str
    sender: str


def resolve_spacemail_settings(engine: Engine, settings: Settings) -> Settings:
    """Resolve platform Spacemail settings without exposing the mailbox password.

    A deployment-level secret takes precedence. If no environment secret is
    present, Level DEV can store the mailbox password in DoobieLogic's encrypted
    integration credential store and the runtime decrypts it only for the SMTP
    connection.
    """

    if settings.spacemail_smtp_password:
        return settings
    try:
        service = IntegrationConfigurationService(engine, settings.integration_encryption_key)
        row = service.get("platform", "global", "spacemail")
    except RuntimeError:
        return settings
    if not row:
        return settings
    configuration = service.public(row)["configuration"]
    secret = service.secret(row)
    if not secret:
        return settings
    return settings.model_copy(
        update={
            "spacemail_smtp_password": secret,
            "spacemail_smtp_username": str(configuration.get("smtp_username") or settings.spacemail_smtp_username),
            "spacemail_from_email": str(configuration.get("from_email") or settings.spacemail_from_email),
            "spacemail_from_name": str(configuration.get("from_name") or settings.spacemail_from_name),
            "spacemail_support_email": str(configuration.get("support_email") or settings.spacemail_support_email),
            "spacemail_help_email": str(configuration.get("help_email") or settings.spacemail_help_email),
            "spacemail_info_email": str(configuration.get("info_email") or settings.spacemail_info_email),
            "spacemail_welcome_email_enabled": bool(configuration.get("welcome_email_enabled", settings.spacemail_welcome_email_enabled)),
        }
    )


def _welcome_plain_text(
    *,
    display_name: str,
    username: str,
    temporary_password: str,
    login_url: str,
    support_email: str,
) -> str:
    greeting = display_name.strip() or username
    return f"""Welcome to DoobieLogic, {greeting}.

Your DoobieLogic account is ready.

Login: {login_url}
Username: {username}
Temporary password: {temporary_password}

You will be required to change this temporary password after signing in.

For account or technical support, contact {support_email}.

DoobieLogic
Cannabis Operations Intelligence
Semper Paratus • Powered by Good Weed and Data
"""


def _welcome_html(
    *,
    display_name: str,
    username: str,
    temporary_password: str,
    login_url: str,
    support_email: str,
) -> str:
    greeting = escape(display_name.strip() or username)
    safe_username = escape(username)
    safe_password = escape(temporary_password)
    safe_login_url = escape(login_url, quote=True)
    safe_support = escape(support_email)
    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#080b0d;color:#f7f3ed;font-family:Arial,Helvetica,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">Your DoobieLogic account is ready.</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;background:#080b0d;padding:28px 12px;">
      <tr><td align="center">
        <table role="presentation" width="620" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:620px;border:1px solid #523018;border-radius:16px;background:#0d1011;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.45);">
          <tr>
            <td style="padding:24px 28px;border-bottom:1px solid #242220;background:#0a0c0d;">
              <div style="font-family:Georgia,'Times New Roman',serif;font-size:29px;font-weight:700;letter-spacing:-1px;line-height:1;">
                <span style="color:#f7f3ed;">Doobie</span><span style="color:#ef7427;">Logic</span>
              </div>
              <div style="margin-top:7px;color:#8e8882;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;">Cannabis Operations Intelligence</div>
            </td>
          </tr>
          <tr>
            <td style="padding:34px 28px 14px;">
              <div style="color:#ef7427;font-size:10px;font-weight:800;letter-spacing:1.8px;text-transform:uppercase;">Account ready</div>
              <h1 style="margin:10px 0 12px;color:#f7f3ed;font-size:28px;line-height:1.15;letter-spacing:-.7px;">Welcome to DoobieLogic, {greeting}.</h1>
              <p style="margin:0;color:#aaa6a0;font-size:15px;line-height:1.65;">Your account has been created and assigned to your organization. Use the temporary credentials below to sign in.</p>
            </td>
          </tr>
          <tr>
            <td style="padding:10px 28px 22px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;border:1px solid #30302f;border-radius:10px;background:#111415;">
                <tr><td style="padding:18px 20px 9px;color:#88827c;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Username</td></tr>
                <tr><td style="padding:0 20px 15px;color:#f1eee9;font-family:Consolas,Menlo,monospace;font-size:16px;font-weight:700;word-break:break-word;">{safe_username}</td></tr>
                <tr><td style="padding:12px 20px 9px;border-top:1px solid #292b2b;color:#88827c;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Temporary password</td></tr>
                <tr><td style="padding:0 20px 18px;color:#ef9b5d;font-family:Consolas,Menlo,monospace;font-size:16px;font-weight:700;word-break:break-all;">{safe_password}</td></tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:0 28px 22px;">
              <a href="{safe_login_url}" style="display:inline-block;padding:13px 22px;border:1px solid #ef7427;border-radius:7px;background:linear-gradient(180deg,#f2833f,#d85d17);color:#ffffff;text-decoration:none;font-size:14px;font-weight:800;">Open DoobieLogic</a>
            </td>
          </tr>
          <tr>
            <td style="padding:0 28px 28px;">
              <div style="padding:14px 16px;border-left:3px solid #ef7427;background:#1b1713;color:#cfc8c1;font-size:13px;line-height:1.55;">For security, you will be required to change this temporary password after your first sign-in.</div>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 28px;border-top:1px solid #242220;background:#090b0c;color:#817b75;font-size:12px;line-height:1.55;">
              Need help? Email <a href="mailto:{safe_support}" style="color:#ef7427;text-decoration:none;">{safe_support}</a>.<br/>
              <span style="color:#5f5b57;">DoobieLogic • Semper Paratus • Powered by Good Weed and Data</span>
            </td>
          </tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def build_welcome_message(
    settings: Settings,
    *,
    recipient: str,
    display_name: str,
    username: str,
    temporary_password: str,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = "Welcome to DoobieLogic — your account is ready"
    message["From"] = formataddr((settings.spacemail_from_name, settings.spacemail_from_email))
    message["To"] = recipient
    message["Reply-To"] = settings.spacemail_support_email
    message["X-Auto-Response-Suppress"] = "All"
    message.set_content(
        _welcome_plain_text(
            display_name=display_name,
            username=username,
            temporary_password=temporary_password,
            login_url=settings.spacemail_login_url,
            support_email=settings.spacemail_support_email,
        )
    )
    message.add_alternative(
        _welcome_html(
            display_name=display_name,
            username=username,
            temporary_password=temporary_password,
            login_url=settings.spacemail_login_url,
            support_email=settings.spacemail_support_email,
        ),
        subtype="html",
    )
    return message


def _smtp_login(settings: Settings):
    context = ssl.create_default_context()
    return smtplib.SMTP_SSL(
        settings.spacemail_smtp_host,
        settings.spacemail_smtp_port,
        timeout=settings.spacemail_smtp_timeout_seconds,
        context=context,
    )


def test_spacemail_connection(settings: Settings) -> dict[str, object]:
    if not settings.spacemail_is_configured:
        return {"ok": False, "message": "Spacemail SMTP credentials are not configured."}
    try:
        with _smtp_login(settings) as smtp:
            smtp.login(settings.spacemail_smtp_username, settings.spacemail_smtp_password)
            code, _ = smtp.noop()
        ok = 200 <= int(code) < 400
        return {"ok": ok, "message": "Spacemail SMTP authentication succeeded." if ok else f"Spacemail SMTP returned status {code}."}
    except (smtplib.SMTPException, OSError, TimeoutError) as exc:
        return {"ok": False, "message": f"Spacemail SMTP connection failed: {exc.__class__.__name__}."}


def send_welcome_email(
    settings: Settings,
    *,
    recipient: str,
    display_name: str,
    username: str,
    temporary_password: str,
) -> WelcomeEmailDelivery:
    recipient = recipient.strip().casefold()
    if not recipient:
        raise SpacemailError("A delivery email address is required for the welcome message.")
    if not settings.spacemail_welcome_email_enabled:
        raise SpacemailError("DoobieLogic welcome email delivery is disabled.")
    if not settings.spacemail_is_configured:
        raise SpacemailError("Spacemail welcome email delivery is not configured on the server.")

    message = build_welcome_message(
        settings,
        recipient=recipient,
        display_name=display_name,
        username=username,
        temporary_password=temporary_password,
    )
    try:
        with _smtp_login(settings) as smtp:
            smtp.login(settings.spacemail_smtp_username, settings.spacemail_smtp_password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError, TimeoutError) as exc:
        raise SpacemailError("Spacemail could not deliver the DoobieLogic welcome email.") from exc

    return WelcomeEmailDelivery(
        sent=True,
        recipient=recipient,
        sender=settings.spacemail_from_email,
    )
