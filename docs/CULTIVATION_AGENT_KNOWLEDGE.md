# Cultivation Agent Knowledge Model

## Goal

The DoobieLogic Cultivation Agent should behave like a source-aware cultivation scientist and operations analyst, not a generic chatbot that guesses at cannabis horticulture.

Its knowledge model combines:

1. canonical facility data from DoobieLogic,
2. approved facility SOPs and cultivation recipes,
3. facility-scoped Knowledge Library sources,
4. an independently written horticultural reasoning framework,
5. model inference only when the higher-confidence layers do not answer the question.

## CHA-informed learning framework

The repository includes:

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
4. peer-reviewed research, government/extension horticulture, and validated manufacturer technical material;
5. professional horticultural education and field-practice references;
6. model inference.

Lower-authority horticultural references may inform operational reasoning, but they do not override a product label, regulation, or approved facility procedure.

## Seeding the built-in framework

The curated-source key is:

`cha_cultivation_learning_framework`

It is registered through the existing AI Knowledge catalog and seed flow. Seeding is facility-scoped by design. Admins should seed the source into each facility where the Cultivation Agent should retrieve it.

The framework is authority level 6 (`reference_framework`). It is useful for reasoning structure and educational coverage, not for making legal or chemical-use determinations.

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

For plant-health, pest/pathogen, nutrient, environmental, or root-zone questions, prefer:

- **Observed evidence** — what the facility actually measured or recorded.
- **Most likely causes** — ranked hypotheses with evidence for and against each.
- **What to check next** — the smallest useful set of measurements or observations.
- **Low-risk immediate controls** — reversible actions supported by facility procedure.
- **Source/SOP boundary** — anything requiring an authoritative product label, regulation, SOP, or specialist review.
- **Confidence and missing data** — what would materially change the recommendation.

The objective is not for the agent to sound certain. The objective is for it to make better cultivation decisions with traceable evidence.