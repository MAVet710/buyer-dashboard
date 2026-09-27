# Production walkthrough audit

Status: DOCUMENTATION_UPDATED. Source inspection only. No browser testing, screenshots, provider actions, database access, deployment, or git operations were performed by this task.

Implemented `productionWalkthroughs: HelpWalkthroughRegistry` in `frontend/src/lib/help/production.ts`: 12 guides, 78 steps, and 164 field guidance entries. All eleven existing production-category articles are retained. The additional guide covers the active extraction outputs, QA, costs, and traceability sub-workspace.

## Covered routes

| Help route | Application route |
| --- | --- |
| `/help/production` | `/production` |
| `/help/production/calendar` | `/production/calendar` |
| `/help/production/run-360` | `/production/runs` |
| `/help/extraction` | `/production/extraction` |
| `/help/extraction/outputs-qa` | `/production/extraction` |
| `/help/white-label-repack` | `/production/repack` |
| `/help/package-studio` | `/production/package-studio` |
| `/help/production/inventory` | `/production/inventory` |
| `/help/production/inventory/transfers` | `/production/inventory/transfers` |
| `/help/production/package-360` | `/inventory/packages` |
| `/help/production/products` | `/production/products` |
| `/help/production/inventory-audits` | `/inventory/audits` |

## Sources used

Route and navigation authority: `frontend/src/App.tsx`, `frontend/src/components/AppShell.tsx`, `frontend/src/lib/workspaceRoutes.ts`. Contract: `frontend/src/lib/help/types.ts`. Existing `helpContent.ts` was used only to inventory the eleven required articles.

Production planning and execution: `ProductionPlanningWorkspace.tsx`, `ProductionPlanner.tsx`, `ProductionNextActions.tsx`, `ProductionCalendar.tsx`, `ProductionPage.tsx`, `ProductionPageLegacy.tsx`, `ProductionRun360Page.tsx`, and `ProductionActualMaterials.tsx` under their existing frontend component/page directories. Validation references include `backend/app/routers/production.py`, `production_mutations.py`, `coman_parity.py`, `coman_parity_legacy.py`, `modules/production_erp/scheduling.py`, and `modules/production_erp/run360_mutations.py`.

Extraction: `frontend/src/pages/ExtractionUnifiedPage.tsx`, `ExtractionOperatorWorkspace.tsx`, `ExtractionPage.tsx`, and `ExtractionAnalyticsWorkspace.tsx`; `backend/app/routers/extraction.py`; `modules/extraction/repository.py` and `hardening_hooks.py`.

Repack and package work: `frontend/src/pages/WhiteLabelRepackPage.tsx`, `whiteLabelRepackParity.ts`, `PackageStudioPage.tsx`, `frontend/src/components/WhiteLabelExecutionHandoff.tsx`; `backend/app/routers/white_label.py`, `package_studio.py`; `modules/repack/execution.py`, `modules/package_studio/service.py`.

Inventory and product detail: `frontend/src/pages/InventoryPage.tsx`, `InventoryTransfersPage.tsx`, `Package360Page.tsx`, `ProductMasterPage.tsx`; `frontend/src/components/ProductionReceiveInventory.tsx`, `InventoryTransferManager.tsx`, `FocusedInventoryAudits.tsx`, `InventoryAudits.tsx`, `MetrcPackageControls.tsx`; `backend/app/routers/inventory.py`, `inventory_transfers.py`, `package_360.py`, `product_master.py`, `audits.py`; `backend/app/schemas/inventory.py`, `inventory_transfers.py`; `modules/inventory_audit/repository.py`. Individual articles include repository-relative source lists for their instructions.

## Corrections and limitations compared with old help

