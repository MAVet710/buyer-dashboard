"""Source guards supplement the real-browser exact-run acceptance cases."""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def source(name: str) -> str:
    return (ROOT / "frontend" / "src" / "pages" / name).read_text(encoding="utf-8")


def test_history_restored_run_closes_the_previous_creation_form():
    floor = source("ExtractionOperatorWorkspace.tsx")
    assert re.search(
        r"useEffect\(\(\)=>\{if\(selectedRunId\)setCreating\(false\)\},\[selectedRunId\]\)",
        floor,
    ), "History navigation must close creation state without relying on the row click handler."
    assert 'const selected=selectedRunId??localSelected;' in floor
    assert '<CurrentRun key={`${scope}:${selected}`}' in floor


def test_pending_explicit_selection_cannot_be_replaced_by_queue_default():
    floor = source("ExtractionOperatorWorkspace.tsx")
    assert 'const selectionPending=useRef(false);' in floor
    assert 'useEffect(()=>{selectionPending.current=false},[selectedRunId]);' in floor
    select = floor.split('const selectRun=useCallback(', 1)[1].split(';\n', 1)[0]
    assert select.index('selectionPending.current=Boolean(onSelectRun)') < select.index('setLocalSelected(runId)')
    assert 'if (selected || creating || selectionPending.current) return;' in floor
    real_stack = (ROOT / 'frontend/e2e/operator-alpha-real.spec.ts').read_text(encoding='utf-8')
    assert 'new URL(reservationResponse.url()).pathname.split("/").at(-2)' in real_stack
    assert 'searchParams.get("extractionRun")).toBe(createdRunId)' in real_stack
    assert 'Start run & consume reserved material' in real_stack


def test_floor_and_advanced_share_scope_qualified_exact_detail_keys():
    for name in ("ExtractionOperatorWorkspace.tsx", "ExtractionPage.tsx"):
        page = source(name)
        compact = re.sub(r"\s+", "", page)
        assert 'queryKey:["extraction-run",selected,scope]' in compact
        assert '/api/v1/extraction/runs/${encodeURIComponent(selected)}' in page
        assert 'detail.data.run.id!==selected' in page
        assert "No other run was selected in its place." in page


def test_parent_keeps_run_identity_when_the_advanced_window_closes():
    page = source("ExtractionUnifiedPage.tsx")
    close = page.split('const closeAdvanced=', 1)[1].split(';\n', 1)[0]
    assert 'updated.delete("extractionPanel")' in close
    assert 'delete("extractionRun")' not in close
    assert 'selectedRunId={selectedRunId} onSelectRun={selectRun}' in page
    assert 'selectedRunId={advancedView==="run"?selectedRunId:""}' in page
