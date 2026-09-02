# DoobieLogic Traceability, Audit, and Master Data Academy

## Audience

Primary agents: Inventory Audit Agent, Nomenclature Agent, Repack Agent.
Secondary use: Inventory, Commercial, Wholesale, Production, Data Hub, Compliance.

## Source posture

This is an independently written synthesis of internal-control, data-reliability, traceability, transformation-genealogy, physical inventory, reconciliation, and master-data principles.

Primary references:
- GAO 2025 Green Book: https://www.gao.gov/greenbook
- GAO Assessing Data Reliability (GAO-20-283G): https://www.gao.gov/products/GAO-20-283G
- GS1 Global Traceability Standard: https://www.gs1.org/standards/gs1-global-traceability-standard/current-standard
- GS1 Fresh Fruit and Vegetable Traceability Guideline: https://www.gs1.org/standards/fresh-fruit-and-vegetable-traceability-guideline/current-standard
- FDA Traceability Lot Code educational page: https://www.fda.gov/food/food-safety-modernization-act-fsma/traceability-lot-code

GS1 and FDA examples are used as transferable traceability concepts, not as cannabis law unless the applicable jurisdiction independently requires them.

## 1. Internal control mindset

GAO's Green Book frames internal control as a process supporting effective operations, reliable reporting, and compliance.

For DoobieLogic, the practical control questions are:
- Who can create, approve, receive, count, adjust, release, transfer, or close a record?
- What evidence proves the transaction occurred?
- Can one person initiate and conceal an error?
- Are physical assets protected?
- Are transactions recorded completely, accurately, and timely?
- Are exceptions reviewed by someone with appropriate authority?

Do not assume a workflow is controlled merely because it is digital.

## 2. Segregation of duties

Where feasible, separate incompatible responsibilities such as:
- ordering from receiving;
- receiving from invoice approval;
- custody from record adjustment;
- count execution from variance approval;
- production execution from final QA release;
- source-data mapping from approval of the mapped result.

Small facilities may need compensating controls when full separation is impractical. The agent should identify the risk, not invent an organizational structure.

## 3. Physical inventory vs system inventory

A physical count is evidence about reality at a point in time. A system quantity is a record of what the system believes should exist.

When they disagree, do not immediately overwrite one with the other.

Investigate:
- receiving not posted or posted incorrectly;
- production consumption or output not recorded;
- transfer in transit;
- sale/fulfillment timing;
- waste/destruction;
- samples/testing consumption;
- repack/transformation;
- unit conversion;
- duplicate transaction;
- wrong package/lot mapping;
- count error;
- unauthorized or unexplained adjustment.

## 4. Audit evidence quality

Evidence should be evaluated for relevance, reliability, and sufficiency.

Stronger evidence often includes:
- direct physical observation;
- source-system transaction record;
- approved manifest/transfer record;
- timestamped production record;
- signed/controlled document;
- independent corroboration;
- immutable/auditable event history.

A handwritten note, memory, or unsupported explanation may be useful context but is weaker evidence.

## 5. Data reliability

GAO's data reliability framework emphasizes accuracy, completeness, and applicability for the intended purpose.

Use these definitions operationally:
- **Completeness:** required records and fields are present.
- **Accuracy:** records reflect the underlying event or source.
- **Consistency:** definitions and entry rules produce comparable results.
- **Applicability:** the data are suitable for the decision being made.

A dataset can be accurate but still inappropriate for a question if the time period, facility, unit, or population is wrong.

## 6. Reconciliation

Reconciliation compares independently derived views of the same underlying reality.

Examples:
- physical count vs DoobieLogic inventory;
- DoobieLogic vs Metrc/BioTrack;
- receiving vs purchase order;
- transfer manifest vs received packages;
- BOM expected consumption vs actual production issue;
- source lot inputs vs repack outputs and waste;
- invoice vs received quantity/cost.

A good reconciliation records both the difference and the evidence that explains it.

## 7. Variance triage

Rank audit variances by business risk, not just absolute units.

Potential risk factors:
- regulated package/plant identity;
- high value;
- large percent variance;
- repeated variance history;
- controlled or restricted status;
- negative inventory;
- lot/COA mismatch;
- unresolved transfer;
- user-adjustment pattern;
- material impact on financial or compliance reporting.

A one-unit discrepancy in a high-risk serialized item can matter more than a larger low-value bulk rounding difference.

## 8. Recount strategy

A recount is most useful when it is independent enough to challenge the first count.

Good recount practice may include:
- clearly defining the item/package/lot scope;
- freezing or accounting for movement during the count window;
- using a second counter where appropriate;
- recounting high-risk locations/items first;
- verifying unit of measure and package identity;
- documenting the result without silently editing the original evidence.

