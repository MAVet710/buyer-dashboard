# DoobieLogic Controlled Agent Learning

DoobieLogic agents use controlled facility learning. This is not autonomous model-weight training and agents do not rewrite application code, SOPs, regulations, permissions, or operational records.

## What every agent can learn

Every registered `AgentProfile` uses the same `AgentLearningEngine` inside `AgentRuntime`.

The engine can learn from three bounded classes of evidence:

1. **Authorized historical operational data** — aggregate numeric associations and grouped outcome differences derived from the datasets the agent is already permitted to read.
2. **Explicitly approved human corrections** — a user may suggest a corrected answer, but it remains pending until Admin/DEV separately approves it for facility learning.
3. **Runtime quality signals** — telemetry and evaluation remain available for provider/routing quality analysis without storing raw prompts or raw operational datasets.

The current agent set includes Operations, Buyer, Purchasing, Inventory, Inventory Audit, Compliance, Nomenclature, Repack, Co-Man Production, Extraction Scientist, Commercial, Commercial Finance, Cultivation, and Data Hub. New agents inherit the learning contract automatically when they use `AgentRuntime`.

## Durable learning record

Migration `0041_agent_learning` creates `ai_agent_learnings`.

Each row is scoped by organization, facility, and agent and contains only an aggregate learning signal:

- learning key/type/source kind;
- human-readable aggregate summary;
- bounded aggregate evidence JSON;
- sample size;
- confidence;
- first/last observed timestamps;
- active state.

Raw source rows are not copied into the learning table. Tenant scope is never selected by a model.

## Historical pattern rules

The learning engine only considers already-sanitized business fields. Sensitive names/credentials/customer/patient/employee fields and identifier-like columns are excluded from pattern generation.

Numeric associations require at least eight usable observations and a meaningful correlation threshold. Group outcome comparisons require enough rows per group and a material difference before they are persisted.

Every generated pattern explicitly states that it is an association rather than proof of causation. The model is instructed to validate confounders and use current deterministic data before acting on a historical association.

Examples of useful learning include:

- Buyer: recurring relationships between inventory coverage, velocity, margin, and aging.
- Purchasing: vendor/delivery patterns, PO fill behavior, budget deployment outcomes, and replenishment signals.
- Inventory: recurring stockout/overstock/aging relationships.
- Audit: recurring variance patterns and recount-risk signals.
- Repack: historical yield/margin/package-allocation associations.
- Production: attainment, throughput, scrap, downtime, machine/capacity and material patterns.
- Extraction: cannabinoid recovery, stage loss, filtration, yield, terpene retention, downtime, turnaround, QA, COGS and margin associations.
- Commercial: fulfillment, allocation, shipment and partner/order outcome patterns.
- Commercial Finance: margin, A/R, invoice aging and working-capital patterns.
- Cultivation: phase/room/strain, harvest timing and handoff outcome patterns when the data exists.
- Data Hub: recurring mapping/completeness/freshness and data-quality patterns.
- Operations: cross-workspace aggregate relationships exposed through its authorized datasets.

## Compliance boundary

Compliance participates in controlled learning only for operational/workflow patterns and recurring evidence gaps.

Human corrected answers are intentionally **not injected into Compliance Agent reasoning** as learned facts. Regulations and legal conclusions must still come from retrieved government/regulatory evidence. Internal compliance/SOP questions may use approved level-2 facility evidence when applicable.

Learning can never create or override:

- a law or regulatory requirement;
- an approved SOP requirement;
- an equipment safety limit;
- an extraction machine setpoint;
- a METRC requirement;
- a permission or tenant boundary.

## Source precedence

Knowledge retrieval now uses source class and effective-date precedence in addition to lexical/vector relevance and authority level.

For a legal/regulatory question, the retrieval pool is filtered to authority level 1 **before** model context is constructed. A facility SOP therefore cannot enter the legal evidence pool and masquerade as law.

When multiple authoritative sources for a retrieved topic exist, citations expose a precedence status such as `preferred_authority`, `older_retrieved_authority`, or `secondary_authority`. Older material is preserved for provenance; the runtime does not silently delete it merely because a newer source exists.

## Feedback approval flow

The Workspace AI drawer provides two feedback paths:

- **Helpful** stores evaluation feedback only and does not change behavior.
- **Suggest correction** stores a sanitized corrected answer with `training_approved=false`.

Admin/DEV can review pending corrected answers from **Data & Settings -> AI & METRC Integrations -> Controlled Agent Learning** and explicitly approve a correction for that organization/facility.

Approval is tenant/facility scoped. An identifier from another organization/facility cannot be approved through the current context.

## Runtime precedence

The evidence order is intentionally conservative:

`trusted tenant scope -> authorization -> current datasets -> deterministic calculations -> authoritative retrieved knowledge -> approved facility learning -> model inference`

Learned history never outranks current deterministic results or authoritative knowledge.

## Transparency

Agent responses expose a bounded `learning` object with:

- whether controlled learning is enabled;
- active pattern count used for the agent;
- approved correction count;
- up to five learned pattern summaries with sample size/confidence.

The React drawer displays this as **Facility learning used** so users can see when historical patterns influenced reasoning.

## Extraction and Future4200

Future4200 remains authority level 6 field-practice knowledge. It may suggest what measurements or hypotheses to investigate, while facility learning determines whether those hypotheses are supported by the facility's own run history.

Exact temperatures, pressures, vacuum levels, solvent ratios, flow rates, media loads, dwell times, cycle times, or other machine setpoints still require approved SOP/equipment/manual or validated run evidence. A forum pattern or learned correlation cannot create an operating recipe.
