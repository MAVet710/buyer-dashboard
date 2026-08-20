"""Method-specific extraction workflow templates.

Templates define operational stages and release gates only. They intentionally do
not hard-code machine setpoints, solvent ratios, pressures, temperatures, or
other equipment-specific process instructions; those belong in approved facility
SOPs and manufacturer documentation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractionStageDefinition:
    key: str
    label: str
    release_gate: bool = False
    qa_gate: bool = False


@dataclass(frozen=True)
class ExtractionWorkflow:
    key: str
    label: str
    method: str
    input_families: tuple[str, ...]
    output_families: tuple[str, ...]
    stages: tuple[ExtractionStageDefinition, ...]

    @property
    def first_stage(self) -> str:
        return self.stages[0].key

    def has_stage(self, key: str) -> bool:
        return any(stage.key == key for stage in self.stages)

    def stage_label(self, key: str) -> str:
        return next((stage.label for stage in self.stages if stage.key == key), key)

    def next_stage(self, key: str) -> str | None:
        keys = [stage.key for stage in self.stages]
        if key not in keys:
            return self.first_stage
        index = keys.index(key)
        return keys[index + 1] if index + 1 < len(keys) else None


COMMON_RELEASE = (
    ExtractionStageDefinition("qa", "QA / COA", qa_gate=True),
    ExtractionStageDefinition("release", "Release", release_gate=True),
)


WORKFLOWS: tuple[ExtractionWorkflow, ...] = (
    ExtractionWorkflow(
        key="bho_live_resin",
        label="BHO · Live Resin",
        method="BHO",
        input_families=("fresh_frozen",),
        output_families=("live_resin", "sauce", "badder", "bulk_concentrate"),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("extraction", "Extraction"),
            ExtractionStageDefinition("recovery", "Solvent Recovery"),
            ExtractionStageDefinition("post_process", "Post-Processing"),
            ExtractionStageDefinition("formulation", "Formulation"),
            ExtractionStageDefinition("packaging", "Filling / Packaging"),
            *COMMON_RELEASE,
        ),
    ),
    ExtractionWorkflow(
        key="bho_cured",
        label="BHO · Cured Material",
        method="BHO",
        input_families=("cured_flower", "trim", "biomass"),
        output_families=("badder", "shatter", "crude", "bulk_concentrate"),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("extraction", "Extraction"),
            ExtractionStageDefinition("recovery", "Solvent Recovery"),
            ExtractionStageDefinition("post_process", "Post-Processing"),
            ExtractionStageDefinition("packaging", "Filling / Packaging"),
            *COMMON_RELEASE,
        ),
    ),
    ExtractionWorkflow(
        key="ethanol_crude",
        label="Ethanol · Crude",
        method="Ethanol",
        input_families=("biomass", "trim", "cured_flower"),
        output_families=("crude",),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("extraction", "Extraction"),
            ExtractionStageDefinition("filtration", "Filtration / Winterization"),
            ExtractionStageDefinition("recovery", "Solvent Recovery"),
            ExtractionStageDefinition("post_process", "Post-Processing"),
            *COMMON_RELEASE,
        ),
    ),
    ExtractionWorkflow(
        key="crude_distillate",
        label="Crude · Distillate",
        method="Distillation",
        input_families=("crude",),
        output_families=("distillate",),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("preparation", "Preparation"),
            ExtractionStageDefinition("distillation", "Distillation"),
            ExtractionStageDefinition("post_process", "Post-Processing"),
            ExtractionStageDefinition("packaging", "Bulk Packaging"),
            *COMMON_RELEASE,
        ),
    ),
    ExtractionWorkflow(
        key="ice_water_hash",
        label="Solventless · Ice Water Hash",
        method="Solventless",
        input_families=("fresh_frozen", "cured_flower"),
        output_families=("hash", "full_melt"),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("wash", "Wash"),
            ExtractionStageDefinition("collection", "Collection / Separation"),
            ExtractionStageDefinition("drying", "Drying"),
            ExtractionStageDefinition("grading", "Grading"),
            ExtractionStageDefinition("packaging", "Packaging"),
            *COMMON_RELEASE,
        ),
    ),
    ExtractionWorkflow(
        key="hash_rosin",
        label="Solventless · Hash Rosin",
        method="Rosin",
        input_families=("hash",),
        output_families=("rosin", "rosin_jam", "fresh_press"),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("press", "Press"),
            ExtractionStageDefinition("collection", "Collection"),
            ExtractionStageDefinition("post_process", "Post-Processing / Cure"),
            ExtractionStageDefinition("packaging", "Packaging"),
            *COMMON_RELEASE,
        ),
    ),
    ExtractionWorkflow(
        key="rosin_vape",
        label="Rosin · Vape Formulation",
        method="Formulation",
        input_families=("rosin",),
        output_families=("vape", "bulk_oil"),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("formulation", "Formulation"),
            ExtractionStageDefinition("filling", "Filling"),
            ExtractionStageDefinition("packaging", "Packaging"),
            *COMMON_RELEASE,
        ),
    ),
    ExtractionWorkflow(
        key="co2_extract",
        label="CO2 · Extract",
        method="CO2",
        input_families=("biomass", "trim", "cured_flower"),
        output_families=("co2_oil", "bulk_oil"),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("extraction", "Extraction"),
            ExtractionStageDefinition("separation", "Separation"),
            ExtractionStageDefinition("post_process", "Post-Processing"),
            ExtractionStageDefinition("packaging", "Bulk Packaging"),
            *COMMON_RELEASE,
        ),
    ),
)


_WORKFLOW_BY_KEY = {workflow.key: workflow for workflow in WORKFLOWS}


def list_extraction_workflows() -> tuple[ExtractionWorkflow, ...]:
    return WORKFLOWS


def get_extraction_workflow(key: str) -> ExtractionWorkflow:
    normalized = str(key or "").strip().casefold()
    workflow = _WORKFLOW_BY_KEY.get(normalized)
    if workflow is None:
        raise ValueError(f"Unknown extraction workflow: {key}")
    return workflow


def default_workflow_for_method(method: str) -> ExtractionWorkflow:
    normalized = str(method or "").strip().casefold()
    for workflow in WORKFLOWS:
        if workflow.method.casefold() == normalized:
            return workflow
    raise ValueError(f"No extraction workflow is configured for method: {method}")
