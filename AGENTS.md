# DoobieLogic Engineering Instructions

## Project

This repository is the DoobieLogic cannabis operations platform. The production application is a **React frontend + FastAPI backend + PostgreSQL/Supabase** system. Legacy Streamlit modules remain as compatibility/reference surfaces while migration parity is protected; they are not the architecture target for new operator-facing work.

DoobieLogic spans retail inventory and purchasing, cultivation, production/manufacturing, extraction, packages/labels/COAs, traceability, wholesale/commercial operations, finance/reporting, customer/storefront workflows, integrations, enterprise controls, and provider-neutral AI assistance.

Read `PLAN.md`, `docs/BACKOFFICE_SCOPE.md`, `docs/PERFORMANCE_CONTRACT.md`, and `docs/CANONICAL_OPERATIONS_FOUNDATION.md` before broad architectural changes.

**Also read `docs/PROJECT_INVARIANTS.md` before changing authentication, local execution, Metrc evaluation logic, facility routing, credentials, evaluation scoring, or workbook submission behavior. Those invariants are standing project contract and must not be overridden by stale deployment assumptions or prior chat context.**

## Core engineering rules

- Do not remove, downgrade, or silently hide existing functionality unless explicitly instructed.
- Preserve approved **UX, UI, navigation, terminology, mobile behavior, and operator workflow** during backend/performance refactors unless a UX change is separately requested.
- Keep one canonical source of truth per operational domain. Do not create competing inventory, production, package, customer, compliance, or financial ledgers to make a screen easier to build.
- Material state changes must remain durable, tenant-scoped, permissioned, auditable, and recoverable.
- External traceability systems such as Metrc/BioTrack are regulated adapters, not DoobieLogic's primary operational database.
- AI may analyze, explain, recommend, and draft. Deterministic services validate and execute approved mutations. Do not give an LLM an unconstrained mutation path.
- Keep modules separated by concern and prefer compatible additive changes over destructive rewrites.
- Do not hardcode a single AI provider into business logic; use the provider-neutral AI runtime.

## Canonical operations foundation

- Use `modules/canonical_cannabis.py` to translate external/provider terminology at integration boundaries. Do not rename authoritative domain tables to mirror Metrc, BioTrack, Dutchie, a lab, or another vendor.
- Keep `modules/material_lineage` as the canonical material-transformation graph. Inventory quantity remains authoritative in the append-only inventory transaction ledger; genealogy explains relationships rather than becoming a second balance ledger.
- Keep `coman_audit_events` as the general operational audit ledger. New material workflow writers should use `modules/coman/audit.py` so provenance, source, correlation ID, and before/after context are structured without breaking legacy readers.
- Reuse one correlation ID across related steps when a workflow crosses domains, such as purchase order -> manifest -> receiving -> COA/release -> inventory/accounting.
- Traceability providers use the common contracts in `modules/traceability/provider_contract.py`, but provider capability declarations never authorize a mutation. Existing permission, mapping, write-contract, queue, readback, and reconciliation gates remain mandatory.
- COA/lab integrations feed the existing structured inventory-quality pipeline. Label Studio resolves verified structured values from that pipeline and genealogy; do not create lab-specific label truth stores.
- RFID/NFC/scanners and AI agents are provenance sources, not privileged mutation paths. Their reviewed actions must still pass deterministic domain services and the same authoritative ledgers as human actions.
- Prefer a modular monolith with clean domain boundaries. Split deployment units only from measured operational need, not to imitate another ERP's microservice count.

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

## Mandatory PC-hosted delivery

Nelson's standing delivery requirement, recorded September 23, 2026: **the PC-hosted release is part of every authorized application change, not an optional follow-up after GitHub work.** Read `docs/PRODUCTION_DEPLOYMENT.md` before release work.

- The finish line is validated source -> integrated release candidate -> actual Windows-PC release -> verification through `ops.doobielogic.io`. A commit, PR, merge, CI pass, or downloadable handoff alone is not a completed application delivery.
- After applicable final-candidate gates pass, continue through the established authorized PC release procedure. Do not routinely ask Nelson to repeat an already authorized deployment request. Respect explicit review-only, no-deploy, maintenance-window, or other scope restrictions.
- Preserve the PC/Cloudflare Tunnel/Caddy/FastAPI architecture and existing hosted Supabase auth/data. Do not substitute Render, Cloud Run, new hosting charges, a new Supabase project, or a replacement user identity.
- Verify the exact deployed frontend/API release identities, local health/readiness, and the affected authenticated public workflow. A passing GitHub build is not evidence of what the PC is serving.
- Use `RELEASED_VERIFIED` only after observed deployment and public acceptance. Until then use `CODE_READY`, `RELEASE_PENDING_PC`, `RELEASE_BLOCKED`, or `ROLLED_BACK`, with the exact unfinished gate.
- If PC access is absent/offline or a release gate fails, keep the release open and identify the concrete blocker. Never bypass authorization, expose secrets, force a broken release, silently change hosting, or claim that deployment happened. Resolve delivery blockers before starting unrelated feature work.
- Discover and verify a protected, owner-authorized machine connection before attempting PC execution. Do not assume a self-hosted runner exists or expose the production PC to untrusted PR workflows. Never install persistent access or relax protection silently.
- Preserve uncommitted workstation changes, local-only launchers/configuration and a recoverable previous release. Do not blindly reset the working tree or reverse production migrations.
- Documentation-only updates may be reported as `DOCUMENTATION_UPDATED`; they do not require a production restart and must not be reported as an application release. Every application-delivery handoff must carry the actual release status and remaining PC acceptance gates.
