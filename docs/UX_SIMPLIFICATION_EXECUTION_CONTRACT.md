# DoobieLogic UX Simplification Execution Contract

## Product objective

DoobieLogic must feel simpler to operate than Distru while preserving and expanding the operational depth already restored and built in the React/FastAPI application.

The governing principle is:

> The software underneath can remain deep. The surface should feel simple.

This work is explicitly authorized as a UX and information-architecture evolution **after** the exact Streamlit parity restoration. The parity baseline remains the feature-preservation source of truth. This project may reorganize how capabilities are exposed, but it may not silently delete, downgrade, weaken, or permanently hide working behavior.

## Navigation rule

**Navigate for jobs. Pop out for context.**

A route represents the job/workspace the operator is performing. A contextual panel represents the entity or evidence the operator is inspecting. A dialog represents a focused action or confirmation.

- **Route = where I am working**
- **Panel = what I am inspecting**
- **Dialog = what I am doing**

360 views and Doobie Agent should increasingly behave as contextual panels when opened from an operational workspace. Canonical routes remain available for deep links, browser refresh, bookmarks, and direct entry.

## Primary information architecture

The daily operational surface is intentionally smaller than the complete capability set.

### Retail Ops

- Home
- Buying
- Inventory
- Wholesale
- Compliance
- Reports

Retail inventory remains the physical source of truth for retail-licensed facilities. Wholesale is a separate commercial job surface when the active facility has commercial capability rather than being hidden under Inventory.

### Production Ops

- Home
- Inventory
- Production
- Wholesale
- Compliance
- Reports

**Wholesale Ops is a first-class commercial workspace.** Production remains the manufacturing source of truth, but sales execution no longer needs to be buried inside the Production navigation. Production continues to own:

- production planning and execution
- extraction
- co-manufacturing
- white label / repack
- production inventory and BOM
- labor, machines, resources, actuals, recommendations, optimization, and run economics

Wholesale Ops owns the commercial execution layer:

- sellable wholesale inventory projections
- direct, account, private-portal, and hosted-storefront orders
- approval-gated storefront demand
- customer and retailer accounts
- lot allocation
- warehouse pick / pack
- fulfillment and shipment execution
- wholesale pricing and storefront publishing

**Production remains the manufacturing source of truth.** Wholesale Ops does not create a second inventory ledger. Both workspaces must use the same organization/facility inventory balances, reservations, allocations, compliance status, and traceability records.

An approved wholesale order becomes an organizational inventory commitment. A submitted storefront request is demand only and does not reduce availability until it is approved. When a specific package or lot is allocated, the soft wholesale commitment becomes a hard lot reservation without double-counting. Production reservations, wholesale commitments, wholesale lot allocations, holds, and physical inventory transactions must all affect the same Available quantity shown throughout DoobieLogic.

Extraction remains a first-class Production capability and must be prominent for extraction/manufacturing facilities.

Settings, integrations, administration, imports, account controls, and similar configuration functions remain fully accessible to authorized users under Settings & Administration rather than occupying daily primary navigation.

## One global context model

The application shell owns the authoritative context for:

- organization
- facility
- operational mode
- license/capability context
- connection/sync state

Individual workspaces must not introduce competing Retail/Production selectors. Facility and operational context changes must continue to respect organization, tenant, license, METRC, BioTrack, and sandbox boundaries.

## Shared inventory availability contract

Physical inventory remains append-only through the canonical inventory transaction ledger. Operational workspaces layer claims onto that physical balance rather than creating competing inventory totals.

For each package or lot, DoobieLogic must distinguish:

- **On Hand** — physical quantity in the inventory ledger
- **Production Reserved** — quantity reserved for an active production job
- **Wholesale Committed** — approved sales-order quantity not yet allocated to a specific package or lot
- **Wholesale Reserved** — quantity allocated to a specific package or lot for a sales order
- **Available** — physical quantity remaining after every active organizational claim that prevents reuse
- **Pending Demand** — submitted but unapproved order requests; visible for planning but excluded from reservation math

