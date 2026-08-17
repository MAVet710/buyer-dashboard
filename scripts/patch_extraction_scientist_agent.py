from pathlib import Path

REGISTRY = Path("services/agent_registry.py")
GEMINI = Path("services/gemini_agent.py")
WORKFLOW = Path(".github/workflows/patch-extraction-scientist.yml")
SCRIPT = Path("scripts/patch_extraction_scientist_agent.py")

registry = REGISTRY.read_text(encoding="utf-8")
old_profile = '''    "extraction": AgentProfile(
        key="extraction",
        name="Extraction Agent",
        role="cannabis extraction operations and profitability analyst",
        description="Analyzes run logs, mass balance, yields, losses, QA holds, process stages, and profitability.",
        focus=("mass balance", "yield", "stage loss", "QA holds", "process efficiency", "COGS", "gross margin"),
        suggested_questions=(
            "Which extraction runs need attention?",
            "Where are we losing the most yield?",
            "Which batches have the biggest profitability or QA risk?",
        ),
    ),
'''
new_profile = '''    "extraction": AgentProfile(
        key="extraction",
        name="Extraction Scientist Agent",
        role="master chemical/process engineer, chief extraction scientist, and source-aware extraction knowledge analyst",
        description=(
            "Combines commercial extraction engineering, run analytics, troubleshooting, process safety, "
            "quality, profitability, and source-grounded field-practice knowledge across hydrocarbon, "
            "solventless, CO2, ethanol, distillation/isolation, and emerging methods."
        ),
        focus=(
            "mass balance",
            "yield and stage loss",
            "hydrocarbon processing",
            "solventless",
            "CO2",
            "ethanol and solvent recovery",
            "distillation and isolation",
            "QA holds",
            "process safety",
            "method comparison",
            "COGS and gross margin",
            "source-grounded troubleshooting",
        ),
        suggested_questions=(
            "Which extraction runs need attention and what evidence points to the root cause?",
            "Compare yield, loss, QA risk, and margin by extraction method.",
            "Troubleshoot this run like a process engineer and tell me what measurements to check next.",
            "What does the loaded source material say about this extraction problem, and where does field practice disagree?",
        ),
    ),
'''
if old_profile not in registry:
    raise SystemExit("extraction profile anchor not found")
REGISTRY.write_text(registry.replace(old_profile, new_profile, 1), encoding="utf-8")

gemini = GEMINI.read_text(encoding="utf-8")
import_anchor = 'from services.agent_registry import AgentProfile, PROFILES, resolve_agent_profile\n'
import_block = import_anchor + '''from services.extraction_agent import (
    EXTRACTION_SPECIALIST_INSTRUCTIONS,
    build_extraction_derived_datasets,
    extraction_method_scope_frame,
    extraction_reference_index_frame,
)
'''
if import_anchor not in gemini:
    raise SystemExit("gemini import anchor not found")
gemini = gemini.replace(import_anchor, import_block, 1)

compliance_anchor = '''        compliance_rule = (
            "- This is a sourced-compliance workflow. Never state a regulation, legal requirement, penalty, or compliance conclusion from model memory. "
            "Only analyze evidence returned by tools or tell the user what should be verified in the app's sourced Compliance Q&A.\\n"
            if active.compliance_grounded_only
            else "- Never infer cannabis regulations from model memory. For legal or regulatory conclusions, use the app's sourced compliance workflow.\\n"
        )
        prompt = f"""You are {active.name}, the {active.role} inside Buyer Dashboard.
'''
compliance_replacement = '''        compliance_rule = (
            "- This is a sourced-compliance workflow. Never state a regulation, legal requirement, penalty, or compliance conclusion from model memory. "
            "Only analyze evidence returned by tools or tell the user what should be verified in the app's sourced Compliance Q&A.\\n"
            if active.compliance_grounded_only
            else "- Never infer cannabis regulations from model memory. For legal or regulatory conclusions, use the app's sourced compliance workflow.\\n"
        )
        specialist_instructions = (
            EXTRACTION_SPECIALIST_INSTRUCTIONS if active.key == "extraction" else ""
        )
        prompt = f"""You are {active.name}, the {active.role} inside Buyer Dashboard.
'''
if compliance_anchor not in gemini:
    raise SystemExit("gemini prompt setup anchor not found")
gemini = gemini.replace(compliance_anchor, compliance_replacement, 1)

prompt_anchor = '''Recent conversation:\\n{history_text or '(none)'}

User request: {question}

Rules:
'''
prompt_replacement = '''Recent conversation:\\n{history_text or '(none)'}

{specialist_instructions}

User request: {question}

Rules:
'''
if prompt_anchor not in gemini:
    raise SystemExit("gemini prompt body anchor not found")
gemini = gemini.replace(prompt_anchor, prompt_replacement, 1)

loader_anchor = '''def _load_extraction_datasets(session_state: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    for public_name, session_key in EXTRACTION_SESSION_DATASETS.items():
        _put_frame(output, public_name, session_state.get(session_key))
    return output
'''
loader_replacement = '''def _load_extraction_datasets(session_state: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    for public_name, session_key in EXTRACTION_SESSION_DATASETS.items():
        _put_frame(output, public_name, session_state.get(session_key))

    # Optional curated excerpts/notes can be loaded by future or tenant-specific
    # extraction workflows. The agent must not claim forum sourcing without them.
    for session_key in ("extraction_reference_notes", "ecc_reference_notes"):
        if "extraction_reference_notes" not in output:
            _put_frame(output, "extraction_reference_notes", session_state.get(session_key))

    output["extraction_method_scope"] = extraction_method_scope_frame()
    output["extraction_reference_index"] = extraction_reference_index_frame()
    output.update(build_extraction_derived_datasets(output))
    return output
'''
if loader_anchor not in gemini:
    raise SystemExit("extraction loader anchor not found")
gemini = gemini.replace(loader_anchor, loader_replacement, 1)
GEMINI.write_text(gemini, encoding="utf-8")

for cleanup in (WORKFLOW, SCRIPT):
    if cleanup.exists():
        cleanup.unlink()
