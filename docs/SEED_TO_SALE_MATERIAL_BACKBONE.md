# Seed-to-Sale Material Backbone

## Governing rules

1. If an operator must re-enter authoritative data DoobieLogic already knows, treat it as a UX defect.
2. If a workflow creates physical output without decrementing actual physical inputs, treat it as a ledger defect.
3. If a finished cannabis lot cannot recursively trace to every durable cannabis source that contributed to it, treat it as a lineage defect.
4. Reservation is planning. Actual consumption is the physical ledger event.
5. Incomplete work may be saved, but it may not be represented as fully closed/released when mandatory material closeout is missing.
6. Inventory quantity remains authoritative in the append-only `coman_inventory_transactions` ledger. Material genealogy layers durable relationships over that ledger; it does not create a second inventory balance.
7. All writes remain organization/facility scoped. Regulatory/state-system mutation remains a separate governed workflow.

## Canonical transformation graph

The shared graph uses:

- `material_transformations`
- `material_transformation_inputs`
- `material_transformation_outputs`
- `material_transformation_losses`

Initial transformation types:

- `harvest_allocation`
- `production_run`

Package Studio remains a durable existing transformation ledger and is folded into the same genealogy query rather than duplicated. Extraction will write the same canonical graph in the next phase.

## Harvest to inventory

Harvest 360 output allocation creates canonical `InventoryLot` rows and append-only `harvest_output` inventory transactions. Each child lot retains the harvest and source-plant ancestry.

Allocation is measurement-basis aware (`wet` or `dry`) so fresh-frozen and dry-material branches can coexist without pretending wet and dry measurements are directly additive. A basis cannot be allocated beyond its measured harvest weight.

## Production actuals

Production Run 360 adds governed `consume_materials` mutation semantics:

- exact preview before commit
- stale preview protection through the existing Run 360 mutation fingerprint
- source lot/facility validation
- organization-wide commitment protection
- actual `production_consume` ledger decrement
- reservation reduction/retirement
- actual-vs-BOM variance retention
- canonical source-lot lineage
- finished output attachment to the same transformation

A BOM-based run cannot complete or QA-release finished material while required inputs have no recorded actual consumption.

## Genealogy

The material-lineage query traverses both directions across:

- harvest -> source plants -> harvest output lots
- production source lots -> production order -> output lots
- existing Package Studio source lots -> transformations -> child lots

The next phase will add extraction intermediate/final outputs, cross-license transfer edges, recall blast-radius queries and contextual Doobie Agent tools on top of this graph.