Active Inventory, Production, Wholesale Ops, Warehouse/Fulfillment, storefront availability, and Doobie Agent inventory reasoning must consume the same availability projection. A module may add workflow-specific filters, but it may not independently calculate a conflicting sellable or usable balance.

Cancellation or release must restore availability. Fulfillment converts the applicable reservation into an inventory decrement. Production consumption converts its reservation into an inventory decrement. Inventory adjustments and outbound movements may not reduce a lot below active commitments/reservations.

## Workspace state contract

Closing contextual information must return the operator to the exact working state whenever technically possible. Workspace state includes:

- route
- organization and facility
- operation mode
- search query
- filters
- sort
- selected rows
- pagination
- saved view
- scroll position
- open contextual panel stack
- Doobie Agent state
- safe unsaved workflow state

Browser back/forward must become authoritative for workspace navigation. Legacy string page navigation and `buyer-dash-pending-page` remain compatibility mechanisms until every migrated workflow is validated.

## Doobie Agent contract

Doobie Agent remains a persistent contextual pop-out/drawer and must not be reduced to a standalone page requirement.

It should receive safe, tenant-scoped context from the active workspace and selected entity. It remains read-only by default. High-impact mutations must use a human-reviewed sequence such as:

1. Stage action
2. Preview action
3. Review action
4. Approve action

The long-term differentiator is cross-functional operational reasoning across Buying, Inventory, Production, Extraction, Orders, Labor, Machines, Packages, Sales, Compliance, Costs, SOPs, and traceability rather than generic chat over ERP data.

## Feature preservation matrix

| Capability family | Preserve | UX target |
| --- | --- | --- |
| Buying / purchasing intelligence | Required | Decision-first Buying workspace with reasons visible before advanced controls |
| Purchase orders / budgets / vendor performance / delivery history | Required | Progressive disclosure beneath Buying |
| Retail inventory / receiving / audits | Required | Search, scan, status, attention, receive first; advanced filters/views preserved |
| Production inventory / BOM / plants where applicable | Required | Material availability tied directly to Production decisions |
| Product 360 / Package 360 / Run 360 | Required | Canonical routes plus contextual panel architecture |
| Audit pause/resume/stop/partial/new/exact selection | Required | No lifecycle regression; mobile scanning remains first-class |
| Production planning / schedule / queue / resources / labor / machines | Required | Today-first surface: Running, Next Up, Blocked, Behind, Completed |
| Extraction | Required | First-class Production workspace with source, yield, waste, testing, compliance, cost |
| Co-Man / white label / repack | Required | Production sub-workspaces |
| Orders / fulfillment / warehouse pick-pack | Required | First-class Wholesale Ops execution; legacy production URLs remain compatibility aliases |
| Distribution / wholesale | Required | First-class Wholesale Ops workspace connected directly to manufacturing inventory |
| Inventory commitments / reservations | Required | One shared availability calculation across Production, Wholesale, Warehouse, Inventory, storefront, and Agent |
| Compliance / traceability / state actions | Required | Issue-first operator language with evidence/technical detail progressively disclosed |
| Label Studio / LabelGuard / nomenclature / MA flower equivalency | Required | Compliance tools remain accessible without dominating first layer |
| METRC / BioTrack / QuickBooks / printing / signed webhooks | Required | Settings/Integration surface; no security or tenant-boundary regression |
| Operational / enterprise control towers | Required | Available from Home without making Home a directory |
| Executive reporting / sales/category trends / profitability | Required | Reports with role-aware starting views |
| Commerce portals / hosted storefronts / service APIs / telemetry | Required | Customer-facing commerce remains connected to Wholesale Ops and canonical commercial orders |
| SOP library / cultivation / harvest economics | Required | Preserved and exposed contextually by capability/role |
| Doobie Agent / provider-neutral AI runtime | Required | Persistent contextual pop-out with safe scoped context |
| Users / roles / permissions / orgs / facilities / sandbox | Required | No auth, permission, tenant, or sandbox regression |
| Theme / reports / DB structures / migrations / security controls | Required | Preserve contracts unless separately migrated with tests |

