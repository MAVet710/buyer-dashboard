# Homepage release execution

Requested by the user after local acceptance on 2026-09-11.

## Source and scope

- Original implementation baseline: `1de2d511b8dd9df1b41336e51a507211bd95950f`.
- Release integration baseline: current `main`, `b3f7f62bff71391271c5c678c103c163461bc5e7`.
- Release branch: `codex/marketing-homepage-release`.
- Isolated checkout preserves the user's original working tree and unrelated AI runtime edits.
- Current production delivery is Render Static Site behind Cloudflare, with Render `checksPass` gating; the old Cloud Run release path is disabled and was not used.

## Integration differences from the initial acceptance report

Latest main adds storefront/age-gate routing, BrowserRouter, offline/PWA behavior, improved query caching and route-level code splitting. These are retained. The marketing page owns its contact section; beta retains its existing contact section. Current PWA manifest/icons remain intact. The scanner dependency gate applies only to actual marketing homepage/beta routes, not portal/storefront flows.

The original report remains a dated local-build record. Its bundle sizes, nginx-based serving setup and 38-test count are not measurements of this newer release source. The release has 74 passing frontend tests, warning-free ESLint, a successful production build and passing zero-cost/parity source gates (179 verified parity items). Nginx improvements remain available for container builds; production Render Static hosting uses its own serving/compression configuration.

Python assertions tied to old homepage copy were updated without weakening operational or regulatory behavior assertions. Ten corresponding pure source-contract tests passed locally. Full Python and browser gates run in GitHub Actions before release approval.

## Release process

Open a focused PR, inspect repository CI results, merge the validated exact head, and verify the public homepage after the existing Render automatic deployment. Do not trigger a duplicate manual Render deployment for a checksPass service.

No backend, database, integration authority, paid infrastructure or AI configuration changes are included. No live beta form submission or email is used for verification.
