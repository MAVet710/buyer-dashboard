from __future__ import annotations

from services.metrc_evaluation_workbook import WORKBOOK_SHEETS, ma_workbook_plan


EXPECTED_REGULATOR_SHEETS = (
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


def test_regulator_workbook_sheet_titles_preserve_exact_whitespace():
    assert WORKBOOK_SHEETS == EXPECTED_REGULATOR_SHEETS
    assert WORKBOOK_SHEETS[1] == "Instructions "
    assert WORKBOOK_SHEETS[7] == "Closed Loop Environment "


def test_ma_plan_classifies_exact_template_titles_by_logical_sheet_name():
    plan = ma_workbook_plan()
    statuses = {row["sheet"]: row["status"] for row in plan["sheets"]}

    # The direct regulator workbook audit established both as MA context/setup:
    # Instructions contains the mandatory facilities prerequisite and the MA
    # States row sends Open Loop evaluators to Closed Loop Environment for
    # beginning-inventory directions. Neither is a scored action sheet.
    assert statuses["Instructions "] == "context"
    assert statuses["Closed Loop Environment "] == "context"
    assert statuses["Closed Loop States PlantBatches"] == "not_applicable_ma"
