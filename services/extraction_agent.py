"""Extraction-specialist guidance and derived read-only datasets for Gemini.

This module keeps the Extraction Agent grounded in actual run data and clearly
separates field-practice sources from authoritative safety/engineering sources.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


EXTRACTION_SPECIALIST_INSTRUCTIONS = r"""
Extraction specialist operating mode:
- Act as a senior chemical/process engineer and extraction scientist for a licensed commercial cannabis-processing environment. Combine chemical-engineering fundamentals, process analytics, quality systems, and practical troubleshooting.
- Technical scope includes hydrocarbon closed-loop processing; solventless ice-water hash, freeze-drying, dry sift, rosin pressing and curing; CO2 extraction; cryogenic ethanol and liquid-solvent processing; evaporation and solvent recovery; short-path and wiped/thin-film distillation; crystallization/isolation; chromatography; ultrasonic, microwave, pressurized-liquid and hydrodynamic-cavitation concepts; and other emerging extraction technologies.
- Treat Future4200, ICMag/International Cannagraphic Cannabis Concentrates, BeanBasement, and Skunk Pharm Research as field-practice / archival communities, not engineering codes. Never attribute a claim to a forum unless the actual source text or a curated note is present in the supplied datasets or user prompt. If no source text is available, say the answer is engineering background rather than forum-sourced consensus.
- When source material is available, distinguish: (1) manufacturer/equipment limits and approved facility SOPs, (2) official safety/code material, (3) peer-reviewed/technical references, and (4) forum field reports. Higher-authority safety and equipment limits override forum practice.
- For loaded production data, actively inspect run logs and derived datasets before answering. Quantify input mass, output mass, computed yield, reported yield, stage loss, QA holds, COGS, revenue, gross margin, method performance, and outlier runs when those fields exist.
- Troubleshooting should be hypothesis-driven: name the observed symptom, most likely mechanisms, evidence to check next, and a safe corrective-action plan. Separate proven evidence from plausible causes.
- When discussing flammable solvents, compressed gases, vacuum systems, pressure vessels, heaters, chillers, or hazardous electrical areas, put engineered safety controls first: approved closed-loop equipment, equipment MAWP/temperature limits, pressure relief, bonding/grounding, ventilation, gas detection, ignition control, hazardous-location-rated equipment, PPE, training, and facility-specific emergency procedures. Never suggest bypassing interlocks, relief devices, ventilation, alarms, or equipment ratings.
- Do not invent exact operating setpoints. Exact temperatures, pressures, vacuum levels, solvent ratios, flow rates, media loads, cycle times, or other process values must come from loaded run data, an approved SOP/equipment manual, or supplied/retrieved source text. Otherwise label any range as general context that requires validation for the specific machine, solvent, product, and facility.
- Cannabinoid conversion/isomerization topics may be discussed for chemistry, analytical testing, impurity/byproduct risk, process safety, quality assurance, and regulatory review. Do not provide step-by-step conversion recipes, reagent ratios, catalyst recipes, or optimization instructions for producing controlled cannabinoid products.
- Use an advanced industry tone, but remain concise enough to support operators and managers making decisions in the Extraction Command Center.
""".strip()


_METHOD_SCOPE = [
    {
        "category": "Hydrocarbons (BHO/PHO)",
        "topics": "closed-loop systems; solvent recovery; phase behavior; chilling; column loading; nitrogen/vapor-pressure assist; CRC principles; live resin; sauce; shatter; troubleshooting",
        "source_expectation": "Approved equipment/SOP first; field-practice sources may supplement when source text is supplied.",
    },
    {
        "category": "Solventless",
        "topics": "ice-water hash; micron fractions; wash mechanics; cold-room controls; freeze-drying; dry sift; rosin pressing; curing; jar-tech concepts; piatella; solventless vape preparation",
        "source_expectation": "Use run data and supplied technical/forum material; distinguish cultivar/material effects from machine effects.",
    },
    {
        "category": "CO2",
        "topics": "subcritical/supercritical behavior; fractionation; terpene separation; pressure-temperature relationships; co-solvent concepts; downstream cleanup",
        "source_expectation": "Machine-specific pressure/temperature setpoints require validated manufacturer/SOP evidence.",
    },
    {
        "category": "Ethanol & Liquid Solvents",
        "topics": "cold ethanol; centrifugal extraction; filtration; solvent recovery; falling-film evaporation; wiped/thin-film evaporation; winterization; crystallization concepts",
        "source_expectation": "Flammability, ventilation, solvent compatibility and recovery limits take precedence over throughput optimization.",
    },
    {
        "category": "Distillation & Isolation",
        "topics": "short-path; wiped/thin-film; devolatilization; fraction collection; crystallization; isolate purification; minor-cannabinoid separation; analytical troubleshooting",
        "source_expectation": "Use validated vacuum/thermal envelopes; no unsourced exact recipes.",
    },
    {
        "category": "Emerging & Experimental",
        "topics": "UAE; MAE; PLE; hydrodynamic cavitation; refrigerant/DME extraction concepts; flash chromatography; CPC/CCC; novel terpene separation",
        "source_expectation": "Treat as experimental unless supported by validated equipment/SOP evidence; explicitly identify scale-up and EHS unknowns.",
    },
    {
        "category": "Conversion Chemistry Review",
        "topics": "CBD/cannabinoid isomerization mechanisms; impurity pathways; analytical methods; reaction-hazard review; QA/regulatory implications",
        "source_expectation": "Analytical and safety review only; no procedural synthesis recipes or reagent optimization.",
    },
]


_REFERENCE_INDEX = [
    {
        "source_name": "Future4200",
        "source_type": "field-practice forum",
        "base_url": "https://future4200.com/",
        "coverage": "commercial extraction, solventless, hydrocarbon systems, CRC, distillation, troubleshooting, equipment discussions",
        "use_rule": "Attribute specific claims only when thread text/curated notes are supplied; validate against equipment and safety requirements.",
    },
    {
        "source_name": "ICMag / International Cannagraphic - Cannabis Concentrates",
        "source_type": "field-practice forum / archive",
        "base_url": "https://www.icmag.com/forums/cannabis-concentrates.34/",
        "coverage": "BHO, hash, rosin, CO2, concentrate processing and long-running community troubleshooting",
        "use_rule": "Treat posts as practitioner evidence, not engineering authority; identify age and conflicting practices when relevant.",
    },
    {
        "source_name": "Skunk Pharm Research",
        "source_type": "technical archive / field-practice reference",
        "base_url": "https://skunkpharmresearch.com/",
        "coverage": "legacy closed-loop extraction, recovery, distillation, decarboxylation and process experimentation",
        "use_rule": "Useful historical technical context; verify older procedures against current equipment, fire/electrical code and facility SOPs.",
    },
    {
        "source_name": "BeanBasement",
        "source_type": "user-requested private/community source",
        "base_url": "",
        "coverage": "cultivation and processing community material when supplied by the user or a curated source collection",
        "use_rule": "Do not fabricate access or citations. Use only source text actually supplied to the app/user conversation.",
    },
    {
        "source_name": "OSHA hazardous-location / flammable-material guidance",
        "source_type": "official safety source",
        "base_url": "https://www.osha.gov/laws-regs/regulations/standardnumber/1910",
        "coverage": "hazardous locations, flammable liquids, electrical and workplace safety controls",
        "use_rule": "Authoritative safety layer; use current applicable requirements and facility AHJ/code interpretation.",
    },
]


def extraction_method_scope_frame() -> pd.DataFrame:
    return pd.DataFrame(_METHOD_SCOPE)


def extraction_reference_index_frame() -> pd.DataFrame:
    return pd.DataFrame(_REFERENCE_INDEX)


def _find_col(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    normalized = {
        "".join(ch for ch in str(col).casefold() if ch.isalnum()): str(col)
        for col in frame.columns
    }
    for alias in aliases:
        key = "".join(ch for ch in alias.casefold() if ch.isalnum())
        if key in normalized:
            return normalized[key]
    return None


def _num(frame: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series:
    column = _find_col(frame, aliases)
    if not column:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _text(frame: pd.DataFrame, aliases: tuple[str, ...], default: str = "") -> pd.Series:
    column = _find_col(frame, aliases)
    if not column:
        return pd.Series(default, index=frame.index, dtype="object")
    return frame[column].fillna(default).astype(str).str.strip()


def _bool(frame: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series:
    column = _find_col(frame, aliases)
    if not column:
        return pd.Series(False, index=frame.index, dtype="bool")
    raw = frame[column]
    if raw.dtype == bool:
        return raw.fillna(False)
    return raw.fillna("").astype(str).str.strip().str.casefold().isin({"true", "1", "yes", "y", "hold"})


def _derived_runs(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    out = pd.DataFrame(index=raw.index)
    out["batch_id"] = _text(raw, ("batch_id_internal", "batch_id", "run_id"))
    out["run_date"] = _text(raw, ("run_date", "date"))
    out["method"] = _text(raw, ("method", "extraction_method"), "Unknown")
    out["strain"] = _text(raw, ("strain", "cultivar"))
    out["product_type"] = _text(raw, ("product_type", "output_type"))
    out["process_stage"] = _text(raw, ("process_stage", "stage"))
    out["status"] = _text(raw, ("status",), "Unknown")
    out["coa_status"] = _text(raw, ("coa_status",), "Unknown")
    out["qa_hold"] = _bool(raw, ("qa_hold",))
    out["input_weight_g"] = _num(raw, ("input_weight_g", "input_weight", "input_g"))
    out["intermediate_output_g"] = _num(raw, ("intermediate_output_g", "intermediate_g"))
    out["finished_output_g"] = _num(raw, ("finished_output_g", "finished_output", "output_g"))
    out["reported_residual_loss_g"] = _num(raw, ("residual_loss_g", "residual_g", "waste_g"))
    out["reported_yield_pct"] = _num(raw, ("yield_pct", "yield"))
    out["reported_post_process_efficiency_pct"] = _num(
        raw, ("post_process_efficiency_pct", "post_efficiency_pct")
    )
    out["estimated_revenue_usd"] = _num(raw, ("estimated_revenue_usd", "est_revenue_usd", "revenue_usd"))
    out["cogs_usd"] = _num(raw, ("total_cogs_usd", "cogs_usd", "cogs"))

    valid_input = out["input_weight_g"].gt(0)
    valid_intermediate = out["intermediate_output_g"].gt(0)
    out["computed_yield_pct"] = np.where(
        valid_input,
        out["finished_output_g"] / out["input_weight_g"] * 100.0,
        np.nan,
    )
    out["yield_delta_pct_points"] = out["reported_yield_pct"] - out["computed_yield_pct"]
    out["input_to_intermediate_loss_g"] = np.where(
        valid_input & out["intermediate_output_g"].notna(),
        out["input_weight_g"] - out["intermediate_output_g"],
        np.nan,
    )
    out["post_process_loss_g"] = np.where(
        valid_intermediate & out["finished_output_g"].notna(),
        out["intermediate_output_g"] - out["finished_output_g"],
        np.nan,
    )
    out["post_process_loss_pct"] = np.where(
        valid_intermediate,
        out["post_process_loss_g"] / out["intermediate_output_g"] * 100.0,
        np.nan,
    )
    out["gross_margin_usd"] = out["estimated_revenue_usd"] - out["cogs_usd"]
    out["gross_margin_pct"] = np.where(
        out["estimated_revenue_usd"].gt(0),
        out["gross_margin_usd"] / out["estimated_revenue_usd"] * 100.0,
        np.nan,
    )

    out["data_integrity_issue"] = (
        out["input_weight_g"].le(0)
        | (out["intermediate_output_g"] > out["input_weight_g"])
        | (out["finished_output_g"] > out["intermediate_output_g"])
        | out["yield_delta_pct_points"].abs().gt(2.0)
        | out["post_process_loss_g"].lt(0)
    )
    return out


def _method_summary(derived: pd.DataFrame) -> pd.DataFrame:
    if derived.empty:
        return pd.DataFrame()
    working = derived.copy()
    working["qa_hold_count"] = working["qa_hold"].astype(int)
    grouped = (
        working.groupby("method", dropna=False)
        .agg(
            run_count=("batch_id", "count"),
            total_input_g=("input_weight_g", "sum"),
            total_finished_output_g=("finished_output_g", "sum"),
            avg_computed_yield_pct=("computed_yield_pct", "mean"),
            median_computed_yield_pct=("computed_yield_pct", "median"),
            avg_post_process_loss_pct=("post_process_loss_pct", "mean"),
            qa_hold_runs=("qa_hold_count", "sum"),
            estimated_revenue_usd=("estimated_revenue_usd", "sum"),
            cogs_usd=("cogs_usd", "sum"),
            gross_margin_usd=("gross_margin_usd", "sum"),
        )
        .reset_index()
    )
    grouped["gross_margin_pct"] = np.where(
        grouped["estimated_revenue_usd"].gt(0),
        grouped["gross_margin_usd"] / grouped["estimated_revenue_usd"] * 100.0,
        np.nan,
    )
    return grouped.sort_values("avg_computed_yield_pct", ascending=False, na_position="last")


def build_extraction_derived_datasets(
    datasets: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """Build read-only derived views from the current extraction run log."""
    raw = datasets.get("extraction_runs")
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        raw = datasets.get("partner_extraction_runs")
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        return {}

    derived = _derived_runs(raw)
    output: dict[str, pd.DataFrame] = {"extraction_run_analysis": derived}

    summary = _method_summary(derived)
    if not summary.empty:
        output["extraction_method_summary"] = summary

    holds = derived[
        derived["qa_hold"]
        | derived["status"].str.casefold().str.contains("hold", na=False)
        | derived["coa_status"].str.casefold().isin({"failed", "not submitted", "rejected"})
    ].copy()
    if not holds.empty:
        output["extraction_qa_holds"] = holds.sort_values("run_date", ascending=False)

    exceptions = derived[
        derived["data_integrity_issue"]
        | derived["post_process_loss_pct"].gt(15)
        | derived["gross_margin_pct"].lt(20)
    ].copy()
    if not exceptions.empty:
        output["extraction_exceptions"] = exceptions.sort_values(
            ["data_integrity_issue", "post_process_loss_pct"],
            ascending=[False, False],
            na_position="last",
        )
    return output
