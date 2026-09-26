# Cultivation system audit and reuse map

Audit checkpoint: 2026-09-26. Authoritative fetched origin/main and committed worktree baseline: `24b615def545e6c7103e55e1d4f27d4a11b93e16`, schema `0085_cultivation_telemetry`. A stale local branch named main is not the release reference. Separate bounded read-only audit and security reviews informed the expansion implementation.

## Canonical components to extend

| Domain | Existing authoritative files and behavior |
|---|---|
| Plants, lifecycle and rooms | `modules/cultivation/models.py`, `service.py`, `bulk.py`; plant phase/room events, active plants, room capacity and estimates. Plants currently use room_code, whereas environmental observations use canonical room UUIDs. |
| Nursery and genetics | `batch_models.py`, `batches.py`; plant groups/members, mother/source-plant links, scoped atomic group operations. Do not introduce a second mother or plant-group registry. |
| Harvest | `modules/operational_moats/models.py::CultivationHarvest` plus `CultivationHarvestPlant`; wet/dry/waste actuals and material-closeout guards. There must not be a competing crop-cycle harvest ledger. |
| Post-harvest | `modules/cultivation/post_harvest.py`, `backend/app/routers/production_mutations.py`; batch state, weights and stage history with sequential/reconciliation safeguards. |
| Material lineage | `modules/material_lineage`; canonical harvest allocation, transformations, inputs, outputs and losses. Inventory quantities remain in `modules/coman/models.py::InventoryTransaction`. |
| Costs and labor | `CultivationCostEntry` supports plant/room/harvest labor, material and overhead. Production and extraction have their own canonical actual/cost events. Cycle summaries require attribution, not copied totals or double-counting. |
| Quality | `modules/inventory_quality/{models,service,coa,lineage_resolution}.py`; structured lab/COA and lot evidence. Neither telemetry nor AI may create substitute lab truth. |
| Extraction and commercial | `modules/extraction/material_backbone.py`, repository/closeout services, `modules/commercial/repository.py`; use exact canonical lot/run/order allocations for downstream relationships. |
| Existing environmental telemetry | `modules/cultivation/telemetry.py`, `telemetry_models.py`, `backend/app/routers/cultivation_telemetry.py`; validated manual batches, idempotency/conflict checks, room targets, bounded stream snapshots and explicit exception-to-Work. |
| Work and audit | `backend/app/services/work.py`, `modules/coman/audit.py`; canonical task lifecycle and transaction-scoped operational evidence. Cultivation must not create an independent task status ledger. |
| Credentials | `modules/integrations/models.py`, `service.py`; encrypted server-side integration secrets and audited configuration. Provider allowlists and safe public projections must be explicitly extended. |
| Forecasts, reports and AI | `backend/app/services/cultivation_intelligence.py`, `reports/cultivation_report.py`, `docs/CULTIVATION_AGENT_KNOWLEDGE.md`, `services/ai`; retain deterministic forecast and grounded context boundaries. |

## Existing operator and API surfaces

`CultivationOpsPage.tsx` composes canonical plant/room/nursery/harvest work, post-harvest handoff and room telemetry. `PlantInventory.tsx` includes `CultivationToday`, `CultivationBatchManager`, `CultivationOperationsControl`, `CultivationIntelligencePanel`, `CultivationRegulatoryHealth` and Plant360. Preserve all of these workflows and the cultivation capability navigation entry.

Most cultivation APIs are below `/api/v1/inventory/production/plants`: plants, groups, bulk transitions, rooms, harvests, costs, lineage, intelligence and telemetry. Intelligence is composed through the inventory reconciliation router. Post-harvest, material-lineage, Metrc cultivation/harvest and report endpoints remain separate canonical boundaries. Use actual registered routes, not guessed aliases.

## Initial draft defects found before integration

The initial uncommitted scaffold had no successor migration/model registration, erased original units on the HTTP/Pydantic path, trusted unvalidated enriched entity references, omitted connection identity from streams, and expanded the backend metric set beyond the React table's supported keys. An actual isolated baseline test run failed at metadata setup with `NoReferencedTableError` for `cultivation_environment_observations.cycle_id` referencing unregistered `cultivation_crop_cycles`. That failure was observed, not a proposed test.

The draft Growlink client also accepted arbitrary HTTPS destinations and authentication headers with default redirect handling. Its guessed response schemas and unconditional capabilities did not constitute a verified vendor integration. Device mapping was current-only, so delayed data could be attributed incorrectly. The spool had no complete collection/replay/retention path and used payload fingerprints without separate stable event-conflict identity.

These are the starting defects for the repair workstream, not claims that the current implementation still has each defect. Closure requires executable regression results. Original draft and the complete independent reports are retained privately in the PC release-evidence directory; no secrets were inspected for this audit.

## Architectural decisions informed by the audit

- Extend existing telemetry vocabulary and manual routes; preserve canonical-equivalence retry compatibility and first-observed raw provenance.
- New device raw evidence belongs in a local storage tier with durable mapping/quality context and bounded aggregate publication, not high-frequency cloud rows.
- Introduce crop-cycle relationships and immutable time-effective recipe/room/device context without replacing plant, harvest, inventory, cost or Work truth.
- Preserve ambiguous/unavailable attribution as explicit unknown evidence. Never choose the first matching cycle as a substitute for a validated relationship.
- Add one forward-safe Alembic successor, preserve existing rows, deny browser-role table access, and test actual runtime grants separately from mocked SQL compilation.
- Compose summary-first Room360/Cycle360, with detail on demand and no live vendor request on routine workspace reads.
- Keep vendor live transport fail-closed until reviewed supported contracts and customer authorization exist; fixture or file import validation is not live API validation.

## Reusable validation

Existing suites inspected: `tests/test_cultivation_telemetry.py`, `test_cultivation_operations_depth.py`, `test_phase4_cultivation_batch_nursery.py`, `test_cultivation_bulk_transition.py`, `test_cultivation_intelligence.py`, `test_cultivation_report_pdf.py`, `test_post_harvest_workflow.py`, `test_post_harvest_api_guards.py`, `test_post_harvest_migration.py`, `test_operator_acceptance_cultivation_production.py` and Metrc cultivation identity/readback/reconciliation suites. Frontend evidence includes `CultivationEnvironmentPanel.test.tsx` and `e2e/cultivation-telemetry.spec.ts`.

Audit inspection is not a passing test result. Release acceptance must also cover raw HTTP/model/dict fidelity, tenant/FK boundaries, immutable mappings/recipes, duplicate/conflict replay, offline restart, retention protection, interval coverage and late data, populated migration, effective permissions and responsive browser workflows. Final source, test and deployment receipts must state their actual scope, SHA and result.
