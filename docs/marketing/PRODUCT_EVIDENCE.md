# Product evidence and safe visual assets

Reviewed 2026-09-11. This review verifies the presence of interfaces and their rendering with synthetic fixtures, not production rollout, customer outcomes, or regulatory approval.

## Approved product screenshots

| Asset | Capture | Size | Public caption |
| --- | --- | --- | --- |
| `/marketing/buyer-workspace.webp` | Real Buyer Dashboard at 1440 × 1000 | 71,580 bytes | Actual product interface · synthetic demo data · beta |
| `/marketing/inventory-workspace.webp` | Real Retail Inventory at 1440 × 1000 | 66,378 bytes | Actual product interface · synthetic demo data · beta |

Both images were captured from the running repository frontend, not reconstructed in illustration software. All API responses came from the existing synthetic fixtures in `frontend/e2e/parity-browser.spec.ts`. The synthetic organization is Parity Cannabis, facility Parity Integrated Facility, and user Parity Operator. Sales, quantities, products, costs, stock status, and dates are fixture examples, not customer proof. Screenshots were visually inspected after WebP encoding. No personal information, credentials, customer records, or real license data appears. Do not use fixture numbers as proof metrics elsewhere.

The capture used a new headless Chrome context, local Vite on port 4182, mocked `/api/v1/**` requests, blocked external requests, and the repository logo asset. It made no production requests and modified no operator UI source. Both captures rendered without JavaScript page errors.

`scripts/capture-marketing-product.mjs` reproduces the captures. Start the existing frontend with `pnpm dev --host 127.0.0.1 --port 4182`. Supply `PLAYWRIGHT_MODULE` and `SHARP_MODULE` as absolute package entry paths, then run the script from the repository root. `CAPTURE_URL` may override the local preview URL. The script also needs the existing frontend TypeScript dependency.

## Visual story recommendation

Use the Buyer screenshot as the main product proof: it shows actual sales trend, category mix, facility context, and the purchasing workspace. Follow with Inventory as the second tab to show available/reserved units, stock cover, and review signals. Keep a short readable explanation beside the image on small screens rather than expecting tiny table text to communicate the value. Offer an expandable full-size capture or equivalent view so visitors can inspect details.

Suggested copy: “See the stock. Find the pressure. Make the next call.” Supporting beta copy: “Review sales trends and category mix, then move into inventory to inspect quantities and stock cover.” This describes the verified interface without claiming measured savings or autonomous action.

## Source-backed workflow presence

| Area | Source | What can be shown accurately | Claim class |
| --- | --- | --- | --- |
| Retail buying | `frontend/e2e/parity-browser.spec.ts`; buyer workspace pages | Sales trend, category mix, inventory health, forecast and SKU review interfaces | SUPPORTED_BUT_BETA |
| Retail inventory | `frontend/src/pages/InventoryPage.tsx`; synthetic browser capture | Product/package views, filters, available/reserved quantities, stock-cover fields | SUPPORTED_BUT_BETA |
| Cultivation | `frontend/src/components/PlantInventory.tsx:17-43` | Plant tag, strain, growth phase, room, estimated harvest, Plant 360 lifecycle history | SUPPORTED_BUT_BETA |
| Production | `frontend/src/pages/ProductionPage.tsx` | Production planning and cost-input interfaces exist; no production reliability or savings claim inferred | SUPPORTED_BUT_BETA |
| Extraction | `frontend/src/pages/ExtractionCommandCenterPage.tsx` | Extraction workspace exists; do not infer certified or unattended regulated actions | SUPPORTED_BUT_BETA |

The UI is evidence of implemented surface area only. Technical verification or existing beta access must not be repackaged as generally available certified software.

## Rejected existing assets

`artifacts/metrc-evaluation/*.png` are evaluation spreadsheets and related evidence, not compelling product interfaces. The inspected `final-plant-batches.png` includes sandbox facility/license identifiers and package/event details. These were deliberately not copied into public assets; they do not establish Metrc certification. Existing product packaging images are merchandise artwork, not ERP interface proof.

## Browser QA readiness

Chrome and Edge executables are installed. The Codex bundled runtime includes Playwright and sharp. The repository contains Playwright configuration and browser specs but does not declare `@playwright/test` in package.json. The isolated screenshot script uses bundled Playwright directly and adds no application dependencies. Firefox was downloaded but could not launch because this host lacks its required side-by-side runtime configuration. Final homepage mobile, accessibility, Lighthouse, CTA, and keyboard validation is documented in `BROWSER_QA_REPORT.md`.

Responsive 480px and 960px versions of both screenshots were added, and `ProductShowcase.tsx` selects them with `srcSet` and `sizes`. Full-size links preserve the original evidence. The public nav mark is optimized to 120 × 120 in `brand.webp`; `apple-touch180.png` is a separate optimized 180 × 180 home-screen icon.
