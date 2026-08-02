begin;

create table if not exists public.legal_policy_versions (
    id varchar(36) primary key,
    policy_type varchar(24) not null,
    version varchar(64) not null,
    effective_at timestamptz not null,
    document_url varchar(1024) not null default '',
    document_sha256 varchar(64) not null,
    requires_reacceptance boolean not null default true,
    published_at timestamptz not null default now(),
    constraint uq_legal_policy_type_version unique (policy_type, version),
    constraint ck_legal_policy_type check (policy_type in ('terms', 'privacy'))
);

create table if not exists public.legal_acceptance_events (
    id varchar(36) primary key,
    user_id varchar(36) not null references public.app_users(id) on delete cascade,
    organization_id varchar(36) references public.coman_organizations(id) on delete set null,
    terms_version varchar(64) not null,
    privacy_version varchar(64) not null,
    statement_version varchar(64) not null,
    acceptance_method varchar(32) not null,
    environment varchar(24) not null,
    accepted_at timestamptz not null default now(),
    ip_address varchar(64) not null default '',
    user_agent text not null default '',
    created_by_user_id varchar(36) references public.app_users(id) on delete set null,
    constraint uq_legal_acceptance_user_versions
        unique (user_id, terms_version, privacy_version),
    constraint ck_legal_acceptance_method check (
        acceptance_method in ('first_login', 'policy_update', 'organization_activation')
    ),
    constraint ck_legal_acceptance_environment check (
        environment in ('production', 'trial', 'sandbox')
    )
);

create index if not exists ix_legal_acceptance_events_user_id
    on public.legal_acceptance_events(user_id);
create index if not exists ix_legal_acceptance_events_organization_id
    on public.legal_acceptance_events(organization_id);
create index if not exists ix_legal_acceptance_user_time
    on public.legal_acceptance_events(user_id, accepted_at);

alter table public.legal_policy_versions enable row level security;
alter table public.legal_acceptance_events enable row level security;

comment on table public.legal_acceptance_events is
    'Append-only server-managed evidence of versioned policy acceptance.';

update alembic_version
set version_num = '0013_legal_acceptance'
where version_num = '0012_inventory_audits';

commit;


