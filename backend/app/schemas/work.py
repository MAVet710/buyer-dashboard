"""Validated public contracts for reusable operational work."""
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

Priority = Literal["low", "medium", "high", "critical"]
WorkStatus = Literal["open", "in_progress", "blocked", "completed"]


class WorkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=20000)
    priority: Priority = "medium"
    assignee_id: str | None = Field(default=None, min_length=1, max_length=36)
    due_at: AwareDatetime | None = None
    entity_type: str = Field(default="", max_length=80)
    entity_id: str = Field(default="", max_length=255)
    workspace: str = Field(default="", max_length=120)
    route: str = Field(default="", max_length=1000)
    notes: str = Field(default="", max_length=20000)
    evidence: str = Field(default="", max_length=20000)

    @field_validator("route")
    @classmethod
    def local_route(cls, value):
        decoded = unquote(value)
        if not value:
            return value
        parsed = urlsplit(decoded)
        roots = {"home", "work", "buying", "inventory", "cultivation", "production", "wholesale", "compliance", "reports", "doobie", "settings"}
        if (not decoded.startswith("/") or decoded.startswith("//") or "\\" in decoded
                or parsed.scheme or parsed.netloc or any(ord(c) < 32 for c in decoded)
                or ".." in parsed.path.split("/") or parsed.path.split("/")[1] not in roots):
            raise ValueError("Use a local operational workspace route.")
        return value

    @model_validator(mode="after")
    def entity_reference(self):
        if bool(self.entity_type) != bool(self.entity_id):
            raise ValueError("Entity type and entity ID must be supplied together.")
        return self


class WorkUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int = Field(ge=1)
    status: WorkStatus | None = None
    assignee_id: str | None = Field(default=None, min_length=1, max_length=36)
    due_at: AwareDatetime | None = None
    priority: Priority | None = None
    blocked_reason: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=20000)
    evidence: str | None = Field(default=None, max_length=20000)

    @model_validator(mode="after")
    def reject_null(self):
        for name in self.model_fields_set - {"assignee_id", "due_at"}:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class TemplateCreate(WorkCreate):
    frequency: Literal["daily", "weekly", "monthly"]
    starts_at: AwareDatetime
    ends_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def schedule(self):
        if self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("End must be on or after start.")
        if self.due_at or self.notes or self.evidence:
            raise ValueError("Templates use starts_at for due time; notes/evidence belong to generated work.")
        return self


class TemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    active: bool | None = None
    assignee_id: str | None = Field(default=None, min_length=1, max_length=36)

    @model_validator(mode="after")
    def reject_null_active(self):
        if "active" in self.model_fields_set and self.active is None:
            raise ValueError("Active cannot be null.")
        return self


class WorkVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
