from pathlib import Path

from backend.app.services.metrc_permission_evidence import (
    DATASET_KEY,
    normalize_permissions,
)


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_permission_normalizer_is_stable_and_does_not_invent_semantics():
    payload = {
        "Permissions": [
            {"Name": "Manage Plants"},
            {"PermissionName": "Manage Packages"},
            {"CreateLocations": True, "DeleteLocations": False},
            "View Transfers",
            {"nested": [{"displayName": "Manage Plants"}]},
        ]
    }
    assert normalize_permissions(payload) == [
        "CreateLocations",
        "Manage Packages",
        "Manage Plants",
        "View Transfers",
    ]


def test_permission_evidence_has_dedicated_non_secret_dataset():
    service = _read("backend/app/services/metrc_permission_evidence.py")
    assert DATASET_KEY == "metrc_permission_evidence"
    assert "encrypted_secret" not in service
    assert '"optional": True' in service
    assert '"provider": "metrc"' in service
    assert '"evidence_type": "employee_permissions"' in service


def test_initial_hydration_no_longer_requires_permission_introspection():
    composition = _read("backend/app/metrc_runtime_composition.py")
    assert 'if str(resource) != "facility_permissions"' in composition
    assert '"required_for_initial_hydration": False' in composition
    assert '"resource": "employee_permissions"' in composition
    assert 'sandbox_integrations._discover_metrc_facilities = (' in composition


def test_successful_permission_introspection_is_persisted_but_failure_is_non_blocking():
    composition = _read("backend/app/metrc_runtime_composition.py")
    assert "MetrcPermissionEvidenceStore(engine).persist(" in composition
    assert 'public["evidence_persisted"] = False' in composition
    assert 'public["evidence_optional"] = True' in composition
    assert "permission evidence must never block normal provider reads" in composition
    assert 'location_settings.router, "/metrc-permissions", persisted_metrc_permissions' in composition
