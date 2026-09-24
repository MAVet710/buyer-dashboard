from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine

from ..config import Settings, get_settings
from ..database import get_engine
from ..services import advisory
from modules.advisory.schemas import LeadInput

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
    # Hidden honeypot: bots receive the same public response without persistence.
    if payload.website:
        return {"accepted": True}

    if not payload.consent:
        raise HTTPException(status_code=422, detail="Beta participation consent is required.")

    match = re.search(r"\d+", payload.facilities)
    locations = max(1, min(10000, int(match.group()) if match else 1))
    details = "\n".join(
        [
            f"Beta facilities / licenses: {payload.facilities}",
            f"Primary POS / ERP: {payload.stack or 'Not provided'}",
            "",
            "What would make DoobieLogic indispensable:",
            payload.must_have or "Not provided",
        ]
    )
    lead = LeadInput(
        name=payload.name,
        email=payload.email,
        company=payload.company,
        role=payload.role,
        state=payload.state,
        operation=payload.operation,
        locations=locations,
        challenge=payload.pain,
        service="beta-program",
        message=details,
        consent=True,
    )
    return advisory.capture_lead(engine, settings, lead)
