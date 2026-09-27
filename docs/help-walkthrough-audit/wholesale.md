# Wholesale walkthrough source audit

Status: DOCUMENTATION_UPDATED. Source inspection only; no browser testing, screenshots, provider calls, database changes, deployments, installs, or git mutations were performed.

Implemented `frontend/src/lib/help/wholesale.ts`, exporting `wholesaleWalkthroughs: HelpWalkthroughRegistry` from the existing `./types` contract. The registry contains 9 guides, 61 steps, and 126 field descriptions. All 7 existing wholesale articles remain covered; Pipeline is restored and Logistics is added.

## Coverage and actual entry routes

| Help route | Application entry | Navigation |
| --- | --- | --- |
| `/help/wholesale` | `/wholesale` | Wholesale Ops > Overview |
| `/help/wholesale/inventory` | `/wholesale` | Wholesale Ops > Inventory |
| `/help/wholesale/orders` | `/wholesale/orders` | Wholesale Ops > Orders |
| `/help/wholesale/warehouse-pick-pack` | `/wholesale/fulfillment` | Wholesale Ops > Fulfillment |
| `/help/wholesale/customers` | `/wholesale?tab=customers` | Wholesale Ops > Customers |
| `/help/wholesale/pipeline` | `/wholesale` | Wholesale Ops > Pipeline |
| `/help/wholesale/accounting` | `/wholesale` | Wholesale Ops > Accounting |
| `/help/wholesale/storefront` | `/wholesale` | Wholesale Ops > Storefront |
| `/help/wholesale/logistics` | `/wholesale` | Wholesale Ops > Logistics |

The current WholesaleOpsPage initializer recognizes `tab=customers` and a `dispatch` ID. It does not recognize generic `tab=inventory`, `tab=pipeline`, `tab=storefront`, or `tab=logistics` links. Guides therefore use the real base route and explicitly instruct the operator to select those tabs. Orders and Warehouse Pick Pack also have standalone routes in workspaceRoutes and active components in App.

## Sources

The per-guide `sourceFiles` arrays provide the precise source mapping. Inspected source groups include:

- Contract and routing: `frontend/src/lib/help/types.ts`, `frontend/src/App.tsx`, `frontend/src/lib/workspaceRoutes.ts`.
- UI: `frontend/src/pages/WholesaleOpsPage.tsx`, `OrdersPage.tsx`, `WarehousePickPackPage.tsx`, `WholesaleCRMPanel.tsx`, `WholesaleAccountingPanel.tsx`, `WholesaleLogisticsPanel.tsx`.
- Imported controls: `frontend/src/components/IdentifierCaptureInput.tsx`, `CommerceStorefrontManager.tsx`, `StorefrontSalesUnitManager.tsx`, `ManifestDraftControl.tsx`, `WholesaleRegulatoryHealth.tsx`.
- Routers: `backend/app/routers/commercial.py`, `commercial_crm.py`, `warehouse.py`, `wholesale_accounting.py`, `wholesale_logistics.py`, `storefronts.py`, `storefront_units.py`, and the portal-access portion of `control_tower.py`.
- Commercial validation and behavior: `modules/commercial/repository.py`, `crm.py`, `crm_contracts.py`, `modules/commercial_finance/service.py`, `pricing.py`, `modules/inventory_availability/service.py`, `services/wholesale_accounting.py`.
- Storefront behavior: `modules/commerce_storefronts/service.py`, `wholesale_service.py`, `studio.py`, `sales_units.py`, `intelligence.py`, and the portal-access portion of `modules/operational_moats/service.py`.
- Dispatch behavior: `modules/wholesale_logistics/schemas.py`, `service.py`, `models.py`.
- Old `frontend/src/lib/helpContent.ts` was used only as the seven-article coverage inventory and to identify outdated instructions.

## Corrections to old help

