"""Massachusetts coverage map for Generic_Evaluation_for_All_States_MASTER 10.2025.

The source workbook contains 22 worksheets. Massachusetts uses the open-loop
cultivation, labs, sales, sales-deliveries, transfer/wholesale, and transfer-
template action sheets. The workbook also directs MA open-loop evaluators to the
Closed Loop Environment sheet for beginning-inventory setup guidance.

For evidence continuity DoobieLogic keeps 47 internal check numbers: check 1 is
the mandatory GET /facilities/v2 prerequisite from the Instructions sheet, while
checks 2-47 correspond to the workbook's 46 explicit regulator action rows.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from services.metrc_evaluation_instruction_contract import (
    INTERNAL_CHECK_COUNT,
    PREREQUISITE_CHECK_COUNT,
    REGULATOR_ACTION_COUNT,
    TASK_SPECIFIC_RULES,
)


@dataclass(frozen=True)
class WorkbookTask:
    number: int
    sheet: str
    step: str
    description: str
    workbook_endpoint: str
    current_endpoint: str
    operation_type: str
    execution_kind: str
    note: str = ""


# These names intentionally preserve the regulator template's exact worksheet
# titles, including the trailing spaces on Instructions and Closed Loop Environment.
WORKBOOK_SHEETS = (
    "CompanyInformation",
    "Instructions ",
    "Permissions",
    "States",
    "Locations",
    "Strains",
    "Items",
    "Closed Loop Environment ",
    "Closed Loop States PlantBatches",
    "PlantBatches",
    "Plants",
    "Harvest",
    "Packages",
    "CA ONLY Labs",
    "LabResults",
    "Sales",
    "Sales with Patient Look Up",
    "Sales Deliveries (NOT CA)",
    "CA- SalesRetailDeliveries",
    "GET Transfers and Wholesale",
    "Transfer Templates",
    "Transfer External Incoming",
)

# Instructions and Closed Loop Environment are required MA context/setup sheets,
# not regulator action sheets. Closed Loop States PlantBatches remains N/A for MA.
MA_CONTEXT_SHEETS = (
    "CompanyInformation",
    "Instructions",
    "Permissions",
    "States",
    "Closed Loop Environment",
)
MA_NA_SHEETS = (
    "Closed Loop States PlantBatches",
    "CA ONLY Labs",
    "Sales with Patient Look Up",
    "CA- SalesRetailDeliveries",
    "Transfer External Incoming",
)
MA_APPLICABLE_TASK_SHEETS = (
    "Locations",
    "Strains",
    "Items",
    "PlantBatches",
    "Plants",
    "Harvest",
    "Packages",
    "LabResults",
    "Sales",
    "Sales Deliveries (NOT CA)",
    "GET Transfers and Wholesale",
    "Transfer Templates",
)


def _task(
    number: int,
    sheet: str,
    step: str,
    description: str,
    workbook_endpoint: str,
    current_endpoint: str,
    operation_type: str,
    execution_kind: str,
    note: str = "",
) -> WorkbookTask:
    return WorkbookTask(number, sheet, step, description, workbook_endpoint, current_endpoint, operation_type, execution_kind, note)


MA_WORKBOOK_TASKS = (
    _task(1, "Instructions", "Facilities", "Discover the sandbox facilities and permissions first.", "GET /facilities/v2/", "GET /facilities/v2/", "facilities", "read", "Mandatory prerequisite from the Instructions sheet; not one of the workbook's 46 explicit action rows."),
    _task(2, "Locations", "Step 1", "Create a location.", "POST /locations/v2/", "POST /locations/v2/", "location_create", "master_write"),
    _task(3, "Locations", "Step 2", "Update the created location.", "PUT /locations/v2/", "PUT /locations/v2/", "location_update", "master_write"),
    _task(4, "Locations", "Step 3", "Read the created location by ID.", "GET /locations/v2/{id}", "GET /locations/v2/{id}", "location_get", "exact_read"),
    _task(5, "Strains", "Step 1", "Create a strain.", "POST /strains/v2/", "POST /strains/v2/", "strain_create", "master_write"),
    _task(6, "Strains", "Step 2", "Update the created strain.", "PUT /strains/v2/", "PUT /strains/v2/", "strain_update", "master_write"),
    _task(7, "Strains", "Step 3", "Read the created strain by ID.", "GET /strains/v2/{id}", "GET /strains/v2/{id}", "strain_get", "exact_read"),
    _task(8, "Items", "Step 1", "Create an item.", "POST /Items/v2/", "POST /items/v2/", "item_create", "master_write"),
    _task(9, "Items", "Step 2", "Update the created item.", "PUT /Items/v2/", "PUT /items/v2/", "item_update", "master_write"),
    _task(10, "Items", "Step 3", "Read the created item by ID.", "GET /Items/v2/{id}", "GET /items/v2/{id}", "item_get", "exact_read"),
    _task(11, "PlantBatches", "Step 1", "Create an immature plant batch with six plants.", "POST /plantbatches/v2/plantings", "POST /plantbatches/v2/plantings", "plant_batch_plantings", "lifecycle_write"),
    _task(12, "PlantBatches", "Step 2", "Create a package from three clones in the batch.", "POST /plantbatches/v2/packages", "POST /plantbatches/v2/packages", "plant_batch_packages", "lifecycle_write"),
    _task(13, "PlantBatches", "Step 3", "Move two plants to growth phase using individual tags.", "POST /plantbatches/v2/growthphase", "POST /plantbatches/v2/growthphase", "plant_batch_growthphase", "lifecycle_write"),
    _task(14, "PlantBatches", "Step 4", "Destroy/delete one plant from the created batch.", "DELETE /plantbatches/v2/", "DELETE /plantbatches/v2/", "plant_batch_delete", "lifecycle_write"),
    _task(15, "Plants", "Step 1", "Move one plant to another location.", "PUT /plants/v2/location", "PUT /plants/v2/location", "plant_location", "lifecycle_write"),
    _task(16, "Plants", "Step 2", "Create an immature batch from a plant.", "POST /plants/v2/plantings", "POST /plants/v2/plantings", "plant_plantings", "lifecycle_write", "MA is open-loop and the Closed Loop Environment sheet supplies beginning-inventory guidance; date parameters are required for opening-inventory calls."),
    _task(17, "Plants", "Step 3", "Create a plant-batch package from a plant.", "POST /plants/v2/plantbatch/packages", "POST /plants/v2/plantbatch/packages", "plant_plantbatch_packages", "lifecycle_write", "Do not send unless the selected facility's fresh provider capability permits the operation. The workbook notes permission-disabled actions typically return HTTP 401."),
    _task(18, "Plants", "Step 4", "Destroy/delete one plant created for evaluation.", "DELETE /plants/v2/", "DELETE /plants/v2/", "plant_delete", "lifecycle_write"),
    _task(19, "Plants", "Step 5", "Record a manicure from a plant.", "POST /plants/v2/manicure", "POST /plants/v2/manicure", "plant_manicure", "lifecycle_write"),
    _task(20, "Plants", "Step 6", "Harvest the remaining evaluation plants.", "PUT /plants/v2/harvest", "PUT /plants/v2/harvest", "plant_harvest", "lifecycle_write", TASK_SPECIFIC_RULES["plant_harvest"]),
    _task(21, "Harvest", "Step 1", "Create a package from the harvest.", "POST /harvests/v2/packages", "POST /harvests/v2/packages", "harvest_packages", "lifecycle_write"),
    _task(22, "Harvest", "Step 2", "Record harvest waste.", "POST /harvests/v2/waste", "POST /harvests/v2/waste", "harvest_waste", "lifecycle_write", TASK_SPECIFIC_RULES["harvest_waste"]),
    _task(23, "Harvest", "Step 3", "Finish the evaluation harvest.", "PUT /harvests/v2/finish", "PUT /harvests/v2/finish", "harvest_finish", "lifecycle_write"),
    _task(24, "Harvest", "Step 4", "Unfinish the evaluation harvest.", "PUT /harvests/v2/unfinish", "PUT /harvests/v2/unfinish", "harvest_unfinish", "lifecycle_write"),
    _task(25, "Packages", "Step 1", "Create a package.", "POST /packages/v2/", "POST /packages/v2/", "package_create", "lifecycle_write"),
    _task(26, "Packages", "Step 2", "Change the package item.", "PUT /packages/v2/item", "PUT /packages/v2/item", "package_item", "lifecycle_write"),
    _task(27, "Packages", "Step 3", "Adjust package quantity as directed by the workbook.", "PUT /packages/v2/adjust", "PUT /packages/v2/adjust", "package_adjust", "lifecycle_write", "Do not reduce a package needed by later sales tasks until those sales tasks are complete."),
    _task(28, "Packages", "Step 4", "Finish the evaluation package.", "PUT /packages/v2/finish", "PUT /packages/v2/finish", "package_finish", "lifecycle_write"),
    _task(29, "Packages", "Step 5", "Unfinish the evaluation package.", "PUT /packages/v2/unfinish", "PUT /packages/v2/unfinish", "package_unfinish", "lifecycle_write"),
    _task(30, "LabResults", "Step 1", "Record lab-test results against an existing lab package.", "POST /labtests/v2/record", "POST /labtests/v2/record", "lab_test_record", "lab_write", TASK_SPECIFIC_RULES["lab_test_record"]),
    _task(31, "Sales", "Step 1", "Create a sales receipt.", "POST /sales/v2/receipts", "POST /sales/v2/receipts", "sales_receipt_create", "sales_write"),
    _task(32, "Sales", "Step 2", "Update the created sales receipt.", "PUT /sales/v2/receipts", "PUT /sales/v2/receipts", "sales_receipt_update", "sales_write"),
    _task(33, "Sales", "Step 3", "Delete the created sales receipt.", "DELETE /sales/v2/receipts/{id}", "DELETE /sales/v2/receipts/{id}", "sales_receipt_delete", "sales_write"),
    _task(34, "Sales Deliveries (NOT CA)", "Step 1", "Create a home delivery with three transactions.", "POST /sales/v2/deliveries", "POST /sales/v2/deliveries", "sales_delivery_create", "sales_write", TASK_SPECIFIC_RULES["sales_delivery_create"]),
    _task(35, "Sales Deliveries (NOT CA)", "Step 2", "Update the delivery to remove one transaction.", "PUT /sales/v2/deliveries/complete", "PUT /sales/v2/deliveries", "sales_delivery_update", "sales_write", "The workbook task line says /complete, but its Metrc Use Only row identifies the update endpoint as PUT /sales/v2/deliveries."),
    _task(36, "Sales Deliveries (NOT CA)", "Step 3", "Complete the delivery with accepted and returned package evidence.", "PUT /sales/v2/deliveries/complete", "PUT /sales/v2/deliveries/complete", "sales_delivery_complete", "sales_write"),
    _task(37, "GET Transfers and Wholesale", "Step 1", "Find incoming transfers in the requested LastModified window.", "GET /transfers/v2/incoming", "GET /transfers/v2/incoming", "transfer_incoming", "transfer_read"),
    _task(38, "GET Transfers and Wholesale", "Step 2", "Find outgoing transfers in the requested LastModified window.", "GET /transfers/v2/outgoing", "GET /transfers/v2/outgoing", "transfer_outgoing", "transfer_read"),
    _task(39, "GET Transfers and Wholesale", "Step 3", "Find rejected transfers.", "GET /transfers/v2/rejected", "GET /transfers/v2/rejected", "transfer_rejected", "transfer_read"),
    _task(40, "GET Transfers and Wholesale", "Step 4", "Find transfer deliveries by manifest/transfer ID.", "GET /transfers/v2/{id}/deliveries", "GET /transfers/v2/{id}/deliveries", "transfer_deliveries", "transfer_read"),
    _task(41, "GET Transfers and Wholesale", "Step 5", "Find packages by delivery ID.", "GET /transfers/v2/delivery/{id}/packages", "GET /transfers/v2/deliveries/{id}/packages", "transfer_delivery_packages", "transfer_read", "Workbook uses legacy singular delivery; current reviewed v2 path uses /deliveries/{id}/packages."),
    _task(42, "GET Transfers and Wholesale", "Step 6", "Find wholesale package pricing by delivery ID.", "GET /transfers/v2/delivery/{id}/packages/wholesale", "GET /transfers/v2/deliveries/{id}/packages/wholesale", "transfer_delivery_packages_wholesale", "transfer_read", "Workbook uses legacy singular delivery; current reviewed v2 path uses /deliveries/{id}/packages/wholesale."),
    _task(43, "Transfer Templates", "Step 1a", "Create outgoing Template A.", "POST /transfers/v2/templates/outgoing", "POST /transfers/v2/templates/outgoing", "transfer_template_create", "transfer_template_write"),
    _task(44, "Transfer Templates", "Step 1b", "Create outgoing Template B.", "POST /transfers/v2/templates/outgoing", "POST /transfers/v2/templates/outgoing", "transfer_template_create", "transfer_template_write"),
    _task(45, "Transfer Templates", "Step 2", "Find both created templates using a date search.", "GET /transfers/v2/templates", "GET /transfers/v2/templates/outgoing", "transfer_template_list", "transfer_read", "Workbook contains an incomplete 'GE' task line and a legacy Metrc Use Only path; current reviewed v2 list endpoint is /templates/outgoing."),
    _task(46, "Transfer Templates", "Step 3", "Find a template's deliveries by template ID.", "GET /transfers/v2/templates/{id}/deliveries", "GET /transfers/v2/templates/outgoing/{id}/deliveries", "transfer_template_deliveries", "transfer_read", "Current reviewed v2 path includes /outgoing before the template ID."),
    _task(47, "Transfer Templates", "Step 4", "Update one of the templates created in Step 1.", "PUT /transfers/v2/templates/outgoing", "PUT /transfers/v2/templates/outgoing", "transfer_template_update", "transfer_template_write"),
)

MA_PREREQUISITE_CHECKS = MA_WORKBOOK_TASKS[:PREREQUISITE_CHECK_COUNT]
MA_REGULATOR_ACTION_TASKS = MA_WORKBOOK_TASKS[PREREQUISITE_CHECK_COUNT:]


def ma_workbook_plan() -> dict[str, object]:
    if len(WORKBOOK_SHEETS) != 22 or len(MA_WORKBOOK_TASKS) != INTERNAL_CHECK_COUNT:
        raise RuntimeError("The MA Metrc workbook coverage map is incomplete.")
    if len(MA_PREREQUISITE_CHECKS) != PREREQUISITE_CHECK_COUNT or len(MA_REGULATOR_ACTION_TASKS) != REGULATOR_ACTION_COUNT:
        raise RuntimeError("The MA Metrc prerequisite/action split does not match the regulator workbook.")

    sheet_status = []
    for sheet in WORKBOOK_SHEETS:
        logical_sheet = sheet.rstrip()
        if logical_sheet in MA_NA_SHEETS:
            status = "not_applicable_ma"
        elif logical_sheet in MA_CONTEXT_SHEETS:
            status = "context"
        else:
            status = "applicable"
        sheet_status.append({"sheet": sheet, "status": status})

    return {
        "workbook": "Generic_Evaluation_for_All_States_MASTER 10.2025",
        "state": "MA",
        "sheet_count": len(WORKBOOK_SHEETS),
        "applicable_task_count": REGULATOR_ACTION_COUNT,
        "regulator_action_count": REGULATOR_ACTION_COUNT,
        "prerequisite_check_count": PREREQUISITE_CHECK_COUNT,
        "internal_check_count": INTERNAL_CHECK_COUNT,
        "task_numbering_note": (
            "DoobieLogic internal check 1 is the mandatory GET /facilities/v2 prerequisite; internal checks 2-47 map to the workbook's 46 explicit action rows."
        ),
        "applicable_task_sheets": list(MA_APPLICABLE_TASK_SHEETS),
        "context_sheets": list(MA_CONTEXT_SHEETS),
        "not_applicable_sheets": list(MA_NA_SHEETS),
        "sheets": sheet_status,
        "prerequisite_checks": [asdict(task) for task in MA_PREREQUISITE_CHECKS],
        "regulator_actions": [asdict(task) for task in MA_REGULATOR_ACTION_TASKS],
        "tasks": [asdict(task) for task in MA_WORKBOOK_TASKS],
        "pass_rule": (
            "Every regulator action must return HTTP 200 and be verifiable from exact provider evidence/readback, and the mandatory facilities/permissions prerequisite must also pass."
        ),
    }
