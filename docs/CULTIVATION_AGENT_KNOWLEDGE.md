# Cultivation Agent Knowledge Model

## Goal

The DoobieLogic Cultivation Agent should behave like a source-aware cultivation scientist and operations analyst, not a generic chatbot that guesses at cannabis horticulture.

Its knowledge model combines:

1. canonical facility data from DoobieLogic,
2. approved facility SOPs and cultivation recipes,
3. facility-scoped Knowledge Library sources,
4. independently written horticultural reasoning and commercial-cultivation curricula,
5. model inference only when the higher-confidence layers do not answer the question.

## Commercial Cannabis Cultivation Academy

The repository now includes:

`knowledge_sources/curated/commercial_cannabis_cultivation_academy.md`

This is an independently written commercial cultivation curriculum synthesized from peer-reviewed cannabis research and university/extension education. It is designed to teach the Cultivation Agent the biological and production reasoning behind commercial cultivation rather than only operational metrics.

The curriculum covers:

- cannabis botany, physiology, genetics, development, and secondary metabolism;
- mother-stock management, cloning, propagation, hardening, and tissue-culture concepts;
- controlled-environment physiology, HVAC/dehumidification, airflow, leaf/canopy microclimates, and CO2 context;
- lighting science including PPFD, DLI, canopy penetration, energy tradeoffs, and cultivar-specific photoperiod response;
- substrate/root-zone physics, irrigation, VWC, EC, dryback, water use, and crop-steering concepts;
- mineral nutrition, nutrient-form effects, deficiency diagnosis, tissue analysis, and source-water/root-zone context;
- IPM, scouting, quarantine, sanitation, beneficial organisms, major cannabis pathogens, HLVd, and integrated disease management;
- canopy architecture, plant density, pruning/defoliation, yield per area, and chemical uniformity;
- harvest maturity and timing;
- drying, curing, storage, moisture/water-activity concepts, microbial risk, and post-harvest process control;
- commercial systems thinking connecting cultivation to labor, automation, QA, inventory, extraction, production, wholesale, energy, water, and room capacity.

The academy includes explicit source links to Cornell, UConn, SIU, UMass, Virginia Tech, PubMed/PMC, Frontiers, MDPI, and current peer-reviewed cannabis research.

### Evidence-transfer discipline

The Cultivation Agent must not treat one study as a universal grow recipe. When applying research, preserve the study context where available:

- drug-type/high-THC vs cannabinoid hemp vs fiber/grain hemp;
- indoor vs greenhouse vs outdoor/tunnel;
- cultivar/genotype/chemotype;
- propagation source;
- substrate and irrigation system;
- plant density and architecture;
- lifecycle stage and photoperiod;
- light, CO2, temperature, humidity, and airflow conditions;
- measured endpoints.

If a paper studied a different chemotype, genotype, production system, substrate, or lifecycle stage than the facility's crop, the agent should state that limitation and lower confidence instead of silently generalizing the result.

The built-in academy source key is:

`commercial_cannabis_cultivation_academy`

It is registered as `research_synthesis` at authority level 4 and remains facility-scoped. It is more authoritative than field-practice/reference-framework material, but it does not override current law, product labels, approved facility SOPs, or facility-specific validated recipes.

## CHA-informed learning framework

The repository also includes:

`knowledge_sources/curated/cha_cultivation_learning_framework.md`

The framework uses the public topic organization visible in the Cannabis Horticultural Association database as an educational map for areas the Cultivation Agent should understand, including IPM, biological controls, pests and pathogens, integrated nutrient management, root-zone and soil biology, propagation, environmental management, crop steering, scouting, regenerative/ecological horticulture, and harvest readiness.

It does not contain copied CHA member lessons, application-rate tables, articles, photographs, or database records.

CHA's Terms of Use restrict scraping, data mining, copying, and storage of its copyrighted material in retrieval systems without written permission. For that reason, `cha.education` is intentionally **not** added to DoobieLogic's approved web-download allowlist.

