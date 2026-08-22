from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class InventoryPackage(BaseModel):
    id: str
    package_id: str
    lot_code: str
    product_id: str
    sku: str
    product_name: str
    material_type: str
    location: str
    status: str
    available: float
    reserved: float
    usable: float
    unit: str
    received_at: datetime | None = None
    expiration_at: datetime | None = None
    attention: str
    sold_30d: float = 0.0
    daily_velocity: float = 0.0
    days_on_hand: float | None = None
    unit_cost: float = 0.0
    retail_price: float = 0.0
    margin_pct: float | None = None


class InventoryFacets(BaseModel):
    statuses: list[str]
    material_types: list[str]
    locations: list[str]


class InventorySummary(BaseModel):
    package_count: int
    available_quantity: float
    reserved_quantity: float
    hold_count: int
    low_balance_count: int


class InventoryResponse(BaseModel):
    operation: Literal["retail", "production"]
    grain: str = "packages"
    items: list[InventoryPackage]
    facets: InventoryFacets
    summary: InventorySummary


class ProductOption(BaseModel):
    id: str
    sku: str
    name: str
    item_type: str
    base_unit: str


class InventoryReceiptCreate(BaseModel):
    product_id: str
    lot_code: str = ""
    package_id: str = ""
    quantity: float = Field(gt=0)
    unit: str
    location: str = "RECEIVING"
    source_name: str = ""
    manifest_reference: str = ""
    lab_testing_state: str = ""
    coa_reference: str = ""
    expiration_at: datetime | None = None
    notes: str = ""


class InventoryReceiptResult(BaseModel):
    lot_id: str
    transaction_id: str
    operation: Literal["retail", "production"]
    status: str


class InventoryReceiptHistoryItem(BaseModel):
    transaction_id: str
    lot_id: str
    product_name: str
    package_id: str
    quantity: float
    unit: str
    manifest_reference: str
    source_name: str
    actor: str
    received_at: datetime


class RetailSaleImportLine(BaseModel):
    source_record_id: str
    sold_at: datetime
    quantity: float
    product_id: str | None = None
    sku: str = ""
    product_name: str
    net_sales: float = 0.0


class RetailSalesImport(BaseModel):
    source_system: str
    import_batch_id: str = ""
    lines: list[RetailSaleImportLine] = Field(min_length=1, max_length=10000)


class RetailSalesImportResult(BaseModel):
    imported: int
    skipped_duplicates: int
    unmapped_products: int


class InventoryAdjustmentCreate(BaseModel):
    lot_id: str
    adjustment_type: Literal["incremental", "set_quantity"]
    quantity: float
    reason: str
    reason_note: str = ""


class InventoryAdjustmentResult(BaseModel):
    transaction_id: str
    lot_id: str
    previous_quantity: float
    delta: float
    final_quantity: float
    reserved_quantity: float
    unit: str
    reason: str


class InventoryAuditCreate(BaseModel):
    audit_number: str
    scope_label: str = "Full facility"
    notes: str = ""
    lot_ids: list[str] = Field(default_factory=list)
    blind_count: bool = True
    recount_tolerance: float = Field(default=0.0, ge=0)


class InventoryAuditSummary(BaseModel):
    id: str
    audit_number: str
    operation_type: Literal["retail", "production"]
    status: str
    scope_label: str
    blind_count: bool
    recount_tolerance: float
    started_at: datetime
    completed_at: datetime | None
    created_by: str


class InventoryAuditLineItem(BaseModel):
    id: str
    lot_id: str
    product_name: str
    package_id: str
    location: str
    expected_quantity: float | None
    counted_quantity: float | None
    variance_quantity: float
    recount_required: bool
    unit: str
    reason: str
    notes: str


class InventoryAuditDetail(BaseModel):
    audit: InventoryAuditSummary
    lines: list[InventoryAuditLineItem]


class InventoryAuditCount(BaseModel):
    line_id: str
    counted_quantity: float = Field(ge=0)
    reason: str = ""
    notes: str = ""


class InventoryAuditCounts(BaseModel):
    counts: list[InventoryAuditCount]


class InventoryAuditStatusChange(BaseModel):
    status: Literal["draft", "in_progress", "paused", "stopped", "cancelled"]


class InventoryAuditComplete(BaseModel):
    post_adjustments: bool = False


class PackageLineageLot(BaseModel):
    lot_id: str
    lot_code: str
    product_name: str = ""
    quantity: float | None = None
    unit: str = ""


class PackageLineageCreation(BaseModel):
    run_number: str
    action_type: str
    parents: list[PackageLineageLot]


class PackageLineageChildOutput(BaseModel):
    lot_id: str | None = None
    lot_code: str
    product_id: str
    inventory_quantity: float
    inventory_unit: str
    purpose: str


class PackageLineageUse(BaseModel):
    run_number: str
    action_type: str
    quantity_consumed: float
    unit: str
    outputs: list[PackageLineageChildOutput]


class PackageLineage(BaseModel):
    lot: dict
    created_by: PackageLineageCreation | None
    used_by: list[PackageLineageUse]
