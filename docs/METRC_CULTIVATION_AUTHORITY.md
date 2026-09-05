# Metrc Cultivation Authority

This document records the implementation boundary for canonical Metrc-backed cultivation in DoobieLogic.

## Identity

Cultivation reconciliation requires exact organization, facility, jurisdiction, environment, license, provider resource, and provider-object identity through the traceability link spine. Mutable room names, strain text, batch names, and display labels do not establish identity.

## Authority

For an exactly linked object, explicit Metrc regulatory state controls the supported regulated fields: plant phase, explicit strain identity, exact linked location, planted date, plant-batch strain/type/location, and harvest strain/location/current plant count/start timestamp.

DoobieLogic enrichment remains local, including notes, planning dates, room capacity, square footage, cycle targets, source/mother metadata, costs, labor, and harvest wet/dry/waste weights until those provider semantics receive a separately verified contract.

## Audit evidence

Every authoritative correction records a durable per-object audit event containing the exact Metrc resource/provider ID, environment, jurisdiction, license, and before/after field deltas. Plant phase, strain, and location corrections additionally retain lifecycle events. Replay of unchanged provider state is idempotent.

## Scale

Linked rooms, groups, plants, and harvests are loaded in bounded set-based queries before reconciliation. The reconciler does not perform a database lookup for every provider row.

## Location behavior

Only Metrc locations referenced by current plant batches, plants, or harvests participate in canonical cultivation reconciliation. A valid but unused provider location is not treated as an identity conflict merely because DoobieLogic has not materialized it as a cultivation room.

## Absence semantics

Absence from an active Metrc cultivation collection does not by itself mean harvested, destroyed, retired, or finished. Terminal lifecycle changes require explicit provider evidence or a separately reviewed workflow contract.

## Evaluation boundary

This architecture does not enable new Metrc writes and does not mark any Generic Evaluation requirement passed. Evaluation status requires actual Massachusetts sandbox execution and provider readback evidence.
