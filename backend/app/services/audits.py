from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryAudit, InventoryAuditLine, InventoryLot, Product
from modules.inventory_audit.repository import InventoryAuditRepository
from modules.inventory_audit.workflow import get_audit_events, set_audit_status

from ..schemas.inventory import InventoryAuditCreate, InventoryAuditDetail, InventoryAuditEventItem, InventoryAuditLineItem, InventoryAuditScanItem, InventoryAuditSummary


class AuditService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.repository = InventoryAuditRepository(engine)

    @staticmethod
    def summary(audit: InventoryAudit, lines: list[InventoryAuditLine] | None = None) -> InventoryAuditSummary:
        line_rows = lines or []
        return InventoryAuditSummary(
            id=audit.id, audit_number=audit.audit_number, operation_type=audit.operation_type,
            status=audit.status, scope_label=audit.scope_label, blind_count=audit.blind_count,
            recount_tolerance=float(audit.recount_tolerance), started_at=audit.started_at,
            completed_at=audit.completed_at, created_by=audit.created_by,
            scanned_count=sum(row.first_count_quantity is not None for row in line_rows),
            total_count=len(line_rows),
            recount_count=sum(bool(row.recount_required) for row in line_rows),
        )

    def list(self, organization_id: str, facility_id: str, operation: str):
        return [self.summary(row, self.repository.list_lines(organization_id, row.id)) for row in self.repository.list_audits(organization_id, facility_id, operation)]

    def create(self, organization_id: str, facility_id: str, operation: str, payload: InventoryAuditCreate, actor: str):
        audit = self.repository.create_audit(
            organization_id, facility_id, audit_number=payload.audit_number, actor=actor,
            scope_label=payload.scope_label, notes=payload.notes, lot_ids=payload.lot_ids or None,
            operation_type=operation, blind_count=payload.blind_count,
            recount_tolerance=payload.recount_tolerance,
        )
        audit = set_audit_status(
            self.repository,
            organization_id,
            facility_id,
            audit.id,
            status="in_progress",
            actor=actor,
        )
        return self.summary(audit, self.repository.list_lines(organization_id, audit.id))

    @staticmethod
    def _line_item(audit: InventoryAudit, line: InventoryAuditLine, lot: InventoryLot, product: Product) -> InventoryAuditLineItem:
        primary_code = str(
            lot.barcode_value
            or lot.compliance_package_id
            or lot.external_inventory_id
            or lot.lot_code
            or product.upc
            or product.sku
        )
        return InventoryAuditLineItem(
            id=line.id,
            lot_id=lot.id,
            product_name=product.name,
            package_id=lot.compliance_package_id or lot.lot_code,
            location=lot.location_code,
            expected_quantity=None if audit.blind_count and line.first_count_quantity is None else float(line.expected_quantity),
            counted_quantity=line.counted_quantity,
            variance_quantity=float(line.variance_quantity),
            recount_required=line.recount_required,
            unit=line.unit,
            reason=line.reason,
            notes=line.notes,
            first_count_quantity=line.first_count_quantity,
            recount_quantity=line.recount_quantity,
            counted_by=line.counted_by,
            sku_or_upc=product.upc or product.sku,
            lot_code=lot.lot_code,
            metrc_package=lot.compliance_package_id,
            primary_code=primary_code,
            unit_cost=float(product.unit_cost or 0.0),
            retail_price=float(product.retail_price or 0.0),
        )

    def detail(self, organization_id: str, facility_id: str, audit_id: str) -> InventoryAuditDetail:
        with Session(self.engine) as session:
            audit = session.get(InventoryAudit, audit_id)
            if not audit or audit.organization_id != organization_id or audit.facility_id != facility_id:
                raise ValueError("Inventory audit was not found in the active facility.")
            rows = session.execute(
                select(InventoryAuditLine, InventoryLot, Product)
                .join(InventoryLot, InventoryLot.id == InventoryAuditLine.lot_id)
                .join(Product, Product.id == InventoryLot.product_id)
                .where(InventoryAuditLine.audit_id == audit.id)
                .order_by(InventoryLot.location_code, Product.name)
            ).all()
            lines = [self._line_item(audit, line, lot, product) for line, lot, product in rows]
        scans = [InventoryAuditScanItem(
            id=row.id,
            raw_code=row.raw_code,
            match_status=row.match_status,
            scan_stage=row.scan_stage,
            scanned_by=row.scanned_by,
            scanned_at=row.scanned_at,
        ) for row in self.repository.list_scans(organization_id, audit_id)]
        events = [InventoryAuditEventItem(
            id=row.id,
            action=row.action,
            actor=row.actor,
            occurred_at=row.occurred_at,
            changes_json=row.changes_json,
        ) for row in get_audit_events(self.repository, organization_id, audit_id)]
        audit_lines = [line for line, _, _ in rows]
        return InventoryAuditDetail(audit=self.summary(audit, audit_lines), lines=lines, scans=scans, events=events)

    def line_item(self, organization_id: str, facility_id: str, audit_id: str, line_id: str) -> InventoryAuditLineItem:
        detail = self.detail(organization_id, facility_id, audit_id)
        line = next((row for row in detail.lines if row.id == line_id), None)
        if line is None:
            raise ValueError("That audit item is no longer available.")
        return line

    def status(self, organization_id: str, facility_id: str, audit_id: str, status: str, actor: str):
        audit = set_audit_status(self.repository, organization_id, facility_id, audit_id, status=status, actor=actor)
        return self.summary(audit, self.repository.list_lines(organization_id, audit.id))
