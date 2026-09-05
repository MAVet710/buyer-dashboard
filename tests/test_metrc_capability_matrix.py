from services.metrc_capability_matrix import (
    RESOURCE_AVAILABLE,
    RESOURCE_DEGRADED,
    RESOURCE_FAILED,
    RESOURCE_NOT_AVAILABLE,
    RESOURCE_RESTRICTED,
    classify_metrc_resource_state,
    classify_metrc_resources,
    metrc_operator_summary,
    summarize_metrc_modules,
)


def _state(resource: str, status: str, *, cursor: str = "", error: str = "", provider_capability: str = "") -> dict:
    return {
        "resource": resource,
        "status": status,
        "cursor": cursor,
        "last_error": error,
        "provider_capability": provider_capability,
    }


def test_successful_resource_is_available_even_with_zero_records():
    result = classify_metrc_resource_state(
        _state("sales_receipts", "succeeded", cursor="initial-full"),
        authenticated_facility_access=True,
    )
    assert result.capability == RESOURCE_AVAILABLE
    assert result.operational_status == "healthy"
    assert result.retry_recommended is False


def test_permission_skipped_remains_conservatively_restricted_without_explicit_permission_metadata():
    result = classify_metrc_resource_state(
        _state("plants_vegetative", "succeeded", cursor="permission-skipped"),
        authenticated_facility_access=True,
    )
    assert result.capability == RESOURCE_RESTRICTED
    assert result.operational_status == "restricted"
    assert result.retry_recommended is False


def test_explicit_provider_capability_can_mark_license_unavailable():
    result = classify_metrc_resource_state(
        _state(
            "plants_vegetative",
            "succeeded",
            cursor="permission-skipped",
            provider_capability="not_available_for_license",
        ),
        authenticated_facility_access=True,
    )
    assert result.capability == RESOURCE_NOT_AVAILABLE
    assert result.operational_status == "healthy"
    assert result.retry_recommended is False


def test_resource_401_after_facility_auth_is_restricted_not_bad_global_credentials():
    result = classify_metrc_resource_state(
        _state(
            "plants_vegetative",
            "failed",
            error="Metrc rejected this resource request (HTTP 401). Verify the saved key pair and selected license permission.",
        ),
        authenticated_facility_access=True,
    )
    assert result.capability == RESOURCE_RESTRICTED
    assert result.operational_status == "restricted"
    assert result.retry_recommended is False


def test_resource_401_without_authenticated_facility_proof_remains_failure():
    result = classify_metrc_resource_state(
        _state("packages", "failed", error="HTTP 401 unauthorized"),
        authenticated_facility_access=False,
    )
    assert result.capability == RESOURCE_FAILED
    assert result.retry_recommended is True


def test_rate_limit_is_degraded_and_retryable():
    result = classify_metrc_resource_state(
        _state("packages", "failed", error="Metrc returned HTTP 429 rate limit"),
        authenticated_facility_access=True,
    )
    assert result.capability == RESOURCE_DEGRADED
    assert result.retry_recommended is True


def test_module_summary_allows_retail_without_cultivation_access():
    states = [
        _state("sales_receipts", "succeeded", cursor="initial-full"),
        _state("sales_deliveries", "succeeded", cursor="initial-full"),
        _state("packages", "succeeded", cursor="initial-full"),
        _state("plant_batches", "failed", error="HTTP 401 permission"),
        _state("plants_vegetative", "failed", error="HTTP 401 permission"),
        _state("plants_flowering", "failed", error="HTTP 401 permission"),
        _state("plant_tags", "failed", error="HTTP 401 permission"),
        _state("strains", "succeeded", cursor="initial-full"),
        _state("harvests", "failed", error="HTTP 401 permission"),
        _state("locations", "succeeded", cursor="initial-full"),
    ]
    capabilities = classify_metrc_resources(states, authenticated_facility_access=True)
    modules = summarize_metrc_modules(capabilities)
    by_module = {row["module"]: row for row in modules}

    assert by_module["sales"]["status"] == "available"
    # Cultivation is partially available because shared reference data such as
    # strains/locations may be readable even when plant lifecycle resources are not.
    assert by_module["cultivation"]["status"] == "available"
    summary = metrc_operator_summary(capabilities, modules)
    assert summary["actionable_failures"] == 0
    assert summary["restricted_resources"] >= 1
    assert summary["healthy"] is True
