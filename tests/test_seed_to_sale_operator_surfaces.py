from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_harvest_360_exposes_guarded_harvest_to_inventory_workflow():
    workspace = _read("frontend/src/components/CultivationOperationsControl.tsx")
    allocation = _read("frontend/src/components/HarvestOutputAllocation.tsx")
    router = _read("backend/app/routers/production_mutations.py")

    assert 'import { HarvestOutputAllocation } from "./HarvestOutputAllocation"' in workspace
    assert "<HarvestOutputAllocation" in workspace
    assert "HARVEST → INVENTORY" in allocation
    assert "/outputs/preview" in allocation
    assert "/outputs/commit" in allocation
    assert "preview_key:preview.preview_key" in allocation
    assert '@cultivation_router.post("/harvests/{harvest_id}/outputs/preview")' in router
    assert '@cultivation_router.post("/harvests/{harvest_id}/outputs/commit", status_code=201)' in router
    assert "GuardedHarvestAllocationService" in router


def test_run_360_materials_tab_exposes_actual_physical_consumption():
    page = _read("frontend/src/pages/ProductionRun360Page.tsx")
    actuals = _read("frontend/src/components/ProductionActualMaterials.tsx")
    router = _read("backend/app/routers/production_mutations.py")

    assert 'import { ProductionActualMaterials } from "../components/ProductionActualMaterials"' in page
    assert "<ProductionActualMaterials" in page
    assert "ACTUAL MATERIALS" in actuals
    assert 'action_type:"consume_materials"' in actuals
    assert "Apply physical consumption" in actuals
    assert "preview_key:preview.preview_key" in actuals
    assert 'action_type == "consume_materials"' in router
    assert "Your role cannot post physical production consumption" in router


def test_package_360_exposes_recursive_seed_to_sale_graph():
    package_360 = _read("frontend/src/components/Package360Window.tsx")
    graph = _read("frontend/src/components/MaterialLineageGraph.tsx")
    router = _read("backend/app/routers/production_mutations.py")

    assert 'import { MaterialLineageGraph } from "./MaterialLineageGraph"' in package_360
    assert "<MaterialLineageGraph" in package_360
    assert "SEED-TO-SALE GENEALOGY" in graph
    assert "/api/v1/material-lineage/lots/${lotId}" in graph
    assert "Source plants" in graph
    assert "Harvest source" in graph
    assert '@lineage_router.get("/lots/{lot_id}")' in router
