-- Human-approved Doobie actions. Apply after 0025_commercial_fin.

create table if not exists public.action_proposals (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 idempotency_key varchar(255) not null, action_type varchar(64) not null, title varchar(255) not null,
 rationale text not null default '', payload_json text not null default '{}', preview_json text not null default '{}',
 financial_impact_usd double precision not null default 0, risk_level varchar(24) not null default 'medium', status varchar(24) not null default 'proposed',
 source_type varchar(64) not null default 'manual', source_id varchar(255) not null default '', created_by varchar(255) not null,
 approved_by varchar(255) not null default '', approved_at timestamptz, expires_at timestamptz,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint uq_action_proposal_org_idempotency unique(organization_id,idempotency_key),
 constraint ck_action_proposal_risk check (risk_level in ('low','medium','high','compliance')),
 constraint ck_action_proposal_status check (status in ('proposed','approved','executing','executed','rejected','failed','expired')),
 constraint ck_action_proposal_financial_impact check (financial_impact_usd >= 0)
);
create index if not exists ix_action_proposals_organization_id on public.action_proposals(organization_id);
create index if not exists ix_action_proposals_facility_id on public.action_proposals(facility_id);
create index if not exists ix_action_proposal_facility_status on public.action_proposals(facility_id,status,created_at);

create table if not exists public.action_executions (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 proposal_id varchar(36) not null references public.action_proposals(id) on delete cascade,
 attempt_number integer not null, status varchar(24) not null default 'started', result_json text not null default '{}', error_message text not null default '',
 actor varchar(255) not null, started_at timestamptz not null default now(), completed_at timestamptz,
 constraint uq_action_execution_attempt unique(proposal_id,attempt_number),
 constraint ck_action_execution_status check (status in ('started','succeeded','failed'))
);
create index if not exists ix_action_executions_organization_id on public.action_executions(organization_id);
create index if not exists ix_action_executions_facility_id on public.action_executions(facility_id);
create index if not exists ix_action_executions_proposal_id on public.action_executions(proposal_id);
create index if not exists ix_action_execution_proposal_time on public.action_executions(proposal_id,started_at);

alter table public.action_proposals enable row level security;
alter table public.action_executions enable row level security;

update public.alembic_version set version_num='0026_doobie_actions' where version_num='0025_commercial_fin';
