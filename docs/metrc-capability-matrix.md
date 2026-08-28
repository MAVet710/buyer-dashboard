# Metrc capability evidence matrix

Verified: 2026-08-28

This matrix records technical API-documentation evidence for DoobieLogic's Metrc integration. It is not a statement of legal authority, license scope, or user permission. Runtime access still requires an exact organization, facility, Metrc license, credential, jurisdiction, environment, and provider permission match.

## Evidence policy

- Market membership comes from Metrc's official partner directory: `https://www.metrc.com/partners/`.
- Jurisdiction evidence comes from that market's official `https://api-<market>.metrc.com/Documentation/` page.
- A capability is enabled only when representative endpoint-family evidence was directly reviewed.
- A temporary documentation failure is never converted into a guessed capability.
- `package_waste` remains `unknown/unverified` because this review did not establish a direct package-waste endpoint family.
- Sandbox endpoint evidence is classified `sandbox-only` and does not authorize production use.
- All provider reads remain read-only until a separate, explicit action framework authorizes mutations.

## Jurisdiction status

| Jurisdiction | Market | Documentation capability review | Runtime posture |
| --- | --- | --- | --- |
| AK | Alaska | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| AL | Alabama | Pending | Unknown capabilities fail closed |
| CA | California | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| CO | Colorado | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| DC | District of Columbia | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| GU | Guam | Pending | Unknown capabilities fail closed |
| IL | Illinois | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| KY | Kentucky | Pending | Unknown capabilities fail closed |
| LA | Louisiana | Pending | Unknown capabilities fail closed |
| ME | Maine | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| MD | Maryland | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| MA | Massachusetts | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| MI | Michigan | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| MN | Minnesota | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| MS | Mississippi | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| MO | Missouri | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| MT | Montana | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| NV | Nevada | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| NJ | New Jersey | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| NY | New York | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| OH | Ohio | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| OK | Oklahoma | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| OR | Oregon | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| RI | Rhode Island | Pending | Unknown capabilities fail closed |
| SD | South Dakota | Verified | Evidence-backed capabilities allowed after tenant/facility mapping |
| VI | U.S. Virgin Islands | Pending | Unknown capabilities fail closed |
| VA | Virginia | Pending | Unknown capabilities fail closed |
| WV | West Virginia | Pending | Unknown capabilities fail closed |

Current directly reviewed jurisdictions: **20 of 28**.

Pending direct documentation review: **AL, GU, KY, LA, RI, VI, VA, WV**.

## Evidence-backed endpoint families

For directly reviewed jurisdictions, the registry records representative current v2 documentation evidence for these resource families when present:

- employee permissions
- items
- packages and package adjustments
- package finish/unfinish
- locations
- lab tests
- incoming/outgoing transfers
- transfer templates and deliveries
- wholesale delivery packages
- manifests
- transporters and vehicles
- plants and plant batches
- harvests
- processing jobs
- sales receipts
- tags
- sandbox setup/package/tag helpers

`facilities/v2/` remains the connection-validation surface for all explicitly registered Metrc markets.

## Normalized read layer

`modules/regulatory/metrc_resources.py` is the provider-neutral read planner. It validates jurisdiction, capability, environment, exact facility license scope, path parameters, and evidence before a request can be emitted. Provider payloads are then wrapped in a stable record envelope while preserving the complete original Metrc record under `source`.

Existing receiving helpers route through the same planner, including paginated incoming transfers, delivery packages, and lab-result reads.

## Refreshing the matrix

Run:

```bash
python scripts/verify_metrc_capabilities.py
```

To inspect one jurisdiction:

```bash
python scripts/verify_metrc_capabilities.py --jurisdiction MA
```

To use it as a strict evidence availability check:

```bash
python scripts/verify_metrc_capabilities.py --strict
```

The verifier intentionally does **not** change registry code. Its output must be reviewed before capability evidence is promoted or removed.
