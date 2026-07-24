# Co-Man Database Foundation

Co-Man uses PostgreSQL as its durable source of truth. Streamlit session state
may cache query results and hold unfinished form values, but it must not be the
only copy of production orders, schedules, run history, labor, or audit events.

## Configuration

Set `COMAN_DATABASE_URL` to the Supabase Session pooler connection string on
port 5432 with SSL required. The completed value is a secret and must only be
stored in local Streamlit secrets or the hosting platform's secret manager.

The application fails closed when this value is missing. It does not silently
create a local production database.

## Migrations

Run migrations from the repository root:

```powershell
$env:COMAN_DATABASE_URL = "<secret connection string>"
alembic upgrade head
```

Migration `0010_catalog_nomenclature_mapper` adds the organization-scoped
Dutchie catalog and confirmed METRC nomenclature mapping tables. These tables
use the same durable Supabase/PostgreSQL connection and organization boundary
as the rest of the operations platform.

The first migration creates tenant-scoped organizations, facilities,
customers, machine models, facility machines, production orders, and audit
events. It seeds verified reference entries for the IMA C-1 FILLER, IMA C-1
MAKER, and Massman / General Packer GP-M3000. Manufacturer rates are reference
values; facility-specific effective rates belong on `coman_facility_machines`.

## Safety

- Never commit a database URL.
- Never log database URLs or passwords.
- Use migrations for schema changes; do not call `create_all` from Streamlit.
- Every operational query must be scoped to an organization and, when
  applicable, a facility.
- Every material status change should append an audit event.
