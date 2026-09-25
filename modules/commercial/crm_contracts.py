"""Validated CRM mutation contracts shared by HTTP and deterministic services."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)

class AccountInput(Input):
    owner: str = Field(default='', max_length=255)
    status: Literal['prospect', 'active', 'on_hold', 'inactive'] = 'prospect'
    next_action: str = Field(default='', max_length=1000)
    next_action_date: date | None = None

class OpportunityInput(Input):
    title: str = Field(min_length=1, max_length=255)
    stage: Literal['lead', 'qualified', 'quoted', 'negotiating', 'won', 'lost'] = 'lead'
    estimated_value: float = Field(default=0, ge=0, le=999999999999)
    expected_close_date: date | None = None
    owner: str = Field(default='', max_length=255)
    source: str = Field(default='', max_length=255)
    next_action: str = Field(default='', max_length=1000)
    next_action_date: date | None = None

class ActivityInput(Input):
    kind: Literal['call', 'email', 'meeting', 'note', 'task_reference'] = 'note'
    body: str = Field(min_length=1, max_length=10000)
    reference: str = Field(default='', max_length=255)

class QuoteLine(Input):
    product_id: str = Field(min_length=1, max_length=36)
    quantity: float = Field(gt=0, le=1000000000)
    unit_price: float | None = Field(default=None, ge=0, le=1000000000)

class QuoteInput(Input):
    title: str = Field(min_length=1, max_length=255)
    opportunity_id: str | None = None
    lines: list[QuoteLine] = Field(min_length=1, max_length=100)
