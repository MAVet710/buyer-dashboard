# Detailed Help Center integration

The six domain reviews are integrated with the current application source at `fd91e4f7991e3d65f7adb81cd0765f0d9e3395bc`. The original domain reports preserve the scope and limitations of each worker's review. Later cultivation changes were reviewed by the primary integrator, including normalized push, guided source mapping, historical deviation Work, and passive nearby-sensor setup.

## Published-content contract

The registry contains 78 guides, 495 task steps, 789 field descriptions and 225 troubleshooting entries. Each step has a stable identifier, concrete instructions and an expected visible result. Guides include prerequisites, completion checks, real app destinations and repository-relative sources. Existing guide URLs are retained. Work Queue and Wholesale Pipeline documentation is restored because those workspaces are present in the current application.

`frontend/src/lib/help` owns detailed content. `HelpWalkthrough` renders fields, warnings, result checks, troubleshooting, printing and image enlargement. Search indexes the full walkthrough text. Run `node frontend/scripts/sync-help-metadata.mjs` after editing guides, rebuild public SEO and synchronize the generated sitemap. Regression tests check coverage, source paths, route mapping, metadata, step IDs and image provenance.

## Screenshot boundaries

Images are actual authorized demonstration-workspace captures, not generated UI. Step images are attached by guide path and stable step ID. Old references remain explicitly dated where retained. Current examples deliberately distinguish missing data, disabled provider access, unsaved forms and preview results from successful business actions.

The primary capture pass used an authenticated DEV Sandbox browser. Business mutations were blocked; a source-file preview was allowed without committing readings. No inventory, account, recipe, crop membership, device approval, sensor discovery, equipment command or regulated provider action was performed merely to obtain a screenshot. Captures that showed a loading queue, an unintended account scope or unrelated state were rejected. A screenshot is not evidence that every workflow was executed end to end.

## Validation and delivery

Source checks, TypeScript, lint, frontend tests and the production build passed before submission. The browser acceptance matrix and exact PC/public release receipt are maintained privately with the release evidence. This document is not itself a claim of successful deployment; use the final controller and public acceptance receipts for that determination.
