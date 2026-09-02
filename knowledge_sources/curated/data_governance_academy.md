# DoobieLogic Data Governance and Reliability Academy

## Audience

Primary agent: Data Hub Agent.
Secondary use: every DoobieLogic agent when the reliability, mapping, provenance, or freshness of source data is material to a conclusion.

## Source posture

This is an independently written synthesis of data reliability, governance, provenance, lineage, mapping, and operational data-quality principles.

Primary references:
- GAO Assessing Data Reliability (GAO-20-283G): https://www.gao.gov/products/GAO-20-283G
- GAO 2025 Green Book: https://www.gao.gov/greenbook
- NIST data and information-management work: https://www.nist.gov/

GAO's current data-reliability framework emphasizes whether data are accurate, complete, and applicable for the intended purpose. Those concepts are central to this academy.

## 1. Data quality is purpose-specific

A dataset is not simply "good" or "bad." It may be reliable enough for one decision and insufficient for another.

Ask:
- What decision will use the data?
- What fields materially support the conclusion?
- What error could change the decision?
- What level of completeness/accuracy is necessary?
- What corroborating evidence exists?

## 2. Core quality dimensions

Use these dimensions explicitly:
- **accuracy:** reflects the underlying event/value;
- **completeness:** required records/fields are present;
- **consistency:** definitions and values agree across records/systems;
- **timeliness/freshness:** current enough for the decision;
- **validity:** conforms to expected domain/format/rules;
- **uniqueness:** duplicates are understood/controlled;
- **applicability:** suitable for the intended question;
- **lineage/provenance:** origin and transformations are known.

Do not collapse all quality issues into a single score without showing the components.

## 3. Source authority

Multiple systems can contain versions of the same concept. Define which is authoritative for which field or event.

Examples:
- state seed-to-sale system may be authoritative for regulated package identity/events;
- DoobieLogic may be canonical for internal planning or approved transformed datasets;
- POS may be authoritative for completed sales transactions;
- accounting system may be authoritative for posted financial entries;
- lab COA may be authoritative for reported test results;
- facility SOP/master-data system may be authoritative for internal definitions.

Authority can be field-specific rather than system-wide.

## 4. Provenance

For material data, retain:
- source system;
- source file/report/API endpoint;
- organization/facility;
- extraction timestamp;
- reporting period;
- version/schema;
- uploader/integration where appropriate;
- transformations;
- validation result.

A number without provenance is harder to trust or reproduce.

## 5. Lineage

Data lineage explains how a value moved from source to result.

Track:
- raw source field;
- mapping rule;
- transformation/conversion;
- join keys;
- filters;
- aggregation;
- derived formula;
- final field/report/tool.

The Data Hub Agent should be able to answer, "Where did this number come from?" without relying on model memory.

## 6. Schema mapping

A mapping should specify more than similar column names.

For each mapped field, consider:
- semantic meaning;
- unit of measure;
- data type;
- allowed values;
- nullable behavior;
- time zone/date basis;
- grain (item, lot, transaction, day, customer, facility);
- identifiers/keys;
- sign convention;
- source system version.

"Qty" in one file may mean on-hand units while another means transaction quantity.

## 7. Grain

Always identify what one row represents.

Examples:
- one sale line;
- one package;
- one inventory snapshot per day;
- one plant;
- one production run;
- one PO line;
- one customer order;
- one COA analyte result.

Joining datasets at incompatible grains can duplicate values and create false totals.

## 8. Keys and entity resolution

Prefer stable identifiers over names.

Potential keys:
- package/plant tag;
- product/SKU ID;
- vendor/customer ID;
- order/PO ID;
- invoice ID;
- production-run ID;
- facility/license ID;
- COA/sample ID.

Name-based matching should be treated as probabilistic when exact IDs are absent.

## 9. Duplicate detection

A duplicate record can be:
- true duplicate ingestion;
- legitimate repeated event;
- multiple lines for same transaction;
- snapshot from different dates;
- same entity from different source systems;
- reversal/correction.

Do not delete duplicates until their business meaning is understood.

## 10. Missing data

Distinguish:
- truly zero;
- blank/null;
- not applicable;
- not collected;
- not mapped;
- withheld/redacted;
- stale/unavailable source;
- parsing failure.

