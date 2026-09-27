# Operations walkthrough audit

Status: documentation implementation complete for lead integration. No browser testing, screenshots, production actions, provider calls, account creation, or database changes were performed.

Output: `frontend/src/lib/help/operations.ts`, exporting `operationsWalkthroughs: HelpWalkthroughRegistry` from the existing `./types` contract. Contains 18 guides and 110 steps. No shared files were edited.

## Coverage

| Help route | Active application route / surface |
| --- | --- |
| `/help/getting-started` | `/home`, sign-in and shell access context |
| `/help/home` | `/home` |
| `/help/home/work-queue` | `/work`, restored live guide |
| `/help/home/control-towers` | `/home/control-tower` and `/home/enterprise` |
| `/help/home/labelguard` | `/home/control-tower`, LabelGuard tab, new |
| `/help/home/sop-control` | `/home/control-tower`, SOP Control tab, new |
| `/help/reports/sales-category-trends` | `/reports/sales-category-trends` |
| `/help/reports/executive` | `/reports/executive` |
| `/help/reports/scheduled` | `/reports/scheduled`, new |
| `/help/reports/insights` | `/reports`, new |
| `/help/settings/location` | `/settings/location`, Facility Setup |
| `/help/settings/imports-data` | `/settings/data`, retail intake/readiness/history |
| `/help/settings/import-production-data` | `/settings/data`, production intake, new |
| `/help/settings/admin` | `/settings/admin` |
| `/help/settings/integrations` | `/settings/integrations` |
| `/help/settings/integration-wizard` | `/settings/integration-wizard`, new |
| `/help/settings/implementation` | `/settings/implementation`, new |
| `/help/doobie-agent` | shell WorkspaceAgent and `/doobie` Action Center |

All ten existing assigned articles remain represented. Existing category IDs are used. Every guide has prerequisites, concrete steps and visible results, completion checks, at least two troubleshooting cases, and repository-relative source evidence. Inputs have field guidance where covered, with safe synthetic examples and no secrets. Conditional labels and dynamic provider/field names are described as conditional rather than invented fixed controls.

## Sources

Route/navigation authority: `frontend/src/App.tsx`, `frontend/src/lib/workspaceRoutes.ts`, `frontend/src/components/AppShell.tsx`. Existing `helpContent.ts` was used as coverage inventory only.

UI sources: `AuthGate.tsx`, `GlobalSearch.tsx`, `WorkspaceAgent.tsx`, `WorkspaceWindow.tsx`, `Product360Drawer.tsx`, `UserPermissionManager.tsx`, `RetailRegulatoryState.tsx`, `KnowledgeLibraryCard.tsx`, `CultivationConnections.tsx` under `frontend/src/components`; `HomePage.tsx`, `WorkQueuePage.tsx`, `OperationsControlTowerPage.tsx`, `EnterpriseControlPage.tsx`, `BuyerTrendsPage.tsx`, `RetailInsightsPage.tsx`, `ExecutiveReportsPage.tsx`, `ScheduledReportsPage.tsx`, `DataSettingsPage.tsx`, `AdminPage.tsx`, `AdminToolsPage.tsx`, `LocationSettingsPage.tsx`, `IntegrationsPage.tsx`, `IntegrationWizardPage.tsx`, `ImplementationReadinessPage.tsx`, `DoobiePage.tsx` under `frontend/src/pages`.

Server evidence: `account.py`, `home.py`, `work.py`, `buyer_parity.py`, `retail_insights.py`, `executive_reports.py`, `adoption.py`, `data_hub.py`, `extraction_parity.py`, `admin.py`, `admin_user_create.py`, `location_settings.py`, `integrations.py`, `native_integrations.py`, `control_tower.py`, `enterprise_control.py`, `ai_agents.py`, `doobie.py` under `backend/app/routers`; `backend/app/schemas/work.py`; `work.py`, `integration_wizard.py`, `implementation_readiness.py`, `scheduled_reports.py` under `backend/app/services`; `modules/data_hub_repository.py`. Individual articles list their relevant source files.

## Material differences from old help

