# Compliance walkthrough audit

Status: CODE_READY for lead integration. Documentation implementation only; no deployment or browser acceptance claimed.

Implemented `complianceWalkthroughs: HelpWalkthroughRegistry` in `frontend/src/lib/help/compliance.ts`: 10 guides, 63 action steps, 128 field descriptions, and 31 troubleshooting cases. All seven original Compliance guide paths remain covered. New guides separately document three substantial existing sub-workspaces.

## Coverage

| Help path | Active application path |
| --- | --- |
| `/help/compliance` | `/compliance` |
| `/help/compliance/qa` | `/compliance/qa` |
| `/help/compliance/traceability` | `/compliance` |
| `/help/compliance/state-actions` | `/compliance/actions` |
| `/help/compliance/label-studio` | `/compliance/labels?labelMode=create` |
| `/help/compliance/label-history-reprints` (new) | `/compliance/labels?labelMode=history` |
| `/help/compliance/advanced-labelguard` (new) | `/compliance/labels?labelMode=advanced` |
| `/help/compliance/facility-coa-library` (new) | `/compliance`, Facility COA Library section |
| `/help/compliance/product-name-mapper` | `/compliance/nomenclature` |
| `/help/compliance/ma-flower-equivalency` | `/compliance/ma-flower-equivalency` |

## Source verification

Each guide contains its own existing repository-relative `sourceFiles` list. Inspected sources include:

- Routing and navigation: `frontend/src/App.tsx`, `frontend/src/components/AppShell.tsx`, `frontend/src/lib/workspaceRoutes.ts`.
- Traceability and attention: `frontend/src/pages/CompliancePage.tsx`, `frontend/src/components/RegulatoryIntelligencePanel.tsx`, `frontend/src/components/StreamlitDialog.tsx`, `backend/app/routers/compliance.py`, `backend/app/services/regulatory_intelligence.py`, `modules/traceability/backoffice.py`, `modules/traceability/repository.py`.
- State Actions: `frontend/src/pages/TraceabilityActionsPage.tsx`, `backend/app/routers/traceability_actions.py`, `modules/traceability/global_ledger.py`.
- Label creation/history: `frontend/src/pages/LabelStudioWorkspacePage.tsx`, `frontend/src/components/InventoryDrivenLabelWorkflow.tsx`, `frontend/src/components/LabelRunHistory.tsx`, `frontend/src/components/LabelLayoutEditor.tsx`, `frontend/src/components/labelDesign.ts`, `frontend/src/lib/labelReprints.ts`, `backend/app/routers/label_printing.py`, `modules/label_studio_workflow.py`, `modules/label_design.py`.
- Advanced labels and certificates: `frontend/src/pages/LabelStudioPage.tsx`, `backend/app/routers/control_tower.py`, `modules/operational_moats/service.py`, `modules/inventory_quality/coa.py`, `modules/inventory_quality/lineage_resolution.py`, `backend/app/services/label_studio.py`, `backend/app/services/label_studio_fast.py`.
- Q&A: `frontend/src/pages/ComplianceQAPage.tsx`, `backend/app/routers/compliance_qa.py`, `compliance_engine.py`.
- Name mapping: `frontend/src/pages/NomenclatureMapperPage.tsx`, `backend/app/routers/parity_tools.py`, `services/nomenclature_mapper.py`, `services/nomenclature_store.py`.
- Equivalency: `frontend/src/pages/MAFlowerEquivalencyPage.tsx`, `modules/ma_flower_equivalency/logic.py`.

## Corrections to old help

- Traceability actually opens Queue & Reconciliation, with an explicit read-only regulatory attention check, facility certificate library, status/provider filters, and transaction inspector.
- State Actions records local intents. Its active page has no provider-dispatch button. The catalog's presence is not proof of dispatch support. Accepted and verified remain distinct. Prepare safe retry requeues an existing eligible exception; Mark reviewed records an exception resolution without claiming provider success.
- Label preview creation saves a run snapshot. It does not reserve, consume, or validate the availability of production material. Tag assignment and later label-run stages do not create or release a provider package.
- History reopens saved facts and design independently of current inventory/Product Master/COA. Reprint ranges preserve original numbering. Archived and incomplete historical snapshots cannot be reprinted. Browser print requests are recorded before physical output is known.
- Advanced LabelGuard is a testing-label review with packaging-only rules excluded. WARNING blocks its print control. COA readiness is separate from PASS. Its direct browser print path does not create a production label-history run.
- Facility COA Library is the normal PDF intake path, including storage before inventory exists. Matching, pending fallback confirmation, inherited evidence, and saved label snapshots are described separately. Upload alone is not compliance approval.
- Product Name Mapper uses organization-wide naming records, replaces the catalog on explicit save, reviews new naming drafts, remembers confirmed mappings, and exports a one-column workbook. It does not rename external products directly.
- MA Flower Equivalency has category-specific grams/milligrams/count inputs, a manual calculation button, and clipboard output. No live package write is implied and no current legal threshold is asserted.

## UI and validation issues for the lead

1. `CompliancePage` displays Cancel action for Submitted and Accepted, but `VALID_TRANSITIONS` rejects cancellation from those states. The article documents the server-allowed states rather than promising all visible cancellation buttons work.
2. Advanced template-builder changes to required fields or source citation do not reset an existing review result in the same way field/template selection changes do. The article instructs a fresh review after rule changes. Browser verification and any fix belong to the lead.
3. MA numeric edits leave the previous result visible while the breakdown renders current input text. Q&A filter/question edits likewise leave the previous answer visible. Articles explicitly require resubmission after edits.
4. Advanced template and COA controls, and the Q&A uploader, may be visible to roles the server rejects. Articles distinguish control visibility from authorization.
5. Tag assignment can use local uniqueness only when there is no supported mapped environment or no synchronized tag inventory. It is not live provider acceptance. The restricted DEV sandbox test pass is called out as test evidence only.
6. The COA library requests up to 250 rows and has no search/pagination controls. A stored unlinked certificate can resolve by tag later; the article asks for Label Studio readback rather than promising the library row automatically changes to Matched on a particular schedule.
7. The transaction selector labels entries by status, operation, and entity, without displaying transaction ID. Duplicate intents can be hard to distinguish. The instructions warn against blind resubmission and direct review of attempt/lifecycle evidence.
8. Advanced template saving defaults to organization scope and retires an active version with the same name. There is no facility-only option in this UI.
9. Q&A source parsing substitutes today's date for an invalid `last_updated`. The guide tells source owners to supply valid reviewed dates; it does not describe the substituted date as authoritative freshness evidence.

## Verification and handoff

- Passed a scoped TypeScript check using the existing local compiler with `--noEmit --strict --skipLibCheck`, targeting only `frontend/src/lib/help/compliance.ts` and its type import. No build output was written.
- Evaluated the registry in memory to check required fields, category IDs, nonempty steps/completion/source lists, globally unique kebab-case step IDs, at least two troubleshooting cases per guide, source-file existence, and absence of em dashes.
- No browser testing, screenshots, image assets, uploads, printing, state-system writes, credential/provider changes, installs, commits, or releases were performed.
- Only the assigned registry and this report were written. Shared integration, search/SEO/navigation, screenshot evidence, and final acceptance remain with the lead.
- Suggested real captures: source/product/quantity selection and readiness; saved preview/layout editor; tag assignment state; history filters and saved replacement range; Advanced LabelGuard source relationship and review findings; COA library link status; transaction tabs and human-review controls; State Actions scope fields and queued-result boundary. Use real authorized test data and show the controls teaching each action.
