from __future__ import annotations

from fastapi.routing import APIRoute

from backend.app.main import app


def _facility_setup_route() -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.endswith("/location-settings/facility-setup"):
            return route
    raise AssertionError("Facility Setup route is not registered on the FastAPI app.")


def test_metrc_runtime_facility_setup_wrapper_preserves_fastapi_dependencies():
    route = _facility_setup_route()

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
    assert request_field_names.isdisjoint({"context", "engine", "settings"})

    dependency_names = {
        getattr(dependency.call, "__name__", "")
        for dependency in route.dependant.dependencies
    }
    assert {"get_request_context", "get_engine", "get_settings"}.issubset(dependency_names)


def test_facility_setup_openapi_does_not_expose_internal_dependencies_as_request_fields():
    schema = app.openapi()
    path = next(
        path
        for path in schema["paths"]
        if path.endswith("/location-settings/facility-setup")
    )
    parameters = schema["paths"][path]["get"].get("parameters", [])
    parameter_names = {str(parameter.get("name") or "") for parameter in parameters}
    assert parameter_names.isdisjoint({"context", "engine", "settings"})
