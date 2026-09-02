from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_commercial_order_list_batches_line_reads() -> None:
    source = (ROOT / "backend/app/routers/commercial.py").read_text(encoding="utf-8")
    order_list = source.split('@router.get("/orders")', 1)[1].split('@router.post("/orders"', 1)[0]

    assert "_scoped_order_lines" in order_list
    assert "lines_by_order" in order_list
    assert "repo.list_order_lines(context.organization_id, order_id=order.id)" not in order_list


def test_commercial_workspace_scopes_lines_to_visible_facility_orders() -> None:
    source = (ROOT / "backend/app/routers/commercial.py").read_text(encoding="utf-8")
    workspace = source.split('@router.get("/workspace")', 1)[1].split('@router.get("/partners")', 1)[0]

    assert "order_ids = {row.id for row in orders}" in workspace
    assert "_scoped_order_lines(engine, context.organization_id, order_ids)" in workspace
    assert "commercial.list_order_lines(context.organization_id)" not in workspace
