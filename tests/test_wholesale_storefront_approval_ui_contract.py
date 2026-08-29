from pathlib import Path


def test_wholesale_overview_surfaces_storefront_approval_queue():
    source = Path("frontend/src/pages/WholesaleOpsPage.tsx").read_text(encoding="utf-8")
    assert "Pending Storefront Orders" in source
    assert "New customer submissions will appear here automatically." in source
    assert "Review order" in source
    assert 'row.status==="submitted"' in source
    assert 'onReview={()=>onTab("storefront")}' in source
