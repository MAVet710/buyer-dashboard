# DoobieLogic Professional Agent Education

## Objective

DoobieLogic specialist agents should combine deterministic operational analysis with profession-level education instead of relying on generic model memory.

This architecture gives every non-cultivation specialist a facility-scoped professional curriculum while preserving the platform's provider-neutral runtime, tenant isolation, read-only defaults, and authoritative compliance boundaries.

Cultivation is intentionally handled by its dedicated cultivation-education work so this PR remains independent.

## Academy map

| Agent | Primary academy coverage |
| --- | --- |
| Operations Agent | Operations and Manufacturing Academy |
| Buyer Agent | Buying, Purchasing, and Inventory Academy |
| Purchasing Agent | Buying, Purchasing, and Inventory Academy |
| Inventory Agent | Buying/Inventory + Traceability/Audit |
| Inventory Audit Agent | Traceability, Audit, and Master Data Academy |
| Compliance Agent | Compliance and Safety Academy; authoritative compliance sources still required |
| Nomenclature Agent | Traceability, Audit, and Master Data Academy |
| Repack Agent | Traceability/Audit + Operations/Manufacturing |
| Co-Man Production Agent | Operations/Manufacturing + Compliance/Safety concepts |
| Extraction Scientist Agent | Extraction Science/Quality + Compliance/Safety concepts |
| Commercial Agent | Commercial/Wholesale/Finance + Traceability |
| Wholesale Agent | Commercial/Wholesale/Finance + Traceability |
| Commercial Finance Agent | Commercial, Wholesale, and Finance Academy |
| Data Hub Agent | Data Governance and Reliability Academy |

Every mapped agent also receives the shared Professional Agent Evidence Framework.

The code mapping lives in:

`services/agent_education.py`

## Built-in knowledge sources

The repository includes:

- `knowledge_sources/curated/professional_agent_evidence_framework.md`
- `knowledge_sources/curated/operations_manufacturing_academy.md`
- `knowledge_sources/curated/buying_purchasing_inventory_academy.md`
- `knowledge_sources/curated/traceability_audit_masterdata_academy.md`
- `knowledge_sources/curated/compliance_safety_academy.md`
- `knowledge_sources/curated/extraction_science_quality_academy.md`
- `knowledge_sources/curated/commercial_wholesale_finance_academy.md`
- `knowledge_sources/curated/data_governance_academy.md`

They are registered through the existing curated Knowledge Library seed flow and are facility-scoped.

## Authority model

All of the new academy syntheses are authority level 4.

That is deliberate.

They may teach professional reasoning, terminology, diagnostic methods, quantitative methods, and transferable engineering/management concepts. They may **not** masquerade as law, regulator guidance, controlling product labels, or approved facility SOPs.

The evidence order is:

1. applicable law/regulation/regulator order/controlling product label;
2. approved facility SOP/policy/specification/contract/master data;
3. canonical DoobieLogic data and deterministic calculations;
4. government technical guidance, standards/research, and the professional academy syntheses;
5. lower-authority field practice;
6. model inference.

## Compliance behavior

The Compliance Agent remains `compliance_grounded_only`.

The Compliance and Safety Academy teaches the agent what evidence to gather and how to reason about compliance and safety domains, but it explicitly cannot satisfy the authoritative-evidence requirement for a compliant/noncompliant or legal conclusion.

Current jurisdiction-specific sources still have to come from the approved Knowledge Library, such as current Cannabis Control Commission regulations/orders/guidance, applicable pesticide labels, OSHA/EPA authority when relevant, or approved facility SOPs.

## Retrieval behavior

`services/ai/context.py` injects the agent's education mapping and retrieval-first rules into the specialist system prompt.

For professional education, troubleshooting, root-cause analysis, and why/how questions, agents are instructed to use `knowledge_search` when available and prefer their mapped academies to unsupported model memory.

Straightforward deterministic questions should still use the existing Python/SQL tools first where applicable. The education layer does not replace deterministic inventory, audit, production, extraction, commercial, or data-quality calculations.

## Source standards

The academies intentionally prioritize:

- NIST / NIST MEP;
- GAO internal-control and data-reliability frameworks;
- NIOSH cannabis worker-safety research;
- EPA Worker Protection Standard education;
- OSHA hazardous-energy requirements;
- NIST cannabis analytical measurement science;
- GS1 traceability concepts;
- FDA quality/traceability concepts used only as transferable quality-system education when they do not legally govern cannabis;
- IRS and FinCEN current cannabis-related financial guidance;
- peer-reviewed/open-access extraction science.

## Licensing posture

These files are independently written syntheses. They do not copy entire standards, courses, books, or protected web pages.

Government and appropriately licensed sources can be used within their applicable legal terms. Commercial standards and university/industry educational material must not be copied, scraped, mirrored, or embedded merely because it is viewable online.

MIT/OpenCourseWare and similar curricula may be useful for identifying what professionals are taught, but restrictive or noncommercial AI-use terms must be respected. DoobieLogic should prefer permissible government, peer-reviewed/open-license, primary technical, and independently written material for commercial retrieval.

## Applicability rule

Agents must preserve relevant source context instead of turning one example into a universal rule.

Depending on the domain, context includes:

- jurisdiction/effective date;
- cannabis operation/facility type;
- product/process/equipment type;
- unit of measure and metric definition;
- scale and throughput;
- supplier/customer terms;
- accounting/tax period;
- source-system version;
- worker/process hazard context.

If a source comes from another industry, the agent must identify it as a transferable concept unless the governing cannabis rule explicitly adopts it.

## Review cadence

Academies have individual review intervals in `services/ai/retrieval/curated_sources.py`.

Fast-changing areas such as compliance/safety and cannabis finance use shorter review cycles. Durable domains such as data reliability, traceability, inventory theory, and operations management may use longer cycles.

Reviewing an academy means validating both the educational content and whether its cited source URLs/authority context remain current.

## Future expansion

High-value next additions can include:

- jurisdiction-specific compliance packs for every legal cannabis state/territory;
- approved facility SOP packs by operation type;
- vendor/equipment manuals that the facility is licensed to ingest;
- more open-access extraction/process-engineering literature;
- state-specific worker/pesticide guidance;
- formal source-version retirement/supersession policies;
- evaluation suites that ask each agent professional scenario questions and score source use, uncertainty, and cross-agent handoffs.

The goal is not to make the model sound more knowledgeable. The goal is to make each agent reason like a better professional while remaining explicit about what it knows, what it measured, what source supports the claim, and what requires human authority.