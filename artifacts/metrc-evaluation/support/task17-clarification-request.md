# Metrc Support Request — MA Evaluation Task 17 Applicability / Authorization

We are completing the Massachusetts Metrc Generic Evaluation (`Generic_Evaluation_for_All_States_MASTER 10.2025`) in the Metrc sandbox.

## Evaluation operation

- Workbook area: Plants, Step 3
- Current MA v2 endpoint: `POST /plants/v2/plantbatch/packages`
- Environment: Massachusetts sandbox

## Observed result

A bounded evaluation attempt returned **HTTP 401**. We have preserved the source plant and reserved package tag and have not retried the mutation blindly.

Our authenticated `GET /facilities/v2/` evidence returned 18 accessible facilities. In the captured facility records, every facility reported:

`FacilityType.CanCreateImmaturePlantPackagesFromPlants = false`

We understand that this facility-type flag is not by itself proof of the cause of the HTTP 401, so we are not assuming a specific missing permission or credential problem.

## Current documentation review

The current Massachusetts v2 API documentation still lists `POST /plants/v2/plantbatch/packages`. The endpoint documentation identifies plant/package inventory permissions relevant to this operation.

## Requested clarification

Please confirm the supported Massachusetts sandbox evaluation procedure for this workbook step:

1. Is `POST /plants/v2/plantbatch/packages` applicable to the MA integrator proficiency evaluation represented by the 10.2025 workbook?
2. If yes, what sandbox facility type/capability must be provisioned for the operation?
3. Does Metrc need to provision or enable an evaluation facility for this capability?
4. If the workbook step is handled differently for Massachusetts, what provider-approved procedure should be used so the evaluation requirement is satisfied and verifiable?
5. Is there any provider-side authorization prerequisite for this endpoint beyond the documented API/employee permission model that an integrator should request for the evaluation sandbox?

We are intentionally not including API keys, authorization headers, or credential values in this request.

Please do not advise us to fabricate or substitute a different task; we want to execute the exact supported MA evaluation procedure and retain verifiable provider evidence.
