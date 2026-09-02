# DoobieLogic Operations and Manufacturing Academy

## Audience

Primary agents: Operations Agent, Co-Man Production Agent, Repack Agent.
Secondary use: Inventory, Purchasing, Commercial, Extraction, Data Hub.

## Source posture

This is an independently written synthesis of durable operations-management, lean-manufacturing, quality, maintenance, and production-control principles. It draws on public U.S. government manufacturing guidance, especially the NIST Manufacturing Extension Partnership (MEP), plus general operations-science concepts.

NIST MEP references:
- Supply Chain Management: https://www.nist.gov/mep/supply-chain
- Lean and Process Improvement: https://www.nist.gov/mep/lean-and-process-improvement
- Total Productive Maintenance example: https://www.nist.gov/mep/successstories/2022/total-productive-maintenance-reduces-equipment-downtime-and-lost-capacity

FDA food CGMP and HACCP material may inform generic quality-system thinking, sanitation, hazard analysis, documented process control, and prerequisite-program concepts, but it must not be represented as controlling cannabis law unless a governing cannabis rule actually incorporates it.
- CGMP overview: https://www.fda.gov/food/guidance-regulation-food-and-dietary-supplements/current-good-manufacturing-practices-cgmps-food-and-dietary-supplements
- HACCP principles: https://www.fda.gov/food/hazard-analysis-critical-control-point-haccp/haccp-principles-application-guidelines

## 1. Process thinking

A commercial operation is a network of processes converting inputs into outputs. Analyze work as flow rather than isolated tasks.

For each process, identify:
- triggering demand;
- required materials;
- labor and skill requirements;
- machine/equipment requirements;
- quality gates;
- queue or waiting points;
- setup/changeover requirements;
- expected processing time;
- expected yield and scrap;
- downstream dependency;
- information needed to release the next step.

A local improvement that creates downstream congestion is not necessarily a system improvement.

## 2. Throughput, cycle time, WIP, and bottlenecks

Keep these concepts distinct:
- **Throughput:** completed good output per unit of time.
- **Cycle time:** elapsed time from defined start to defined finish.
- **Work in process (WIP):** work that entered the process but is not complete.
- **Capacity:** maximum sustainable output under defined assumptions.
- **Utilization:** actual use relative to available capacity.
- **Bottleneck/constraint:** resource or step limiting system output.

High utilization everywhere can increase queues and make the system less responsive. A constrained resource deserves different scheduling attention from a nonconstraint.

When a production queue is late, ask whether the cause is demand overload, material shortage, labor shortage, equipment availability, long setup, quality hold, rework, upstream delay, or unrealistic standard time.

## 3. Capacity analysis

Capacity should be computed from actual limiting resources, not guessed from calendar hours alone.

Consider:
- scheduled operating time;
- planned downtime;
- unplanned downtime;
- crew availability and qualification;
- machine availability;
- setup/changeover time;
- speed loss;
- quality loss/rework;
- material availability;
- sanitation or QA release time;
- batch-size constraints;
- routing requirements.

Do not promise job-level capacity if the application lacks routing, run-rate, changeover, or resource-eligibility data.

## 4. Overall equipment effectiveness concepts

OEE is commonly decomposed into availability, performance, and quality. It is a diagnostic model, not a universal target.

Use the decomposition to ask:
- Is output lost because equipment is not available?
- Is it running slower than the defined ideal/standard?
- Is it making unusable or reworked output?

Do not infer an OEE percentage unless the required denominators are present and consistently defined. Compare like with like across machines and periods.

NIST MEP's Total Productive Maintenance examples emphasize equipment reliability, preventive maintenance, downtime reduction, availability, quality, and lost capacity.

## 5. Total productive maintenance and equipment reliability

Treat maintenance as production capacity protection.

Useful signals include:
- downtime frequency and duration;
- failure mode;
- mean time between failures where data support it;
- mean time to repair where data support it;
- maintenance backlog;
- repeated alarms;
- consumable/tool replacement history;
- cleaning/sanitation-related stoppage;
- startup and changeover defects;
- operator-observed deterioration.

Do not recommend bypassing guards, safety interlocks, hazardous-energy controls, or manufacturer requirements to recover throughput.

## 6. Setup and changeover

NIST MEP identifies quick changeover/setup reduction as a method for reducing the time between the last good unit of one run and the first good unit of the next.

Analyze changeover into:
- shutdown and clearing;
- material removal;
- sanitation/cleaning;
- tooling/fixture changes;
- recipe/configuration changes;
- line clearance;
- startup checks;
- first-piece/first-batch quality approval.

