-- Design-partner pilot and case-study measurement. Apply after 0027_benchmark_net.

create table if not exists public.design_partner_accounts (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 status varchar(24) not null default 'prospect', champion_name varchar(255) not null default '', champion_email varchar(320) not null default '',
 pain_profile text not null default '', success_targets_json text not null default '{}', started_at date, target_case_study_date date,
 notes text not null default '', updated_by varchar(255) not null,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint uq_design_partner_org unique(organization_id),
 constraint ck_design_partner_status check (status in ('prospect','pilot','live','case_study','graduated','churned'))
);
create index if not exists ix_design_partner_accounts_organization_id on public.design_partner_accounts(organization_id);
create index if not exists ix_design_partner_status on public.design_partner_accounts(status,started_at);

create table if not exists public.design_partner_metrics (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 account_id varchar(36) not null references public.design_partner_accounts(id) on delete cascade,
 metric_key varchar(120) not null, baseline_value double precision not null default 0, current_value double precision not null default 0,
 unit varchar(64) not null default '', direction varchar(16) not null default 'higher', evidence text not null default '', updated_by varchar(255) not null,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint uq_design_partner_metric_key unique(account_id,metric_key)
);
create index if not exists ix_design_partner_metrics_organization_id on public.design_partner_metrics(organization_id);
create index if not exists ix_design_partner_metrics_account_id on public.design_partner_metrics(account_id);

create table if not exists public.design_partner_feedback (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 account_id varchar(36) not null references public.design_partner_accounts(id) on delete cascade,
 area varchar(120) not null, severity varchar(24) not null default 'medium', feedback text not null, status varchar(24) not null default 'open',
 submitted_by varchar(255) not null, resolved_by varchar(255) not null default '', resolved_at timestamptz,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint ck_design_partner_feedback_severity check (severity in ('low','medium','high','critical')),
 constraint ck_design_partner_feedback_status check (status in ('open','planned','shipped','declined'))
);
create index if not exists ix_design_partner_feedback_organization_id on public.design_partner_feedback(organization_id);
create index if not exists ix_design_partner_feedback_account_id on public.design_partner_feedback(account_id);
create index if not exists ix_design_partner_feedback_account_status on public.design_partner_feedback(account_id,status,created_at);

alter table public.design_partner_accounts enable row level security;
alter table public.design_partner_metrics enable row level security;
alter table public.design_partner_feedback enable row level security;

update public.alembic_version set version_num='0028_design_partners' where version_num='0027_benchmark_net';