## How the agent should reason

The Cultivation Agent is instructed to:

- distinguish facility facts from horticultural education and model inference;
- search the facility Knowledge Library before giving technical cultivation recommendations when the retrieval tool is available;
- diagnose from measurements and trends instead of jumping from one symptom to one answer;
- rank plausible causes and identify the next measurement that would separate them;
- preserve study context and distinguish cannabis-specific evidence from evidence transferred from hemp or general greenhouse horticulture;
- use an IPM hierarchy before escalating to chemical controls;
- avoid inventing pesticide legality, application rates, REI/PHI, tank mixes, nutrient recipes, pH/EC targets, irrigation recipes, VPD targets, light targets, or CO2 setpoints;
- preserve mother/source lineage during propagation and crop-health investigations;
- distinguish controller setpoints from actual sensor readings and observed plant response;
- distinguish a harvest timing forecast from biologically confirmed readiness;
- connect cultivation risks to drying/curing, Production, Extraction, Wholesale, Purchasing, and future inventory availability.

## Evidence precedence

Use the highest applicable evidence available:

1. law, regulator guidance, and controlling product labels;
2. approved facility SOPs, recipes, sanitation plans, and safety procedures;
3. canonical DoobieLogic facility measurements and operational records;
4. peer-reviewed cannabis-specific research;
5. university/extension cannabis and controlled-environment horticulture;
6. validated manufacturer technical material;
7. professional horticultural education and field-practice references;
8. model inference.

Lower-authority horticultural references may inform operational reasoning, but they do not override a product label, regulation, or approved facility procedure.

## Seeding the built-in frameworks

The cultivation curated-source keys are:

- `cha_cultivation_learning_framework`
- `commercial_cannabis_cultivation_academy`

Both are registered through the existing AI Knowledge catalog and seed flow. Seeding is facility-scoped by design. Admins should seed the sources into each facility where the Cultivation Agent should retrieve them.

The CHA framework is authority level 6 (`reference_framework`). It is useful for reasoning structure and educational coverage.

The commercial academy is authority level 4 (`research_synthesis`). It carries stronger scientific educational weight because it is built from peer-reviewed and university/extension sources, while still remaining below controlling regulations, labels, SOPs, and validated facility evidence.

## Adding licensed CHA material later

If DoobieLogic receives written authorization from CHA, or the facility supplies a lawfully licensed/exported CHA document set, ingest those exact authorized documents through the existing Knowledge Library rather than changing the Cultivation Agent prompt.

For each licensed source:

- retain its source title and provenance;
- retain the applicable URL when appropriate;
- record version/effective-date metadata where available;
- keep the material facility scoped unless licensing and tenancy rules explicitly permit broader use;
- upload only material covered by the permission/license;
- preserve citation metadata so the agent can identify which claims came from the authorized source;
- do not add `cha.education` to automated downloading merely because one document was licensed; only enable automated retrieval if the permission explicitly allows it.

This lets DoobieLogic become more knowledgeable over time without coupling the agent to one commercial education provider or weakening source governance.

## Expected answer shape for troubleshooting

For plant-health, pest/pathogen, nutrient, environmental, root-zone, lighting, irrigation, propagation, harvest, or post-harvest questions, prefer:

- **Observed evidence** — what the facility actually measured or recorded.
- **Research/SOP context** — which source applies and how closely its production conditions match the facility.
- **Most likely causes** — ranked hypotheses with evidence for and against each.
- **What to check next** — the smallest useful set of measurements or observations.
- **Low-risk immediate controls** — reversible actions supported by facility procedure.
- **Commercial consequence** — likely effect on yield, timing, labor, QA, downstream supply, or cost.
- **Source/SOP boundary** — anything requiring an authoritative product label, regulation, SOP, or specialist review.
- **Confidence and missing data** — what would materially change the recommendation.

The objective is not for the agent to sound certain. The objective is for it to make better cultivation decisions with traceable evidence and explicit limits.