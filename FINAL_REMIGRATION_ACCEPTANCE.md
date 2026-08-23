# Final Streamlit Remigration Acceptance

## Baseline

The remigration is audited against the last intact operator-facing Streamlit implementation at commit `c63b2ba83c5e73c6b9d9aee30f51d1b4e1cf9785`, with the supplied Buyer/Purchasing recording used as higher-priority operator evidence. DoobieLogic branding is the approved name substitution; workflow redesign is not accepted as parity.

## Source and behavior verification

The final remigration contract now covers the global shell, role-aware Home, Retail and Production Inventory, Product 360, Package 360, receiving, audits and scanner lifecycle, Purchasing/Buyer Dashboard, PO Builder, budget, trends, delivery analytics, Compliance Q&A, nomenclature mapping, Admin/users/passwords/roles, organizations/facilities/licenses, integrations, Production/Cultivation inventory, plants, Co-Man, Extraction, White Label/Repack, Package Studio, Orders/Finance, Traceability, Data Hub, Location Settings and executive reports.

`tests/test_streamlit_remigration_contract.py` and `tests/test_final_streamlit_surface_contract.py` intentionally fail when the recovered operator surfaces or cross-workspace actions are removed or hidden again. Existing behavioral API/repository tests continue to cover calculations, tenant/facility isolation, durable writes and exports.

## Browser acceptance

`frontend/e2e/parity-browser.spec.ts` is the real-browser responsive acceptance gate. It runs Chromium at 390, 430, 768, 1024 and 1440 px, rejects document overflow, captures full-page screenshot evidence, and exercises the restored Buyer command center, all five White Label/Repack tabs, the Package Studio right-side/full-screen work window, and the separate Production Inventory experience.

The shared `StreamlitDialog` plus the final `streamlit-exact.css` layer applies the same work-window geometry across Product 360, Package 360, audit count entry, adjustments, receiving history, plant detail and other migrated dialogs: full-screen at mobile/tablet breakpoints and a right-side work window on desktop.

## License and operation boundary

Production Inventory is shared by manufacturing and cultivation licenses. Manufacturing-only workflows remain manufacturing-only. The API uses `require_inventory_operation_capability` for shared inventory/audits/product-master access and retains `get_production_context` for manufacturing-only endpoints. A dedicated cultivation-only regression test prevents the previous shell/API capability mismatch from returning.

## Buyer data-source selector

The Uploads / Dutchie Live selector is preserved and sent on every API request as `X-DoobieLogic-Data-Mode`. Buyer endpoints use the selected request context. The pinned Streamlit Dutchie client itself did not implement live fetching; therefore the migrated app preserves the explicit unavailable/not-implemented state rather than fabricating live Dutchie data.

## Reports

The React/FastAPI report endpoints reuse the retained Streamlit PDF builders for Buyer Operations, Co-Man Production, Extraction Operations and White Label/Repack. Retail, Production and Company executive-pack composition remains available. Competitor Intelligence was not a first-class report workspace in the pinned Streamlit navigation; the legacy pack only appended a competitor PDF when an already-generated session PDF existed, so there is no standalone competitor report surface to migrate.

## Production release rule

Production promotion is permitted only after the exact-parity contract, full backend suite, frontend lint/test/build, browser matrix, API/frontend container builds, migration startup check and security scans are green on the final commit. The normal production workflow must then run database migrations before API traffic readiness and must verify both API health endpoints before deploying the web service to `ops.doobielogic.io`.
