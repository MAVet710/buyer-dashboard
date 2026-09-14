"""Regulator-authored Massachusetts Metrc evaluation rules from the 10.2025 workbook.

This module preserves the workbook's visible instructions without renumbering the
existing DoobieLogic evidence map. The regulator workbook contains 46 explicit
action rows plus a mandatory GET /facilities/v2 prerequisite, which DoobieLogic
tracks as internal check 1 for evidence continuity.
"""

from __future__ import annotations


REGULATOR_ACTION_COUNT = 46
PREREQUISITE_CHECK_COUNT = 1
INTERNAL_CHECK_COUNT = REGULATOR_ACTION_COUNT + PREREQUISITE_CHECK_COUNT

USER_KEY_POLICY = {
    "mode": "reuse_existing_only",
    "bootstrap_endpoint_allowed": False,
    "generate_user_key_allowed": False,
    "rotate_user_key_allowed": False,
    "replace_user_key_allowed": False,
    "rule": (
        "Evaluation reruns must reuse the already-active MA sandbox API User Key. "
        "Do not call /sandbox/v2/integrator/setup, provision a new user key, rotate, "
        "or replace the stored user key during an evaluation rerun."
    ),
}

WORKBOOK_EXECUTION_RULES = (
    "Run GET /facilities/v2 first for the API User Key and use the returned facility permissions as provider truth.",
    "All actions must return HTTP 200 and be verifiable before submission.",
    "A permission-disabled action typically returns HTTP 401 Unauthorized.",
    "All sections marked D on the Permissions sheet must be completed for the requested facility/profile; O means optional.",
    "Do not run all task families against one global facility license. Use the facility/profile appropriate to the action and verify it in the fresh facilities response before the action.",
    "Only modify data in facilities Metrc directs you to and data you created; do not delete data you did not create.",
    "As each action is completed, populate the workbook verification fields with the requested provider evidence.",
    "Minify request JSON or provider response evidence when placing it into a workbook cell.",
    "Open-loop Massachusetts uses the Closed Loop Environment sheet as setup/context for beginning inventory directions.",
    "Date parameters are required for the opening-inventory calls described on the Closed Loop Environment sheet; contact API support if a date range is needed.",
)

# D = dependent/required for that permission profile. O = optional.
MA_PERMISSION_DEPENDENCIES = {
    "grow": {
        "required": (
            "Locations",
            "Strains",
            "Plant Batches / Plants",
            "Harvests",
            "Items",
            "Packages",
            "GET Transfers / Wholesale",
        ),
        "optional": ("Transfer Template / External Incoming",),
    },
    "processor": {
        "required": (
            "Strains",
            "Items",
            "Packages",
            "GET Transfers / Wholesale",
        ),
        "optional": ("Transfer Template / External Incoming",),
    },
    "labs": {
        "required": (
            "Strains",
            "Packages",
            "Labs",
            "GET Transfers / Wholesale",
        ),
        "optional": (
            "Items",
            "Transfer Template / External Incoming",
        ),
    },
    "sales": {
        "required": (
            "Strains",
            "Items",
            "Packages",
            "Sales",
            "Sales Deliveries",
            "GET Transfers / Wholesale",
        ),
        "optional": ("Transfer Template / External Incoming",),
    },
}

# The action sheets are executed against different sandbox facility permission
# profiles. Keeping this explicit prevents a valid Grow license from being used
# for Lab or Sales calls (a common cause of permission-specific HTTP 401s).
GROW_OPERATIONS = frozenset({
    "location_create", "location_update", "location_get",
    "strain_create", "strain_update", "strain_get",
    "item_create", "item_update", "item_get",
    "plant_batch_plantings", "plant_batch_packages", "plant_batch_growthphase", "plant_batch_delete",
    "plant_location", "plant_plantings", "plant_plantbatch_packages", "plant_delete", "plant_manicure", "plant_harvest",
    "harvest_packages", "harvest_waste", "harvest_finish", "harvest_unfinish",
    "package_create", "package_item", "package_adjust", "package_finish", "package_unfinish",
})
LAB_OPERATIONS = frozenset({"lab_test_record"})
SALES_OPERATIONS = frozenset({
    "sales_receipt_create", "sales_receipt_update", "sales_receipt_delete",
    "sales_delivery_create", "sales_delivery_update", "sales_delivery_complete",
})
TRANSFER_OPERATIONS = frozenset({
    "transfer_incoming", "transfer_outgoing", "transfer_rejected", "transfer_deliveries",
    "transfer_delivery_packages", "transfer_delivery_packages_wholesale",
    "transfer_template_create", "transfer_template_list", "transfer_template_deliveries", "transfer_template_update",
})

