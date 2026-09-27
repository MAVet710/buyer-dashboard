# Cultivation walkthrough audit

Documentation implementation only. No browser testing, screenshots, application mutations, provider access, releases, installs, or git mutations were performed.

## Delivered

- Registry: `frontend/src/lib/help/cultivation.ts`
- Export: `cultivationWalkthroughs: HelpWalkthroughRegistry`
- 10 articles, 63 steps. All categories are `cultivation`.
- Existing articles retained: `/help/cultivation`, `/help/cultivation/post-harvest`.
- New articles: `/help/cultivation/room-360`, `/help/cultivation/environment`, `/help/cultivation/crop-cycle-360`, `/help/cultivation/recipes`, `/help/cultivation/connections`, `/help/cultivation/imports`, `/help/cultivation/evidence-maintenance`, `/help/cultivation/plant-exposure`.
- Application destinations: `/cultivation`, `/cultivation/post-harvest`, and `/settings/integrations?provider=cultivation`. The connections, imports, and maintenance articles deliberately use the real Integrations route rather than inventing a Cultivation tab.

## Source verification

Each article includes its specific repository-relative source files. Main sources inspected:

- Route and contract: `frontend/src/App.tsx`, `frontend/src/lib/workspaceRoutes.ts`, `frontend/src/lib/help/types.ts`.
- Active pages: `frontend/src/pages/CultivationOpsPage.tsx`, `frontend/src/pages/PostHarvestPage.tsx`, `frontend/src/pages/IntegrationsPage.tsx`.
- Plant and harvest UI: `PlantInventory.tsx`, `CultivationOperationsControl.tsx`, `CultivationBatchManager.tsx`, `PostHarvestBoard.tsx`, and supporting cultivation summary component source under `frontend/src/components`.
- Intelligence UI: `CultivationIntelligenceWorkspace.tsx`, `Room360.tsx`, `CurrentRoomConditions.tsx`, `CropCycle360.tsx`, `RecipeEditor.tsx`, `recipeDraftPayload.ts`, `PlantExposure.tsx`, `CultivationConnections.tsx`, `CultivationIntelligenceShared.tsx`, `cultivationIntelligenceTypes.ts`, `cultivationIntelligenceQueries.ts`, and `CultivationEnvironmentPanel.tsx`.
- Server boundaries: `backend/app/routers/cultivation_intelligence_workspace.py`, `cultivation_intelligence.py`, `plants.py`, and `production_mutations.py`; `backend/app/schemas/plants.py`.
- Validation and behavior: `modules/cultivation/intelligence_service.py`, `gateway.py`, `service.py`, `bulk.py`, `post_harvest.py`, `telemetry.py`, and export adapters `adapters/normalized.py`, `adapters/growlink.py`.

## Important differences from the old help

- The old overview's generic "Run the grow" instructions now identify room setup, exact plant actions, atomic bulk changes, and local harvest planning.
- The old Post-Harvest article suggested a release workflow without explaining the actual board boundary. The new article describes append-only current-total measurements, forward stage changes, final reconciliation, and locked corrections. Ready is not inventory creation, laboratory approval, or regulatory release.
- Final Ready validation requires positive source dry weight, output reconciliation within 1 g, and WIP no greater than 1 g. The operational instruction is to record final measured WIP at 0 g. Locked corrections must still satisfy reconciliation.
- Intelligence recipes, room evidence, cycles, connections, imports, and retention were absent from the old coverage inventory.
- No automatic Metrc success, pairing, cloud Growlink authorization, hardware control, or automatic Work creation is promised. Local harvest planning remains distinct from regulated execution.
- Source and display units, timezone-aware event inputs, UTC hour aggregate windows, unknown/stale readings, partial measured DLI, and connection clocks are explicitly separated.
- Plant exposure currently returns `unknown` with an empty interval list. The article documents that actual limitation instead of implying that adding cohort membership creates individual exposure.
- A cycle's harvest link is immutable and requires an actual harvest timestamp plus exact membership at that timestamp. Closing occupancy and saving its successor are separate writes.
- Initial device placement can establish historical context, but subsequent mapping revisions must be future-effective and later than the previous revision. The UI is not a backdated placement correction tool.

## UI limitations and follow-up observations

- Recipe bounds and manual observation labels change with measurement units. Articles use the exact C labels as explicitly conditional examples and explain the changing units.
- Several plant filters have placeholders or option text rather than persistent labels. The walkthrough identifies their actual visible text rather than inventing labels.
- `PlantDetail` refreshes plants after an individual change but does not explicitly invalidate its `plant-events` query. The article tells the reader to reopen the plant for refreshed Lifecycle history instead of promising immediate history refresh.
- Standalone Post-Harvest does not pass `onOpenHarvest`, so its board does not render Open Harvest 360. The article does not claim that button is available there.
- Cycle nursery-group and harvest linking fields require internal record IDs. The cycle form has no harvest picker; the guide makes the ID requirement explicit. A more accessible selection UI is an implementation opportunity, not a documented feature.
- Current room source readings, manual telemetry, recipe targets, and manual room targets are separate surfaces. The docs avoid implying one configuration automatically changes another.
- The local maintenance form's Read dated aggregates button also applies the window used by Build selected local aggregates. The walkthrough explains both actions rather than treating the first as a build.
- Retention preview checks prerequisites only and intentionally has no eligible-row count. Removal has no UI undo. Revocation likewise has no restoration control in this screen.
- Some shared evidence text contains a literal question-mark separator. No UI source was changed.
- Full regulated Metrc execution, nursery batch regulatory dialogs, harvest output allocation, and dedicated harvest costing tutorials are outside the detailed new intelligence articles. The overview covers entry and local planning without inventing the guarded execution sequence.

## Validation and lead integration

- Targeted TypeScript compiler check passed for `cultivation.ts` and its actual `types.ts` contract with `noEmit`.
- In-memory registry validation passed: 10 guides, 63 globally unique kebab-case step IDs, at least two troubleshooting cases per guide, all cited source paths exist, and no em dashes.
- No application test suite or browser acceptance was run. No screenshot assets were created.
- Lead work remains: registry integration, Help Center search/navigation/SEO, and genuine authenticated screenshots showing each relevant action and result. Capture the actual conditional role-dependent controls; do not substitute generic module artwork.
- Documentation status: `DOCUMENTATION_UPDATED`. This report makes no application release claim.

## Current-release follow-up

Reviewed against 6c581e5c, schema 0087. Updated file-versus-push configuration, replaced retired JSON mapping-text instructions with guided channel fields and server normalized preview, and added explicit producer authorization and historical-deviation Work walkthroughs. Device/room mappings remain time-effective; Growlink remains export-only; no hardware control is documented. This is source review, not proof of hardware connectivity.
