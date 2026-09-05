from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _run_clean_startup_assertions(source: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_metrc_runtime_facility_setup_wrapper_preserves_fastapi_dependencies():
    _run_clean_startup_assertions(
        r'''
import importlib
import inspect
from fastapi.params import Depends
from backend.app.main import app  # noqa: F401 - imports the real composed production graph

location_settings = importlib.import_module("backend.app.routers.location_settings")
signature = inspect.signature(location_settings.facility_setup_overview)
for name in ("context", "engine", "settings"):
    parameter = signature.parameters[name]
    assert isinstance(parameter.default, Depends), (name, parameter.default, signature)
'''
    )


def test_facility_setup_openapi_does_not_expose_internal_dependencies_as_request_fields():
    _run_clean_startup_assertions(
        r'''
from backend.app.main import app

schema = app.openapi()
path = next(
    path for path in schema["paths"]
    if path.endswith("/location-settings/facility-setup")
)
parameters = schema["paths"][path]["get"].get("parameters", [])
parameter_names = {str(parameter.get("name") or "") for parameter in parameters}
assert parameter_names.isdisjoint({"context", "engine", "settings"}), parameter_names
'''
    )