Replacing all missing values with zero can create false conclusions.

## 11. Freshness

Freshness should be measured relative to the operational need.

Examples:
- live inventory may need near-current data;
- monthly finance review may tolerate older posted periods;
- a regulation requires effective-date/version tracking;
- static master data may change infrequently.

Expose last successful sync, source-report period, and stale thresholds separately.

## 12. Time semantics

Time errors are common.

Verify:
- event timestamp vs report date;
- local time zone vs UTC;
- business day cutoff;
- order date vs ship date vs receive date;
- inventory snapshot time;
- effective date;
- created_at vs updated_at.

Do not compare two time series until their time basis aligns.

## 13. Units and conversions

Store or preserve the original unit when possible.

Before conversion:
- identify source unit;
- identify target unit;
- use a documented deterministic conversion;
- respect density or concentration dependencies when relevant;
- preserve precision/rounding rules;
- do not infer count-to-mass relationships.

## 14. Validation layers

Useful validation categories:
- structural: file readable, expected columns/types;
- domain: values in allowed ranges/sets;
- referential: foreign keys/entities resolve;
- reconciliation: totals agree with authoritative source;
- temporal: dates/timestamps plausible;
- business-rule: state transitions make sense;
- cross-source: independent systems agree where expected.

## 15. Reconciliation testing

For a material dataset, compare totals and counts to a known control when possible.

Examples:
- file total sales vs source-system report total;
- inventory package count vs seed-to-sale package count;
- PO received units vs receiving records;
- production output vs inventory package creation;
- COA count vs released batch count.

Explain tolerances rather than hiding differences.

## 16. Transformation transparency

Derived fields should have deterministic definitions.

Examples:
- days of supply;
- gross margin;
- aging days;
- fill rate;
- yield;
- OEE components;
- A/R days;
- variance percentage.

The Data Hub Agent should report formula, source fields, and assumptions.

## 17. Data contracts

A data contract can define:
- schema;
- required fields;
- types;
- units;
- allowed values;
- source owner;
- refresh expectation;
- versioning;
- failure behavior.

When an upstream source changes, fail visibly rather than silently mapping the wrong column.

## 18. Tenant isolation

Organization/facility scope is part of data correctness and security.

Never:
- merge data across facilities without authorized intent;
- retrieve another organization's knowledge;
- use global defaults to fill tenant-specific regulatory facts;
- expose source records outside the authorized scope.

A technically accurate cross-tenant result is still an invalid result.

## 19. PII and sensitive data minimization

Only expose fields needed for the operational question. Prefer aggregation or bounded rows where possible.

Do not place secrets, credentials, tokens, unnecessary personal information, or unrelated sensitive fields into model context.

## 20. Data reliability assessment workflow

For a decision-critical source:
1. Define intended use.
2. Identify critical fields.
3. Review source/provenance and known limitations.
4. Check completeness.
5. Test accuracy against source evidence or samples.
6. Check consistency/validity.
7. Assess freshness.
8. Assess applicability to purpose.
9. Document limitations.
10. Decide whether data are reliable enough for the intended conclusion.

## 21. Confidence

Confidence should decrease when:
- source is stale;
- key fields are missing;
- mapping is inferred;
- identifiers do not resolve;
- reconciliation fails;
- units are ambiguous;
- data grain is unclear;
- sample is too small;
- different sources materially conflict.

Do not compensate for bad data with more confident prose.

## 22. Data-quality handoffs

If a domain agent encounters unreliable data, the Data Hub Agent should help answer:
- which source failed;
- which field/mapping is affected;
- which downstream calculations are contaminated;
- whether there is a safe fallback source;
- what must be re-imported, remapped, or reconciled;
- whether historical results need reprocessing.

## Recommended answer pattern

For a data-quality question:
- **Intended use** — what decision depends on the data.
- **Source/provenance** — origin, period, facility, freshness.
- **Reliability findings** — accuracy, completeness, consistency, applicability.
- **Mapping/lineage** — where the critical fields came from.
- **Impact** — which metrics/agents/reports are affected.
- **Remediation** — smallest deterministic fix or evidence request.
- **Confidence** — whether the data are reliable enough for the intended purpose.