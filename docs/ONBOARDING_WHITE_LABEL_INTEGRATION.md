# White Label onboarding/reporting integration verification

Status: **CODE_READY — local candidate only**. No push, PR, merge, deployment,
hosting/DNS change, Windows Scheduled Task, POS, or Dutchie Live was performed.

Base: `0123cfb0b6b461a9727aa558fff6f8138543ef3d`.
Onboarding source: `8beb71cbb4e7a99fcb97f42f8a7e686e471f2016`.
Only the Integration Wizard delta from
`e9a5c00645c4da5ab5eb510601313fdc4573baae` was cherry-picked.

Single migration head: `0083_onboarding_reporting`, directly after
`0082_white_label_execution`. No wizard migration was introduced.

The rebase had one content conflict in `frontend/src/pages/HomePage.tsx`.
Both Home actions (Work Queue and Implementation Readiness) are retained. An
encoding mismatch detected by a source-contract test was corrected against the
base's original UTF-8 text. The wizard cherry-pick had no conflicts.

Readiness stores a nullable canonical user FK with the existing Work assignment
eligibility rules. Owner names are batch-projected for display. Readiness metadata
does not duplicate Work lifecycle fields. An explicit action creates Work and the
annotation reference transactionally; subsequent clicks reuse it. Work completion
does not override observed readiness evidence. Optional platform services remain
visible but do not count as required provider blockers.

Report subscriptions and receipts retain durable, idempotent processing, visible
deferred/failed/uncertain outcomes and validated Spacemail dispatch. Existing
`reports.export` permissions now also gate subscription creation and delivery.
Admin/DEV role gates remain in place. Migration rollback refuses to discard
evidence, and PostgreSQL RLS/browser-role revocations remain intact.

## Validation

- 248 backend cases passed across the focused domain, integration, security,
  migration and downstream source-contract selection. The initial broad run had
  247 passes and the Home encoding failure; the corrected source contract and
  readiness/wizard selection then passed all 35 cases.
- All 135 frontend unit tests across 28 files passed.
- Frontend ESLint and TypeScript/Vite production build passed.
- Four Edge browser acceptance cases passed at 1280px and 390px via
  `playwright.adoption.config.ts`: wizard configuration save/secret clearing,
  durable resume, optional skip, validation failure, canonical owner selection,
  explicit Work linking, report idempotency headers, deferred history and pause
  persistence. No overflow or browser exceptions were observed in the new
  readiness/report checks. Mobile screenshots were visually inspected.
- `git diff --check` passed.

Backend selection: `test_onboarding_reporting`, `test_integration_wizard`,
`test_doobie_work`, `test_white_label_execution`, `test_wholesale_crm`,
`test_enterprise_permissions`, `test_native_integrations_api_security`,
`test_native_integrations_production`, `test_web_integration_exact_parity`,
`test_executive_reports`, `test_web_executive_report_pack_parity`,
`test_migration_revision_contract`, `test_migration_revision_capacity`,
`test_security_migration_rollback`, `test_api_security_posture`,
`test_final_streamlit_surface_contract`, `test_ux_routing_contract`, and
`test_parity_phase_1_8_closure`.

## Remaining release gates

No local integration blocker remains. Browser acceptance uses isolated API
fixtures; it does not establish live-provider or authenticated public acceptance.
PostgreSQL migration application, live Spacemail delivery, authenticated public
workflow acceptance and PC deployment were intentionally not performed under the
explicit no-deploy instruction. PostgreSQL migration SQL and browser-role controls
were verified offline; migration/model parity and evidence-preserving rollback
were exercised with SQLite. Unattended reports still need an authorized caller
of the existing due-run endpoint; saving a subscription does not install a timer.

## Files changed from the White Label base

- backend/app/main.py
- backend/app/routers/adoption.py
- backend/app/services/adoption_models.py
- backend/app/services/implementation_readiness.py
- backend/app/services/integration_wizard.py
- backend/app/services/scheduled_reports.py
- docs/DOOBIE_WORK.md
- docs/INTEGRATION_WIZARD.md
- docs/ONBOARDING_REPORTING.md
- docs/ONBOARDING_WHITE_LABEL_INTEGRATION.md
- frontend/e2e/fixtures/integration-wizard-entry.tsx
- frontend/e2e/fixtures/integration-wizard.html
- frontend/e2e/integration-wizard.spec.ts
- frontend/e2e/onboarding-reporting.spec.ts
- frontend/playwright.adoption.config.ts
- frontend/src/App.tsx
- frontend/src/components/AppShell.tsx
- frontend/src/lib/workspaceRoutes.ts
- frontend/src/pages/AdoptionPages.test.tsx
- frontend/src/pages/HomePage.tsx
- frontend/src/pages/ImplementationReadinessPage.tsx
- frontend/src/pages/IntegrationWizardPage.test.tsx
- frontend/src/pages/IntegrationWizardPage.tsx
- frontend/src/pages/IntegrationsPage.tsx
- frontend/src/pages/ScheduledReportsPage.tsx
- frontend/src/pages/adoption.css
- migrations/versions/0083_onboarding_reporting.py
- tests/test_integration_wizard.py
- tests/test_onboarding_reporting.py
- tests/test_white_label_execution.py
- tests/test_wholesale_crm.py
