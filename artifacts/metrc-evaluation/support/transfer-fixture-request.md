# Metrc Support Request — MA Evaluation Transfer / Wholesale Fixtures

We are completing the Massachusetts Metrc Generic Evaluation (`Generic_Evaluation_for_All_States_MASTER 10.2025`) and need real provider records for the transfer/wholesale read section.

## Required evaluation chain

The applicable workbook requires verifiable records for:

- `GET /transfers/v2/incoming`
- `GET /transfers/v2/outgoing`
- `GET /transfers/v2/rejected`
- `GET /transfers/v2/{id}/deliveries`
- `GET /transfers/v2/deliveries/{id}/packages`
- `GET /transfers/v2/deliveries/{id}/packages/wholesale`

The incoming/outgoing workbook rows require the applicable LastModified search windows.

## Discovery already completed

Authenticated discovery covered **18 accessible facilities**. For each facility we queried incoming, outgoing, and rejected transfers: **54 read-only requests total**.

All 54 requests returned **HTTP 200** and **zero records**.

These empty responses demonstrate successful reads but do not satisfy workbook steps that require an actual transfer/manifest record and linked children. We will not fabricate IDs or count an empty list as a found-record pass.

## Requested sandbox fixtures / procedure

Please provide or identify accessible Massachusetts sandbox records sufficient to verify:

1. at least one incoming transfer with a known LastModified timestamp;
2. at least one outgoing transfer with a known LastModified timestamp;
3. at least one rejected transfer;
4. a real transfer/manifest ID with at least one linked delivery;
5. a real delivery ID with package children;
6. wholesale package pricing children for the delivery where required by the evaluation.

If integrators are expected to create these reference records through another documented sandbox procedure, please identify that procedure rather than supplying static fixtures.

We will preserve the full facility → transfer → delivery → package/wholesale evidence chain. No API keys or authorization headers are included in this request.
