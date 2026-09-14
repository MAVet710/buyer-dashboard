"""Non-API workbook fields required for a complete Metrc evaluation submission."""

from __future__ import annotations


COMPANY_INFORMATION_REQUIRED_FIELDS = (
    "Integrator Company Name",
    "Company Web Site",
    "Company Telephone Number",
    "Company Email Contact",
    "Company Address",
    "Company City and State",
    "Company Zip Code",
    "Primary Contact Name",
    "Primary Contact Email",
    "Primary Contact Telephone Number",
    "Name of Vendor Software you are developing",
    "Vendor Key Used",
    "User Key Used",
)

COMPANY_INFORMATION_OPTIONAL_FIELDS = (
    "Secondary Contact Name",
    "Secondary Contact Email",
    "Secondary Contact Telephone Number",
)

# The workbook's Permissions page asks which access families are being sought.
# DoobieLogic's full vertical MA evaluation requires the supported families below;
# actual state/facility grants are still proven by GET /facilities/v2 and never
# inferred from these requested labels.
MA_FULL_PERMISSION_REQUEST = (
    "Locations",
    "Strains",
    "Plant Batches / Plants",
    "Harvests",
    "Items",
    "Packages",
    "Sales",
    "Sales Deliveries",
    "Labs",
    "GET Transfers / Wholesale",
    "Transfer Template / External Incoming",
)

SECRET_WORKBOOK_FIELDS = ("Vendor Key Used", "User Key Used")

# Rules transcribed from the actual Generic Evaluation 10.2025 workbook.
# They are submission/evaluation policy, not inferred provider behavior.
MA_WORKBOOK_INSTRUCTIONS = {
    "facility_scope": (
        "All sections marked with a 'D' must be completed per facility, and all dependent permissions must be completed when requesting access."
    ),
    "permission_layers": (
        "Facility permissions are set by the state; the Vendor Key should have full sandbox permissions; the API User Key inherits the permissions of the Metrc user at the time the key is generated."
    ),
    "user_key_reuse": (
        "Evaluation reruns must reuse the existing active API User Key. Do not call sandbox integrator setup, generate a replacement user key, rotate the key, or overwrite the saved credential unless the operator explicitly starts a separate provisioning action."
    ),
    "http_401": (
        "The workbook states that an action whose permission is not enabled will typically return HTTP 401 Unauthorized. Treat a scoped 401 as a permission/facility investigation signal, not automatic proof that the credential itself is invalid."
    ),
    "http_200": (
        "All applicable evaluation actions must return HTTP 200 and be verifiable before submission."
    ),
    "data_safety": (
        "GET access may inspect sandbox data, but modify only data in facilities Metrc directs the integrator to use and data created by the integrator. Do not delete provider data the integrator did not create."
    ),
    "open_loop_context": (
        "Massachusetts is an open-loop state and the workbook directs evaluators to the Closed Loop Environment sheet for starting-inventory guidance. That sheet is evaluation context for MA even though the Closed Loop States PlantBatches task sheet is not applicable."
    ),
}


def ma_submission_context() -> dict[str, object]:
    return {
        "company_information": {
            "required_fields": list(COMPANY_INFORMATION_REQUIRED_FIELDS),
            "optional_fields": list(COMPANY_INFORMATION_OPTIONAL_FIELDS),
            "secret_fields": list(SECRET_WORKBOOK_FIELDS),
            "rule": (
                "Required company/contact fields must be completed for submission. Vendor/User key cells belong only in the local submission workbook; credentials must never be committed to GitHub or copied into normal evidence JSON."
            ),
        },
        "permissions": {
            "requested_families_for_full_ma_evaluation": list(MA_FULL_PERMISSION_REQUEST),
            "verification": "GET /facilities/v2 is authoritative for the actual facility and user permissions returned by Metrc.",
            "per_facility_rule": MA_WORKBOOK_INSTRUCTIONS["facility_scope"],
            "permission_layers": MA_WORKBOOK_INSTRUCTIONS["permission_layers"],
            "http_401_rule": MA_WORKBOOK_INSTRUCTIONS["http_401"],
        },
        "rerun": {
            "existing_user_key_only": True,
            "bootstrap_allowed": False,
            "rule": MA_WORKBOOK_INSTRUCTIONS["user_key_reuse"],
        },
        "workbook_instructions": dict(MA_WORKBOOK_INSTRUCTIONS),
    }
