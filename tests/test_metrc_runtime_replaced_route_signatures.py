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
import importlib
import inspect
from fastapi.params import Depends
from backend.app.main import app  # noqa: F401 - imports the real composed production graph

sandbox_integrations = importlib.import_module("backend.app.routers.sandbox_integrations")
functions = (
    sandbox_integrations.sandbox_runtime_status,
    sandbox_integrations.run_sandbox_sync,
    sandbox_integrations.retry_sandbox_sync,
)
for function in functions:
    signature = inspect.signature(function)
    for name in ("context", "engine", "settings"):
        parameter = signature.parameters[name]
        assert isinstance(parameter.default, Depends), (
            function.__name__, name, parameter.default, signature
        )

sync_signature = inspect.signature(sandbox_integrations.run_sandbox_sync)
assert "payload" in sync_signature.parameters, sync_signature
assert sync_signature.parameters["payload"].default is inspect.Parameter.empty
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
