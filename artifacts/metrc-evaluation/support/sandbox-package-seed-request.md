# Metrc Support Request — MA Sandbox Package Provisioning

We are completing the Massachusetts Metrc Generic Evaluation (`Generic_Evaluation_for_All_States_MASTER 10.2025`) and need legitimate retail package inventory for the Sales / Sales Delivery evaluation sequence.

## Provisioning endpoint reviewed

Current Massachusetts sandbox documentation exposes:

`POST /sandbox/v2/packages/create`

## Observed result

A prerequisite provisioning attempt returned **HTTP 401** after the same integration context successfully completed read-only item-detail, active-item, and available-package-tag requests.

This attempt was only a sandbox stock prerequisite. We are **not** treating it as task 25 or as a Sales evaluation attempt.

The exact cause of the 401 is unknown. We are not assuming a missing named permission or changing authentication schemes without provider documentation.

## Requested clarification

Please confirm the supported procedure for provisioning legitimate sales-capable package inventory in the Massachusetts integrator sandbox:

1. Is `POST /sandbox/v2/packages/create` intended to be available to our integrator/user sandbox context?
2. Are there facility-type or provider-side provisioning prerequisites for this sandbox endpoint?
3. Does the endpoint require any authorization condition beyond the documented MA sandbox authentication model?
4. If direct sandbox package creation is not enabled for this context, can Metrc provision or identify an existing package suitable for the Sales and Sales Delivery workbook steps?
5. What package attributes/state should be used to ensure the reference package is eligible for the required receipt and delivery transactions?

We do not need to share API key values in this request. We will retain actual provider readback evidence for any package used in the evaluation.
