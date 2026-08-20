-- Wholesale fulfillment and finance. Apply after 0024_production_erp.

create table if not exists public.commercial_shipments (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 commercial_order_id varchar(36) not null references public.commercial_orders(id) on delete cascade,
 shipment_number varchar(80) not null, status varchar(24) not null default 'planned',
 manifest_reference varchar(255) not null default '', carrier varchar(255) not null default '', tracking_reference varchar(255) not null default '',
 shipped_at timestamptz, delivered_at timestamptz, notes text not null default '', created_by varchar(255) not null,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint uq_commercial_shipment_org_number unique(organization_id,shipment_number),
 constraint ck_commercial_shipment_status check (status in ('planned','picking','packed','manifested','shipped','delivered','cancelled'))
);
create index if not exists ix_commercial_shipments_organization_id on public.commercial_shipments(organization_id);
create index if not exists ix_commercial_shipments_facility_id on public.commercial_shipments(facility_id);
create index if not exists ix_commercial_shipments_commercial_order_id on public.commercial_shipments(commercial_order_id);
create index if not exists ix_commercial_shipment_facility_status on public.commercial_shipments(facility_id,status,created_at);

create table if not exists public.commercial_invoices (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 commercial_order_id varchar(36) not null references public.commercial_orders(id) on delete restrict,
 partner_id varchar(36) not null references public.commercial_trade_partners(id) on delete restrict,
 invoice_number varchar(80) not null, status varchar(24) not null default 'draft', issue_date date not null, due_date date not null,
 currency varchar(8) not null default 'USD', subtotal_usd double precision not null default 0, discount_usd double precision not null default 0,
 tax_usd double precision not null default 0, total_usd double precision not null default 0, balance_usd double precision not null default 0,
 notes text not null default '', created_by varchar(255) not null, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint uq_commercial_invoice_org_number unique(organization_id,invoice_number),
 constraint ck_commercial_invoice_status check (status in ('draft','sent','partial','paid','overdue','void')),
 constraint ck_commercial_invoice_amounts check (subtotal_usd >= 0 and discount_usd >= 0 and tax_usd >= 0 and total_usd >= 0 and balance_usd >= 0)
);
create index if not exists ix_commercial_invoices_organization_id on public.commercial_invoices(organization_id);
create index if not exists ix_commercial_invoices_facility_id on public.commercial_invoices(facility_id);
create index if not exists ix_commercial_invoices_commercial_order_id on public.commercial_invoices(commercial_order_id);
create index if not exists ix_commercial_invoices_partner_id on public.commercial_invoices(partner_id);
create index if not exists ix_commercial_invoice_facility_status_due on public.commercial_invoices(facility_id,status,due_date);

create table if not exists public.commercial_invoice_lines (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 invoice_id varchar(36) not null references public.commercial_invoices(id) on delete cascade,
 commercial_order_line_id varchar(36) references public.commercial_order_lines(id) on delete set null,
 product_id varchar(36) not null references public.coman_products(id) on delete restrict,
 position integer not null, description varchar(512) not null, quantity double precision not null, unit varchar(32) not null,
 unit_price_usd double precision not null, line_total_usd double precision not null,
 constraint uq_commercial_invoice_line_position unique(invoice_id,position),
 constraint ck_commercial_invoice_line_amounts check (quantity > 0 and unit_price_usd >= 0 and line_total_usd >= 0)
);
create index if not exists ix_commercial_invoice_lines_organization_id on public.commercial_invoice_lines(organization_id);
create index if not exists ix_commercial_invoice_lines_invoice_id on public.commercial_invoice_lines(invoice_id);
create index if not exists ix_commercial_invoice_lines_commercial_order_line_id on public.commercial_invoice_lines(commercial_order_line_id);
create index if not exists ix_commercial_invoice_lines_product_id on public.commercial_invoice_lines(product_id);

create table if not exists public.commercial_payments (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 invoice_id varchar(36) not null references public.commercial_invoices(id) on delete cascade,
 amount_usd double precision not null, payment_date date not null, method varchar(64) not null default 'other', reference varchar(255) not null default '',
 notes text not null default '', recorded_by varchar(255) not null, recorded_at timestamptz not null default now(),
 constraint ck_commercial_payment_amount check (amount_usd > 0)
);
create index if not exists ix_commercial_payments_organization_id on public.commercial_payments(organization_id);
create index if not exists ix_commercial_payments_facility_id on public.commercial_payments(facility_id);
create index if not exists ix_commercial_payments_invoice_id on public.commercial_payments(invoice_id);
create index if not exists ix_commercial_payment_invoice_date on public.commercial_payments(invoice_id,payment_date);

create table if not exists public.customer_price_rules (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 partner_id varchar(36) not null references public.commercial_trade_partners(id) on delete cascade,
 product_id varchar(36) not null references public.coman_products(id) on delete cascade,
 price_usd double precision not null default 0, discount_pct double precision not null default 0, active boolean not null default true,
 notes text not null default '', updated_by varchar(255) not null, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint uq_customer_price_partner_product unique(partner_id,product_id),
 constraint ck_customer_price_values check (price_usd >= 0 and discount_pct >= 0 and discount_pct <= 100)
);
create index if not exists ix_customer_price_rules_organization_id on public.customer_price_rules(organization_id);
create index if not exists ix_customer_price_rules_partner_id on public.customer_price_rules(partner_id);
create index if not exists ix_customer_price_rules_product_id on public.customer_price_rules(product_id);
create index if not exists ix_customer_price_org_active on public.customer_price_rules(organization_id,active);

alter table public.commercial_shipments enable row level security;
alter table public.commercial_invoices enable row level security;
alter table public.commercial_invoice_lines enable row level security;
alter table public.commercial_payments enable row level security;
alter table public.customer_price_rules enable row level security;

update public.alembic_version set version_num='0025_commercial_fin' where version_num='0024_production_erp';
