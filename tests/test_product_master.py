from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Base, Organization, Product, TradePartner
from modules.product_master import (
    ProductMasterRepository,
    ProductValueEvent,
    ProductVendorLink,
    normalize_alias,
)


@pytest.fixture()
def product_master_env():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        org = Organization(name="Buyer Dash Labs", slug="buyer-dash-labs")
        other_org = Organization(name="Other Org", slug="other-org")
        session.add_all([org, other_org])
        session.flush()
        product = Product(
            organization_id=org.id,
            sku="GMO-PR-1G",
            name="GMO Pre-Roll 1g",
            item_type="finished_good",
            base_unit="unit",
            unit_cost=3.0,
            retail_price=12.0,
        )
        same_org_product = Product(
            organization_id=org.id,
            sku="GMO-PR-5PK",
            name="GMO Pre-Roll 5pk",
            item_type="finished_good",
            base_unit="unit",
        )
        other_product = Product(
            organization_id=other_org.id,
            sku="OTHER-1",
            name="Other Product",
            item_type="finished_good",
            base_unit="unit",
        )
        vendor = TradePartner(
            organization_id=org.id,
            name="Vendor One",
            partner_type="vendor",
        )
        vendor_two = TradePartner(
            organization_id=org.id,
            name="Vendor Two",
            partner_type="both",
        )
        customer = TradePartner(
            organization_id=org.id,
            name="Retail Customer",
            partner_type="customer",
        )
        session.add_all([product, same_org_product, other_product, vendor, vendor_two, customer])
        session.flush()
        ids = {
            "org": org.id,
            "other_org": other_org.id,
            "product": product.id,
            "same_org_product": same_org_product.id,
            "other_product": other_product.id,
            "vendor": vendor.id,
            "vendor_two": vendor_two.id,
            "customer": customer.id,
        }
    return engine, sessions, ids


def test_product_profile_and_snapshot_preserve_canonical_product_id(product_master_env):
    engine, _sessions, ids = product_master_env
    repo = ProductMasterRepository(engine)
    profile = repo.update_profile(
        ids["org"],
        ids["product"],
        actor="buyer",
        brand="House Brand",
        category="Pre-Rolls",
        subcategory="Single",
        strain="GMO",
        manufacturer="Buyer Dash Labs",
        product_format="1g pre-roll",
        image_url="/products/cowboy-kush/pre-roll.png",
        description="Canonical finished-good identity.",
    )
    assert profile.product_id == ids["product"]

    snapshot = repo.snapshot(ids["org"], ids["product"])
    assert snapshot["product"].id == ids["product"]
    assert snapshot["profile"].brand == "House Brand"
    assert snapshot["profile"].strain == "GMO"
    assert snapshot["profile"].product_format == "1g pre-roll"
    assert snapshot["profile"].image_url == "/products/cowboy-kush/pre-roll.png"


def test_vendor_links_enforce_vendor_role_and_single_primary(product_master_env):
    engine, sessions, ids = product_master_env
    repo = ProductMasterRepository(engine)

    first = repo.link_vendor(
        ids["org"],
        ids["product"],
        ids["vendor"],
        actor="buyer",
        vendor_sku="V1-GMO",
        is_primary=True,
        lead_time_days=5,
        minimum_order_quantity=24,
        case_pack=12,
    )
    assert first.is_primary is True
    assert first.lead_time_days == 5

    second = repo.link_vendor(
        ids["org"],
        ids["product"],
        ids["vendor_two"],
        actor="buyer",
        vendor_sku="V2-GMO",
        is_primary=True,
        lead_time_days=3,
    )
    assert second.is_primary is True

    with sessions() as session:
        links = list(
            session.scalars(
                select(ProductVendorLink)
                .where(ProductVendorLink.product_id == ids["product"])
                .order_by(ProductVendorLink.partner_id)
            )
        )
        assert sum(1 for link in links if link.is_primary) == 1
        assert next(link for link in links if link.partner_id == ids["vendor_two"]).is_primary is True

    with pytest.raises(ValueError, match="not configured as a vendor"):
        repo.link_vendor(
            ids["org"],
            ids["product"],
            ids["customer"],
            actor="buyer",
        )


