# Metrc Support Request — MA Evaluation Eligible Lab Package

We are completing the Massachusetts Metrc Generic Evaluation (`Generic_Evaluation_for_All_States_MASTER 10.2025`). The applicable LabResults step requires a real provider execution of:

`POST /labtests/v2/record`

## Current prerequisite state

Our evaluation run has lab-related item/reference metadata, but that does not establish an eligible lab package. We have not fabricated a package or submitted invented test results.

The current Massachusetts v2 API documentation also exposes `GET /labtests/v2/types`, which we use to discover current test definitions before preparing any bounded record request.

## Requested sandbox prerequisite / procedure

Please provide or identify the supported Massachusetts sandbox procedure for obtaining an eligible package for the LabResults evaluation step, including:

1. the authorized lab facility/license where the record operation should be executed;
2. an actual package that is eligible for `POST /labtests/v2/record`;
3. the current applicable lab test-type definitions for that package/facility;
4. legitimate sandbox result data or the provider-approved method for constructing evaluation result values;
5. any required package/testing state that must exist before the record operation is accepted.

If the package must be created through another documented workflow, please identify that workflow.

We will verify package identity, facility scope, request, response, and provider readback. We will not place API keys or credential values in the evaluation evidence or this support request.
