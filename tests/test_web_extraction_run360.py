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


def test_react_extraction_analytics_and_toll_forms_match_streamlit_source_order():
    source = (ROOT / "frontend" / "src" / "pages" / "ExtractionCommandCenterPage.tsx").read_text(encoding="utf-8")
    for label in [
        "Extraction Command Center Parity",
        "Executive Overview",
        "Run Analytics",
        "Toll Processing",
        "Compliance / METRC",
        "Data Input",
        "Doobie Ops Brief",
        "Add Run Record",
        "Run Date",
        "State / Jurisdiction",
        "Facility / License Name",
        "Client Name",
        "Internal Batch ID",
        "METRC Package ID - Input",
        "METRC Package ID - Output",
        "METRC Manifest / Transfer ID",
        "Post Process Efficiency Pct",
        "Add Toll Processing Job",
        "Client License / Registration",
        "Material Received Date",
        "Promised Completion Date",
        "Expected Output (g)",
        "Actual Output (g)",
    ]:
        assert label in source or label.casefold().replace(" ", "_") in source.casefold()
    assert source.index("Run Date") < source.index("Run Notes") < source.index("Add Run\"")
    toll_section = source[source.index('{tab==="toll"'):source.index('{tab==="compliance"')]
    assert "streamlit-expander" in toll_section
    assert "Internal Batch ID" not in toll_section
    assert "Processing Fee (USD)" not in toll_section
    assert "Job Notes" not in toll_section


def test_extraction_parity_fields_are_durable_columns_not_serialized_notes():
    model = (ROOT / "modules" / "extraction" / "models.py").read_text(encoding="utf-8")
    router = (ROOT / "backend" / "app" / "routers" / "extraction_parity.py").read_text(encoding="utf-8")
    migration = (ROOT / "migrations" / "versions" / "0038_extraction_parity_fields.py").read_text(encoding="utf-8")
    for field in [
        "manual_batch_id_internal",
        "run_date",
        "jurisdiction",
        "manual_input_weight_g",
        "manual_finished_output_g",
        "metrc_manifest_or_transfer_id",
        "estimated_revenue_usd",
        "client_license_snapshot",
        "expected_output_g",
        "actual_output_g",
        "job_status",
    ]:
        assert field in model
        assert field in migration
    assert "json.dumps" not in router
