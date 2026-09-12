# MA package resume contract review

Reviewed 2026-09-12 against the original regulator workbook and current public Metrc documentation. No company credentials were used to retrieve documentation.

## Original workbook

The Packages worksheet Step 1 explicitly permits either the Harvest Step 1 package or an existing package. This permits an independent tasks 25-26 path; it does not waive or pass tasks 17-24. Tasks 27-29 remain held for downstream consumers.

## Official documentation inspected

Public collection: https://sandbox-api-ma.metrc.com/Documentation/postman-json

Targeted method pages, as linked by the official documentation UI:
- https://sandbox-api-ma.metrc.com/Documentation/Method?key=Sandbox.post_sandbox_v2_facility_tags.POST
- https://sandbox-api-ma.metrc.com/Documentation/Method?key=Sandbox.get_sandbox_v2_tagtypes.GET
- https://sandbox-api-ma.metrc.com/Documentation/Method?key=Sandbox.post_sandbox_v2_packages_create.POST
- https://sandbox-api-ma.metrc.com/Documentation/Method?key=Packages.post_packages_v2_.POST
- https://sandbox-api-ma.metrc.com/Documentation/Method?key=Sales.get_sales_v2_customertypes.GET

Captured in GitHub Actions public documentation jobs 103600219175 and 103601323840. Temporary fetch/patch workflows were removed after review; normal CI must run on the final branch SHA.

### Findings

The Postman export omits a tag-generation body, but the full method documentation explicitly supports `{ "TagType": "Marijuana Package", "Count": 100 }`. The runner uses one requested tag, after discovering its actual type. The response contains TagType, Count and Labels. Never infer a successful POST from a change in available tags.

Tag type discovery returns objects including Name and TagInventoryType. Sales customer types instead return strings, with no licenseNumber parameter. Filtering string values out of those results incorrectly manufactures an empty list.

Opening-balance package creation supports Count and optional FilterBy/FilterValue. It is a provisioning operation, not workbook task 25. Its documentation distinguishes unauthorized keys and disallowed request origin as possible 401 causes; our previous 401 does not identify which occurred.

The package-create example uses null for optional RequiredLabTestBatches. The shared builder now preserves omitted/explicit null rather than silently coercing it to false; explicitly supplied legacy booleans remain unchanged.

The collection inherits Basic authentication, including for setup, but the user's written Metrc setup instruction explicitly requires the Connect vendor key in x-metrc-key. Preserve that setup-specific implementation. Do not extrapolate it to other endpoint families or regenerate the established user.

## Execution boundary

The pending runner now requires explicit organization, facility, source label and source ID. It defaults to read-only preflight; execute mode additionally requires approval matching its exact run ID. A PostgreSQL transaction advisory lock serializes evaluation workers for the facility. All event reads are tenant-scoped. Mutation intent is durable before dispatch, and interrupted/failed mutations cannot be automatically retried.

No credential value is exported. IDs alone are not success: task 25 must also verify the created package's item/unit/quantity and the source decrease from 3 to 2. Task 26 must read back the actual requested new item. Only task-specific evidence with these postconditions may contribute to evaluation counts.

No new task is claimed passed by this document.
