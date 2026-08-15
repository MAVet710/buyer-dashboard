# DoobieLogic Buyer Dash User Guide

Buyer Dash is a cannabis operations workspace for retail buying, inventory control, production planning, Co-Man execution, extraction, and customer fulfillment.

## First login

1. Open the application and sign in with the username and temporary password issued by your administrator.
2. Create a private password if prompted.
3. Review and accept the current Terms of Service and Privacy Policy.
4. Confirm the organization and facility shown in **Access Context**.
5. Start from **Operations Home**. The shortcuts shown there are filtered for your role.

If no organization or facility is available, contact an administrator. Production and commercial records cannot open without an explicit tenant context.

## Navigation

- **Home** — role-specific shortcuts, source readiness, facility context, and connection status.
- **Retail Ops** — inventory, trends, buying, compliance, audits, nomenclature, and repack tools.
- **Production Ops** — Co-Man and extraction planning and execution.
- **Commercial Ops** — customer orders and fulfillment.
- **Data & Integrations** — guided uploads, source readiness, import history, Dutchie/METRC settings, and shared operational data.

The first selector chooses an operations area. The second opens a workspace inside that area.

## Data Import Center

Use **Data & Integrations → Data Hub** instead of searching for upload controls throughout the application.

### Retail data flow

1. Choose the dataset: Inventory, Product Sales, Sales/Pricing Detail, or Quarantine.
2. Upload CSV, XLSX, or XLS.
3. Review the detected row count, columns, required-field mapping, and preview.
4. Confirm the source and publish it.
5. Open Retail Operations. Published data is reused across compatible tools.

Uploading a replacement does not become operational until it is reviewed and published.
Published files are saved to Supabase for the selected organization and facility,
so they return after sign-out, a Streamlit restart, or a deployment. Data Hub keeps
the active file plus two prior versions for each dataset. Files must be 10 MB or less.
The History tab shows who published each version and whether it is active or archived.

## Doobie AI

Doobie is Buyer Dash's cannabis-operations AI. When the DEV team has connected
the shared service, its status appears as **Doobie Connected**. Buyer briefs,
inventory checks, extraction briefs, and the Main AI Copilot use the same
grounded Doobie API. Responses can include recommended actions, risk flags,
inefficiencies, confidence, sources, and a request for missing jurisdictional
context. If Doobie cannot verify an exact compliance rule, Buyer Dash shows that
limitation instead of presenting the answer as confirmed law.

Only LEVEL DEV users can view or change Doobie service credentials. Company
users see METRC integration controls and the enabled AI experiences, but never
the shared API key.

### Production data flow

- Extraction imports support automatic header detection, mapping, preview, and deduplication.
- Co-Man products, lots, machines, customers, schedules, crews, and production records are durable master data. Enter them in Co-Man rather than re-uploading them for every job.

## Retail Operations

### Inventory Dashboard

Shows revenue, days on hand, low stock, out-of-stock products, inventory value, reorder actions, aging risk, and SKU-level detail. Use the filters near the table for product, category, vendor, expiration, and velocity.

### Trends

Reviews category mix, package-size mix, velocity, fast movers, and changing sales patterns using the published retail sources.

### Buyer Intelligence

Summarizes buyer priorities and risks. AI-assisted functions are available only when Doobie AI is connected and licensed.

### Inventory Counts

Creates durable audit sessions for retail or production inventory.

1. Import the current Dutchie inventory export for the audit scope.
2. Start an audit.
3. Scan a Dutchie barcode/QR code with a phone/tablet camera, Bluetooth scanner, USB scanner, or typed code.
4. Enter the counted quantity in the item dialog.
5. Pause, stop for review, resume, or complete the audit.
6. Recount discrepancies and export the final result.

### Slow Movers

Identifies products with excess days on hand and proposes review, markdown, transfer, or purchasing actions.

### MA Flower Equivalency

Calculates Massachusetts adult-use Dutchie package flower-equivalency values for concentrates, vapes, edibles, beverages, and infused pre-rolls. Confirm live operational values with your compliance team.

### Delivery Impact

Compares sales before and after deliveries and identifies delivered products associated with revenue or traffic changes.

### PO Builder and Purchasing Budget

Builds purchase orders from reorder recommendations and reviews spend against available purchasing budget.

### Compliance Q&A

Answers from structured reviewed source material. Confirm state, adult-use/medical scope, citation, source URL, last-updated date, and review status before relying on an answer.

### Nomenclature Mapper

Uploads a facility's Dutchie catalog as the naming standard, then converts METRC manifest items into matching Dutchie names. Known items reuse the catalog; new items are generated using the detected facility naming pattern. The final export contains the corrected item names.

### White Label / Repack

Models bulk weight, package formats, labor, packaging costs, pricing, yield, and margin for retail repack or private-label work.

## Production Operations

### Co-Man Production

Supports internal production and customer-owned contract manufacturing.

- Maintain products, pack sizes, lots, customers, BOMs, machines, hand-labor areas, and crews.
- Convert bulk weight into recommended finished configurations.
- Compare margin, labor, yield, throughput, and machine capacity.
- Schedule machine and hand-labor work, including stickering, casing, packing, tubing, and final case pack.
- Record actual production, downtime, variances, and completion history.

Every facility includes hand-labor capacity because finishing and final pack activities cannot be fully eliminated by automation.

### Extraction Command Center

Tracks source inventory, extraction runs, stage weights, yields, costs, estimated value, QA/COA status, and operational risks. Partner workbooks can be mapped and imported through Data Hub.

## Commercial Operations

Tracks customers, sales orders, line items, requested delivery dates, ownership, fulfillment state, and margin. Use it to connect customer commitments to production and inventory readiness.

## Executive reports

Executive Report Packs are separated into Retail and Production outputs. Reports include product names in product-level action tables, repeated section identity on continuation pages, and operational KPIs appropriate to the selected workspace.

## Roles

- **DEV** — platform-wide support, diagnostics, integrations, organizations, facilities, users, and sandbox access.
- **Admin** — organization administration and assigned operational workspaces.
- **Buyer** — retail analytics, purchasing, audits, compliance, and reports.
- **Planner** — production planning, scheduling, orders, and capacity.
- **Supervisor** — execution oversight, audits, production status, and variances.
- **Operator** — assigned execution and count workflows.
- **QA** — audit, compliance, hold, COA, and production-quality workflows.
- **Read only** — authorized views without operational mutation.

## Mobile use

- Use Operations Home shortcuts to avoid deep navigation.
- Inventory Counts supports phone/tablet cameras and external scanners.
- Tables can be searched and opened fullscreen.
- Rotate to landscape when reviewing wide operational tables.

## Support and safety

- Never share your password or integration keys.
- Sign out on shared devices.
- The application signs out inactive durable accounts after the configured idle period.
- Operational calculators and AI guidance do not replace state regulations, METRC requirements, POS documentation, or your compliance team's review.
