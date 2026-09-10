# Traceability reconciliation ledger

DoobieLogic uses one provider-neutral ledger for Metrc, BioTrack, and future state systems. Operational inventory, production, receiving, and cultivation records remain the local source of truth; the ledger records the external compliance projection and its verification evidence.

## Lifecycle

`requested → validated → queued → submitted → accepted → verified`

Rejected or uncertain writes may move to `reconciliation_required`. Provider acceptance is shown as **Provider Accepted**, not **Synced**. Only a verified readback or an explicitly reviewed reconciliation can reach **Synced**.

Operator labels are:

| Durable state | Operator label |
| --- | --- |
| requested, validated, queued | Pending |
| submitted | Awaiting Verification |
| accepted | Provider Accepted |
| verified | Synced |
| rejected | Failed |
| reconciliation_required | Reconciliation Required |
| cancelled | Blocked |

## Recorded scope and evidence

Each transaction is bound server-side to organization, facility, and provider environment. It records correlation and idempotency keys, direction, source, entity and parent/related entities, external ID/tag, attempts, classified error and retryability, reconciliation and resolution state, safe request/response summaries, actor, and timestamps.

Payloads are sanitized recursively before persistence. Credential-like keys such as API keys, authorization headers, tokens, passwords, and client secrets are replaced with `[REDACTED]`.

The React API exposes paginated exception queries under `/api/v1/traceability-actions/ledger/exceptions` and bounded Entity 360 history under `/api/v1/traceability-actions/entities/{type}/{id}/history`. Package, Product, Plant, Harvest, and Production Run 360 show current sync state, recent events, unresolved exceptions, and latest successful inbound/outbound evidence.

Incremental Metrc reads write one correlated inbound ledger event per resource only after the provider delta and local snapshot persistence complete. Transport and provider failures create classified exceptions. Safe retries retain the original idempotency key, use bounded backoff, and only prepare the existing action for separately authorized dispatch.

## Safety boundaries

- Metrc/BioTrack intents require explicit jurisdiction, sandbox/production environment, and license.
- Idempotency is enforced within organization, facility, and provider scope.
- HTTP success does not mark a transaction verified.
- Recording reconciliation facts does not change lifecycle state.
- Retry eligibility is visible but does not cause silent retry.
- Manual lifecycle changes require an authorized role, confirmation, reason, and audit history.
- Unsupported provider operations remain blocked even if they appear in the provider-neutral action catalog.
