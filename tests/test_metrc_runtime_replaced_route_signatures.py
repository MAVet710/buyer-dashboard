from __future__ import annotations

from fastapi.routing import APIRoute

from backend.app.main import app


def _route(suffix: str, method: str) -> APIRoute:
    for route in app.routes:
        if (
            isinstance(route, APIRoute)
            and route.path.endswith(suffix)
            and method in (route.methods or set())
        ):
            return route
    raise AssertionError(f"Expected {method} route ending in {suffix!r}.")


def _request_field_names(route: APIRoute) -> set[str]:
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


def test_runtime_replaced_sandbox_routes_preserve_fastapi_dependency_contracts():
    routes = (
        _route("/integrations/sandbox/{provider}/runtime", "GET"),
        _route("/integrations/sandbox/{provider}/sync", "POST"),
        _route("/integrations/sandbox/{provider}/retry", "POST"),
    )
    for route in routes:
        names = _request_field_names(route)
        assert names.isdisjoint({"context", "engine", "settings"})
        dependency_names = {
            getattr(dependency.call, "__name__", "")
            for dependency in route.dependant.dependencies
        }
        assert {"get_request_context", "get_engine", "get_settings"}.issubset(dependency_names)

    sync_route = routes[1]
    assert "payload" in {field.name for field in sync_route.dependant.body_params}
    assert "payload" not in {field.name for field in sync_route.dependant.query_params}


def test_runtime_replaced_sandbox_openapi_keeps_sync_payload_in_request_body():
    schema = app.openapi()
    paths = schema["paths"]
    sync_path = next(
        path
        for path in paths
        if path.endswith("/integrations/sandbox/{provider}/sync")
    )
    operation = paths[sync_path]["post"]
    parameter_names = {str(parameter.get("name") or "") for parameter in operation.get("parameters", [])}
    assert parameter_names.isdisjoint({"context", "engine", "settings", "payload"})
    assert "requestBody" in operation
