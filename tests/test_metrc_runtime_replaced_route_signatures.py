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


def test_runtime_replaced_sandbox_routes_preserve_fastapi_dependency_contracts():
    _run_clean_startup_assertions(
        r'''
from backend.app.main import app


def route_for(suffix: str, method: str):
    return next(
        route for route in app.routes
        if str(getattr(route, "path", "")).endswith(suffix)
        and method in (getattr(route, "methods", None) or set())
        and getattr(route, "dependant", None) is not None
    )


def request_field_names(route) -> set[str]:
    return {
        field.name
        for field in (
            list(route.dependant.path_params)
            + list(route.dependant.query_params)
            + list(route.dependant.header_params)
            + list(route.dependant.cookie_params)
            + list(route.dependant.body_params)
        )
    }

routes = (
    route_for("/integrations/sandbox/{provider}/runtime", "GET"),
    route_for("/integrations/sandbox/{provider}/sync", "POST"),
    route_for("/integrations/sandbox/{provider}/retry", "POST"),
)
for route in routes:
    names = request_field_names(route)
    assert names.isdisjoint({"context", "engine", "settings"}), (route.path, names)
    dependency_names = {
        getattr(dependency.call, "__name__", "")
        for dependency in route.dependant.dependencies
    }
    assert {"get_request_context", "get_engine", "get_settings"}.issubset(dependency_names), (route.path, dependency_names)

sync_route = routes[1]
assert "payload" in {field.name for field in sync_route.dependant.body_params}
assert "payload" not in {field.name for field in sync_route.dependant.query_params}
'''
    )


def test_runtime_replaced_sandbox_openapi_keeps_sync_payload_in_request_body():
    _run_clean_startup_assertions(
        r'''
from backend.app.main import app

schema = app.openapi()
paths = schema["paths"]
sync_path = next(
    path for path in paths
    if path.endswith("/integrations/sandbox/{provider}/sync")
)
operation = paths[sync_path]["post"]
parameter_names = {str(parameter.get("name") or "") for parameter in operation.get("parameters", [])}
assert parameter_names.isdisjoint({"context", "engine", "settings", "payload"}), parameter_names
assert "requestBody" in operation
'''
    )
