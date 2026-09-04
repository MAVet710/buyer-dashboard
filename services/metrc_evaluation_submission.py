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
        },
    }
