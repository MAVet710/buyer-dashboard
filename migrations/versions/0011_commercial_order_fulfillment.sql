create table if not exists public.commercial_trade_partners (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    name varchar(255) not null,
    partner_type varchar(24) not null,
    license_or_registration varchar(255) not null default '',
    contact_name varchar(255) not null default '',
    contact_email varchar(320) not null default '',
    contact_phone varchar(64) not null default '',
    payment_terms varchar(64) not null default 'Net 30',
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_commercial_partner_org_name unique (organization_id, name),
    constraint ck_commercial_partner_type
        check (partner_type in ('customer', 'vendor', 'both'))
);
create index if not exists ix_commercial_trade_partners_organization_id
    on public.commercial_trade_partners(organization_id);
create index if not exists ix_commercial_partner_org_active
    on public.commercial_trade_partners(organization_id, active);

create table if not exists public.commercial_orders (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    partner_id varchar(36) not null references public.commercial_trade_partners(id) on delete restrict,
    order_number varchar(64) not null,
    order_type varchar(16) not null,
    order_date date not null default current_date,
    due_at timestamptz,
    status varchar(32) not null default 'draft',
    payment_status varchar(32) not null default 'not_invoiced',
    currency varchar(8) not null default 'USD',
    external_reference varchar(255) not null default '',
    notes text not null default '',
    created_by varchar(255) not null,
    updated_by varchar(255) not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_commercial_order_org_number unique (organization_id, order_number),
    constraint ck_commercial_order_type check (order_type in ('sales', 'purchase')),
    constraint ck_commercial_order_status check (
        status in ('draft', 'confirmed', 'allocated', 'partially_fulfilled', 'fulfilled', 'cancelled')
    ),
    constraint ck_commercial_order_payment_status check (
        payment_status in ('not_invoiced', 'draft', 'sent', 'partial', 'paid', 'overdue')
    )
);
create index if not exists ix_commercial_orders_organization_id
    on public.commercial_orders(organization_id);
create index if not exists ix_commercial_orders_facility_id
    on public.commercial_orders(facility_id);
create index if not exists ix_commercial_orders_partner_id
    on public.commercial_orders(partner_id);
create index if not exists ix_commercial_orders_facility_status_due
    on public.commercial_orders(facility_id, status, due_at);

create table if not exists public.commercial_order_lines (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    commercial_order_id varchar(36) not null references public.commercial_orders(id) on delete cascade,
    product_id varchar(36) not null references public.coman_products(id) on delete restrict,
    position integer not null,
    description varchar(512) not null,
    sku_snapshot varchar(120) not null default '',
    quantity double precision not null,
    unit varchar(32) not null,
    unit_price double precision not null default 0,
    fulfilled_quantity double precision not null default 0,
    notes text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_commercial_order_line_position unique (commercial_order_id, position),
    constraint ck_commercial_order_line_quantity check (quantity > 0),
    constraint ck_commercial_order_line_price check (unit_price >= 0),
    constraint ck_commercial_order_line_fulfilled check (fulfilled_quantity >= 0)
);
create index if not exists ix_commercial_order_lines_organization_id
    on public.commercial_order_lines(organization_id);
create index if not exists ix_commercial_order_lines_commercial_order_id
    on public.commercial_order_lines(commercial_order_id);
create index if not exists ix_commercial_order_lines_product_id
    on public.commercial_order_lines(product_id);

create table if not exists public.commercial_order_lot_allocations (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    commercial_order_id varchar(36) not null references public.commercial_orders(id) on delete cascade,
    commercial_order_line_id varchar(36) not null references public.commercial_order_lines(id) on delete cascade,
    lot_id varchar(36) not null references public.coman_inventory_lots(id) on delete restrict,
    quantity double precision not null,
    fulfilled_quantity double precision not null default 0,
    status varchar(24) not null default 'reserved',
    reserved_by varchar(255) not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_commercial_order_line_lot unique (commercial_order_line_id, lot_id),
    constraint ck_commercial_allocation_quantity check (quantity > 0),
    constraint ck_commercial_allocation_fulfilled check (fulfilled_quantity >= 0),
    constraint ck_commercial_allocation_status
        check (status in ('reserved', 'partial', 'fulfilled', 'released'))
);
create index if not exists ix_commercial_order_lot_allocations_organization_id
    on public.commercial_order_lot_allocations(organization_id);
create index if not exists ix_commercial_order_lot_allocations_facility_id
    on public.commercial_order_lot_allocations(facility_id);
create index if not exists ix_commercial_order_lot_allocations_commercial_order_id
    on public.commercial_order_lot_allocations(commercial_order_id);
create index if not exists ix_commercial_order_lot_allocations_commercial_order_line_id
    on public.commercial_order_lot_allocations(commercial_order_line_id);
create index if not exists ix_commercial_order_lot_allocations_lot_id
    on public.commercial_order_lot_allocations(lot_id);

alter table public.coman_inventory_transactions
    add column if not exists commercial_order_id varchar(36);
alter table public.coman_inventory_transactions
    add column if not exists commercial_order_line_id varchar(36);
create index if not exists ix_coman_inventory_transactions_commercial_order_id
    on public.coman_inventory_transactions(commercial_order_id);
create index if not exists ix_coman_inventory_transactions_commercial_order_line_id
    on public.coman_inventory_transactions(commercial_order_line_id);

alter table public.commercial_trade_partners enable row level security;
alter table public.commercial_orders enable row level security;
alter table public.commercial_order_lines enable row level security;
alter table public.commercial_order_lot_allocations enable row level security;
