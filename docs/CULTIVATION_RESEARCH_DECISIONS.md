# Cultivation intelligence research decisions

Reviewed: 2026-09-26. This document records product/engineering decisions, not cultivation prescriptions or a release claim.

## Evidence hierarchy

Facility-approved SOPs and recipes define intended conditions. Observations record actual conditions. Canonical plant/harvest/material/quality/cost records define operational outcomes. Research supplies context, not universal target ranges. Vendor marketing verifies advertised capabilities only; an implementable integration also needs reviewed endpoint, authentication, pagination, unit and entitlement contracts.

## Commercial workflow implications

1. Keep genotype, stage, room, light exposure, elapsed coverage and final measured outputs separate. A controlled indoor cannabis experiment found light-related yield responses did not imply the same response in cannabinoid concentration. Do not substitute canopy sensors or physiological proxies for measured saleable output, or turn one experiment into a facility recipe. Source: Rodriguez-Morrison, Llewellyn and Zheng (2021), https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2021.646020/full
2. Attribute nursery observations to the correct production objective. A greenhouse study on one named cultivar in the vegetative stage measured cutting-production and water-use responses. Its population is not all flowering cultivars or indoor facilities. Preserve mother/genetics/nursery cohort, stage and facility context before any cross-cycle comparison. Source: https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2024.1371702/full
3. Keep cultivation and post-harvest handling connected. A multi-year commercial greenhouse study examined microbial results alongside genotype, environment and handling. Product implication: preserve harvest identity, operation time, post-harvest stage and actual lab results so quality evidence is not reduced to a room temperature chart. It does not justify an automated treatment or a universal microbial threshold. Source: Punja et al. (2023), https://www.frontiersin.org/journals/microbiology/articles/10.3389/fmicb.2023.1192035/full
4. Scouting should record where, when, what was observed and the follow-up. University of Connecticut greenhouse guidance explicitly notes variability by location, cultivar and time. Use the commercial scouting workflow pattern, not crop-specific treatment recommendations; that guidance is not itself a cannabis pesticide label. Source: https://ipm.cahnr.uconn.edu/scouting-for-key-insect-and-mite-pests-on-key-plants-in-the-greenhouse/
5. Economics must follow attributable inputs and measured outputs. Link canonical cultivation costs, labor entries and harvest allocations; do not duplicate financial ledgers or call incomplete allocations true COGS. A numerator without an allocation basis, or a yield without known plant/time/area denominators, stays explicitly incomplete. This is an engineering integrity requirement, not a forecast of crop profitability.

## Analysis boundaries

- Comparisons are descriptive associations, not causal conclusions. Show sample counts, missing coverage, cultivar/stage, sensor placement and recipe version.
- Distinguish sample mean from elapsed-time-weighted mean. Intervals end at the next reading, invalid evidence, approved stage/mapping boundary, or configured maximum hold time, whichever occurs first.
- Missing or stale collection is a connection/data-quality problem, not proof that the room is healthy or unhealthy.
- Separate discrete irrigation totals from cumulative meters, rates and durations. Never silently sum overlapping independent sensors.
- Do not infer plant-level exposure from its current room. Use verified occupancy history; unavailable history stays unknown.
- Do not infer testing, grade, dryback, revenue or cost allocation from unrelated records or example acceptance numbers.
- No numerical agronomic targets, pesticide recommendations, automatic Work creation or equipment control are introduced by these research decisions.
