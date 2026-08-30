alter table public.traceability_transactions
    add column if not exists jurisdiction varchar(16) not null default '',
    add column if not exists environment varchar(24) not null default '',
    add column if not exists direction varchar(16) not null default 'outbound',
    add column if not exists last_attempt_at timestamptz,
    add column if not exists retry_eligible boolean not null default false,
    add column if not exists local_state_json text not null default '{}',
    add column if not exists provider_state_json text not null default '{}',
    add column if not exists readback_result_json text not null default '{}',
    add column if not exists mismatch_reason text not null default '',
    add column if not exists reconciliation_evidence_json text not null default '{}';

create index if not exists ix_traceability_tx_reconciliation
    on public.traceability_transactions(organization_id, facility_id, retry_eligible, status);

update public.alembic_version
set version_num = '0056_trace_reconciliation'
where version_num = '0055_receiving_preflight';
