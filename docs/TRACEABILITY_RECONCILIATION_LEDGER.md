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

Each transaction is bound server-side to organization and facility and records provider, jurisdiction, environment, license, direction, entity, operation, provider reference, attempts, retry eligibility, local state, provider state, readback result, mismatch reason, reconciliation evidence, actor, and timestamps.

Payloads are sanitized recursively before persistence. Credential-like keys such as API keys, authorization headers, tokens, passwords, and client secrets are replaced with `[REDACTED]`.

The React API exposes facility-scoped ledger list and detail resources under `/api/v1/traceability-actions/ledger`. Package 360 surfaces the latest operator status, provider scope, attempts, retry state, and mismatch/error without requiring the operator to leave the package context.

## Safety boundaries

- Metrc/BioTrack intents require explicit jurisdiction, sandbox/production environment, and license.
- Idempotency is enforced within organization, facility, and provider scope.
- HTTP success does not mark a transaction verified.
- Recording reconciliation facts does not change lifecycle state.
- Retry eligibility is visible but does not cause silent retry.
- Manual lifecycle changes require an authorized role, confirmation, reason, and audit history.
- Unsupported provider operations remain blocked even if they appear in the provider-neutral action catalog.
