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
from fastapi.routing import APIRoute
from backend.app.main import app

route = next(
    route for route in app.routes
    if isinstance(route, APIRoute)
    and route.path.endswith("/location-settings/facility-setup")
)
request_field_names = {
    field.name
    for field in (
        list(route.dependant.path_params)
        + list(route.dependant.query_params)
        + list(route.dependant.header_params)
        + list(route.dependant.cookie_params)
        + list(route.dependant.body_params)
    )
}
assert request_field_names.isdisjoint({"context", "engine", "settings"}), request_field_names
dependency_names = {
    getattr(dependency.call, "__name__", "")
    for dependency in route.dependant.dependencies
}
assert {"get_request_context", "get_engine", "get_settings"}.issubset(dependency_names), dependency_names
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
