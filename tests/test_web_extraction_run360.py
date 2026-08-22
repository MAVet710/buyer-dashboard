from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_react_extraction_run_360_preserves_streamlit_drawer_tabs_and_actions():
    source = (ROOT / "frontend" / "src" / "pages" / "ExtractionPage.tsx").read_text(encoding="utf-8")
    for label in [
        "Extraction Operations",
        "Run board first. Click a run once to open its full production, QA, COGS and traceability context.",
        "Active Runs",
        "QA / Holds",
        "Traceability Exceptions",
        "Active Run COGS",
        "New Extraction Run",
        "Batch / Run ID",
        "Strain / cultivar",
        "Target product family",
        "Lead operator",
        "Facility license",
        "Run notes",
        "RUN 360 · durable production object",
        "Overview",
        "Inputs",
        "Process",
        "Outputs + QA",
        "COGS",
        "Traceability",
        "History",
        "Reserve source lot",
        "Consume reserved material",
        "Record stage update",
        "Create output / WIP package",
        "Create quarantined output",
        "Record QA event",
        "Release run + output inventory",
        "Add cost",
        "Queue output package creation",
        "Validate + queue",
        "Open Traceability Operations",
    ]:
        assert label in source
    assert source.index("Overview") < source.index("History")
    assert "StreamlitDialog" in source


def test_extraction_router_exposes_the_complete_durable_run_360_contract():
    source = (ROOT / "backend" / "app" / "routers" / "extraction.py").read_text(encoding="utf-8")
    for contract in [
        'repo.run_360(',
        '"workflow"',
        '"cost_events"',
        '"traceability"',
        '@router.get("/products")',
        '@router.post("/runs/{run_id}/notes")',
        '@router.post("/inputs/{input_id}/release")',
        '@router.post("/runs/{run_id}/traceability/output-package"',
        "ExtractionTraceabilityService(engine).queue_output_package_creation",
    ]:
        assert contract in source
