from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class RunInput(Input):
    service_date: date
    driver_name: str | None = Field(default=None, max_length=255)
    driver_license_number: str | None = Field(default=None, max_length=128)
    vehicle_make: str | None = Field(default=None, max_length=128)
    vehicle_model: str | None = Field(default=None, max_length=128)
    vehicle_license_plate_number: str | None = Field(default=None, max_length=64)
    notes: str = Field(default="", max_length=4000)


class StopInput(Input):
    shipment_id: str = Field(min_length=1, max_length=36)
    planned_start: AwareDatetime | None = None
    planned_end: AwareDatetime | None = None
    address_snapshot: str = Field(min_length=1, max_length=2000)
    contact_snapshot: str = Field(default="", max_length=2000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def valid_pairs(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Supply both coordinates or neither.")
        if (self.planned_start is None) != (self.planned_end is None):
            raise ValueError("Supply both planned window timestamps or neither.")
        if self.planned_start and self.planned_end < self.planned_start:
            raise ValueError("Planned window ends before it starts.")
        return self


class VersionInput(Input):
    version: int = Field(ge=1)


class AddStop(VersionInput, StopInput):
    pass


class EditRun(VersionInput, RunInput):
    pass


class Reorder(VersionInput):
    stop_ids: list[str] = Field(max_length=100)


class Outcome(VersionInput):
    status: Literal["planned", "loaded", "en_route", "arrived", "delivered", "partial", "rejected", "returned"]
    recipient_name: str = Field(default="", max_length=255)
    delivered_at: AwareDatetime | None = None
    outcome_notes: str = Field(default="", max_length=4000)
    acknowledgment_name: str = Field(default="", max_length=255)
