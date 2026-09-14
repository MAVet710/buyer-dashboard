"""Non-API workbook fields required for a complete Metrc evaluation submission."""

from __future__ import annotations

from services.metrc_evaluation_instruction_contract import (
    MA_PERMISSION_DEPENDENCIES,
    USER_KEY_POLICY,
    ma_instruction_contract,
)


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

# Keep the full list for submission form compatibility, but do not interpret it
# as meaning every family is dependent/required on every facility. The workbook's
# D/O matrix in MA_PERMISSION_DEPENDENCIES is authoritative for that distinction.
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
    instruction_contract = ma_instruction_contract()
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
            "dependencies_by_profile": {
                profile: {
                    "required": list(values["required"]),
                    "optional": list(values["optional"]),
                }
                for profile, values in MA_PERMISSION_DEPENDENCIES.items()
            },
            "verification": (
                "GET /facilities/v2 is authoritative for the actual facility and API User Key permissions returned by Metrc. "
                "A workbook D means dependent/required for that requested facility/profile; O means optional."
            ),
            "user_key_policy": dict(USER_KEY_POLICY),
        },
        "instruction_contract": instruction_contract,
    }
