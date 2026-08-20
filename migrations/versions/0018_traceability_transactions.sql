begin;

create table if not exists public.traceability_transactions (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    provider varchar(24) not null,
    license_number varchar(255) not null default '',
    operation_type varchar(120) not null,
    entity_type varchar(64) not null,
    entity_id varchar(255) not null,
    idempotency_key varchar(255) not null,
    status varchar(32) not null default 'requested',
    request_payload_json text not null default '{}',
    response_payload_json text not null default '{}',
    external_reference varchar(255) not null default '',
    error_code varchar(120) not null default '',
    error_message text not null default '',
    attempt_count integer not null default 0,
    next_attempt_at timestamptz,
    reason varchar(255) not null default '',
    requested_by varchar(255) not null,
    approved_by varchar(255) not null default '',
    requested_at timestamptz not null default now(),
    submitted_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_traceability_tx_scope_idempotency unique (
        organization_id, facility_id, provider, idempotency_key
    ),
    constraint ck_traceability_tx_provider check (
        provider in ('metrc','biotrack','other')
    ),
    constraint ck_traceability_tx_status check (
        status in (
            'requested','validated','queued','submitted','accepted','rejected',
            'verified','reconciliation_required','cancelled'
        )
    ),
    constraint ck_traceability_tx_attempt_count check (attempt_count >= 0)
);

create index if not exists ix_traceability_transactions_organization_id
    on public.traceability_transactions(organization_id);
create index if not exists ix_traceability_transactions_facility_id
    on public.traceability_transactions(facility_id);
create index if not exists ix_traceability_tx_facility_status
    on public.traceability_transactions(facility_id, status, requested_at);
create index if not exists ix_traceability_tx_entity
    on public.traceability_transactions(organization_id, entity_type, entity_id, requested_at);

create table if not exists public.traceability_transaction_attempts (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    transaction_id varchar(36) not null references public.traceability_transactions(id) on delete cascade,
    attempt_number integer not null,
    request_payload_json text not null default '{}',
    response_payload_json text not null default '{}',
    http_status integer,
    error_code varchar(120) not null default '',
    error_message text not null default '',
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    constraint uq_traceability_attempt_number unique (transaction_id, attempt_number),
    constraint ck_traceability_attempt_number check (attempt_number > 0)
);

create index if not exists ix_traceability_transaction_attempts_organization_id
    on public.traceability_transaction_attempts(organization_id);
create index if not exists ix_traceability_transaction_attempts_facility_id
    on public.traceability_transaction_attempts(facility_id);
create index if not exists ix_traceability_transaction_attempts_transaction_id
    on public.traceability_transaction_attempts(transaction_id);
create index if not exists ix_traceability_attempt_tx_time
    on public.traceability_transaction_attempts(transaction_id, started_at);

alter table public.traceability_transactions enable row level security;
alter table public.traceability_transaction_attempts enable row level security;

comment on table public.traceability_transactions is
    'Provider-neutral Buyer Dash state-traceability action ledger with idempotency, lifecycle, retry, and reconciliation state.';
comment on table public.traceability_transaction_attempts is
    'Immutable external submission attempt history for Buyer Dash traceability actions; credentials are never stored here.';

update public.alembic_version
set version_num = '0018_traceability_transactions'
where version_num = '0017_package_studio';

commit;