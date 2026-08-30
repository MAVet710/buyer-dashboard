# Controlled receiving discrepancies

DoobieLogic keeps state-system truth and physical receiving truth separate.

For Metrc-backed inbound receiving, the provider quantity, unit, package identity, manifest/source, lab state, facility license, jurisdiction, and environment remain provider-controlled. Operators do not edit those values to make a delivery appear to match.

## Operator flow

1. Open the inbound transfer for the active facility.
2. Map each incoming package to the local product and receiving room.
3. Enter the **physical count** and physical condition for each package.
4. Confirm provider state. DoobieLogic stores the exact read-only preflight snapshot.
5. If the physical package set/count/unit/condition matches the provider snapshot, the receipt may proceed to the second provider readback.
6. If it does not match, choose **Record discrepancy & block receipt**.
7. The discrepancy becomes durable and local inventory posting is blocked.
8. An authorized supervisor/QA/admin/developer reviews and resolves the exception with a reason.
9. After resolution, refresh the physical review. If discrepancy history exists on the same preflight, a fresh exact physical observation set is mandatory before posting.
10. DoobieLogic performs the existing second fresh provider read. Only an exact provider match can enter the atomic local receipt path.

## Durable discrepancy types

- `short`: observed quantity is below provider quantity.
- `over`: observed quantity is above provider quantity.
- `missing`: a provider package is not physically present, including a zero physical count.
- `unexpected`: a physically observed package is not part of the provider-confirmed transfer snapshot.
- `damaged`: quantity may match, but the package condition requires review.
- `other`: unit mismatch or another physical exception requiring review.

## Safety boundaries

- Recording or resolving a discrepancy never writes to Metrc.
- Recording or resolving a discrepancy never creates or adjusts inventory.
- Metrc quantity and unit remain read-only in the receiving UI.
- Open discrepancies block local inventory before the second provider call.
- A discrepancy resolution is an audit decision, not permission to silently accept a different quantity.
- After discrepancy history exists, posting requires a fresh exact physical count.
- The second provider readback must still match the original prepared snapshot.
- The existing `processing` unknown-outcome state continues to prevent blind retry after an interrupted local post.
- Discrepancy inspection is bound to the exact organization, facility, operation, preflight, and transfer.
- Resolution is restricted to authorized supervisor/QA/admin/developer roles.
- A newer provider preflight cancels open discrepancies attached to the superseded snapshot instead of carrying stale exceptions forward.

## Provider acceptance remains outside this workflow

This feature does not invent an inbound Metrc acceptance endpoint. Where the jurisdiction/provider requires transfer acceptance in the state system, that action remains outside this read-only receiving control until a separately reviewed and verified provider write contract exists.

## Relationship to reconciliation

Receiving discrepancies answer a different question from the traceability synchronization ledger:

- **Receiving discrepancy:** what was physically observed does not match the provider-confirmed inbound shipment.
- **Traceability reconciliation:** DoobieLogic and the external state system disagree about an external compliance action or readback state.

Both are explicit and auditable. Neither condition is hidden by mutating local data to force apparent agreement.