- Work Queue is a live persistent facility workflow. Recurring templates generate due work on request; they are not an automatic browser scheduler. UTC schedule behavior and local display are explained.
- Data Hub uses Readiness, Import Retail Data, Import Production Data, and History. Retail inspection is separate from publication; replacement changes the active revision. Production intake appends extraction runs and has separate defaults, mapping confidence, and deduplication behavior.
- Normal Create User provisions the authentication identity and app access together. Optional email, 12-character temporary password validation, role/organization changes resetting facility checks, no-facility access, and separate permission overrides are documented. No direct Supabase manipulation is suggested.
- Location opens Facility Setup, including deliberate live reads, reviewed provider changes, permission introspection, and local receiving defaults. Auto-map only reuses approved mappings.
- Integration Wizard and Implementation Readiness are distinct live routes. Connection validation, mapping, manual attestation, and operational evidence aren't interchangeable. Readiness task creation doesn't copy Owner/Target date to queue assignment/due time.
- Scheduled Reports actually sends mail for Test delivery. First delivery is one cadence from creation; due processing is explicit or through an authorized scheduler. Mail acceptance is distinct from recipient receipt, and uncertain outcomes require review.
- `/reports` remains live as Reports & Insights but is separate from the standard Sales & Category Trends submenu destination. Its CSV export varies by tab; delivery export contains receipts, not before/after detail.
- Doobie Agent is contextual and can report narrowly authorized applied actions. The `/doobie` route is an Action Center, not the conversational window. Conversation clear doesn't undo business actions.
- Company Executive Pack is scoped to the selected organization/facility, not an implied multi-site consolidation. Buyer controls and repack contribution have session-specific inputs.

## UI issues and limits for the lead

1. **Metrc environment mismatch:** `IntegrationsPage.tsx` saves only state, license number, and key from its METRC card. `MetrcSave.environment` defaults to `production`, and `save_metrc` persists it. The card is shown in Metrc Sandbox mode but offers no Environment input. The guide calls out this risk and does not tell users to resave sandbox connections through that form. Verify/fix before capturing or teaching new sandbox credential setup. No credentials were read or changed.
2. **SOP scope mismatch:** SOP Control submits `activate: true` but omits `facility_specific`; the schema defaults it to false, creating organization-wide scope. The new SOP guide explicitly identifies organization scope and immediate activation. There is no draft save or scope selector in this form.
3. **Dutchie Live limitation:** `buyer_parity._require_available_data_mode` rejects Dutchie Live as unimplemented. The Trends UI still points users to Inventory Dashboard. Guides instead describe the actual active Data Hub sources and Uploads mode.
4. **Production mapping limitation:** the extraction import UI exposes mapping controls only below confidence 0.75. The guide directs users to correct/reinspect a bad higher-confidence file rather than inventing an always-available mapping editor. Numeric preview conversion can display invalid numbers as zero, making explicit preview review important.
5. **Action Center visibility:** the tower truncates preview JSON and does not visibly render its approve/execute/reject mutation errors. The guide directs full review to the `/doobie` modal and avoids promising an error banner for tower decisions.
6. **Navigation mismatch:** `primaryCategory` doesn't list Integration Wizard in its Settings classification. Its route is valid and it is present in settings links, but active-category presentation may be inconsistent. `/reports` has no separate standard Reports submenu item. The guides give real route access rather than inventing a sidebar button.
7. **AI evidence limits:** WorkspaceAgent renders source summaries and freshness but not always source URLs or full legal review metadata. It displays bounded subsets of sources/actions/warnings. The guide doesn't promise complete citation details or automatic provider acceptance.
8. **Bounded views:** Home displays eight inbox items; Work Queue pages contain 50 tasks with at most 500 offered assignees; trends tables return at most 500 rows; scheduled delivery history pages contain 50 entries and processing handles ten due subscriptions per request.
9. **Specialized surfaces:** embedded cultivation integration management, knowledge publication, DEV facility/storefront ownership tools, and the tower's cultivation/commerce mutation forms are present. This implementation documents the assigned cross-cutting workflows and adds LabelGuard/SOP guides; the lead should coordinate specialized cultivation, compliance, and commercial capture/article ownership rather than duplicating their full workflows here.

## Verification

- Read-only TypeScript compiler API check against `operations.ts` and the current `types.ts`: zero diagnostics, no output emitted.
- In-memory registry inspection: 18 articles, 110 steps, no duplicate step IDs within an article, all step IDs kebab-case, no em dashes, and every `sourceFiles` path exists.
- No install, full application build, browser test, screenshot generation, commit, or deployment was performed. Lead still owns registry integration, navigation/search/SEO, real action-specific captures, and any release gates.
