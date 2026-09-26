# Popup readability verification

Status: **CODE_READY**. This bounded frontend change has not been committed or deployed. The primary delivery owner retains integrated application and PC release acceptance.

## Cause and correction

`WorkspaceWindow` referenced `--surface`, which is undefined in the actual app cascade. Chrome computed `background-color: rgba(0, 0, 0, 0)`. Its footer and controls used the legacy translucent `--surface-2`; sticky tabs repeated the undefined token. The modal panel itself already had an opaque gradient, but its sticky heading faded to transparent and stayed dark in light mode. Search and multi-select menus used translucent raised surfaces.

The new `--dl-popup-surface` resolves through the existing `--dl-surface-solid`: `#111412` in dark mode and white in light mode. Every consumer has a solid `#111412` fallback. No page-wide surface token, layout, event handler, backdrop, marketing section, homepage, or Help page was redesigned.

Changed selectors:

- `workspace-window.css`: `.workspace-window`, `.workspace-window-actions .icon-button`, `.workspace-window-footer`, `.workspace-window .view-tabs` use the solid popup surface. Window border references now use the existing `--dl-border` with fallback; `.workspace-window-heading p` uses opaque `--dl-text-soft` instead of undefined `--muted`.
- `streamlit-exact.css`: `.modal-heading` uses the solid theme-aware popup surface. The modal gradient and translucent backdrop remain intact.
- `popup-surfaces.css`, imported last in `main.tsx`: `.global-search-results`, `.multi-select-menu`, `.multi-select-control[open]`, and `.commerce-launcher-window` use the shared solid surface and existing text token.
- Scoped to `.workspace-window`, `.modal`, and `.commerce-launcher-window`: `.table-wrap` has a solid base, `table th` uses readable secondary text, `.secondary` uses the solid surface, and inactive `.view-tabs` buttons use the opaque secondary text token. Window action icons use that text token too. The two narrow important declarations override existing important table/button theme rules.

## Observed browser results

| Surface | Before alpha | After alpha |
| --- | --- | --- |
| Workspace content and sticky tabs | 0 | 1 |
| Workspace footer and action button fill | 0.82 | 1 |
| Search and multi-select menu, dark | 0.96 | 1 |
| Search and multi-select menu, light | 0.98 | 1 |
| Modal sticky heading | Gradient fades from 1 to 0 | 1 throughout |
| Modal content | Opaque gradient | Opaque gradient retained |
| Commerce launcher | 1, fixed dark fallback | 1, follows theme |

Measured light-theme table-heading contrast improved from 3.31:1 to 5.01:1. All sampled final text has contrast at least 4.5:1, alpha 1, and ancestor opacity 1. Own-background alpha assertions are separate from effective ancestor alpha: an opaque page canvas must not hide a transparent popup regression. Computed gradient contrast uses the first stop; visual inspection additionally covers the scrolled heading and busy background.

Installed Chrome ran the actual `WorkspaceWindow` and `StreamlitDialog`, plus search, multi-select and commerce markup using their actual selectors. A stylesheet-order test compares the fixture imports to `main.tsx`. The fixture places dense alternating black/white text and table rows behind the popups. It imports no application API client, auth, or provider integration. Requests outside loopback 4197 or to `/api` are aborted and fail the test.

Checks at 390x900 and 1280x900 in both dark and light themes passed: computed surfaces, readable heading/body/footer/input/table/sticky headers/buttons, no page horizontal overflow, nested window Escape, nested dialog Close, desktop drag/maximize/minimize/restore, keyboard focus, and missing-token fallback. Screenshots include workspace, nested window, dialog, scrolled dialog, menus, and commerce.

## Reproduce

From `frontend`, first verify that port 4197 is unused. Use existing local dependencies; no installation is needed.

```powershell
Get-NetTCPConnection -LocalPort 4197 -ErrorAction SilentlyContinue
node node_modules/vite/bin/vite.js build --config e2e/fixtures/popup-readability.config.ts --configLoader runner
node node_modules/vite/bin/vite.js preview --config e2e/fixtures/popup-readability.config.ts --configLoader runner --host 127.0.0.1 --port 4197 --strictPort
```

In a second terminal:

```powershell
node node_modules/@playwright/test/cli.js test e2e/popup-readability.spec.ts --config playwright.config.ts --output tmp/popup-readability/test-results
node node_modules/eslint/bin/eslint.js e2e/popup-readability.spec.ts e2e/fixtures/popup-readability-entry.tsx e2e/fixtures/popup-readability.config.ts src/main.tsx
```

Stop only the fixture preview process after testing. The fixture configuration disables environment loading and has no API proxy. The build/preview path avoids a sandbox ancestor-directory denial in esbuild dependency discovery. Final fixture build passed with 1601 modules; focused lint passed with zero warnings/errors; final Chrome suite passed **6 tests in 9.0 seconds**. A full application build/lint was not run by this bounded worker.

## Evidence and limits

Synthetic screenshots and computed JSON are in ignored `frontend/tmp/popup-readability/`. `report.json` combines all before/after reports. Filenames use `{before|after}-{dark|light}-{390|1280}-{workspace|nested|dialog|dialog-scrolled|menus|commerce}.png`; per-theme/viewport JSON accompanies them. Baseline captures used original HEAD CSS through a read-only Vite load plugin, without reverting working source. Baseline checks passed 5 tests with the new fallback test intentionally skipped.

The Doobie-style fixture is a real shared window titled Doobie workspace, not a production assistant conversation. No separate persistent assistant panel, command palette, or custom tooltip surface was found in this checkout; browser-native title tooltips are unchanged. Support is a link in this checkout, not a modal. Commerce/search/menu markup is synthetic and does not exercise business/API interactions. Marketing/home/Help visual acceptance and authenticated public workflows remain with the primary owner.

Existing behavior remains: Escape while a StreamlitDialog is nested inside a WorkspaceWindow closes both because both components register window Escape listeners. The baseline and final tests observe this. Nested WorkspaceWindow Escape closes only the top window. Changing event semantics was outside the authorized CSS scope.
