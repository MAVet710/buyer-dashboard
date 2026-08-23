"""Method-specific extraction workflow templates and process semantics.

Templates define operational stages, stage-level measurements, traceability fields,
and release gates. They intentionally do not hard-code machine setpoints, solvent
ratios, pressures, temperatures, or other equipment-specific process instructions;
those belong in approved facility SOPs and manufacturer documentation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


MAX_TERPENE_PERCENTAGE = 20.0
TERPENE_HANDLING_MODES = (
    "Native / No Add-Back",
    "Reintroduced Cannabis Terpenes",
    "Botanically Derived Terpenes",
    "Terp Fraction Recombined",
    "Custom Blend",
)

INTERMEDIATE_PRODUCT_TYPES = (
    "Crude Oil",
    "Winterized Oil",
    "Filtered Oil",
    "Decarbed Oil",
    "Distillate",
    "Live Resin Fraction",
    "Bubble Hash",
    "Dry Sift",
    "Rosin",
    "CO2 Oil",
    "Bulk Oil",
)

FINAL_PRODUCT_TYPES = (
    "Live Resin",
    "Badder",
    "Budder",
    "Batter",
    "Shatter",
    "Crumble",
    "Sugar",
    "Sauce",
    "Terp Sauce",
    "Diamonds",
    "Diamonds in Sauce",
    "HTE",
    "HTFSE",
    "Distillate",
    "CO2 Oil",
    "RSO",
    "Bulk Oil",
    "Vape Oil",
    "Vape Cart Fill",
    "Disposable Fill",
    "Hash Rosin",
    "Live Rosin",
    "Bubble Hash",
    "Full Melt",
    "Dry Sift",
    "Pressed Hash",
    "Temple Ball",
    "Infused Pre-Roll Input",
)


@dataclass(frozen=True)
class ExtractionStageDefinition:
    key: str
    label: str
    release_gate: bool = False
    qa_gate: bool = False
    optional: bool = False
    output_fields: tuple[str, ...] = ()


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
        normalized = str(key or "").strip().casefold()
        return any(stage.key.casefold() == normalized for stage in self.stages)

    def stage_label(self, key: str) -> str:
        normalized = str(key or "").strip().casefold()
        return next((stage.label for stage in self.stages if stage.key.casefold() == normalized), key)

    def stage(self, key: str) -> ExtractionStageDefinition | None:
        normalized = str(key or "").strip().casefold()
        return next((stage for stage in self.stages if stage.key.casefold() == normalized), None)

    def next_stage(self, key: str) -> str | None:
        normalized = str(key or "").strip().casefold()
        keys = [stage.key for stage in self.stages]
        normalized_keys = [value.casefold() for value in keys]
        if normalized not in normalized_keys:
            return self.first_stage
        index = normalized_keys.index(normalized)
        return keys[index + 1] if index + 1 < len(keys) else None


COMMON_RELEASE = (
    ExtractionStageDefinition("qa", "QA / COA", qa_gate=True),
    ExtractionStageDefinition("release", "Release", release_gate=True),
)


# STEP 1: centralized family-level stage map. The durable WORKFLOWS below keep
# the existing workflow keys so historical runs continue to resolve correctly.
EXTRACTION_WORKFLOW_TEMPLATES: dict[str, tuple[str, ...]] = {
    "Hydrocarbon": (
        "Intake",
        "Extraction",
        "Solvent Recovery / Purge",
        "Dewax / Post-Process",
        "Separation / Crystallization",
        "Formulation",
        "Filling / Packaging",
        "Final Output",
    ),
    "Ethanol": (
        "Intake",
        "Extraction / Wash",
        "Solvent Recovery",
        "Winterization",
        "Filtration",
        "Decarboxylation",
        "Distillation",
        "Formulation",
        "Filling / Packaging",
        "Final Output",
    ),
    "CO2": (
        "Intake",
        "Extraction",
        "Separation",
        "Refinement",
        "Winterization",
        "Decarboxylation",
        "Distillation",
        "Formulation",
        "Filling / Packaging",
        "Final Output",
    ),
    "Ice Water Hash": (
        "Intake",
        "Wash / Agitation",
        "Bag Separation",
        "Drying",
        "Grading",
        "Rosin Press",
        "Final Output",
    ),
    "Dry Sift": (
        "Intake",
        "Screening / Sifting",
        "Refinement",
        "Pressed Hash",
        "Rosin Press",
        "Final Output",
    ),
    "Rosin": (
        "Intake",
        "Preparation / Bagging",
        "Press",
        "Collection",
        "Curing / Jar Tech",
        "Formulation",
        "Filling / Packaging",
        "Final Output",
    ),
}


WORKFLOWS: tuple[ExtractionWorkflow, ...] = (
    ExtractionWorkflow(
        key="bho_live_resin",
        label="BHO · Live Resin",
        method="BHO",
        input_families=("fresh_frozen",),
        output_families=("live_resin", "sauce", "badder", "bulk_concentrate"),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("extraction", "Extraction", output_fields=("extraction_output_g",)),
            ExtractionStageDefinition("recovery", "Solvent Recovery / Purge", output_fields=("purge_output_g",)),
            ExtractionStageDefinition("post_process", "Dewax / Post-Process", output_fields=("purge_output_g",)),
            ExtractionStageDefinition(
                "separation_crystallization",
                "Separation / Crystallization",
                optional=True,
                output_fields=("crystallization_output_g", "sauce_fraction_g", "diamond_fraction_g"),
            ),
            ExtractionStageDefinition("formulation", "Formulation", optional=True),
            ExtractionStageDefinition("packaging", "Filling / Packaging"),
            ExtractionStageDefinition("final_output", "Final Output"),
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
            ExtractionStageDefinition("extraction", "Extraction", output_fields=("extraction_output_g",)),
            ExtractionStageDefinition("recovery", "Solvent Recovery / Purge", output_fields=("purge_output_g",)),
            ExtractionStageDefinition("post_process", "Dewax / Post-Process", output_fields=("purge_output_g",)),
            ExtractionStageDefinition(
                "separation_crystallization",
                "Separation / Crystallization",
                optional=True,
                output_fields=("crystallization_output_g", "sauce_fraction_g", "diamond_fraction_g"),
            ),
            ExtractionStageDefinition("formulation", "Formulation", optional=True),
            ExtractionStageDefinition("packaging", "Filling / Packaging"),
            ExtractionStageDefinition("final_output", "Final Output"),
            *COMMON_RELEASE,
        ),
    ),
    ExtractionWorkflow(
        key="ethanol_crude",
        label="Ethanol · Extraction / Refinement",
        method="Ethanol",
        input_families=("biomass", "trim", "cured_flower"),
        output_families=("crude", "distillate", "rso", "bulk_oil", "vape"),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("extraction", "Extraction / Wash", output_fields=("crude_output_g",)),
            ExtractionStageDefinition("recovery", "Solvent Recovery", output_fields=("crude_output_g",)),
            ExtractionStageDefinition("winterization", "Winterization", optional=True, output_fields=("winterized_output_g",)),
            ExtractionStageDefinition("filtration", "Filtration", optional=True, output_fields=("filtered_output_g",)),
            ExtractionStageDefinition("decarboxylation", "Decarboxylation", optional=True, output_fields=("decarbed_output_g",)),
            ExtractionStageDefinition("distillation", "Distillation", optional=True, output_fields=("distillate_output_g",)),
            ExtractionStageDefinition("post_process", "Post-Processing", optional=True),
            ExtractionStageDefinition("formulation", "Formulation", optional=True),
            ExtractionStageDefinition("packaging", "Filling / Packaging"),
            ExtractionStageDefinition("final_output", "Final Output"),
            *COMMON_RELEASE,
        ),
    ),
    ExtractionWorkflow(
        key="crude_distillate",
        label="Crude · Distillate",
        method="Distillation",
        input_families=("crude",),
        output_families=("distillate", "bulk_oil", "vape"),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("preparation", "Preparation"),
            ExtractionStageDefinition("distillation", "Distillation", output_fields=("distillate_output_g",)),
            ExtractionStageDefinition("post_process", "Post-Processing", optional=True),
            ExtractionStageDefinition("formulation", "Formulation", optional=True),
            ExtractionStageDefinition("packaging", "Bulk / Filling / Packaging"),
            ExtractionStageDefinition("final_output", "Final Output"),
            *COMMON_RELEASE,
        ),
    ),
    ExtractionWorkflow(
        key="ice_water_hash",
        label="Solventless · Ice Water Hash",
        method="Solventless",
        input_families=("fresh_frozen", "cured_flower"),
        output_families=("hash", "full_melt", "rosin"),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("wash", "Wash / Agitation", output_fields=("wash_output_g",)),
            ExtractionStageDefinition("collection", "Bag Separation", output_fields=("wash_output_g",)),
            ExtractionStageDefinition("drying", "Drying", output_fields=("dried_hash_output_g",)),
            ExtractionStageDefinition("grading", "Grading", output_fields=("dried_hash_output_g",)),
            ExtractionStageDefinition("rosin_press", "Rosin Press", optional=True, output_fields=("rosin_output_g",)),
            ExtractionStageDefinition("packaging", "Packaging"),
            ExtractionStageDefinition("final_output", "Final Output"),
            *COMMON_RELEASE,
        ),
    ),
    ExtractionWorkflow(
        key="dry_sift",
        label="Solventless · Dry Sift",
        method="Dry Sift",
        input_families=("cured_flower", "trim", "kief"),
        output_families=("dry_sift", "pressed_hash", "rosin"),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("sifting", "Screening / Sifting", output_fields=("sift_output_g",)),
            ExtractionStageDefinition("refinement", "Refinement", output_fields=("sift_output_g",)),
            ExtractionStageDefinition("pressed_hash", "Pressed Hash", optional=True, output_fields=("sift_output_g",)),
            ExtractionStageDefinition("rosin_press", "Rosin Press", optional=True, output_fields=("rosin_output_g",)),
            ExtractionStageDefinition("packaging", "Packaging"),
            ExtractionStageDefinition("final_output", "Final Output"),
            *COMMON_RELEASE,
        ),
    ),
    ExtractionWorkflow(
        key="hash_rosin",
        label="Solventless · Hash Rosin",
        method="Rosin",
        input_families=("hash", "flower"),
        output_families=("rosin", "rosin_jam", "fresh_press", "vape"),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("preparation", "Preparation / Bagging", optional=True),
            ExtractionStageDefinition("press", "Press", output_fields=("rosin_output_g",)),
            ExtractionStageDefinition("collection", "Collection", output_fields=("rosin_output_g",)),
            ExtractionStageDefinition("post_process", "Curing / Jar Tech", optional=True, output_fields=("rosin_output_g",)),
            ExtractionStageDefinition("formulation", "Formulation", optional=True),
            ExtractionStageDefinition("packaging", "Filling / Packaging"),
            ExtractionStageDefinition("final_output", "Final Output"),
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
            ExtractionStageDefinition("final_output", "Final Output"),
            *COMMON_RELEASE,
        ),
    ),
    ExtractionWorkflow(
        key="co2_extract",
        label="CO2 · Extraction / Refinement",
        method="CO2",
        input_families=("biomass", "trim", "cured_flower"),
        output_families=("co2_oil", "bulk_oil", "distillate", "vape"),
        stages=(
            ExtractionStageDefinition("intake", "Intake / Staging"),
            ExtractionStageDefinition("extraction", "Extraction", output_fields=("crude_output_g",)),
            ExtractionStageDefinition("separation", "Separation", output_fields=("crude_output_g",)),
            ExtractionStageDefinition("post_process", "Refinement", output_fields=("filtered_output_g",)),
            ExtractionStageDefinition("winterization", "Winterization", optional=True, output_fields=("winterized_output_g",)),
            ExtractionStageDefinition("decarboxylation", "Decarboxylation", optional=True, output_fields=("decarbed_output_g",)),
            ExtractionStageDefinition("distillation", "Distillation", optional=True, output_fields=("distillate_output_g",)),
            ExtractionStageDefinition("formulation", "Formulation", optional=True),
            ExtractionStageDefinition("packaging", "Filling / Packaging"),
            ExtractionStageDefinition("final_output", "Final Output"),
            *COMMON_RELEASE,
        ),
    ),
)


_WORKFLOW_BY_KEY = {workflow.key: workflow for workflow in WORKFLOWS}

_METHOD_FAMILY_ALIASES = {
    "bho": "hydrocarbon",
    "butane": "hydrocarbon",
    "pho": "hydrocarbon",
    "propane": "hydrocarbon",
    "hydrocarbon": "hydrocarbon",
    "hydrocarbon blend": "hydrocarbon",
    "ethanol": "ethanol",
    "co2": "co2",
    "co₂": "co2",
    "solventless": "ice_water_hash",
    "ice water hash": "ice_water_hash",
    "bubble hash": "ice_water_hash",
    "dry sift": "dry_sift",
    "kief": "dry_sift",
    "rosin": "rosin",
    "distillation": "ethanol",
    "formulation": "rosin",
}

_METHOD_OUTPUT_FIELDS = {
    "hydrocarbon": (
        "extraction_output_g",
        "purge_output_g",
        "crystallization_output_g",
        "sauce_fraction_g",
        "diamond_fraction_g",
    ),
    "ethanol": (
        "crude_output_g",
        "winterized_output_g",
        "filtered_output_g",
        "decarbed_output_g",
        "distillate_output_g",
    ),
    "co2": (
        "crude_output_g",
        "winterized_output_g",
        "filtered_output_g",
        "decarbed_output_g",
        "distillate_output_g",
    ),
    "ice_water_hash": ("wash_output_g", "dried_hash_output_g", "rosin_output_g"),
    "dry_sift": ("sift_output_g", "rosin_output_g"),
    "rosin": ("rosin_output_g",),
}


def list_extraction_workflows() -> tuple[ExtractionWorkflow, ...]:
    return WORKFLOWS


def get_extraction_workflow(key: str) -> ExtractionWorkflow:
    normalized = str(key or "").strip().casefold()
    workflow = _WORKFLOW_BY_KEY.get(normalized)
    if workflow is None:
        raise ValueError(f"Unknown extraction workflow: {key}")
    return workflow


def method_family(method: str) -> str:
    normalized = str(method or "").strip().casefold()
    return _METHOD_FAMILY_ALIASES.get(normalized, normalized.replace(" ", "_"))


def workflows_for_method(method: str) -> tuple[ExtractionWorkflow, ...]:
    family = method_family(method)
    if family == "hydrocarbon":
        return tuple(workflow for workflow in WORKFLOWS if workflow.method == "BHO")
    if family == "ethanol":
        return tuple(workflow for workflow in WORKFLOWS if workflow.method in {"Ethanol", "Distillation"})
    if family == "co2":
        return tuple(workflow for workflow in WORKFLOWS if workflow.method == "CO2")
    if family == "ice_water_hash":
        return tuple(workflow for workflow in WORKFLOWS if workflow.key == "ice_water_hash")
    if family == "dry_sift":
        return tuple(workflow for workflow in WORKFLOWS if workflow.key == "dry_sift")
    if family == "rosin":
        return tuple(workflow for workflow in WORKFLOWS if workflow.method in {"Rosin", "Formulation"})
    return tuple(workflow for workflow in WORKFLOWS if workflow.method.casefold() == str(method or "").strip().casefold())


def default_workflow_for_method(method: str) -> ExtractionWorkflow:
    candidates = workflows_for_method(method)
    if candidates:
        return candidates[0]
    raise ValueError(f"No extraction workflow is configured for method: {method}")


def method_aware_stage_fields(method: str) -> tuple[str, ...]:
    """Return optional stage-output fields relevant to the selected extraction family."""
    return _METHOD_OUTPUT_FIELDS.get(method_family(method), ())


def stage_output_fields(workflow_key: str, stage_key: str) -> tuple[str, ...]:
    workflow = get_extraction_workflow(workflow_key)
    stage = workflow.stage(stage_key)
    return stage.output_fields if stage else ()


def validate_terpene_percentage(value: float | int | None) -> float:
    percentage = float(value or 0.0)
    if percentage < 0:
        raise ValueError("Terpene percentage cannot be negative.")
    if percentage > MAX_TERPENE_PERCENTAGE:
        raise ValueError(
            f"Terpene percentage above {MAX_TERPENE_PERCENTAGE:.0f}% is outside the supported formulation range."
        )
    return percentage


def calculate_terpene_weight_g(
    formulation_base_g: float | int | None,
    terpene_percentage: float | int | None = None,
    manual_terpene_weight_g: float | int | None = None,
) -> float:
    """Calculate optional terpene add-back mass, allowing an explicit manual override."""
    base = max(0.0, float(formulation_base_g or 0.0))
    if manual_terpene_weight_g is not None:
        manual = float(manual_terpene_weight_g)
        if manual < 0:
            raise ValueError("Terpene weight cannot be negative.")
        return manual
    percentage = validate_terpene_percentage(terpene_percentage)
    return base * (percentage / 100.0)


def _positive(value: object) -> float:
    try:
        numeric = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return numeric if numeric > 0 else 0.0


def _stage_output_value(stage: ExtractionStageDefinition, values: Mapping[str, object]) -> float:
    direct = _positive(values.get(stage.key))
    if direct:
        return direct
    if not stage.output_fields:
        return 0.0
    parts = {field: _positive(values.get(field)) for field in stage.output_fields}
    if parts.get("sauce_fraction_g") or parts.get("diamond_fraction_g"):
        fractions = parts.get("sauce_fraction_g", 0.0) + parts.get("diamond_fraction_g", 0.0)
        if fractions > 0:
            return fractions
    for field in reversed(stage.output_fields):
        if parts.get(field, 0.0) > 0:
            return parts[field]
    return 0.0


def calculate_final_output_g(
    workflow_key: str,
    stage_outputs: Mapping[str, object] | None = None,
    *,
    formulation_used: bool = False,
    formulation_base_g: float | int | None = None,
    terpene_weight_g: float | int | None = None,
    explicit_finished_output_g: float | int | None = None,
) -> float:
    """Resolve finished mass from the last real production stage.

    STEP 8 semantics:
    - a manually recorded finished/final-stage value wins because it already
      represents measured finished mass;
    - when formulation is used and no later measured output exists, formulation
      additions such as terpene mass are added to the formulation base;
    - when formulation is not used, the last measured real production stage is
      used without blindly adding terpene mass.
    """
    explicit = _positive(explicit_finished_output_g)
    if explicit:
        return explicit

    workflow = get_extraction_workflow(workflow_key)
    values = dict(stage_outputs or {})
    production_stages = [stage for stage in workflow.stages if not stage.qa_gate and not stage.release_gate]
    stage_values = [(stage, _stage_output_value(stage, values)) for stage in production_stages]

    if formulation_used and workflow.has_stage("formulation"):
        formulation_index = next(index for index, (stage, _value) in enumerate(stage_values) if stage.key == "formulation")
        # A measured formulation/filling/packaging/final output already includes
        # whatever formulation ingredients were actually present, so do not add
        # terpene mass a second time.
        for stage, value in reversed(stage_values[formulation_index:]):
            if value > 0:
                return value

        base = max(0.0, float(formulation_base_g or 0.0))
        if base <= 0:
            for _stage, value in reversed(stage_values[:formulation_index]):
                if value > 0:
                    base = value
                    break
        terpene = max(0.0, float(terpene_weight_g or 0.0))
        return base + terpene

    for _stage, value in reversed(stage_values):
        if value > 0:
            return value
    return 0.0
