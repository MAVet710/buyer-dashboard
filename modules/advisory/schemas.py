from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

Service = Literal['inventory-profit-audit', 'fractional-purchasing', 'compliance-operational-audit', 'sop-workflow-development', 'metrc-technology', 'production-extraction', 'operational-diagnostic', 'beta-program', 'not-sure']
LeadStatus = Literal['NEW', 'CONTACTED', 'QUALIFIED', 'CONSULTATION_BOOKED', 'PROPOSAL_SENT', 'CLIENT', 'CLOSED_LOST']
SourceTool = Literal['operations-score', 'inventory-health-check']
QUESTION_IDS = tuple(f'{group}-{index}' for group in ('inventory', 'purchasing', 'processes', 'people-production', 'technology') for index in range(1, 6))


class InputModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Attribution(InputModel):
    landing_page: str = Field(default='', max_length=240)
    referrer: str = Field(default='', max_length=240)
    utm_source: str = Field(default='', max_length=100)
    utm_medium: str = Field(default='', max_length=100)
    utm_campaign: str = Field(default='', max_length=100)
    utm_content: str = Field(default='', max_length=100)
    utm_term: str = Field(default='', max_length=100)

    @field_validator('landing_page')
    @classmethod
    def path_only(cls, value: str) -> str:
        if not value:
            return ''
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith('/') or value.startswith('//') or '\\' in value:
            raise ValueError('Landing page must be a local path.')
        return parsed.path

    @field_validator('referrer')
    @classmethod
    def origin_only(cls, value: str) -> str:
        if not value:
            return ''
        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Referrer must be an HTTP(S) origin.')
        return f'{parsed.scheme}://{parsed.netloc}'

    @field_validator('utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term')
    @classmethod
    def campaign_slug(cls, value: str) -> str:
        if value and not re.fullmatch(r'[A-Za-z0-9 _.-]{1,100}', value):
            raise ValueError('Use campaign labels without personal information or URLs.')
        return value


def validate_answers(value: dict[str, StrictInt | None]) -> dict[str, StrictInt | None]:
    if set(value) != set(QUESTION_IDS):
        raise ValueError('Provide all 25 known question IDs; use null for not applicable.')
    if any(answer is not None and not 0 <= answer <= 4 for answer in value.values()):
        raise ValueError('Answers must be integers from 0 to 4, or null.')
    if sum(answer is not None for answer in value.values()) < 15:
        raise ValueError('Answer at least 15 applicable questions.')
    return value


class ScoreInput(InputModel):
    tool_inputs: dict[str, StrictInt | None]
    _validate = field_validator('tool_inputs')(validate_answers)


class LeadInput(InputModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    phone: str = Field(default='', max_length=40)
    company: str = Field(min_length=2, max_length=160)
    role: str = Field(min_length=2, max_length=120)
    state: str = Field(min_length=2, max_length=80)
    operation: str = Field(min_length=2, max_length=120)
    locations: StrictInt = Field(ge=1, le=10000)
    challenge: str = Field(min_length=10, max_length=2000)
    service: Service
    message: str = Field(default='', max_length=4000)
    consent: Literal[True]
    website: str = Field(default='', max_length=200)
    source_tool: SourceTool | None = None
    tool_inputs: dict[str, StrictInt | None] | None = None
    attribution: Attribution = Field(default_factory=Attribution)
    submission_id: UUID | None = None

    @field_validator('consent', mode='before')
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError('Explicit consent is required.')
        return value

    @field_validator('email')
    @classmethod
    def email_address(cls, value: str) -> str:
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid email address.')
        return value.casefold()

    @field_validator('name', 'email', 'phone', 'company', 'role', 'state', 'operation', 'challenge', 'message')
    @classmethod
    def no_control_characters(cls, value: str) -> str:
        if any(ord(char) < 32 and char not in '\n\t' for char in value):
            raise ValueError('Control characters are not permitted.')
        return value

    @model_validator(mode='after')
    def tool_boundary(self):
        if self.source_tool == 'operations-score':
            if self.tool_inputs is None:
                raise ValueError('Operations score inputs are required.')
            validate_answers(self.tool_inputs)
        elif self.tool_inputs is not None:
            raise ValueError('Only operations score answers may be submitted; inventory CSV data stays in your browser.')
        return self


class LeadUpdate(InputModel):
    status: LeadStatus
    expected_version: StrictInt = Field(ge=1)
    note: str = Field(default='', max_length=1000)


class EventInput(InputModel):
    event: Literal['consulting_page_view', 'service_page_view', 'operations_score_started', 'operations_score_completed', 'inventory_check_started', 'inventory_check_completed', 'consultation_cta_clicked', 'consultation_form_started', 'consultation_form_submitted', 'audit_cta_clicked', 'resource_article_view', 'service_internal_link_clicked']
    placement: Literal['navigation', 'hero', 'product', 'solutions', 'extraction', 'intelligence', 'integrations', 'trust', 'faq', 'final', 'footer', 'beta', 'consulting', 'resources', 'contact', 'consultation', 'tool']
    item: str = Field(default='', max_length=64, pattern=r'^(?:[a-z][a-z0-9-]{0,63})?$')
    consent: Literal[True]
    _explicit_consent = field_validator('consent', mode='before')(LeadInput.explicit_consent.__func__)