def test_external_mappings_and_aliases_are_collision_safe_and_tenant_scoped(product_master_env):
    engine, _sessions, ids = product_master_env
    repo = ProductMasterRepository(engine)

    mapping = repo.map_external(
        ids["org"],
        ids["product"],
        system_name="Metrc",
        external_id="ITEM-123",
        external_name="GMO Pre-Roll",
        actor="buyer",
    )
    assert mapping.system_name == "metrc"

    repo.add_alias(
        ids["org"],
        ids["product"],
        "GMO PR 1 Gram",
        actor="buyer",
        source="dutchie_import",
    )
    assert normalize_alias("  GMO---PR 1 GRAM ") == "gmo pr 1 gram"
    assert repo.resolve_alias(ids["org"], "gmo pr 1 gram").id == ids["product"]

    with pytest.raises(ValueError, match="different Buyer Dash product"):
        repo.map_external(
            ids["org"],
            ids["same_org_product"],
            system_name="Metrc",
            external_id="ITEM-123",
            actor="buyer",
        )

    with pytest.raises(ValueError, match="different Buyer Dash product"):
        repo.add_alias(
            ids["org"],
            ids["same_org_product"],
            "GMO PR 1 Gram",
            actor="buyer",
        )

    other_alias = repo.add_alias(
        ids["other_org"],
        ids["other_product"],
        "GMO PR 1 Gram",
        actor="other-buyer",
    )
    assert other_alias.product_id == ids["other_product"]
    assert repo.resolve_alias(ids["other_org"], "gmo pr 1 gram").id == ids["other_product"]


def test_value_history_is_append_only_and_mirrors_current_product_values(product_master_env):
    engine, sessions, ids = product_master_env
    repo = ProductMasterRepository(engine)

    cost = repo.record_value(
        ids["org"],
        ids["product"],
        value_type="unit_cost",
        amount=3.25,
        actor="buyer",
        partner_id=ids["vendor"],
        source="purchase_order",
        source_reference="PO-1001",
    )
    assert cost.previous_amount == 3.0
    assert cost.amount == 3.25

    retail = repo.record_value(
        ids["org"],
        ids["product"],
        value_type="retail_price",
        amount=14.0,
        actor="buyer",
        source="pricing_review",
    )
    assert retail.previous_amount == 12.0

    landed_one = repo.record_value(
        ids["org"],
        ids["product"],
        value_type="landed_cost",
        amount=3.60,
        actor="buyer",
        partner_id=ids["vendor"],
    )
    landed_two = repo.record_value(
        ids["org"],
        ids["product"],
        value_type="landed_cost",
        amount=3.75,
        actor="buyer",
        partner_id=ids["vendor"],
    )
    assert landed_one.previous_amount is None
    assert landed_two.previous_amount == 3.60

    with sessions() as session:
        product = session.get(Product, ids["product"])
        assert product.unit_cost == 3.25
        assert product.retail_price == 14.0
        events = list(
            session.scalars(
                select(ProductValueEvent).where(ProductValueEvent.product_id == ids["product"])
            )
        )
        assert len(events) == 4


def test_product_master_rejects_cross_tenant_access(product_master_env):
    engine, _sessions, ids = product_master_env
    repo = ProductMasterRepository(engine)

    with pytest.raises(ValueError, match="Product was not found"):
        repo.update_profile(
            ids["other_org"],
            ids["product"],
            actor="intruder",
            brand="Wrong tenant",
        )

    with pytest.raises(ValueError, match="Vendor was not found"):
        repo.link_vendor(
            ids["other_org"],
            ids["other_product"],
            ids["vendor"],
            actor="intruder",
        )


def test_product_master_migration_pair_stays_aligned():
    py = open("migrations/versions/0020_product_master.py", encoding="utf-8").read()
    sql = open("migrations/versions/0020_product_master.sql", encoding="utf-8").read()
    assert 'revision = "0020_product_master"' in py
    assert 'down_revision = "0019_pkgstudio_po_index"' in py
    assert "set version_num = '0020_product_master'" in sql
    for table in (
        "product_master_profiles",
        "product_vendor_links",
        "product_external_mappings",
        "product_aliases",
        "product_value_events",
    ):
        assert table in py
        assert table in sql
