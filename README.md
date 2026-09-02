# DoobieLogic Buyer Dash

DoobieLogic Buyer Dash is a multi-workspace cannabis operations platform. The production application is built around a **React/Vite frontend, FastAPI backend, and PostgreSQL/Supabase durable data layer**. Legacy Streamlit modules remain in the repository as compatibility/reference surfaces while migration parity is protected.

The platform supports retail inventory and purchasing, cultivation, production/manufacturing, extraction, Package/Label Studio, COAs and QA, traceability, wholesale/commercial operations, finance/reporting, customer/storefront workflows, integrations, enterprise administration, and provider-neutral AI assistance.

## Product workspaces

- **Operations Home** — role-specific actions, readiness, exceptions, and shared operational context.
- **Retail Operations** — inventory, buying, purchasing, audits, trends, compliance, receiving, transfers, and product/package work.
- **Production Operations** — planning, calendar, Run 360 execution, cultivation, manufacturing/Co-Man, extraction, Package Studio, inventory, QA, and COGS.
- **Commercial / Wholesale Operations** — customers, sales orders, fulfillment, pick/pack, manifests, invoicing/A/R, storefronts, and customer portals.
- **Compliance & Traceability** — COAs, labels, regulatory workflows, reconciliation, and Metrc/provider integration surfaces.
- **Data, Integrations & Enterprise** — imports, source readiness, provider configuration, organization/facility controls, and administrative tooling.

See `PLAN.md` for the current product mandate, `docs/BACKOFFICE_SCOPE.md` for the application boundary, `docs/PERFORMANCE_CONTRACT.md` for the performance bar, and `docs/AI_RUNTIME.md` for the provider-neutral DoobieLogic AI Runtime.

## Production architecture

- `frontend/` — React 19 + Vite operator, storefront, portal, and marketing surfaces.
- `backend/app/` — FastAPI API, routers, auth context, observability, and application services.
- `modules/` — durable domain models/services for inventory, production, cultivation, commercial, traceability, analytics, and shared workflows.
- `services/` — shared integrations, AI runtime, migration/compatibility logic, and supporting services.
- `reports/` — report/export generation.
- `migrations/versions/` — Alembic and hosted database migrations.
- `tests/` — unit, integration, architecture, security, migration, operator acceptance, performance-contract, and regression coverage.
- `streamlit_app.py` / `app.py` — legacy compatibility/reference surfaces; do not use them as the target for new production UI architecture.

## Local development

### Backend

Create a Python 3.12 virtual environment, install dependencies, configure `.env`, then start FastAPI:

```bash
python -m pip install -r requirements.txt -r backend/requirements.txt
uvicorn backend.app.main:app --reload
```

### Frontend

From `frontend/`:

```bash
pnpm install
pnpm dev
```

Use the configured local API URL/environment expected by the frontend. The hosted production targets are `ops.doobielogic.io` and `api.doobielogic.io`.

Legacy Streamlit can still be started for compatibility/reference work where explicitly required, but it is not the normal production-development target.

## Required configuration

### Database

`DATABASE_URL` / `COMAN_DATABASE_URL` resolves to the PostgreSQL/Supabase connection used for durable operational data. Hosted API connection pooling is deliberately bounded; application N+1 behavior must be fixed in code rather than hidden by increasing the pool.

### Authentication and tenant safety

- Durable users, roles, organizations, facilities, and permissions are enforced server-side.
- Production/commercial/cultivation operations fail closed without valid tenant/facility context.
- AI datasets, tools, retrieval, telemetry, cache keys, and browser history remain tenant scoped.
- PostgreSQL RLS exists as an additional boundary; server-side services still must pass and enforce organization/facility identifiers.

### Optional integrations

- Metrc/provider traceability configuration is managed through authorized integration surfaces.
- Dutchie interoperability is transitional/optional and must not become a permanent system-of-record dependency.
- DoobieLogic Native AI Runtime provider configuration is documented in `docs/AI_RUNTIME.md`.

## Operational architecture rules

- One canonical source of truth per domain.
- Material state changes are durable, permissioned, auditable, and recoverable.
- External traceability providers are regulated adapters, not the primary DoobieLogic database.
- AI may analyze/recommend/draft; deterministic services validate and execute approved mutations.
- Long-running workflows save, stop, resume, and expose state rather than trapping the operator in one request/session.
- Mobile floor workflows are first-class.
- Performance is part of usability: follow `docs/PERFORMANCE_CONTRACT.md`, avoid per-row HTTP/SQL fan-out, and load expensive detail only when the operator needs it.

## Database migrations

Application code and migrations must remain safe for rolling deployments. Production database changes run through the repository's migration/release gates; do not mutate hosted schema manually as a substitute for a migration.

## Quality checks

Backend/repository checks include compilation, quality gates, and pytest. Frontend checks include lint, unit tests, TypeScript/Vite build, real-browser parity, and operator acceptance. GitHub Actions also validates container startup, migrations, release-candidate behavior, and security scans before production cutover.

Useful local checks include:

```bash
python -m compileall -q backend modules services reports tests
python scripts/quality_gate.py
python -m pytest -q
```

and from `frontend/`:

```bash
pnpm lint
pnpm test
pnpm build
```

## Security

Do not commit secrets, credentials, production exports, customer manifests, access tokens, or database URLs. See `SECURITY.md` for reporting and deployment expectations.

## Deployment

Production runs React/FastAPI on Google Cloud Run with PostgreSQL/Supabase. API and web candidates are built and verified before traffic cutover. AI inference is deliberately external to the normal FastAPI image so model infrastructure can be scaled or replaced independently without degrading ordinary operational availability.
