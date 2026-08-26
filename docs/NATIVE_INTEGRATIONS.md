# DoobieLogic Native Integrations

This runbook covers the production integration layer introduced after the Beat Distru release.

## Core rules

- Organization and facility scope are mandatory for operational provider work.
- Provider credentials are encrypted with `INTEGRATION_ENCRYPTION_KEY` and are never returned to the browser after save.
- `configured` does not mean `connected`. A provider becomes `connected` only after its provider-specific validation succeeds.
- AI recommendations never bypass deterministic validation or human approval for state-system mutations.
- Traceability lifecycle is explicit: `requested -> validated -> queued -> submitted -> accepted/rejected -> verified/reconciliation_required`.
- An accepted provider response is not the same as verified reconciliation.

## Metrc

Existing user credentials remain scoped to the active facility/license. The native receiving routes add live inbound reads:

- `GET /api/v1/native-integrations/metrc/incoming`
- `GET /api/v1/native-integrations/metrc/transfers/{transfer_id}/deliveries`
- `GET /api/v1/native-integrations/metrc/deliveries/{delivery_id}/packages`

Delivery-package preview compares live package labels to DoobieLogic inventory and reports `new` vs `already_received`. It does not mutate inventory.

Traceability actions are queued through `/api/v1/traceability-actions/queue`. Only Supervisor, QA, Admin, or DEV can dispatch queued provider mutations. Automatic Metrc dispatch is intentionally limited to operations with an explicit deterministic adapter. At this release those are package finish and package adjustment. Unsupported operations remain visible rather than being sent through a generic arbitrary-JSON escape hatch.

## BioTrack

BioTrack is state-contract driven. DoobieLogic does not pretend one BioTrack endpoint contract applies to every jurisdiction.

Admin/DEV routes:

- `POST /api/v1/native-integrations/biotrack`
- `POST /api/v1/native-integrations/biotrack/test`
- `POST /api/v1/native-integrations/biotrack/clear`

Required configuration includes an approved HTTPS base URL, facility/license, explicit login path, environment, username and password. Production requires `confirm_production=true`. A production connection should only be enabled after the applicable regulator/provider has issued the required API access and contract documentation.

## QuickBooks Online

Admin/DEV routes:

- `POST /api/v1/native-integrations/quickbooks`
- `POST /api/v1/native-integrations/quickbooks/test`
- `POST /api/v1/native-integrations/quickbooks/clear`
- `GET /api/v1/native-integrations/quickbooks/links`
- `POST /api/v1/native-integrations/quickbooks/item-links`
- `POST /api/v1/native-integrations/quickbooks/customers/{partner_id}/sync`
- `POST /api/v1/native-integrations/quickbooks/invoices/{invoice_id}/sync`

OAuth client ID, client secret and refresh token are encrypted. Rotated refresh tokens are persisted back into the encrypted provider record.

DoobieLogic uses `accounting_sync_links` to keep external IDs and QuickBooks SyncTokens durable. This prevents duplicate creates and supports version-safe updates.

Customer records can be created/updated from DoobieLogic trade partners. Invoice sync is intentionally blocked until:

1. the invoice customer has a QuickBooks customer link, and
2. every local product on the invoice has an explicit QuickBooks Item link.

DoobieLogic does not silently invent Item mappings because that can corrupt COGS/revenue categorization in the accounting system.

## Label printing and LabelGuard

Employee routes live under `/api/v1/label-printing`. Printer profiles can use browser, edge or ZPL transport. Print jobs are durable and tied to a versioned label template plus a LabelGuard review.

- A LabelGuard `fail` blocks printing.
- A `warning` requires an authorized override and reason.
- A `pass` can proceed through the normal authorized print workflow.

Edge printer agents use service-account routes:

- `GET /api/v1/external/v1/print-jobs`
- `POST /api/v1/external/v1/print-jobs/{job_id}/claim`
- `POST /api/v1/external/v1/print-jobs/{job_id}/complete`

Use facility-scoped service accounts where possible. Required scopes are `printing:read` and `printing:write`.

## Signed webhooks

Admin/DEV routes live under `/api/v1/webhooks`. The previous `/api/v1/control-tower/enterprise/webhooks` creation route remains only as a compatibility alias and is routed through the same secure implementation.

Signing secrets are shown once, encrypted at rest, and can be rotated. Delivery headers include:

- `X-DoobieLogic-Event`
- `X-DoobieLogic-Delivery`
- `X-DoobieLogic-Timestamp`
- `X-DoobieLogic-Signature: sha256=<hmac>`

The signature input is `<timestamp>.<raw JSON body>`. Consumers should compute HMAC-SHA256 with the webhook signing secret and use constant-time comparison.

Deliveries retry transient network/429/5xx failures and move to dead-letter after the configured attempt limit. 2xx is the only success class.

## Deployment gate

Migration head for this release is `0045_native_integrations`. The production readiness check requires:

- `accounting_sync_links`
- `printer_profiles`
- `label_print_jobs`

in addition to the prior operational tables. Never promote an API candidate whose database revision does not match the image Alembic head.
