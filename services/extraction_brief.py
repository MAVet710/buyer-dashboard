"""Grounded extraction brief generation for the Extraction Command Center.

This replaces generic rules-provider output with deterministic run evidence first,
then an optional provider-neutral DoobieLogic interpretation over the same read-only datasets.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from services.agent_registry import PROFILES
from services.extraction_agent import build_extraction_derived_datasets
from services.ai.workspace_compat import DoobieWorkspaceAgent as GeminiWorkspaceAgent


_BAD_OUTPUT_TOKENS = (
    "mailto:",
    "[operations:",
    "[department_knowledge:",
    "grounded source context:",
    "module curriculum:",
    "epa:",
    "shopify",
    "national retail federation",
    "nacds",
)

_OPTIONAL_CAPABILITIES = {
    "terpene retention": {"input_terpene_pct", "finished_terpene_pct", "terpene_retention_pct"},
    "turnaround": {"turnaround_hours"},
    "rework": {"rework_required"},
    "residual solvent": {"residual_solvent_status"},
    "downtime": {"downtime_minutes"},
    "validated run settings": {"settings_verified", "sop_reference"},
}


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _frame(value: Any) -> pd.DataFrame | None:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        return pd.DataFrame(value)
    if isinstance(value, tuple) and value and all(isinstance(item, dict) for item in value):
        return pd.DataFrame(list(value))
    return None


def _datasets_from_payload(data: dict[str, Any]) -> dict[str, pd.DataFrame]:
    datasets: dict[str, pd.DataFrame] = {}
    aliases = {
        "runs": "extraction_runs",
        "runlog": "extraction_runs",
        "runrows": "extraction_runs",
        "run_data": "extraction_runs",
        "rundata": "extraction_runs",
        "extractionruns": "extraction_runs",
        "jobs": "extraction_jobs",
        "tolljobs": "extraction_jobs",
        "clientjobs": "extraction_jobs",
        "extractionjobs": "extraction_jobs",
        "inventory": "extraction_inventory",
        "extractioninventory": "extraction_inventory",
        "materials": "extraction_inventory",
        "weekly": "extraction_weekly",
        "weeklysummary": "extraction_weekly",
    }
    for key, value in dict(data or {}).items():
        frame = _frame(value)
        if frame is None or frame.empty:
            continue
        name = aliases.get(_norm(key), str(key))
        datasets[name] = frame

    for wrapper in ("data", "context", "payload", "run_data"):
        nested = data.get(wrapper)
        if isinstance(nested, dict):
            for key, value in _datasets_from_payload(nested).items():
                datasets.setdefault(key, value)

    run_frame = datasets.get("extraction_runs")
    if isinstance(run_frame, pd.DataFrame) and not run_frame.empty:
        datasets.update(build_extraction_derived_datasets({"extraction_runs": run_frame}))
    return datasets


def _column_set(frame: pd.DataFrame | None) -> set[str]:
    if not isinstance(frame, pd.DataFrame):
        return set()
    return {str(col) for col in frame.columns}


def _capability_presence(runs: pd.DataFrame) -> dict[str, bool]:
    columns = _column_set(runs)
    return {name: required.issubset(columns) for name, required in _OPTIONAL_CAPABILITIES.items()}


def _safe_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _run_id(row: pd.Series) -> str:
    for key in ("batch_id", "batch_id_internal", "run_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return "Unnamed run"


def _evidence(datasets: dict[str, pd.DataFrame]) -> tuple[str, list[str], list[str], dict[str, bool]]:
    raw = datasets.get("extraction_runs")
    derived = datasets.get("extraction_run_analysis")
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        return (
            "No extraction run rows are loaded, so there is no run-level evidence to brief.",
            ["Load current extraction run data before asking for process recommendations."],
            ["No extraction run data available"],
            {name: False for name in _OPTIONAL_CAPABILITIES},
        )

    if not isinstance(derived, pd.DataFrame) or derived.empty:
        derived = raw.copy()

    capabilities = _capability_presence(raw)
    recommendations: list[str] = []
    risks: list[str] = []

    run_count = len(raw)
    total_input = _safe_number(derived.get("input_weight_g", pd.Series(dtype=float))).sum()
    total_output = _safe_number(derived.get("finished_output_g", pd.Series(dtype=float))).sum()
    yield_values = _safe_number(derived.get("computed_yield_pct", pd.Series(dtype=float))).dropna()
    average_yield = float(yield_values.mean()) if not yield_values.empty else None

    lines = [f"**Current run evidence:** {run_count} run(s), {total_input:,.1f} g input and {total_output:,.1f} g finished output."]
    if average_yield is not None:
        lines.append(f"Average computed yield across loaded runs: **{average_yield:.2f}%**.")

    if "qa_hold" in derived.columns:
        holds = derived[derived["qa_hold"].fillna(False).astype(bool)].copy()
        if not holds.empty:
            ids = [_run_id(row) for _, row in holds.head(4).iterrows()]
            risks.append(f"{len(holds)} run(s) are on QA hold: {', '.join(ids)}")
            recommendations.append(f"Resolve QA release blockers for {', '.join(ids)} before treating their output as available.")

    if "post_process_loss_pct" in derived.columns:
        losses = _safe_number(derived["post_process_loss_pct"])
        high_loss = derived.loc[losses > 15].copy()
        if not high_loss.empty:
            row = high_loss.loc[losses.loc[high_loss.index].idxmax()]
            rid = _run_id(row)
            value = float(losses.loc[row.name])
            risks.append(f"{rid} has {value:.1f}% post-process loss")
            recommendations.append(f"Review the stage transition on {rid}; its measured post-process loss is {value:.1f}%.")

    if "gross_margin_pct" in derived.columns:
        margins = _safe_number(derived["gross_margin_pct"])
        low_margin = derived.loc[margins < 20].copy()
        if not low_margin.empty:
            row = low_margin.loc[margins.loc[low_margin.index].idxmin()]
            rid = _run_id(row)
            value = float(margins.loc[row.name])
            risks.append(f"{rid} has {value:.1f}% estimated gross margin")
            recommendations.append(f"Review material, processing, and packaging cost drivers on {rid}; estimated gross margin is {value:.1f}%.")

    if capabilities.get("terpene retention"):
        retention = _safe_number(raw["terpene_retention_pct"])
        usable = retention.dropna()
        if not usable.empty:
            idx = usable.idxmin()
            rid = str(raw.loc[idx].get("batch_id_internal") or "Unnamed run")
            value = float(retention.loc[idx])
            lines.append(f"Lowest measured terpene retention: **{rid} at {value:.1f}%**.")
            if value < 65:
                risks.append(f"{rid} has low measured terpene retention ({value:.1f}%)")
                recommendations.append(f"Investigate material handling and validated stage controls on {rid}; measured terpene retention is {value:.1f}%.")

    if capabilities.get("turnaround"):
        tat = _safe_number(raw["turnaround_hours"])
        usable = tat.dropna()
        if not usable.empty:
            idx = usable.idxmax()
            rid = str(raw.loc[idx].get("batch_id_internal") or "Unnamed run")
            lines.append(f"Longest measured turnaround: **{rid} at {float(tat.loc[idx]):.1f} hours**.")

    if capabilities.get("rework"):
        rework = raw["rework_required"].fillna(False).astype(bool)
        count = int(rework.sum())
        if count:
            ids = raw.loc[rework, "batch_id_internal"].astype(str).head(4).tolist()
            risks.append(f"{count} run(s) require rework: {', '.join(ids)}")
            recommendations.append(f"Review the documented rework causes for {', '.join(ids)} before scheduling repeat production.")

    if capabilities.get("residual solvent"):
        status = raw["residual_solvent_status"].fillna("").astype(str).str.casefold()
        failed = raw.loc[status.isin({"failed", "fail", "flagged"})]
        if not failed.empty:
            ids = failed["batch_id_internal"].astype(str).head(4).tolist()
            risks.append(f"Residual-solvent QA is failed/flagged on {', '.join(ids)}")
            recommendations.append(f"Keep {', '.join(ids)} blocked from release and follow the validated QA/CAPA workflow.")

    if capabilities.get("downtime"):
        downtime = _safe_number(raw["downtime_minutes"])
        usable = downtime.dropna()
        if not usable.empty and float(usable.max()) > 0:
            idx = usable.idxmax()
            rid = str(raw.loc[idx].get("batch_id_internal") or "Unnamed run")
            lines.append(f"Highest logged downtime: **{rid} at {float(downtime.loc[idx]):.0f} minutes**.")

    missing = [name for name, present in capabilities.items() if not present]
    if missing:
        lines.append("**Unavailable measurements:** " + ", ".join(missing) + ". The brief will not recommend benchmarking those metrics.")

    if not recommendations:
        recommendations.append("No run-level exception crosses the current deterministic checks; maintain batch-level yield, QA, stage-loss, and margin monitoring.")

    return "\n\n".join(lines), recommendations[:6], risks[:6], capabilities


def _reject_ai(text: str, runs: pd.DataFrame, capabilities: dict[str, bool]) -> bool:
    lowered = str(text or "").casefold()
    if not lowered:
        return True
    if any(token in lowered for token in _BAD_OUTPUT_TOKENS):
        return True
    unsupported_terms = {
        "terpene": "terpene retention",
        "turnaround": "turnaround",
        "rework": "rework",
        "residual solvent": "residual solvent",
        "downtime": "downtime",
        "run setting": "validated run settings",
        "pressure": "validated run settings",
        "temperature": "validated run settings",
    }
    for token, capability in unsupported_terms.items():
        if token in lowered and not capabilities.get(capability, False):
            return True
    ids = runs.get("batch_id_internal", pd.Series(dtype=str)).astype(str).tolist()
    real_ids = [rid.casefold() for rid in ids if rid and rid != "nan"]
    if real_ids and not any(rid in lowered for rid in real_ids):
        return True
    return False


def generate_extraction_brief(
    data: dict[str, Any],
    *,
    state: str | None = None,
    question: str | None = None,
) -> dict[str, Any]:
    """Return the standard Buyer Dashboard brief contract using local evidence."""
    datasets = _datasets_from_payload(dict(data or {}))
    runs = datasets.get("extraction_runs")
    evidence, recommendations, risks, capabilities = _evidence(datasets)

    if not isinstance(runs, pd.DataFrame) or runs.empty:
        return {
            "answer": evidence,
            "explanation": "Extraction recommendations require current run-level evidence.",
            "recommendations": recommendations,
            "confidence": "low",
            "sources": [],
            "mode": "extraction",
            "routed_mode": "extraction",
            "routed_by": "Buyer Dashboard grounded extraction brief",
            "ai": {"provider": "deterministic", "model": ""},
            "risk_flags": risks,
            "inefficiencies": [],
            "needs_clarification": True,
            "missing_context": ["current extraction run rows"],
        }

    agent = GeminiWorkspaceAgent(profile=PROFILES["extraction"])
    ai_text = ""
    provider = "deterministic"
    model = ""
    if agent.enabled:
        availability = ", ".join(f"{name}={'available' if present else 'missing'}" for name, present in capabilities.items())
        prompt = (
            str(question or "Which extraction risks and process opportunities matter most?").strip()
            + "\n\nUse only the loaded run/job/inventory evidence. Name actual batch IDs and measurements. "
            "Do not add external retail/compliance sources or generic curriculum text. "
            "Do not recommend benchmarking a metric marked missing. "
            f"Measurement availability: {availability}."
        )
        try:
            candidate = agent.run(
                prompt,
                datasets,
                app_mode="Production Operations",
                section="Extraction Command Center",
                profile=PROFILES["extraction"],
            ).strip()
            if not _reject_ai(candidate, runs, capabilities):
                ai_text = candidate
                provider = agent.provider or "ai_runtime"
                model = agent.model
        except Exception:
            ai_text = ""

    answer = evidence
    if ai_text:
        answer += "\n\n**DoobieLogic AI extraction interpretation**\n\n" + ai_text

    return {
        "answer": answer,
        "explanation": "This brief is grounded in the currently supplied extraction rows. Missing measurements are explicitly excluded from recommendations.",
        "recommendations": recommendations,
        "confidence": "high" if len(runs) >= 3 else "medium",
        "sources": [],
        "mode": "extraction",
        "routed_mode": "extraction",
        "routed_by": "Buyer Dashboard grounded extraction brief",
        "ai": {"provider": provider, "model": model},
        "risk_flags": risks,
        "inefficiencies": [],
        "needs_clarification": False,
        "missing_context": [],
    }
