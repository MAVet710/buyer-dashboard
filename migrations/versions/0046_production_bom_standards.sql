CREATE TABLE IF NOT EXISTS production_bom_standards (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL REFERENCES coman_organizations(id) ON DELETE CASCADE,
    bom_id VARCHAR(36) NOT NULL REFERENCES coman_product_boms(id) ON DELETE CASCADE,
    standard_labor_hours DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (standard_labor_hours >= 0),
    standard_machine_hours DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (standard_machine_hours >= 0),
    standard_cycle_hours DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (standard_cycle_hours >= 0),
    resource_category VARCHAR(120) NOT NULL DEFAULT '',
    qa_required BOOLEAN NOT NULL DEFAULT FALSE,
    compliance_checkpoint TEXT NOT NULL DEFAULT '',
    created_by VARCHAR(255) NOT NULL,
    updated_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_production_bom_standard_bom UNIQUE (bom_id)
);

CREATE INDEX IF NOT EXISTS ix_production_bom_standards_organization_id
    ON production_bom_standards (organization_id);
CREATE INDEX IF NOT EXISTS ix_production_bom_standards_bom_id
    ON production_bom_standards (bom_id);
CREATE INDEX IF NOT EXISTS ix_production_bom_standard_org_bom
    ON production_bom_standards (organization_id, bom_id);
