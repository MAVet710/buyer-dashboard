# DoobieLogic Buyer Dash

DoobieLogic Buyer Dash is a multi-workspace cannabis operations platform built with Streamlit, PostgreSQL/Supabase, pandas, Plotly, and ReportLab.

It supports retail inventory intelligence, purchasing, inventory audits, nomenclature normalization, Co-Man planning and execution, extraction operations, commercial fulfillment, integrations, and executive reporting.

## Product workspaces

- **Operations Home** — role-specific task launcher and readiness status.
- **Retail Operations** — inventory, trends, audits, slow movers, delivery impact, purchasing, compliance, nomenclature, MA flower equivalency, and repack.
- **Production Operations** — Co-Man capacity/scheduling/execution and Extraction Command Center.
- **Commercial Operations** — customers, orders, fulfillment, and margin.
- **Data & Integrations** — guided source imports, extraction partner mapping, source status, history, METRC, Dutchie, and platform integrations.

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for user-facing instructions and [docs/AI_RUNTIME.md](docs/AI_RUNTIME.md) for the provider-neutral DoobieLogic AI Runtime architecture, local inference setup, security model, and benchmark instructions.

## Architecture

- `streamlit_app.py` — Streamlit Cloud entrypoint.
- `app.py` — legacy application composition root. New product work is extracted into modules rather than added inline.
- `modules/` — workspace UI, workflow, and domain behavior.
- `services/` — authentication, tenants, persistence, integrations, normalization, AI runtime, and shared application services.
- `reports/` — Retail and Production executive report generators.
- `migrations/versions/` — Alembic and standalone Supabase SQL migrations.
- `tests/` — unit, architecture, persistence, migration, report, mobile, security, AI-runtime, and workflow regression coverage.

## Local setup

1. Create a Python 3.12 virtual environment.
2. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and configure the required values.
4. Start the application:

   ```bash
   streamlit run streamlit_app.py
   ```

## Required configuration

### Database

`COMAN_DATABASE_URL` must contain the Supabase session-pooler PostgreSQL connection string. Durable users, organizations, facilities, Co-Man, commercial, nomenclature, audits, and legal acceptance use this database.

### License authority

- `DOOBIE_BASE_URL` (or legacy `DOOBIELOGIC_URL`)
- `DOOBIE_API_KEY` (or legacy `DOOBIELOGIC_API_KEY`)

Buyer Dash validates DoobieLogic-issued licenses and supports a bounded cached grace period when the license service is temporarily unavailable.

### Optional integrations

- Dutchie credentials described in `docs/dutchie.md`
- METRC integrator configuration managed by authorized administrators
- DoobieLogic Native AI Runtime local/cloud provider configuration described in `docs/AI_RUNTIME.md`

## Authentication and tenant safety

- Passwords are bcrypt-hashed.
- Durable sessions enforce an idle timeout (`DOOBIE_SESSION_IDLE_MINUTES`, default 90).
- Every durable user has a role and organization assignment.
- Facility roles restrict operational access.
- Production and commercial workspaces fail closed without explicit organization and facility context.
- AI datasets, tools, retrieval, mapping memory, telemetry, cache keys, and browser conversation history remain organization/facility scoped.
- PostgreSQL tables have RLS enabled; server-side service access remains responsible for passing and enforcing tenant identifiers.

Before broad multi-company onboarding, complete the planned move to token/JWT-backed Supabase Auth policies. Do not remove the current authentication path until migration, account linking, rollback, and owner recovery have been tested in staging.

## Data persistence

- Durable operational records live in PostgreSQL/Supabase.
- Retail file sources are staged in the current authenticated application context and reused across Retail Operations.
- The Data Import Center provides an explicit upload → inspect → review → publish flow.
- DEV Sandbox data is isolated from non-demo tenants.

## Database migrations

Apply migrations in order. Every schema change includes:

- an Alembic revision (`.py`), and
- a transaction-safe standalone Supabase SQL migration (`.sql`) when required by the hosted deployment workflow.

Application code must remain backward-safe during rolling deployment. Production migrations require explicit approval and verification.

## Quality checks

Run:

```bash
python -m compileall -q app.py modules services reports tests
python scripts/quality_gate.py
python -m pytest -q
```

GitHub Actions runs compilation, focused quality checks, dependency consistency, the full test suite, frontend lint/tests/build, browser parity, container startup checks, migrations, and security scans on pull requests and pushes to `main`.

## Security

Do not commit secrets, production exports, customer manifests, access tokens, or database URLs. See [SECURITY.md](SECURITY.md) for reporting and deployment expectations.

## Deployment

The React/FastAPI production architecture is validated independently from the legacy Streamlit surface. AI inference is deliberately external to the FastAPI image so local/open-weight model infrastructure can be scaled or replaced independently without affecting normal operational availability.