## Quantitative UX victory conditions

For the ten highest-frequency operator workflows, record the baseline and redesigned workflow using:

- meaningful clicks/taps
- page transitions
- context switches
- required fields
- required decisions
- completion time where automatable

The redesign should reduce interaction count, context switching, or required decision-making by **at least 25% where reasonably achievable** without removing validation, compliance, approval, or security safeguards.

Initial target contracts:

| Workflow | Target |
| --- | --- |
| Find a package from Inventory | <= 2 meaningful interactions after search/scan input |
| Inspect package without abandoning Inventory | 0 destructive workspace transitions |
| Open Product 360 from Inventory | underlying filters/search/scroll preserved |
| Receive scheduled delivery | reachable within one primary navigation level |
| Start inventory audit | <= 3 meaningful interactions after entering Inventory |
| Resume inventory audit | Home -> Continue -> resumed audit |
| Understand reorder recommendation | reason visible without leaving Buying |
| Ask Doobie about selected entity | selected context already attached when safe |
| Identify next production job | visible on Production Today without opening planning settings |
| Inspect run and return | production queue/schedule state preserved |
| See inventory promised to wholesale | Active Inventory shows reduced Available quantity and reservation/commitment context |
| Fulfill wholesale order | approval -> commitment -> lot allocation -> pick/pack -> shipment without duplicate inventory entry |

## Real routing migration

React Router is already a production dependency. Introduce canonical URLs incrementally while preserving legacy page-name navigation during the migration.

Canonical route families:

- `/home`
- `/buying`
- `/buying/purchase-orders`
- `/inventory`
- `/inventory/audits`
- `/inventory/products/:id`
- `/inventory/packages/:id`
- `/production`
- `/production/runs/:id`
- `/production/extraction`
- `/wholesale`
- `/wholesale/orders`
- `/wholesale/fulfillment`
- `/compliance`
- `/compliance/issues/:id`
- `/reports`
- `/settings`

Legacy `/production/orders` and `/production/fulfillment` remain compatibility aliases during the routing migration.

Back, forward, refresh, deep-link, bookmark, and legacy pending-page behavior are release gates.

## Competitive displacement validation

Do not declare the UX simplification complete until representative Distru-displacement workflows are compared against DoobieLogic.

Validate at minimum:

- purchase raw material
- receive cannabis inventory
- create manufactured product
- create/use BOM
- execute production run
- track yield, waste, and loss
- inspect package lineage
- create sales/wholesale order
- approve storefront demand without reserving unapproved requests
- expose wholesale commitments in Active Inventory
- pick and pack order
- transfer inventory
- reconcile traceability
- investigate discrepancy
- calculate COGS
- inspect historical transaction/evidence trail
- operate multiple facilities

Each workflow must be classified:

- **Doobie advantage**
- **Parity**
- **Distru advantage**

For each, evaluate discoverability, context changes, operational intelligence, Doobie Agent assistance, state preservation, mobile usability, and tenant/facility safety.

High-frequency workflows may not remain undocumented Distru advantages at project completion.

## Incremental implementation phases

1. Feature/capability/route/permission/state audit and preservation matrix
2. AppShell and information architecture
3. Real routing plus legacy compatibility
4. Reusable workspace and 360 panel architecture
5. Doobie Agent contextual pop-out improvements
6. Home attention/continue/today redesign
7. Inventory and Receiving
8. Buying
9. Production and Extraction
10. Wholesale Ops, Distribution, Orders, and Fulfillment
11. Compliance
12. Data / Settings / Admin simplification
13. Mobile, keyboard, focus, accessibility, responsive polish
14. Full parity/security/regression testing
15. Competitive displacement validation

No giant uncontrolled rewrite. Each phase must leave the application operable and preserve security and tenant isolation.