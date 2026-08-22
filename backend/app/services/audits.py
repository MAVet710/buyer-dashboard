from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryAudit, InventoryAuditLine, InventoryLot, Product
from modules.inventory_audit.repository import InventoryAuditRepository
from modules.inventory_audit.workflow import set_audit_status

from ..schemas.inventory import InventoryAuditCreate, InventoryAuditDetail, InventoryAuditLineItem, InventoryAuditSummary


class AuditService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.repository = InventoryAuditRepository(engine)

    @staticmethod
    def summary(audit: InventoryAudit) -> InventoryAuditSummary:
        return InventoryAuditSummary(
            id=audit.id, audit_number=audit.audit_number, operation_type=audit.operation_type,
            status=audit.status, scope_label=audit.scope_label, blind_count=audit.blind_count,
            recount_tolerance=float(audit.recount_tolerance), started_at=audit.started_at,
            completed_at=audit.completed_at, created_by=audit.created_by,
        )

    def list(self, organization_id: str, facility_id: str, operation: str):
        return [self.summary(row) for row in self.repository.list_audits(organization_id, facility_id, operation)]

    def create(self, organization_id: str, facility_id: str, operation: str, payload: InventoryAuditCreate, actor: str):
        audit = self.repository.create_audit(
            organization_id, facility_id, audit_number=payload.audit_number, actor=actor,
            scope_label=payload.scope_label, notes=payload.notes, lot_ids=payload.lot_ids or None,
            operation_type=operation, blind_count=payload.blind_count,
            recount_tolerance=payload.recount_tolerance,
        )
        return self.summary(audit)

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
            lines = [InventoryAuditLineItem(
                id=line.id, lot_id=lot.id, product_name=product.name,
                package_id=lot.compliance_package_id or lot.lot_code, location=lot.location_code,
                expected_quantity=None if audit.blind_count and line.counted_quantity is None else float(line.expected_quantity),
                counted_quantity=line.counted_quantity, variance_quantity=float(line.variance_quantity),
                recount_required=line.recount_required, unit=line.unit, reason=line.reason, notes=line.notes,
            ) for line, lot, product in rows]
        return InventoryAuditDetail(audit=self.summary(audit), lines=lines)

    def status(self, organization_id: str, facility_id: str, audit_id: str, status: str, actor: str):
        return self.summary(set_audit_status(self.repository, organization_id, facility_id, audit_id, status=status, actor=actor))