OPERATION_PROFILE_CAPABILITIES = {
    "grow": ("CanGrowPlants",),
    "labs": ("CanTestPackages",),
    "sales_receipt": ("CanSellToConsumers", "CanSellToPatients", "CanSellToCaregivers"),
    "sales_delivery": ("CanDeliverSalesToConsumers", "CanDeliverSalesToPatients"),
}

TASK_SPECIFIC_RULES = {
    "lab_test_record": (
        "Use an existing package in the Lab for the lab-result task. If no eligible lab package exists, contact API support rather than fabricating provider state."
    ),
    "plant_harvest": (
        "Plants may join the same harvest only when the harvest name matches exactly and the action occurs on the same calendar day."
    ),
    "harvest_waste": "Moisture loss is not recorded as harvest waste.",
    "sales_delivery_create": (
        "Use a provider-valid SalesCustomerType (Patient or Consumer as applicable) and create the delivery with exactly three transactions before the workbook update/completion steps."
    ),
}


def operation_facility_profile(operation: str) -> str:
    selected = str(operation or "").strip().casefold()
    if selected in GROW_OPERATIONS:
        return "grow"
    if selected in LAB_OPERATIONS:
        return "labs"
    if selected in SALES_OPERATIONS:
        return "sales"
    if selected in TRANSFER_OPERATIONS:
        return "transfers"
    if selected == "facilities":
        return "prerequisite"
    if selected == "workbook_plan":
        return "context"
    return "unknown"


def operation_required_capabilities(operation: str) -> tuple[str, ...]:
    selected = str(operation or "").strip().casefold()
    profile = operation_facility_profile(selected)
    if profile == "grow":
        return OPERATION_PROFILE_CAPABILITIES["grow"]
    if profile == "labs":
        return OPERATION_PROFILE_CAPABILITIES["labs"]
    if selected.startswith("sales_receipt_"):
        return OPERATION_PROFILE_CAPABILITIES["sales_receipt"]
    if selected.startswith("sales_delivery_"):
        return OPERATION_PROFILE_CAPABILITIES["sales_delivery"]
    return ()


def ma_instruction_contract() -> dict[str, object]:
    return {
        "regulator_action_count": REGULATOR_ACTION_COUNT,
        "prerequisite_check_count": PREREQUISITE_CHECK_COUNT,
        "internal_check_count": INTERNAL_CHECK_COUNT,
        "user_key_policy": dict(USER_KEY_POLICY),
        "execution_rules": list(WORKBOOK_EXECUTION_RULES),
        "permission_dependencies": {
            profile: {
                "required": list(values["required"]),
                "optional": list(values["optional"]),
            }
            for profile, values in MA_PERMISSION_DEPENDENCIES.items()
        },
        "operation_profiles": {
            "grow": sorted(GROW_OPERATIONS),
            "labs": sorted(LAB_OPERATIONS),
            "sales": sorted(SALES_OPERATIONS),
            "transfers": sorted(TRANSFER_OPERATIONS),
        },
        "task_specific_rules": dict(TASK_SPECIFIC_RULES),
        "permission_semantics": {
            "D": "required per facility/profile requested",
            "O": "optional",
            "dependent_rule": "When requesting access, complete all dependent required permissions for that facility/profile.",
            "user_key_snapshot_rule": (
                "The API User Key carries the facility/permission access held by the Metrc user at the time the key was generated."
            ),
            "sandbox_vendor_rule": "The sandbox Vendor Key should have full permissions.",
        },
    }
