# Metrc Phase 1B package write promotion

Phase 1B continues the competitive-displacement traceability program after the canonical reconciliation ledger shipped in migration `0056_traceability_reconciliation`.

## Current promotion state

The following Metrc v2 package endpoints now have explicit deterministic payload builders in `services/metrc_native.py`:

| DoobieLogic operation | Metrc endpoint | Deterministic body | Network dispatch |
| --- | --- | --- | --- |
| `package_move` | `PUT /packages/v2/location` | `Label`, `Location`, `MoveDate`, optional `Sublocation` | Locked |
| `package_unfinish` | `PUT /packages/v2/unfinish` | `Label` | Locked |
| `package_item_update` | `PUT /packages/v2/item` | `Label`, `Item` | Locked |
| `package_note_update` | `PUT /packages/v2/note` | `PackageLabel`, `Note` | Locked |

The official Metrc Massachusetts v2 documentation lists all four endpoints. The request-field shapes used here are also cross-checked against a generated Metrc v2 SDK model surface. That is sufficient to implement and regression-test deterministic payload construction, but it is **not** treated as sufficient evidence to enable a compliance-changing network write.

## Why dispatch remains locked

DoobieLogic intentionally separates these claims:

1. Endpoint documented.
2. Deterministic payload implemented.
3. Request accepted by a real Metrc sandbox.
4. Fresh provider readback confirms the intended state.
5. Reconciliation evidence is durable in the DoobieLogic traceability ledger.
6. Production execution is explicitly promoted for the verified jurisdiction/environment.

Phase 1B currently completes steps 1 and 2 for the four operations above. Steps 3-5 require working sandbox credentials and controlled test records. Production enablement must not occur before those gates are complete.

`require_metrc_write_contract()` remains the final network gate. All four contracts continue to have `dispatch_enabled=False`, so even a correctly constructed payload cannot leave DoobieLogic through `submit_metrc_action()` yet.

## Sandbox verification checklist

When sandbox access is available, verify each operation separately.

### Package move

- Create or select a sandbox package with a known starting location.
- Read the package immediately before the change.
- Submit `PUT /packages/v2/location` using the deterministic body.
- Capture the provider response and request attempt in the traceability ledger.
- Perform a fresh `GET /packages/v2/{label}` or equivalent package readback.
- Confirm Location, Sublocation, and movement date semantics match the request.
- Confirm repeated/idempotent behavior does not create an unsafe duplicate effect.

### Package unfinish

- Finish a disposable sandbox package through the already controlled finish path.
- Confirm it is inactive/finished through provider readback.
- Submit `PUT /packages/v2/unfinish` with only the package label.
- Perform a fresh package readback.
- Confirm the package returns to the expected active lifecycle state.

### Package item update

- Select a disposable sandbox package and valid target Item.
- Capture the original Item.
- Submit `PUT /packages/v2/item` with `Label` and `Item`.
- Perform a fresh package readback.
- Confirm the provider Item matches the requested Item.
- Treat permission, test-state, or lifecycle restrictions as provider preconditions rather than bypassing them.

### Package note update

- Capture the existing package note through provider readback when available.
- Submit `PUT /packages/v2/note` using `PackageLabel` and `Note`.
- Perform a fresh package readback.
- Confirm the provider note matches exactly.
- Verify the facility user has the Metrc permission required to manage package notes.

## Promotion rule

After successful sandbox write/readback evidence exists for an operation:

- add focused provider integration evidence/tests;
- update the relevant write-contract note;
- constrain the contract to the exact verified jurisdictions/environments;
- enable sandbox dispatch first;
- run the normal traceability queue → dispatch → provider accepted → readback → verified flow;
- only then consider production promotion.

Do not turn on all jurisdictions merely because the endpoint name exists on multiple Metrc documentation sites. Jurisdiction capability and permission differences remain authoritative.

## Safety properties preserved by this slice

- no generic arbitrary Metrc path or arbitrary JSON dispatch exists;
- unknown payload keys are not forwarded by the new builders;
- tenant/facility/license/jurisdiction/environment scope remains server controlled;
- human approval and dispatch roles remain unchanged;
- `accepted` does not mean `verified`;
- retry eligibility does not cause silent retry;
- missing payload requirements fail before any network request;
- actual network dispatch for these four operations remains impossible until the registry is explicitly promoted.