Measure changeover loss separately from runtime speed loss.

## 7. Flow, batching, and queues

Batching can reduce setup frequency but increase WIP, waiting, inventory exposure, and response time. Smaller batches can improve responsiveness but may increase setup burden.

The correct batch size is a tradeoff between:
- setup/changeover cost;
- demand size;
- shelf-life/age risk;
- material availability;
- labor availability;
- equipment constraints;
- QA/testing constraints;
- downstream demand;
- traceability and recall scope.

## 8. Lean waste categories

Use lean concepts to find non-value-added work without treating headcount reduction as the objective.

Common waste patterns include:
- waiting;
- excess motion;
- unnecessary transportation;
- overprocessing;
- excess inventory/WIP;
- defects/rework;
- overproduction;
- unused employee knowledge.

Cannabis examples may include waiting on QA release, searching for materials, repeated manual transcription, unnecessary package moves, duplicate counts, late line clearance, avoidable reprints, or producing ahead of realistic demand.

## 9. Standard work and process control

A stable process needs a defined current method before improvement can be measured.

Useful controlled elements include:
- approved BOM or formula;
- approved routing;
- material identity and lot requirements;
- equipment assignment;
- process sequence;
- documented checkpoints;
- expected yield range where the facility has validated one;
- sampling/QA requirements;
- sanitation/line-clearance requirements;
- authorized deviations.

Do not invent standards the facility has not approved.

## 10. Yield, scrap, rework, and mass balance

Separate:
- planned yield;
- actual good output;
- recoverable WIP;
- normal process loss;
- abnormal loss;
- scrap/waste;
- rework;
- samples/testing consumption;
- inventory adjustment.

A production variance is not automatically theft, operator error, or process failure. Reconcile material movement and transformation first.

## 11. Quality at the source

Quality should be detected as close to the process step as practical. Rework discovered late consumes more capacity and may obscure the originating cause.

When defects rise, compare:
- machine;
- material lot;
- operator/crew;
- shift;
- product/BOM;
- setup/changeover;
- environmental condition;
- maintenance event;
- measurement system;
- recent process change.

## 12. Root-cause analysis

Use evidence rather than blame. A useful production root-cause investigation asks:
- What changed?
- When did the deviation begin?
- Is it product-specific, machine-specific, shift-specific, material-specific, or facility-wide?
- Did the measurement system change?
- What evidence would disprove the leading hypothesis?

Corrective action should address the cause, while containment protects current product and schedule.

## 13. Production scheduling

Prioritization should consider more than due date.

Possible factors:
- customer/production due date;
- material readiness;
- QA hold/release;
- machine eligibility;
- setup family;
- labor/skill availability;
- batch-size economics;
- downstream capacity;
- aging/shelf-life pressure;
- inventory shortage impact;
- contractual or compliance constraints.

The agent should explain why changing sequence improves the system rather than simply sorting by one field.

## 14. Labor and staffing

Separate headcount from effective capacity. Effective labor capacity depends on:
- attendance;
- qualification;
- training;
- assignment;
- line balance;
- indirect work;
- sanitation/changeover burden;
- breaks and schedule;
- machine constraints;
- rework burden.

Do not recommend unsafe staffing or skipping required controls to recover schedule.

## 15. Safety boundary

Production optimization stops where worker safety begins. Unexpected machine startup, hazardous energy, guarding, chemical hazards, compressed systems, solvents, heat, pressure, and electrical hazards require the applicable safety program and qualified personnel.

OSHA's control-of-hazardous-energy standard is the controlling source when it applies; this educational synthesis must never be used to create a lockout/tagout exception.

## 16. Cannabis-specific systems thinking

Commercial cannabis production adds:
- regulated source/package identity;
- lot/batch genealogy;
- testing/QA release;
- label and package requirements;
- waste tracking;
- license/facility boundaries;
- potency or formulation specifications;
- extraction/cultivation handoffs;
- controlled sellable inventory.

A production plan is not operationally ready if those required inputs or releases are missing.

## Recommended answer pattern

When analyzing production performance:
1. State the observed schedule/output deviation.
2. Quantify the loss by material, time, capacity, quality, or cost when possible.
3. Classify the likely constraint: material, labor, equipment, setup, quality, data, or downstream.
4. Rank causes with evidence.
5. Identify the next measurement or record needed.
6. Recommend low-risk containment and the next human decision.
7. Show downstream impact on Inventory, Purchasing, Wholesale, Finance, or Compliance.
8. State source/SOP/safety boundaries and confidence.