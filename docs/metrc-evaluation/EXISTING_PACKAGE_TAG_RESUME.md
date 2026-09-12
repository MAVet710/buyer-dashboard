# MA package evaluation: explicitly allocated existing tags

## Purpose and scope

Tasks 25-26 can use an already-available package tag without calling the sandbox
provisioning endpoints. The existing integration credentials and normal provider
authorization still apply. This does not resolve the separate Task 17, lab,
sales-stock, or transfer-fixture prerequisites and does not change their status.

Official endpoint reference, reviewed 2026-09-12:
https://api-ma.metrc.com/Documentation/

The current MA documentation lists `GET /tags/v2/package/available` separately
from `GET /sandbox/v2/tagtypes` and `POST /sandbox/v2/facility/tags`.

## Configuration

Keep the existing organization, facility, source-package and run-ID settings.
Set `METRC_PACKAGE_EVAL_TAG_ALLOCATION` to the JSON object below, using real
values derived from the preserved checkpoint. Do not commit the populated
allocation, credentials, provider responses or evaluation state to Git.

```json
{
  "schema_version": 1,
  "run_id": "<same approved package run ID>",
  "evaluation_run_id": "<original evaluation run ID>",
  "state": "MA",
  "environment": "sandbox",
  "license_number": "<authorized source license>",
  "source_id": "<actual source package provider ID as a string>",
  "source_label": "<actual source package label>",
  "destination_label": "<one explicitly selected different available label>",
  "protected_labels": ["<source label>", "<Task 17 reserved label>"],
  "task17_reserved_label": "<Task 17 reserved label>",
  "checkpoint_sha256": "<SHA-256 of preserved state.local.json bytes>",
  "reservation_evidence_sha256": "<SHA-256 of Task 17 tag-discovery evidence bytes>"
}
```

Include every other protected package label for the same facility in
`protected_labels`, not only the two minimum entries illustrated above.
Hashes are provenance references, not signatures or current-availability proof.
Do not change the original checkpoint files to make their hashes match.

## Execution gates

1. Start in `preflight` mode. The plan must match the exact run, MA sandbox,
   source package and authorized license. The destination may not be protected.
2. Fresh facility, source-package, compatible-item and available-tag reads must
   pass. The tag row must belong to the discovered provider facility and have
   the `CannabisPackage` inventory type. Missing or ambiguous tags fail closed.
3. This existing-tag path does not call sandbox provisioning or sales reference
   endpoints. It is an explicit choice, never an automatic response to a 401.
4. Execute only after clean preflight and exact-run approval. Persist the
   allocation, recheck availability, and durably claim each operation before
   contacting Metrc. Claims use a short PostgreSQL advisory-lock transaction;
   that transaction ends before HTTP work, preserving the one-connection budget.
5. Existing started markers without verified results block retries. Do not erase
   those markers, switch run IDs, or silently choose another tag. Reconcile the
   provider outcome and retain the original attempt evidence.
6. Task 25 must verify the new package and source quantity; Task 26 must verify
   the actual changed item. A successful build or preflight is not a task pass.
7. Preserve Task 17's reserved plant/tag. Do not execute Tasks 27-29 while later
   consumers still depend on the package. Disable execution after the bounded run.

## Tests

`python -m pytest -q tests/test_metrc_existing_package_tag.py`

These are offline synthetic-provider regressions, not Metrc evidence. The
transaction tests use mocked sessions; real PostgreSQL and provider execution
must still be observed in the authorized runtime before certification claims.