- The active Production page is Production Planning with Plan, Calendar, and Operations. New Job and the older operations tabs remain inside Operations. The old overview did not explain this navigation.
- Calendar saves an explicit previewed placement. Its browser-local inputs become UTC timestamps. Its conflict acknowledgement does not release QA or reserve material.
- Run 360 separates planned reservation, physical consumption, planned output, measured actual totals, QA, and costs. Risky changes use previews. Output actuals are totals, not incremental additions.
- Extraction's floor flow uses New run, Plan run & reserve, preflight confirmations, and Start run & consume reserved material. Those actions have different inventory effects. Stage progress, local QA release, and provider acceptance are separate.
- The new extraction output guide documents the actual Outputs + QA, COGS, and Traceability controls. Queued output-package creation is not provider acceptance.
- White Label plans are saved server-side drafts. Approval creates a production handoff without reserving or consuming stock. The source picker does not guarantee source acceptance: saving and approval check availability, units, QA, and COA evidence. Allocations below 100% are allowed and leave material unallocated.
- Package Studio has seven actual actions, positive finished quantities and source equivalents, unique output codes, balance review, and local commit. Metrc tags are references; external sync remains Not requested for this workflow.
- Production receiving and production audit instructions are separate from retail snapshot intake. The production receiving form has no retail upload or COA input.
- Production Package 360 and audits do not have dedicated production URL paths. Their guides use the real shared routes and explain the production entry context.
- No new article was added for every Operations setup tab or every Management & Compliance subsection. Existing eleven-guide coverage is preserved; the additional extraction output article targets the important release workflow. Browser screenshots, search/SEO integration, and authenticated acceptance remain lead-owned.

## Source-visible UI issues for the lead

These are code observations, not browser-confirmed defects. No UI changes were made.

1. Package 360's Inventory button navigates to the general `Inventory` page, which App mounts without the production initial operation. The production help explicitly sends users back through Materials when checking production availability.
2. Focused audit creation refreshes the dashboard but does not select the new audit. The guide tells users to find its name in Audit Dashboard and choose Open.
3. Extraction planning creates a run and reserves the input in separate requests. Starting consumes input lines before a separate stage-start request. Partial success must be inspected before retrying. The guide includes this immediately beside those actions.
4. Extraction start sums source quantities into `input_weight_g` without an explicit conversion in that UI function, while reservation accepts the source base unit. Check non-gram feedstock behavior during acceptance; the guide keeps reservation units distinct from gram-labeled stage fields.
5. Production receiving submits `lab_testing_state: "TestPassed"` and an empty COA reference without presenting either quality field. The guide does not imply that this form establishes reviewed COA evidence or makes material eligible for repack.
6. White Label Step 5 evaluates `coa_status` and `label_review_status`, but the current React form has no controls for those values and defaults both to Needs Review. Source QA acceptance is checked separately by the service. The help doesn't invent a checkbox that clears those checklist rows.
7. Package Studio Source Trail selects from currently available packages, so a depleted source may not be offered. Recent Runs and identifier-based Package 360 remain useful review entry points.
8. Package Studio initializes some editable output products from the first active product. The guide requires an explicit product check rather than treating that default as the intended output.
9. `ProductionActualMaterials` uses a distinct inventory query key, while the Run 360 refresh invalidates other inventory keys. A displayed source balance may need a fresh inventory view after consumption; the guide does not promise that this table itself is refreshed.
10. Calendar displays at most four event buttons per date. More events are represented by a count, not an expansion control. The guide points to the run queue for other records.
11. Source-unit field labels in Package Studio are dynamic. The guide's field entries show the real gram-based labels and explicitly explain that the selected source unit replaces `g`.

## Verification

- Isolated TypeScript check passed using the existing local compiler with `--noEmit --strict --target ES2021 --moduleResolution node --skipLibCheck` against only `frontend/src/lib/help/production.ts`.
- An in-memory registry inspection confirmed 12 guides, 78 unique kebab-case step IDs, 164 field entries, required top-level content, at least two troubleshooting cases per guide, existing source paths, and no em dashes.
- No emitted build files, dependency installation, full application tests, browser sessions, or screenshots were used.
- Release and browser acceptance remain outside this explicitly scoped documentation-subagent task.
