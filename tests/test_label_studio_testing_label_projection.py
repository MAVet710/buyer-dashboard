import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.label_studio import LabelInventoryService
from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.product_master.models import ProductMasterProfile
from modules.product_master.packaging import ProductPackagingProfile


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def test_party_pack_projection_matches_approved_testing_label_semantics():
    engine = _engine()
    current_tag = "1A40A030000C60D0000080706"
    with Session(engine) as session, session.begin():
        org = Organization(name="Approved Label Operator", slug="approved-label-operator")
        session.add(org)
        session.flush()
        facility = Facility(
            organization_id=org.id,
            name="Bud's Goods & Services",
            code="MFG",
            license_number="MP281819",
            license_type="Marijuana Product Manufacturer",
            production_enabled=True,
        )
        session.add(facility)
        session.flush()
        product = Product(
            organization_id=org.id,
            sku="PARTY-TRICH-14G",
            name="Jay's Party Pack - Tricheratops",
            item_type="finished_good",
            base_unit="unit",
        )
        session.add(product)
        session.flush()
        session.add(
            ProductMasterProfile(
                organization_id=org.id,
                product_id=product.id,
                brand="Jay's Party Pack",
                category="Pre-Rolls",
                strain="Tricheratops",
                manufacturer="Bud's Goods & Services",
                product_format="Pre-Roll Multipack",
            )
        )
        session.add(
            ProductPackagingProfile(
                organization_id=org.id,
                product_id=product.id,
                net_content=14.0,
                net_content_unit="g",
                units_per_package=28,
                sellable_unit="each",
                warning_text="Packaging-only warning should not be required by the testing-label UI.",
            )
        )
        lot = InventoryLot(
            organization_id=org.id,
            facility_id=facility.id,
            product_id=product.id,
            lot_code="TRIC-FBH3-2026.08.06",
            compliance_package_id=current_tag,
            location_code="FINISHED-GOODS",
            notes=json.dumps(
                {
                    "serial_number": "0D637",
                    "harvest_date": "2026-06-08",
                    "package_date": "2026-08-05",
                    "cultivated_by": "Salisbury Cultivation and Production Manufacturing, LLC",
                    "cultivator_license": "MC282630 / MP281819",
                    "cultivator_phone": "978-517-8010",
                    "cultivator_email": "hello@example.test",
                    "packaged_by": "Bud's Goods & Services",
                    "packager_license": "MP281507",
                    "packager_phone": "774-500-2837",
                    "sold_by": "Bud's Goods & Provisions",
                    "seller_license": "MR282410 / MR282319 / MR281774",
                    "seller_phone": "774-500-2837",
                    "seller_email": "buds@example.test",
                    "seller_website": "budsgoods.example",
                }
            ),
        )
        session.add(lot)
        session.flush()
        session.add(
            InventoryTransaction(
                organization_id=org.id,
                facility_id=facility.id,
                lot_id=lot.id,
                transaction_type="receipt",
                quantity_delta=40,
                unit="unit",
                actor="tester",
            )
        )
        org_id, facility_id = org.id, facility.id

    source = LabelInventoryService(engine).list_sources(org_id, facility_id)[0]
    label = source["label"]

    assert label["product_name"] == "Jay's Party Pack - Tricheratops"
    assert label["package_size"] == "14 g"
    assert label["net_contents"] == "NET WT. .49383 OZ"
    assert label["package_composition"] == "28 x 0.50g Pre-Rolls"
    assert label["serial_number"] == "0D637"
    assert label["harvest_date"] == "2026-06-08"
    assert label["package_date"] == "2026-08-05"

    assert label["cultivated_by"] == "Salisbury Cultivation and Production Manufacturing, LLC"
    assert label["cultivator_license"] == "MC282630 / MP281819"
    assert "978-517-8010" in label["cultivator_contact"]
    assert label["packaged_by"] == "Bud's Goods & Services"
    assert label["packager_license"] == "MP281507"
    assert label["sold_by"] == "Bud's Goods & Provisions"
    assert label["seller_license"] == "MR282410 / MR282319 / MR281774"
    assert "budsgoods.example" in label["seller_contact"]

    assert source["qr"]["value"] == current_tag
    assert "<svg" in source["qr"]["svg"]
    assert source["barcode"]["value"] == current_tag
    assert source["barcode"]["format"] == "Code128"
    assert "<svg" in source["barcode"]["svg"]