- Replaced the nonexistent Orders & Fulfillment tab instruction with Orders, Allocate & Fulfill, and the actual separate Fulfillment workspace.
- Explained that storefront approval and quote conversion create drafts. Confirmation and reservation are separate writes; fulfilled quantities change only when shipments post.
- Explained the actual Inventory columns and blocked-stock toggle. There is no package-detail button in that table.
- Customer 360 supports relationship fields, opportunities, quotes, activities, and Work follow-ups. It has no general contact-edit form. New customers are created in Orders > Trade Partners.
- Accounting is read-only. Invoice creation, marking sent, payment posting, and customer price rules are in Orders > Wholesale + Finance. Mark invoice sent is a status write, not an email send. Update payment is an order label, not a recorded invoice payment.
- The invoice route explicitly requires complete fulfillment. Payment posting enforces a positive amount no greater than the balance.
- Studio design saves are separate from foundation, catalog, and display-unit saves. Publish design publishes the saved design draft, not pending local edits.
- Logistics records delivery evidence without changing inventory, fulfilled quantity, provider manifests, or invoices. Exceptions can create linked reconciliation Work.

## UI issues and integration limitations

1. Storefront manager has no visible error rendering for many foundation, design, catalog, approval, rejection, and portal mutations. Do not capture an apparently unchanged form as proof of a successful save. The guide tells operators to inspect saved state rather than repeatedly clicking uncertain writes.
2. Studio's draft-dirty indicator and Publish design enablement derive from the server snapshot. Unsaved local edits can coexist with Published design is current. Save design draft must precede Publish design.
3. Display-unit mismatch: `WholesaleCommerceStorefrontService.admin_snapshot` changes listing `unit`/`sales_unit` but leaves stored price, minimum, and case quantities in base units. The display-unit API forwards those values unchanged, and StorefrontSalesUnitManager labels them with `sales_unit` under Displayed minimum and Displayed increment. Public catalog conversion is separate. The catalog editor also combines converted availability/unit labels with stored base-unit terms. The guide identifies base-unit save semantics and requires checking the actual public site; it does not promise the management table's displayed quantities are converted correctly. This needs an application fix outside this assignment.
4. Storefront Base price, minimum/case, Featured, and announcement inputs lack individual labels or use only table headings/placeholders. Field descriptions use the actual heading or placeholder and explain it rather than inventing labels. Page-section ordering includes nested buttons. Browser/accessibility verification remains needed.
5. Inventory Blocked reasons are a hover `title`, which is difficult to discover on touch devices. The guide flags this limitation. There is no direct source-lot link in the inventory table.
6. Overview Open buttons select a tab but don't focus the corresponding order. Summary tables are bounded; the guide gives the applicable visible row limits and tells the operator to retain the order number.
7. Logistics departure requires the commercial shipment to be `manifested` or `shipped` with a nonblank manifest reference for every stop. This is stricter than warehouse posting's package-backed-only manifest guard. The logistics article explicitly reflects the stricter current server rule.
8. Logistics locks all planning after loading begins. There is no stop-edit form after addition; planned stops can be removed, and run details can be edited while planning is open. The outcome form records no numeric accepted/returned quantities, so notes plus reconciliation Work are required for quantity investigation.
9. Order finance acts on the first invoice/shipment returned for the selected order and has no explicit invoice action selector. The guide requires reviewing the invoice row before payment. Accounting rounds dollar values for display; exact amounts should be checked in finance detail.
10. New Order initializes Unit Price from product cost, including when Product changes. Customer pricing rules don't retroactively update saved quote/order/invoice lines. Both behaviors are called out.
11. The storefront approval service creates the order before updating the request in a separate transaction. An uncertain approval response should be reconciled against both request status and Orders before retrying. The article doesn't claim atomic or retry-safe approval.
12. Overview embeds regulated manifest preparation controls. The wholesale overview explains the local-versus-provider boundary and refers to the approved traceability process; it does not duplicate a provider submission walkthrough owned by compliance documentation.

## Validation and remaining evidence

Used the already-installed TypeScript compiler for an isolated strict, no-emit check against the real HelpWalkthroughRegistry type. Also validated registry shape, required sections, at least two troubleshooting cases per guide, globally unique kebab-case step IDs, required field descriptions, existence of every referenced source path, and absence of em dashes. No unrelated build artifacts or test files were written.

The lead still owns registry integration, search/SEO/navigation, and real browser screenshots. Useful capture targets are the quantity/unit comparison in Inventory, a reviewed order draft and reservation, the warehouse identity-match message, Customer 360's saved next action, a quote's reviewed prices and conversion result, invoice/payment detail, Studio's saved-versus-published state, a storefront request decision, and logistics stop evidence/reconciliation. Any portal token or actual customer/contact/license data must be excluded or redacted from captures. No browser or production acceptance is claimed here.
