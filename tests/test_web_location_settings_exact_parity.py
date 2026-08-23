from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_location_settings_preserve_streamlit_facility_scoped_receive_controls():
    source = read("modules/location_settings.py")
    web = read("frontend/src/pages/LocationSettingsPage.tsx")
    backend = read("backend/app/routers/location_settings.py")

    for label in (
        "DATA & SETTINGS / LOCATION",
        "Location settings",
        "Inventory receiving",
        "Auto-map products during receive",
        "Default receiving room",
        "Save location settings",
        "Auto-map never guesses a new catalog relationship.",
    ):
        assert label in source
        assert label in web
    assert "previously reviewed" in source
    assert "previously reviewed" in web
    assert "context.organization_id" in backend
    assert "context.facility_id" in backend
