# Zero-Training Operator Acceptance

## Mission
A new operator with no DoobieLogic-specific training must be able to take one Blue Dream lineage from cultivation to a received wholesale transfer, then reconstruct that lineage through Recall 360 and Doobie Agent.

Canonical lifecycle:

1. Create Blue Dream plant/plant batch.
2. Advance cultivation stage.
3. Harvest and create harvested material.
4. Consume source material in a production/extraction run.
5. Record extraction output.
6. Record QA/COA and release the output.
7. Package finished goods.
8. Create and approve a wholesale order.
9. Create outbound transfer/manifest.
10. Receive at destination license/facility.
11. Reconstruct genealogy in Recall 360.
12. Ask Doobie Agent to trace the finished package to its source plant/harvest and production run.

## Pass criteria

- All 12 lifecycle milestones are reachable through operator surfaces.
- No browser crash.
- No unhandled API 5xx.
- No dead-end operator state.
- State survives workspace/facility transitions.
- Finished package genealogy reaches source cultivation material.
- Recall 360 and Doobie Agent agree on source lineage.

## Friction telemetry

Record at minimum:

- Clicks
- Decisions/selections
- Manual text/number inputs
- Workspace/facility context switches
- Backtracking
- Dead ends
- API 4xx/5xx responses
- Lifecycle milestone completion

The usability score is a secondary signal. Raw friction counts and the exact stage where friction occurs are the primary evidence.

## Interpretation

A technically green run is not automatically a usability pass. An operator can complete the lifecycle while still encountering excessive navigation, repeated data entry, ambiguous terminology, or recoverable errors. Those should become targeted simplification work even when the acceptance journey reaches the final milestone.
