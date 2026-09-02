# DoobieLogic Engineering Instructions

## Project

This repository is the DoobieLogic cannabis operations platform. The production application is a **React frontend + FastAPI backend + PostgreSQL/Supabase** system. Legacy Streamlit modules remain as compatibility/reference surfaces while migration parity is protected; they are not the architecture target for new operator-facing work.

DoobieLogic spans retail inventory and purchasing, cultivation, production/manufacturing, extraction, packages/labels/COAs, traceability, wholesale/commercial operations, finance/reporting, customer/storefront workflows, integrations, enterprise controls, and provider-neutral AI assistance.

Read `PLAN.md`, `docs/BACKOFFICE_SCOPE.md`, and `docs/PERFORMANCE_CONTRACT.md` before broad architectural changes.

## Core engineering rules

- Do not remove, downgrade, or silently hide existing functionality unless explicitly instructed.
- Preserve approved **UX, UI, navigation, terminology, mobile behavior, and operator workflow** during backend/performance refactors unless a UX change is separately requested.
- Keep one canonical source of truth per operational domain. Do not create competing inventory, production, package, customer, compliance, or financial ledgers to make a screen easier to build.
- Material state changes must remain durable, tenant-scoped, permissioned, auditable, and recoverable.
- External traceability systems such as Metrc/BioTrack are regulated adapters, not DoobieLogic's primary operational database.
- AI may analyze, explain, recommend, and draft. Deterministic services validate and execute approved mutations. Do not give an LLM an unconstrained mutation path.
- Keep modules separated by concern and prefer compatible additive changes over destructive rewrites.
- Do not hardcode a single AI provider into business logic; use the provider-neutral AI runtime.

## Performance requirements

Performance is part of the product contract. Follow `docs/PERFORMANCE_CONTRACT.md`.

- Do not introduce per-row HTTP requests or per-row SQL queries for list/planning surfaces.
- Prefer bounded summary/read-model endpoints, set-based SQL, grouped aggregates, and detail-on-demand hydration.
- Do not load COA bodies, genealogy, event history, generated QR/barcode assets, or other expensive detail for every row when the UI only needs a selector/list summary.
- Do not put Metrc, AI, payment, or another external provider on routine workspace critical paths unless the view explicitly requests live-provider data.
- Do not solve application N+1 behavior by increasing Cloud Run/database resources first.
- Preserve the visible UI while optimizing internals unless the task explicitly calls for a UI change.

## Compliance and traceability guardrails

Compliance answers must rely on reviewed/retrieved source material rather than model memory. Where the product presents a compliance answer, preserve its required state/jurisdiction, medical/adult-use scope, citation/source URL, last-updated information, and confidence/review status.

Never invent regulations. Do not claim an external traceability mutation succeeded until the provider response and required readback/reconciliation confirm it. Provider-changing actions remain fail-closed when an exact supported contract has not been validated.

## Tenant and security requirements

- Every operational read/write must preserve organization/facility/license scope.
- Never expose secrets, API keys, database URLs, production exports, customer manifests, or credentials in source, logs, fixtures, or browser payloads.
- Keep authorization checks in deterministic server-side code.
- Do not weaken RLS/server-side tenant enforcement or authentication boundaries for convenience or performance.

## Quality and release expectations

- Keep React/FastAPI parity and current operator acceptance behavior green.
- Add regression coverage for material workflow or performance changes.
- Database changes must follow the repository migration rules and remain rolling-deployment safe.
- A change is not complete because the page renders: functionality, permissions, auditability, realistic-data performance, mobile/browser behavior, migrations, and failure/recovery paths must still pass their applicable gates.
