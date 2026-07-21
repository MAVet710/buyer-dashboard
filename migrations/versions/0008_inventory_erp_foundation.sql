create table if not exists public.coman_products (
 id varchar(36) primary key, organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 sku varchar(120) not null, name varchar(255) not null, item_type varchar(32) not null,
 base_unit varchar(32) not null, unit_cost double precision not null default 0, active boolean not null default true,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint uq_coman_product_org_sku unique(organization_id, sku));
create index if not exists ix_coman_products_organization_id on public.coman_products(organization_id);

create table if not exists public.coman_product_boms (
 id varchar(36) primary key, organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 output_product_id varchar(36) not null references public.coman_products(id) on delete restrict,
 version integer not null default 1, output_quantity double precision not null default 1,
 expected_loss_pct double precision not null default 0, notes text not null default '', active boolean not null default true,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint uq_coman_bom_product_version unique(organization_id, output_product_id, version));
create index if not exists ix_coman_product_boms_organization_id on public.coman_product_boms(organization_id);
create index if not exists ix_coman_product_boms_output_product_id on public.coman_product_boms(output_product_id);

create table if not exists public.coman_bom_components (
 id varchar(36) primary key, organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 bom_id varchar(36) not null references public.coman_product_boms(id) on delete cascade,
 input_product_id varchar(36) not null references public.coman_products(id) on delete restrict,
 quantity double precision not null, unit varchar(32) not null, scrap_pct double precision not null default 0,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint uq_coman_bom_component unique(bom_id, input_product_id));
create index if not exists ix_coman_bom_components_organization_id on public.coman_bom_components(organization_id);
create index if not exists ix_coman_bom_components_bom_id on public.coman_bom_components(bom_id);
create index if not exists ix_coman_bom_components_input_product_id on public.coman_bom_components(input_product_id);

create table if not exists public.coman_inventory_lots (
 id varchar(36) primary key, organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 product_id varchar(36) not null references public.coman_products(id) on delete restrict,
 lot_code varchar(255) not null, compliance_package_id varchar(255) not null default '',
 location_code varchar(120) not null default 'UNASSIGNED', status varchar(32) not null default 'available',
 received_at timestamptz, expiration_at timestamptz, notes text not null default '',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint uq_coman_lot_facility_code unique(facility_id, lot_code));
create index if not exists ix_coman_inventory_lots_organization_id on public.coman_inventory_lots(organization_id);
create index if not exists ix_coman_inventory_lots_facility_id on public.coman_inventory_lots(facility_id);
create index if not exists ix_coman_inventory_lots_product_id on public.coman_inventory_lots(product_id);

create table if not exists public.coman_inventory_transactions (
 id varchar(36) primary key, organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 lot_id varchar(36) not null references public.coman_inventory_lots(id) on delete restrict,
 transaction_type varchar(40) not null, quantity_delta double precision not null, unit varchar(32) not null,
 production_order_id varchar(36) references public.coman_production_orders(id) on delete set null,
 reason varchar(255) not null default '', reference varchar(255) not null default '', actor varchar(255) not null,
 occurred_at timestamptz not null default now());
create index if not exists ix_coman_inventory_transactions_organization_id on public.coman_inventory_transactions(organization_id);
create index if not exists ix_coman_inventory_transactions_facility_id on public.coman_inventory_transactions(facility_id);
create index if not exists ix_coman_inventory_transactions_lot_id on public.coman_inventory_transactions(lot_id);
create index if not exists ix_coman_inventory_transactions_production_order_id on public.coman_inventory_transactions(production_order_id);
create index if not exists ix_coman_inventory_tx_lot_time on public.coman_inventory_transactions(lot_id, occurred_at);

create table if not exists public.coman_material_reservations (
 id varchar(36) primary key, organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 production_order_id varchar(36) not null references public.coman_production_orders(id) on delete cascade,
 lot_id varchar(36) not null references public.coman_inventory_lots(id) on delete restrict,
 quantity double precision not null, unit varchar(32) not null, status varchar(24) not null default 'reserved',
 reserved_by varchar(255) not null, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint uq_coman_reservation_order_lot unique(production_order_id, lot_id));
create index if not exists ix_coman_material_reservations_organization_id on public.coman_material_reservations(organization_id);
create index if not exists ix_coman_material_reservations_facility_id on public.coman_material_reservations(facility_id);
create index if not exists ix_coman_material_reservations_production_order_id on public.coman_material_reservations(production_order_id);
create index if not exists ix_coman_material_reservations_lot_id on public.coman_material_reservations(lot_id);

alter table public.coman_products enable row level security;
alter table public.coman_product_boms enable row level security;
alter table public.coman_bom_components enable row level security;
alter table public.coman_inventory_lots enable row level security;
alter table public.coman_inventory_transactions enable row level security;
alter table public.coman_material_reservations enable row level security;

create or replace function public.coman_prevent_inventory_ledger_mutation()
returns trigger language plpgsql as $$
begin
 raise exception 'Inventory ledger entries are immutable; post a correcting transaction instead.';
end;
$$;
drop trigger if exists coman_inventory_ledger_immutable on public.coman_inventory_transactions;
create trigger coman_inventory_ledger_immutable before update or delete on public.coman_inventory_transactions
for each row execute function public.coman_prevent_inventory_ledger_mutation();
