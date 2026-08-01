alter table public.coman_products
    add column if not exists retail_price double precision not null default 0;
alter table public.coman_products
    add column if not exists upc varchar(64) not null default '';
alter table public.coman_products
    add column if not exists external_product_id varchar(120) not null default '';
create index if not exists ix_coman_products_upc on public.coman_products(upc);
create index if not exists ix_coman_products_external_product_id on public.coman_products(external_product_id);

alter table public.coman_inventory_lots
    add column if not exists external_inventory_id varchar(120) not null default '';
alter table public.coman_inventory_lots
    add column if not exists barcode_value varchar(512) not null default '';
create index if not exists ix_coman_inventory_lots_external_inventory_id
    on public.coman_inventory_lots(external_inventory_id);
create index if not exists ix_coman_inventory_lots_barcode_value
    on public.coman_inventory_lots(barcode_value);

create table if not exists public.inventory_audits (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    audit_number varchar(64) not null,
    status varchar(24) not null default 'draft',
    operation_type varchar(24) not null default 'production',
    blind_count boolean not null default true,
    recount_tolerance double precision not null default 0,
    scope_label varchar(255) not null default 'Full facility',
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    created_by varchar(255) not null,
    completed_by varchar(255) not null default '',
    notes text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_inventory_audit_org_number unique (organization_id, audit_number),
    constraint ck_inventory_audit_status
        check (status in ('draft', 'in_progress', 'completed', 'cancelled')),
    constraint ck_inventory_audit_operation_type
        check (operation_type in ('retail', 'production'))
);
create index if not exists ix_inventory_audits_organization_id
    on public.inventory_audits(organization_id);
create index if not exists ix_inventory_audits_facility_id
    on public.inventory_audits(facility_id);
create index if not exists ix_inventory_audits_facility_status
    on public.inventory_audits(facility_id, status, started_at);

create table if not exists public.inventory_audit_lines (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    audit_id varchar(36) not null references public.inventory_audits(id) on delete cascade,
    lot_id varchar(36) not null references public.coman_inventory_lots(id) on delete restrict,
    expected_quantity double precision not null,
    first_count_quantity double precision,
    recount_quantity double precision,
    counted_quantity double precision,
    variance_quantity double precision not null default 0,
    recount_required boolean not null default false,
    unit varchar(32) not null,
    reason varchar(255) not null default '',
    notes text not null default '',
    counted_by varchar(255) not null default '',
    counted_at timestamptz,
    adjustment_transaction_id varchar(36)
        references public.coman_inventory_transactions(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_inventory_audit_line_lot unique (audit_id, lot_id),
    constraint ck_inventory_audit_expected_nonnegative check (expected_quantity >= 0),
    constraint ck_inventory_audit_counted_nonnegative
        check (counted_quantity is null or counted_quantity >= 0)
);
create index if not exists ix_inventory_audit_lines_organization_id
    on public.inventory_audit_lines(organization_id);
create index if not exists ix_inventory_audit_lines_facility_id
    on public.inventory_audit_lines(facility_id);
create index if not exists ix_inventory_audit_lines_audit_id
    on public.inventory_audit_lines(audit_id);
create index if not exists ix_inventory_audit_lines_lot_id
    on public.inventory_audit_lines(lot_id);
create index if not exists ix_inventory_audit_lines_adjustment_transaction_id
    on public.inventory_audit_lines(adjustment_transaction_id);
create index if not exists ix_inventory_audit_lines_audit_counted
    on public.inventory_audit_lines(audit_id, counted_at);

create table if not exists public.inventory_audit_scans (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    audit_id varchar(36) not null references public.inventory_audits(id) on delete cascade,
    audit_line_id varchar(36) references public.inventory_audit_lines(id) on delete set null,
    raw_code text not null,
    normalized_code varchar(512) not null,
    match_status varchar(24) not null,
    scan_stage varchar(24) not null,
    scanned_by varchar(255) not null,
    scanned_at timestamptz not null default now(),
    constraint ck_inventory_audit_scan_status
        check (match_status in ('matched', 'unmatched', 'ambiguous')),
    constraint ck_inventory_audit_scan_stage
        check (scan_stage in ('first_count', 'recount'))
);
create index if not exists ix_inventory_audit_scans_organization_id
    on public.inventory_audit_scans(organization_id);
create index if not exists ix_inventory_audit_scans_facility_id
    on public.inventory_audit_scans(facility_id);
create index if not exists ix_inventory_audit_scans_audit_id
    on public.inventory_audit_scans(audit_id);
create index if not exists ix_inventory_audit_scans_audit_line_id
    on public.inventory_audit_scans(audit_line_id);
create index if not exists ix_inventory_audit_scans_audit_time
    on public.inventory_audit_scans(audit_id, scanned_at);

alter table public.inventory_audits enable row level security;
alter table public.inventory_audit_lines enable row level security;
alter table public.inventory_audit_scans enable row level security;
