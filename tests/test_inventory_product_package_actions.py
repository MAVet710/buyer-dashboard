from pathlib import Path


INVENTORY_PAGE = Path("frontend/src/pages/InventoryPage.tsx")


def _source() -> str:
    return INVENTORY_PAGE.read_text(encoding="utf-8")


def test_product_selection_resolves_underlying_packages_for_package_actions():
    source = _source()

    assert 'const selectedPackages=grain==="packages"?selected:packageRows.filter' in source
    assert 'const productPackages=selected.length===1?packageRows.filter' in source
    assert 'function openPackageAction(action:PackageAction)' in source
    assert 'setPackageChoice(action)' in source


def test_product_view_package_actions_are_not_silently_disabled_by_grain():
    source = _source()

    assert 'disabled={selected.length!==1||grain!=="packages"}' not in source
    assert 'disabled={grain!=="packages"}' not in source
    assert 'onClick={()=>openPackageAction("studio")}' in source
    assert 'onClick={()=>openPackageAction("adjust")}' in source


def test_product_label_printing_expands_to_real_package_rows():
    source = _source()

    assert 'selectedPackages.map(row=><article className="inventory-label"' in source
    assert 'Print labels for every package under the selected product(s)' in source


def test_multiple_packages_prompt_for_an_explicit_package_choice():
    source = _source()

    assert 'title={packageChoice==="adjust"?"Choose package to adjust":"Choose package to work on"}' in source
    assert 'productPackages.map(pkg=><button' in source
    assert 'onClick={()=>choosePackage(pkg)}' in source


def test_adjust_permission_still_blocks_unauthorized_roles():
    source = _source()

    assert 'disabled={selected.length!==1||selectedPackages.length===0||!adjustAllowed}' in source
    assert 'Adjustment permission required' in source
