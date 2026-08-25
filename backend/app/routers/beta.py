from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
import re
import smtplib
import ssl

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine

from ..config import Settings, get_settings
from ..database import get_engine
from ..services.spacemail import resolve_spacemail_settings

router = APIRouter(prefix="/beta", tags=["beta"])


class BetaApplication(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    company: str = Field(min_length=2, max_length=160)
    role: str = Field(min_length=2, max_length=120)
    operation: str = Field(min_length=2, max_length=80)
    facilities: str = Field(min_length=1, max_length=40)
    stack: str = Field(default="", max_length=240)
    state: str = Field(min_length=2, max_length=80)
    pain: str = Field(min_length=10, max_length=4000)
    must_have: str = Field(default="", max_length=4000)
    consent: bool
    website: str = Field(default="", max_length=200)

    @field_validator("name", "company", "role", "operation", "facilities", "stack", "state", "pain", "must_have", "website")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Enter a valid work email address.")
        return normalized


@router.post("/apply", status_code=status.HTTP_202_ACCEPTED)
def submit_beta_application(
    payload: BetaApplication,
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    # Hidden honeypot. Bots that populate it receive the same public response but
    # do not create mail or expose the filtering rule.
    if payload.website:
        return {"accepted": True}

    if not payload.consent:
        raise HTTPException(status_code=422, detail="Beta participation consent is required.")

    mail_settings = resolve_spacemail_settings(engine, settings)
    if not mail_settings.spacemail_is_configured:
        raise HTTPException(status_code=503, detail="Beta applications are temporarily unavailable. Please try again shortly.")

    recipient = str(mail_settings.spacemail_info_email or mail_settings.spacemail_support_email).strip().casefold()
    if not recipient:
        raise HTTPException(status_code=503, detail="Beta application delivery is not configured.")

    message = EmailMessage()
    message["Subject"] = f"DoobieLogic Beta Application — {payload.company} — {payload.name}"
    message["From"] = formataddr((mail_settings.spacemail_from_name, mail_settings.spacemail_from_email))
    message["To"] = recipient
    message["Reply-To"] = payload.email
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain="doobielogic.io")
    message["X-Auto-Response-Suppress"] = "All"
    message.set_content(
        "\n".join(
            [
                "New DoobieLogic Beta Partner application",
                "",
                f"Name: {payload.name}",
                f"Email: {payload.email}",
                f"Company: {payload.company}",
                f"Role: {payload.role}",
                f"Operation type: {payload.operation}",
                f"Facilities / licenses: {payload.facilities}",
                f"State: {payload.state}",
                f"Primary POS / ERP: {payload.stack or 'Not provided'}",
                "",
                "Biggest operational problem:",
                payload.pain,
                "",
                "What would make DoobieLogic indispensable:",
                payload.must_have or "Not provided",
                "",
                "Beta data / feedback consent: Yes",
            ]
        )
    )

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(
            mail_settings.spacemail_smtp_host,
            mail_settings.spacemail_smtp_port,
            timeout=mail_settings.spacemail_smtp_timeout_seconds,
            context=context,
        ) as smtp:
            smtp.login(mail_settings.spacemail_smtp_username, mail_settings.spacemail_smtp_password)
            refused = smtp.send_message(message)
            if refused:
                raise RuntimeError("recipient rejected")
    except (smtplib.SMTPException, OSError, TimeoutError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="We could not deliver the beta application right now. Please try again shortly.",
        ) from exc

    return {"accepted": True}
