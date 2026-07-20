# Buyer Dashboard Persistence Audit

## Store permanently in PostgreSQL

- Application users, roles, active status, password hashes, and facility access
- Organizations, facilities, customers, and brands
- Co-Man machine catalog and facility-specific performance standards
- Production orders, schedules, labor assignments, production runs, downtime,
  yield, waste, QA holds, and audit events
- White Label / Repack scenarios that are explicitly saved
- Extraction runs, external toll jobs, input lots, outputs, and reconciliation
- Integration configuration metadata and encrypted credentials
- Compliance source metadata, review status, citations, and update history

## Store files in object storage, with metadata in PostgreSQL

- Uploaded inventory and sales exports when the user explicitly saves them
- Delivery manifests, COAs, customer specifications, and finished reports
- Import filename, checksum, uploader, organization, facility, reporting period,
  storage location, processing status, and retention date

Raw reports should not be stored as large database rows. Supabase Storage can be
used later; access policies and retention rules must be added before enabling it.

## Keep temporary

- Unsaved form drafts
- Current filter selections and navigation state
- Derived DataFrames that can be rebuilt from source records
- Chart data and AI prompt context
- Short-lived upload previews

Streamlit session state remains appropriate for these values.

## Migration order

1. Durable application users and facility roles
2. Saved White Label scenarios and extraction/toll operational records
3. Upload metadata plus optional private object storage
4. Integration-secret consolidation and encryption
5. Historical analytics snapshots only where recomputation is too expensive

## Current risks still open

- The main `app.py` is a large monolith and should be split by workspace.
- Existing integration stores fall back to local SQLite and should be moved to
  the shared configured database after credential encryption is introduced.
- Login throttling is currently session-local; persistent rate limiting should
  be added before a wider public launch.
- The free Supabase plan has no production-grade backup guarantee. Scheduled
  exports are required until the deployment moves to a backed-up plan.
