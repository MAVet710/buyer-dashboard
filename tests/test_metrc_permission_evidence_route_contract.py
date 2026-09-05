from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_composed_permissions_route_keeps_provider_enforcement_fail_closed():
    composition = _read("backend/app/metrc_runtime_composition.py")
    location_settings = _read("backend/app/routers/location_settings.py")

    # The original route still owns authentication, trusted mapping, employee identity,
    # and provider error handling. Composition only appends optional persistence after
    # a successful provider response.
    assert "result = original_metrc_permissions(" in composition
    assert 'if result.get("status") != "synced" or not result.get("can_introspect")' in composition
    assert "_trusted_metrc(context, engine, settings)" in location_settings
    assert '"employees/v2/permissions"' in location_settings
    assert '"provider_enforced"' in location_settings
