from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class InventoryTransferDispatchLine(BaseModel):
    source_lot_id: str = Field(min_length=1, max_length=64)
    quantity: float = Field(gt=0)
    commercial_order_line_id: str = Field(default="", max_length=64)


class InventoryTransferDispatchCreate(BaseModel):
    destination_facility_id: str = Field(min_length=1, max_length=64)
    manifest_reference: str = Field(min_length=1, max_length=255)
    external_transfer_id: str = Field(default="", max_length=255)
    notes: str = Field(default="", max_length=4000)
    state_transfer_confirmed: bool = False
    lines: list[InventoryTransferDispatchLine] = Field(min_length=1, max_length=500)


class InventoryTransferReceiveLine(BaseModel):
    operation: Literal["retail", "production"]
    lot_code: str = Field(default="", max_length=255)
    package_id: str = Field(default="", max_length=255)
    location: str = Field(default="RECEIVING", max_length=120)
    notes: str = Field(default="", max_length=4000)
    state_receipt_confirmed: bool = False


class InventoryTransferCancel(BaseModel):
    reason: str = Field(default="", max_length=4000)
    state_cancel_confirmed: bool = False


class InventoryTransferLineItem(BaseModel):
    id: str
    source_lot_id: str
    destination_lot_id: str | None
    product_id: str
    product_name: str
    quantity: float
    received_quantity: float
    unit: str
    source_lot_code: str
    source_package_id: str
    destination_lot_code: str
    destination_package_id: str
    source_transaction_id: str
    destination_transaction_id: str | None
    status: Literal["shipped", "received", "cancelled"]
    received_at: datetime | None


class InventoryTransferItem(BaseModel):
    id: str
    organization_id: str
    source_facility_id: str
    destination_facility_id: str
    source_facility_name: str
    destination_facility_name: str
    source_license_number: str
    destination_license_number: str
    manifest_reference: str
    external_transfer_id: str
    status: Literal["shipped", "partially_received", "received", "cancelled"]
    direction: str
    notes: str
    created_by: str
    shipped_at: datetime
    received_at: datetime | None
    cancelled_at: datetime | None
    lines: list[InventoryTransferLineItem]