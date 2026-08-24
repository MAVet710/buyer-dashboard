# DoobieLogic approved knowledge sources

This directory contains the reviewed public-source catalog and curated field-practice notes for the DoobieLogic AI knowledge layer. It is intentionally separate from customer/facility SOP uploads.

## Safety model

- Only HTTPS hosts explicitly listed in `approved_sources.json` may be downloaded by the approved-source seeder.
- Redirect destinations are validated against the same exact-host allowlist.
- Jurisdiction-specific authority-level 1 material must remain facility scoped.
- Massachusetts regulatory sources are not global knowledge. Until facilities have an explicit jurisdiction/state field enforced by retrieval, the facility boundary prevents Massachusetts rules from becoming another state's compliance evidence.
- METRC and Dutchie material is authority level 3 operational/vendor documentation. It must not be represented as law or regulatory authority.
- Curated community/forum material is authority level 6 field practice. It may support hypothesis generation, KPI design, and troubleshooting questions, but it cannot override approved SOPs, equipment manuals, engineering limits, safety requirements, or validated facility run data.
- Curated repository knowledge can only be loaded from `knowledge_sources/curated`; path traversal and arbitrary local-file access are rejected.
- Draft and archived regulations do not belong in the active source catalog.
- Identical source bytes are deduplicated by SHA-256. When content at an approved source URL or curated source identity changes, the new version is indexed and the prior version at that facility is made inactive.
- `force_reindex` exists for an intentional re-index, including a later vector-embedding rebuild. It is never required for ordinary refreshes.

## Current Massachusetts baseline

The starter catalog is reviewed as of 2026-08-24 and includes the current June 18, 2026 copies of 935 CMR 500 and 935 CMR 501, selected Cannabis Control Commission guidance/orders, current Massachusetts Metrc bulletins, and relevant Dutchie inventory/Metrc workflow documentation.

The catalog is source metadata, not a substitute for checking publication status. Review cadence is recorded per source so a future scheduled verifier can flag stale URLs or superseded documents.

## Curated extraction field practice

`knowledge_sources/curated/future4200_extraction_field_practice.md` distills recurring process-improvement themes from selected Future4200 extraction discussions. The pack intentionally focuses on measurement and troubleshooting patterns rather than forum recipes.

Its main operating ideas are:

- measure cannabinoid recovery, not only crude mass yield;
- use mass balance to locate stage losses;
- test spent biomass/residues when a loss cannot be explained;
- diagnose vacuum/recovery-system integrity before assuming a capital upgrade is needed;
- treat filtration as a measurable unit operation;
- normalize comparisons for input potency and material condition;
- use controlled experiments and predefined success metrics;
- troubleshoot distillation from feed quality, maintenance state, and validated machine baselines.

Future4200-derived field practice may answer “what should we investigate next?” It must not, by itself, answer “what exact temperature/pressure/solvent ratio/flow/media load/dwell time should we run?” Exact operating parameters still require an approved SOP, equipment manual, validated facility data, or an appropriately authoritative engineering/safety source.

## In-app use

Level DEV users see the Knowledge Library on `Data & Settings -> AI & METRC Integrations`.

- **Seed / Update Approved Sources** indexes both the built-in allowlisted public catalog and the built-in curated field-practice packs for the currently selected facility.
- **Upload & Index** accepts PDF, DOCX, TXT, Markdown, and HTML for internal SOPs, policies, manuals, and reviewed references.
- Government/regulatory uploads remain subject to the server-side authority policy in `backend/app/routers/ai_agents.py`; clients cannot self-assign authority levels.

The AI Knowledge Library list is tenant/facility scoped and does not return organization or facility identifiers in document rows.

## Offline bundle

A developer can create a reproducible local snapshot of remote approved sources without touching the application database:

```bash
python scripts/build_knowledge_bundle.py --output knowledge_bundle
```

Download a subset by repeating `--key`:

```bash
python scripts/build_knowledge_bundle.py \
  --key ma_935_cmr_500_current \
  --key ma_935_cmr_501_current \
  --output knowledge_bundle
```

The generated `bundle.json` records final URL, content type, retrieval time, byte size, and SHA-256 for every downloaded source. Curated repository notes are source-controlled separately and are seeded directly from the trusted repository path. The `knowledge_bundle/` output is intentionally not a source-controlled knowledge database.

## Adding a public source

1. Confirm the source is authoritative for the class assigned to it.
2. Prefer the original regulator/vendor/manufacturer URL, not a mirror.
3. Add the exact hostname to `allowed_domains` only if the publisher is intentionally trusted.
4. Record jurisdiction and effective/version dates when they exist.
5. Choose the authority class already defined by the runtime.
6. Keep jurisdiction-specific regulatory material facility scoped.
7. Add/update catalog tests.
8. Review the source periodically and deactivate or replace it when superseded.

## Adding curated community knowledge

1. Do not place raw forum dumps in the regulatory/public-source manifest.
2. Write a bounded curated note under `knowledge_sources/curated` with source provenance.
3. Keep it authority level 6 / `field_practice` unless a higher-authority source independently supports the claim.
4. Remove or generalize unsafe recipe-style setpoints and clearly state where machine/SOP validation is required.
5. Add the curated source through the server-controlled `curated_sources.py` registry.
6. Add tests for authority, facility scope, path safety, and idempotent seeding.
