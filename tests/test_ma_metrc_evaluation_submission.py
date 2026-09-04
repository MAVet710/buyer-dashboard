from services.metrc_evaluation_submission import (
    COMPANY_INFORMATION_REQUIRED_FIELDS,
    MA_FULL_PERMISSION_REQUEST,
    SECRET_WORKBOOK_FIELDS,
    ma_submission_context,
)


def test_company_information_context_includes_required_submission_fields_without_secret_values():
    context = ma_submission_context()
    company = context["company_information"]
    assert "Integrator Company Name" in COMPANY_INFORMATION_REQUIRED_FIELDS
    assert "Name of Vendor Software you are developing" in COMPANY_INFORMATION_REQUIRED_FIELDS
    assert set(SECRET_WORKBOOK_FIELDS) == {"Vendor Key Used", "User Key Used"}
    assert company["secret_fields"] == ["Vendor Key Used", "User Key Used"]
    assert "vendor" not in company
    assert "user_key" not in company


def test_full_ma_permission_request_tracks_every_supported_workbook_family():
    assert set(MA_FULL_PERMISSION_REQUEST) >= {
        "Locations",
        "Strains",
        "Plant Batches / Plants",
        "Harvests",
        "Items",
        "Packages",
        "Labs",
        "Sales",
        "Sales Deliveries",
        "GET Transfers / Wholesale",
        "Transfer Template / External Incoming",
    }
