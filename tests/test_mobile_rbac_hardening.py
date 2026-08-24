from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.app.auth import RequestContext
from backend.app.routers.audits import WRITE_ROLES as AUDIT_WRITE_ROLES
from backend.app.routers.inventory import ADJUSTMENT_ROLES, RECEIVING_ROLES, _require_receiving
from backend.app.routers.package_studio import COMMIT_ROLES as PACKAGE_STUDIO_COMMIT_ROLES
from backend.app.routers.purchasing import BUY_ROLES


ROOT = Path(__file__).resolve().parents[1]


def _context(role: str) -> RequestContext:
    return RequestContext(
        user_id=f"{role or 'anonymous'}-user",
        organization_id="org-rbac",
        facility_id="facility-rbac",
        role=role,
    )


def test_inventory_receiving_role_matrix_fails_closed():
    assert RECEIVING_ROLES == {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa", "trial"}

    for role in sorted(RECEIVING_ROLES):
        _require_receiving(_context(role))

    for role in ("read_only", "user", "", "unknown"):
        with pytest.raises(HTTPException) as exc_info:
            _require_receiving(_context(role))
        assert exc_info.value.status_code == 403
        assert "does not allow inventory receiving" in str(exc_info.value.detail)


def test_read_only_is_excluded_from_every_inventory_mutation_role_set():
    mutation_role_sets = {
        "receiving": RECEIVING_ROLES,
        "adjustments": ADJUSTMENT_ROLES,
        "audits": AUDIT_WRITE_ROLES,
        "package_studio": PACKAGE_STUDIO_COMMIT_ROLES,
        "purchasing": BUY_ROLES,
    }
    for action, roles in mutation_role_sets.items():
        assert "read_only" not in roles, f"read_only unexpectedly gained {action} mutation access"
        assert "user" not in roles, f"generic user unexpectedly gained {action} mutation access"


def test_inventory_react_surface_uses_authenticated_role_to_disable_mutations():
    page = (ROOT / "frontend" / "src" / "pages" / "InventoryPage.tsx").read_text(encoding="utf-8")

    assert 'const role=account.data?.user.role??""' in page
    assert 'const receivingAllowed=["dev","admin","buyer","planner","supervisor","operator","qa","trial"].includes(role)' in page
    assert 'const auditAllowed=["dev","admin","buyer","supervisor","operator","qa","trial"].includes(role)' in page
    assert 'const packageStudioAllowed=["dev","admin","buyer","planner","supervisor","operator","qa"].includes(role)' in page
    assert 'const purchasingAllowed=["dev","admin","supervisor","buyer"].includes(role)' in page
    assert 'const adjustAllowed=["dev","admin","supervisor","operator","qa"].includes(role)' in page

    assert 'disabled={!receivingAllowed}' in page
    assert 'disabled={!auditAllowed}' in page
    assert 'disabled={!purchasingAllowed}' in page
    assert '||!packageStudioAllowed}' in page
    assert '||!adjustAllowed}' in page
    assert 'receiving&&receivingAllowed?' in page
    assert 'studio&&packageStudioAllowed' in page
    assert 'adjusting&&adjustAllowed&&actionPackage' in page


def test_mobile_browser_contract_covers_read_only_and_operator_paths():
    spec = (ROOT / "frontend" / "e2e" / "inventory-product-actions-mobile.spec.ts").read_text(encoding="utf-8")

    assert 'role: "read_only"' in spec
    assert 'read-only inventory stays read-only at ${width}px' in spec
    assert 'getByRole("button", { name: "Receive inventory" })).toBeDisabled()' in spec
    assert 'getByRole("button", { name: "Package Studio", exact: true })).toBeDisabled()' in spec
    assert 'getByRole("button", { name: "Audit", exact: true })).toBeDisabled()' in spec
    assert 'getByRole("button", { name: "Add to PO" })).toBeDisabled()' in spec
    assert 'getByRole("button", { name: "Work on package" })).toBeDisabled()' in spec
    assert 'getByRole("button", { name: "Adjust", exact: true })).toBeDisabled()' in spec
    assert 'getByRole("button", { name: "Print labels" })' in spec
