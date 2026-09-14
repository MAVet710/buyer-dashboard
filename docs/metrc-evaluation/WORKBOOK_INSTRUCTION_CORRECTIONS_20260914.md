# MA Metrc Generic Evaluation 10.2025 instruction corrections

Source: direct review of the regulator-provided workbook uploaded 2026-09-14.

## Rerun credential rule

Evaluation reruns reuse the existing active Vendor Key and API User Key. The evaluation runner must not invoke `/sandbox/v2/integrator/setup`, generate a replacement user key, rotate the user key, or overwrite the saved user credential. User-key provisioning remains a separate explicit admin action.

This intentionally mirrors Metrc/Postman execution: existing credentials + exact facility `licenseNumber` + reviewed endpoint + reviewed payload.

## Permission model

The workbook distinguishes three permission layers:

1. Facility permissions set by the state.
2. Vendor Key permissions, which should be full in sandbox.
3. API User Key permissions inherited from the Metrc user when the key is generated.

The workbook notes that when permission for an action is not enabled, the action will typically return HTTP 401 Unauthorized. Therefore a scoped 401 is a permission/facility investigation signal and is not, by itself, proof that the saved key is invalid.

The Permissions sheet also states that sections marked `D` must be completed per facility and dependent permissions must be completed when requesting access.

## Counting model

The workbook contains 46 explicit regulator action rows. DoobieLogic historically added `GET /facilities/v2/` as internal Task 1, producing 47 internal checks. Historical numbering is preserved to avoid invalidating evidence, but reports must distinguish:

- 46 regulator action rows
- 1 mandatory facilities/permissions prerequisite
- 47 internal evidence checks

## Massachusetts open-loop context

Massachusetts is marked Open Loop = YES and the States sheet directs the evaluator to the `Closed Loop Environment ` sheet for starting-inventory direction. That sheet is therefore MA evaluation context. The separate `Closed Loop States PlantBatches` task sheet remains not applicable to MA.

## Submission rules

All applicable actions must return HTTP 200 and be verifiable before submission. GETs may inspect sandbox data, but evaluation writes must only modify data in facilities Metrc directs the integrator to use and data created by the integrator. Do not delete provider data that the integrator did not create.

The final XLSX also requires regulator verification fields to be populated; filling only CompanyInformation is not sufficient for final submission.