## 9. Traceability identity levels

GS1 distinguishes class/product identity, batch/lot identity, and instance-level serialization.

Translate the concept into cannabis carefully:
- a product/SKU describes what the item is;
- a batch/lot/package identifies a production or inventory lineage group;
- a serialized plant/tag/package may identify one physical instance where the regulatory system uses that model.

Do not collapse these identity levels into one field.

## 10. Transformation genealogy

When inputs are transformed into outputs, preserve the relationship.

Examples:
- bulk flower into packaged eighths;
- multiple source packages into a production batch;
- biomass into extract;
- extract into infused products;
- bulk concentrate into smaller wholesale units;
- package consolidation/splitting where the governing system permits it.

GS1 traceability guidance teaches that repacked/reconfigured product should receive appropriate new output identity while retaining linkage to original inputs. FDA traceability education similarly treats transformation as a point where lot identity may change while key data remain linked.

The exact cannabis package/tag behavior must come from the applicable seed-to-sale and regulatory rules.

## 11. One step back / one step forward is not enough for internal operations

A useful internal genealogy should support:
- source input identification;
- transformation event;
- output identification;
- quantities consumed/produced;
- waste/loss;
- time and location;
- responsible workflow/user where appropriate;
- QA/COA linkage;
- downstream allocation or transfer.

This allows both backward and forward investigation.

## 12. Recall and containment reasoning

When quality or compliance risk is discovered, traceability should answer:
- What exact lots/packages/outputs are affected?
- Which source inputs contributed?
- Where are affected outputs now?
- What is still on hand, transferred, sold, destroyed, or in production?
- What unaffected inventory can remain available?

Do not broaden or narrow scope without evidence.

## 13. Master data governance

Master data includes controlled definitions used across transactions, such as:
- product/SKU;
- brand;
- cultivar/strain;
- product type/category;
- weight/size;
- unit of measure;
- package/lot identity;
- vendor/customer;
- room/location;
- machine/work center;
- BOM/material;
- regulatory item type.

Bad master data creates downstream errors that look like transaction problems.

## 14. Nomenclature normalization

A naming standard should preserve meaning while reducing accidental variation.

Separate attributes before generating a display name:
- brand;
- cultivar/strain;
- product form/type;
- size/weight;
- category/subcategory;
- flavor or formulation attribute where legitimate;
- package count where relevant.

Do not infer missing attributes from a product name unless marked as a proposed mapping requiring review.

## 15. Duplicate detection

Potential duplicates should be ranked, not automatically merged.

Evidence can include:
- normalized name similarity;
- same brand;
- same size/UOM;
- same product type;
- same regulatory item/reference;
- shared barcode/identifier;
- shared vendor catalog ID.

Near-identical names can still represent legally or commercially distinct products.

## 16. Unit-of-measure control

A major source of inventory error is mixing incompatible units.

Before arithmetic or reconciliation:
- identify stored unit;
- identify transaction unit;
- identify conversion source;
- verify mass/volume/count basis;
- preserve precision appropriate to the system;
- never create an undocumented conversion factor.

## 17. Repack control model

For repack/white-label work, reconcile:
- source package/lot;
- source usable quantity;
- package plan;
- packaging materials;
- actual packaged output;
- samples/testing;
- process loss/waste;
- remaining source bulk;
- output package identities;
- label/COA linkage;
- release status.

The equation should close within valid measurement/rounding behavior. Unexplained residual is an exception to investigate, not a value to hide.

## 18. Audit trails

An audit trail should preserve:
- original event;
- actor/system;
- timestamp;
- before/after state when relevant;
- reason code or explanation;
- related source document;
- approval when required.

Corrections should be traceable to what they corrected.

## 19. Anomaly detection

An anomaly is a signal, not proof of misconduct.

Useful patterns include:
- repeated adjustments by same user/item;
- adjustments immediately before/after counts;
- repeated negative inventory;
- unusual quantity precision;
- duplicate package IDs;
- transaction timestamps outside normal workflow;
- recurring receiving shortfalls;
- systematic differences between source systems.

Investigate with corroborating evidence before assigning cause.

## 20. Recommended answer pattern

For an audit/traceability/master-data problem:
1. State the exact object, lot/package, location, and time scope.
2. Show the conflicting evidence sources.
3. Quantify the variance in compatible units.
4. Rank plausible transaction/process causes.
5. Identify the next source record or recount that would resolve the issue.
6. Preserve genealogy and audit trail; never recommend silently overwriting evidence.
7. State compliance implications only from authoritative current sources.
8. Report confidence and unresolved gaps.